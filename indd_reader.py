"""Read editable article candidates from native InDesign documents."""
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import unquote
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from indd_text import SIGNATURE


@dataclass(frozen=True)
class Box:
    page: int
    left: float
    top: float
    right: float
    bottom: float
    section: str = ''

    def overlaps_columns(self, other):
        return self.page == other.page and min(self.right, other.right) > max(self.left, other.left)


@dataclass
class Story:
    key: str
    paragraphs: list
    box: Box | None

    @property
    def text(self):
        return '\n\n'.join(text for text, _ in self.paragraphs)


HEADING = re.compile(r'\b(headline|title|heading\s*1?)\b', re.I)
NON_ARTICLE = re.compile(r'\b(photo|caption|calendar|credit|masthead|parent page|running head|page number)\b', re.I)
INSET_LABEL = re.compile(r'^(events calendar|newsroom staff|crossword puzzle|from the front|'
                         r'arts|news|sports|features|science and health|p\.\s*\d+)$', re.I)
IDENTITY = (1, 0, 0, 1, 0, 0)


def transform(element):
    return tuple(map(float, element.get('ItemTransform', '1 0 0 1 0 0').split()))


def apply_transform(matrix, x, y):
    a, b, c, d, tx, ty = matrix
    return a*x + c*y + tx, b*x + d*y + ty


def compose(parent, child):
    a, b, c, d, tx, ty = child
    ax, ay = apply_transform(parent, a, b)
    bx, by = apply_transform(parent, c, d)
    return ax-parent[4], ay-parent[5], bx-parent[4], by-parent[5], *apply_transform(parent, tx, ty)


def bounds(points, matrix):
    x, y = zip(*(apply_transform(matrix, *p) for p in points))
    return min(x), min(y), max(x), max(y)


def intersection(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def read_frames(package, design):
    story_frames = defaultdict(list)
    item_stories = {}
    page_number = 0
    sections = {}
    masters = {}
    for ref in design:
        path = ref.get('src', '')
        if path.startswith('MasterSpreads/'):
            master = ElementTree.fromstring(package.read(path)).find('MasterSpread')
            if master is not None:
                name = re.sub(r'^[A-Z0-9]+\s*[-–]\s*', '', master.get('Name', '')).strip()
                if name.casefold() not in ('parent', 'master', '[none]'):
                    masters[master.get('Self')] = name
    for ref in design:
        path = ref.get('src', '')
        if not path.startswith('Spreads/'):
            continue
        spread = ElementTree.fromstring(package.read(path)).find('Spread')
        if spread is None:
            continue
        pages = {}
        for page in spread.findall('Page'):
            page_number += 1
            sections[page_number] = masters.get(page.get('AppliedMaster'), '')
            top, left, bottom, right = map(float, page.get('GeometricBounds').split())
            pages[page_number] = bounds([(left, top), (right, top), (right, bottom), (left, bottom)], transform(page))

        def walk(node, parent, groups=()):
            matrix = compose(parent, transform(node))
            if node.tag == 'Group':
                groups = (*groups, node.get('Self'))
            if node.tag in ('TextFrame', 'TextPath'):
                story = node.get('ParentStory')
                item_stories[node.get('Self')] = [story]
                for group in groups:
                    item_stories.setdefault(group, []).append(story)
                anchors = [tuple(map(float, p.get('Anchor').split())) for p in node.findall('./Properties/PathGeometry/GeometryPathType/PathPointArray/PathPointType')]
                if anchors and pages:
                    frame = bounds(anchors, matrix)
                    page_id = max(pages, key=lambda key: intersection(pages[key], frame))
                    if intersection(pages[page_id], frame):
                        previous = node.get('PreviousTextFrame')
                        story_frames[story].append((previous not in (None, '', 'n'), page_id, frame))
                return
            for child in node:
                if child.tag not in ('Properties', 'Page'):
                    walk(child, matrix, groups)

        for child in spread:
            if child.tag not in ('Properties', 'Page'):
                walk(child, IDENTITY)

    positions = {}
    for key, frames in story_frames.items():
        _, page_id, frame = min(frames)
        positions[key] = Box(page_id, *frame, section=sections[page_id])
    return positions, item_stories


def story_paragraphs(element):
    paragraphs = []
    chunks = []
    paragraph_style = ''

    def finish():
        text = ''.join(chunks).replace('\u00ad', '').replace('\u200b', '').strip()
        if text:
            paragraphs.append((text, paragraph_style))
        chunks.clear()

    def walk(node):
        nonlocal paragraph_style
        if node.tag == 'ParagraphStyleRange':
            style = unquote(node.get('AppliedParagraphStyle', '')).rsplit('/', 1)[-1].split(':')[-1]
            if not chunks:
                paragraph_style = style
        if node.tag == 'Content':
            chunks.append(node.text or '')
        elif node.tag == 'Br':
            finish()
        elif node.tag not in ('Properties', 'Note', 'Footnote', 'Endnote', 'Rectangle', 'Oval', 'Polygon',
                              'TextFrame', 'TextPath', 'Group'):
            for child in node:
                walk(child)

    walk(element)
    finish()
    return paragraphs


def author_names(text):
    if len(text) > 125:
        return []
    authors = re.split(r'\s*,\s*(?:and\s+)?|\s+(?:and|&)\s+', text, flags=re.I)
    if all(2 <= len(name.split()) <= 7 and all(c.isalpha() or c in " .’'‐-" for c in name)
           and name[0].isupper() for name in authors):
        return authors
    return []

def byline(text):
    match = re.fullmatch(r'By\s+(.+)', ' '.join(text.split()), re.I)
    return author_names(match[1]) if match else []

def is_heading(style):
    return HEADING.search(style) and not NON_ARTICLE.search(style) and not re.search(r'\bsub[- ]?(head|title)', style, re.I)

def split_story(story):
    starts = [i for i, (text, style) in enumerate(story.paragraphs) if is_heading(style) and len(text) < 200]
    # Adjacent styled lines can be one wrapped headline.
    starts = [i for j, i in enumerate(starts) if j == 0 or i > starts[j-1] + 1]
    if len(starts) < 2:
        return [story]
    starts[0] = 0
    return [Story(f'{story.key}:{i+1}', story.paragraphs[start:end], story.box)
            for i, (start, end) in enumerate(zip(starts, starts[1:] + [len(story.paragraphs)]))]

def candidate(title, authors, paragraphs, key):
    return dict(title=title, authors=authors, kind='article', body='\n\n'.join(paragraphs),
                native_key='story:' + key, source_parts=[])


def story_candidate(story, title='', authors=None):
    paragraphs = list(story.paragraphs)
    if not title:
        title_lines = []
        while len(paragraphs) > 1 and is_heading(paragraphs[0][1]) and len(paragraphs[0][0]) < 200:
            title_lines.append(paragraphs.pop(0)[0])
        title = ' '.join(' '.join(title_lines).split())
    names = byline(paragraphs[0][0]) if len(paragraphs) > 1 else []
    if names:
        paragraphs.pop(0)
    elif not authors and len(paragraphs) > 2 and re.fullmatch(r'(?:sincerely|take care|best(?: regards)?),', paragraphs[-2][0], re.I):
        names = author_names(paragraphs[-1][0])
    item = candidate(title or 'Untitled article', names or authors or [], [text for text, _ in paragraphs], story.key)
    item['source_section'] = story.box.section if story.box else ''
    return item


def group_articles(stories, design, item_stories):
    items = []
    used = set()
    by_key = {story.key: story for story in stories}
    for article in design.iter('Article'):
        keys = list(dict.fromkeys(key for member in article.findall('ArticleMember')
                                  for key in item_stories.get(member.get('ItemRef'), []) if key in by_key))
        paragraphs = [p for key in keys for p in by_key[key].paragraphs if not NON_ARTICLE.search(p[1])]
        if paragraphs:
            position = next((by_key[key].box for key in keys if by_key[key].box), None)
            item = story_candidate(Story(article.get('Self'), paragraphs, position))
            name = article.get('Name', '')
            if item['title'] == 'Untitled article' and name and not re.fullmatch(r'Article\s*\d*', name, re.I):
                item['title'] = name
            items.append(item)
            used.update(keys)

    headlines = []
    bylines = []
    bodies = []
    fallback = []
    for story in (part for source in stories if source.key not in used and source.box for part in split_story(source)):
        text = story.text
        styles = [style for _, style in story.paragraphs]
        if byline(text):
            bylines.append(story)
        elif all(is_heading(style) for style in styles) and len(text) < 200:
            if not INSET_LABEL.fullmatch(' '.join(text.split())):
                headlines.append(story)
        elif not all(NON_ARTICLE.search(style) for style in styles):
            if len(text) >= 95 and (any(re.search(r'\bbody\b', style, re.I) for style in styles)
                                    or len(re.findall(r'[.!?][”’"]?(?:\s|$)', text)) >= 2):
                bodies.append(story)
            else:
                fallback.append(story)

    # Match each body to the closest preceding headline in the same columns.
    grouped = defaultdict(list)
    for body in bodies:
        if is_heading(body.paragraphs[0][1]):
            items.append(story_candidate(body))
            continue
        matches = [h for h in headlines if h.box.overlaps_columns(body.box)
                   and h.box.top <= body.box.top + 12
                   and body.box.top - h.box.bottom < 480]
        heading = min(matches, key=lambda h: (abs(body.box.top - h.box.bottom), abs(body.box.left - h.box.left)), default=None)
        if heading:
            grouped[heading.key].append(body)
        else:
            item = story_candidate(body)
            if item['title'] != 'Untitled article' or item['authors'] or len(body.text) >= 900:
                items.append(item)

    active_headings = [heading for heading in headlines if grouped[heading.key]]
    matched_bylines = defaultdict(list)
    for author in bylines:
        matches = [h for h in active_headings if h.box.overlaps_columns(author.box)
                   and max(h.box.top - author.box.bottom, author.box.top - h.box.bottom, 0) <= 175]
        heading = min(matches, key=lambda h: (max(h.box.top - author.box.bottom, author.box.top - h.box.bottom, 0),
                                             abs(author.box.left - h.box.left)), default=None)
        if heading:
            matched_bylines[heading.key].append(author)

    for heading in sorted(active_headings, key=lambda h: (h.box.page, h.box.top, h.box.left)):
        title = ' '.join(heading.text.split())
        parts = []
        upcoming = sorted(grouped[heading.key], key=lambda p: p.box.top)
        while upcoming:
            top = upcoming[0].box.top
            row = [part for part in upcoming if part.box.top - top < 20]
            parts.extend(sorted(row, key=lambda p: p.box.left))
            upcoming = upcoming[len(row):]
        names = list(dict.fromkeys(tuple(byline(a.text)) for a in matched_bylines[heading.key]))
        paragraphs = [p for part in parts for p in part.paragraphs]
        item = story_candidate(Story(heading.key, paragraphs, heading.box), title,
                               list(names[0]) if len(names) == 1 else [])
        if not item['source_section']:
            labels = {label.text.strip().title() for label in stories if label.box
                      and label.box.overlaps_columns(heading.box)
                      and 0 <= label.box.top - heading.box.bottom <= 50
                      and re.fullmatch(r'news|features|arts|sports|science and health', label.text.strip(), re.I)}
            if len(labels) == 1:
                item['source_section'] = labels.pop()
        items.append(item)
    if not items:
        placed = bodies or fallback or headlines
        items = [story_candidate(story) for story in (placed or stories) if story.key not in used]
    return items


def read_package(path):
    with ZipFile(path) as package:
        design = ElementTree.fromstring(package.read('designmap.xml'))
        positions, item_stories = read_frames(package, design)
        stories = []
        for ref in design:
            path = ref.get('src', '')
            if not path.startswith('Stories/'):
                continue
            node = ElementTree.fromstring(package.read(path)).find('Story')
            if node is not None:
                key = node.get('Self')
                paragraphs = story_paragraphs(node)
                if paragraphs:
                    stories.append(Story(key, paragraphs, positions.get(key)))
        return group_articles(stories, design, item_stories)


def read_indd(data, reader):
    if not data.startswith(SIGNATURE):
        raise ValueError('Choose an Adobe InDesign .indd document.')
    if not reader.is_file():
        raise ValueError('The INDD reader is missing. Restore tools/indd.exe from the app files.')
    try:
        with tempfile.TemporaryDirectory(prefix='current-indd-') as scratch:
            source = Path(scratch) / 'source.indd'
            package = Path(scratch) / 'stories.idml'
            source.write_bytes(data)
            result = subprocess.run([str(reader), 'convert', str(source), str(package)], timeout=75,
                                    capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if result.returncode:
                raise ValueError('Could not read this INDD. It may be damaged or use an unsupported InDesign version.')
            items = read_package(package)
    except subprocess.TimeoutExpired:
        raise ValueError('Reading this INDD took too long.') from None
    except (BadZipFile, ElementTree.ParseError, KeyError, OSError):
        raise ValueError('Could not recover the text from this INDD.') from None
    if not items:
        raise ValueError('No editable text was found in this INDD. Text converted to outlines cannot be recovered.')
    return items
