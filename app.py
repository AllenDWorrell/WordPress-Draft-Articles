"""The Current: INDD workbench for WordPress drafts."""
import argparse,base64,copy,hashlib,html,json,mimetypes,re,secrets,threading
import urllib.error,urllib.parse,urllib.request,uuid,webbrowser
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from indd_text import extract_issue,author_slug
from indd_reader import read_indd

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'native-data'
DATA.mkdir(exist_ok=True)
TOKEN=secrets.token_urlsafe(32)
LOCK=threading.RLock()
DEFAULT_PORT=3000
DEFAULT_SITE='https://sites.nova.edu/mako-media-network'

def content_security_policy():
    return ("default-src 'self'; img-src 'self'; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")

def wordpress_settings():
    fields = {'WP_SITE': 'site', 'WP_USERNAME': 'username', 'WP_APPLICATION_PASSWORD': 'password'}
    settings = dict(site=DEFAULT_SITE, username='', password='')
    try:
        lines = (ROOT / '.env').read_text(encoding='utf-8-sig').splitlines()
    except FileNotFoundError:
        return settings
    except (OSError, UnicodeError):
        raise ValueError('Could not read .env. Save it as a UTF-8 text file beside app.py.') from None
    for line in lines:
        key, separator, value = line.partition('=')
        key = key.strip()
        if separator and key in fields:
            value = value.strip()
            if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
                value = value[1:-1].strip()
            settings[fields[key]] = value
    settings['site'] = (settings['site'] or DEFAULT_SITE).rstrip('/')
    return settings

def wordpress_ready(settings):
    return bool(settings['username'] and settings['password'].replace(' ', ''))

def uid():return uuid.uuid4().hex

def is_article(item):return item.get('kind','article')=='article'
def folder(sid):
    if not re.fullmatch(r'[a-f0-9]{32}',sid or ''):raise ValueError('Invalid issue identifier.')
    path=DATA/sid
    if not path.is_dir():raise ValueError('Issue not found.')
    return path
def apply_default_tags(a):
    before=copy.deepcopy(a)
    tags=a.setdefault('tags',[])
    if a.get('default_tags_version')!=1:
        if not any(t.casefold()=='add-about' for t in tags):tags.append('add-about')
        a['default_tags_version']=1
    previous=a.get('default_author_names',[])
    names=list(dict.fromkeys(p.get('name','').strip() for p in a.get('authors',[]) if p.get('name','').strip()))
    prior_keys={name.casefold() for name in previous}
    current_keys={name.casefold() for name in names}
    stale={'posts by '+name.casefold() for name in previous if name.casefold() not in current_keys}
    tags[:]=[tag for tag in tags if tag.casefold() not in stale]
    for name in names:
        label='Posts By '+name
        if name.casefold() not in prior_keys and not any(t.casefold()==label.casefold() for t in tags):tags.append(label)
    a['default_author_names']=names
    if tags!=before.get('tags',[]):a['reviewed']=False
    return a!=before

def load(sid):
    project=json.loads((folder(sid)/'project.json').read_text('utf8'))
    changed=False
    excluded=[a for a in project['articles'] if not is_article(a)]
    if excluded:
        prior=project.setdefault('excluded_items',[])
        known={a['id'] for a in prior}
        prior.extend(a for a in excluded if a['id'] not in known)
        project['articles']=[a for a in project['articles'] if is_article(a)]
        changed=True
    for a in project['articles']:
        clean_authors=[{'name': person.get('name','').strip(), 'slug': (person.get('slug') or person.get('wp_slug') or '').strip()}
                       for person in a.get('authors',[])]
        if clean_authors != a.get('authors',[]):
            a['authors']=clean_authors
            changed=True
        if 'primary_author' in a:
            del a['primary_author']
            changed=True
        if 'featured_image' in a:
            del a['featured_image']
            changed=True
        changed=apply_default_tags(a) or changed
    logpath=DATA/'wordpress-drafts.json'
    history=json.loads(logpath.read_text('utf8')) if logpath.exists() else {}
    for a in project['articles']:
        if a.get('wordpress_draft'):continue
        identity=a.get('native_key',a['id'])
        legacy_key=draft_key(DEFAULT_SITE,project,identity)
        legacy=history.get(legacy_key)
        record=None
        if isinstance(legacy,int) and not isinstance(legacy,bool) and legacy>0:
            record=dict(id=legacy,status='draft',site=DEFAULT_SITE,edit_url=draft_edit_url(DEFAULT_SITE,legacy))
        for candidate in history.values():
            if isinstance(candidate,dict) and candidate.get('status')=='draft' and candidate.get('source_hash')==project.get('source_hash','') and candidate.get('native_key')==identity:
                record=candidate;break
        if record:
            a['wordpress_draft']=record.copy();changed=True
    if changed:save(project)
    return project

def draft_key(site,project,identity):
    return hashlib.sha256((site.rstrip('/')+'|'+project.get('source_hash','')+'|'+identity).encode()).hexdigest()

def draft_edit_url(site,post_id):
    return site.rstrip('/')+'/wp-admin/post.php?post='+str(post_id)+'&action=edit'

def write_json(path, data):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf8')
    temp.replace(path)

def save(project):
    write_json(folder(project['id'])/'project.json', project)
def save_edits(data):
    previous=load(data['id']);saved={a['id']:a for a in previous['articles']};edited=[]
    excluded_ids={a['id'] for a in previous.get('excluded_items',[])}
    for incoming in data['articles']:
        if incoming['id'] in excluded_ids or not is_article(incoming):continue
        a=copy.deepcopy(saved.get(incoming['id'],article()))
        a['id']=incoming['id']
        for key in ('title','authors','body','body_html','categories','categories_edited','tags','reviewed','generated_author_tags','auto_author_tags','default_tags_version','default_author_names','slug'):
            if key in incoming:a[key]=incoming[key]
        apply_default_tags(a)
        edited.append(a)
    previous['articles']=edited;save(previous);return previous
def article(title='Untitled article',author=''):
    a=dict(id=uid(),title=title,authors=[dict(name=author,slug='')] if author else [],body='',source_body='',
                categories=[],tags=[],reviewed=False,kind='article',source='Manual',source_parts=[])
    apply_default_tags(a)
    return a

def saved_projects():
    files = sorted(DATA.glob('*/project.json'), key=lambda path: path.stat().st_mtime, reverse=True)
    for file in files:
        yield json.loads(file.read_text('utf8'))

def set_active_issue(issue_id):
    path = DATA / 'active-issue.json'
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(issue_id), 'utf8')
    temp.replace(path)

def active_issue_id():
    path = DATA / 'active-issue.json'
    if path.exists():
        return json.loads(path.read_text('utf8'))
    # Resume a saved issue when upgrading from the issue switcher.
    issue_id = next((p['id'] for p in saved_projects() if any(is_article(a) for a in p['articles'])), None)
    set_active_issue(issue_id)
    return issue_id

def require_active_issue(issue_id):
    if not issue_id or issue_id != active_issue_id():
        raise ValueError('This INDD is no longer open. Refresh the app to continue.')

def extraction_recipe(digest):
    recipes = (json.loads(path.read_text('utf8')) for path in (ROOT/'issue-recipes').glob('*.json'))
    return next((recipe for recipe in recipes if recipe['source_sha256'] == digest), None)

def import_indd(raw,name):
    if active_issue_id():
        raise ValueError('Close the open INDD before choosing another file.')
    if len(raw)>100*1024*1024:raise ValueError('Choose an INDD smaller than 100 MB.')
    digest=hashlib.sha256(raw).hexdigest()
    saved = next((p for p in saved_projects() if p.get('source_hash') == digest), None)
    if saved:
        project = load(saved['id'])
        set_active_issue(project['id'])
        return project
    recipe = extraction_recipe(digest)
    recovered = extract_issue(raw, recipe) if recipe else read_indd(raw, ROOT / 'tools' / 'indd.exe')
    sid=uid();dest=DATA/sid;dest.mkdir();(dest/'source.indd').write_bytes(raw)
    items=[]
    for item in recovered:
        if not is_article(item):continue
        a=article(item['title']);a.update(body=item['body'],source_body=item['body'],kind=item['kind'],native_key=item['native_key'],
                  source='INDD',source_parts=item['source_parts'],source_bytes_verified=bool(recipe),
                  source_section=item.get('source_section', ''))
        a['authors']=[dict(name=name,slug='') for name in item['authors']]
        a['generated_author_tags']=['coauthor-'+author_slug(p['name']) for p in a['authors']]
        a['tags']+=a['generated_author_tags']
        apply_default_tags(a)
        items.append(a)
    project=dict(id=sid,name=recipe['issue'] if recipe else Path(name).stem,source_name=name,source_hash=digest,
                 mode='indd-only',text_only=True,articles=items,notes=recipe['notes'] if recipe else [],
                 summary=dict(items=len(items),native_frames=sum(len(a['source_parts']) for a in items)))
    save(project)
    set_active_issue(sid)
    return project

def post_text(a, site=''):
    authors=[person for person in a.get('authors',[]) if str(person.get('name','')).strip()]
    paragraphs=[]
    if authors:
        rendered=[]
        for person in authors:
            name=html.escape(str(person['name']).strip())
            author_slug=str(person.get('slug','')).strip()
            href=site.rstrip('/')+'/author/'+urllib.parse.quote(author_slug,safe='')+'/' if site else '/author/'+urllib.parse.quote(author_slug,safe='')+'/'
            rendered.append('<a href="'+html.escape(href,quote=True)+'">'+name+' </a>')
        paragraphs.append('<p class="byline">By '+'and '.join(rendered)+'<span class="bybullet"> •</span></p>')
    if a.get('body_html'):
        paragraphs.append(str(a['body_html']))
        return '\n'.join(paragraphs)
    body=str(a.get('body','')).replace('\r\n','\n').replace('\r','\n').strip()
    if body:
        paragraphs.extend('<p>'+ '<br>'.join(html.escape(line) for line in part.split('\n')) +'</p>'
                          for part in re.split(r'\n\s*\n',body) if part.strip())
    return '\n'.join(paragraphs)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('WordPress redirected the request. Use the final HTTPS site address; credentials were not forwarded.')

class WordPressError(ValueError):
    def __init__(self, status, message):
        self.status = status
        super().__init__(f'WordPress returned {status}: {message}')

def validate_wordpress_site(site):
    try:
        parsed = urllib.parse.urlsplit(site)
        valid = (parsed.scheme == 'https' and parsed.hostname and parsed.username is None
                 and parsed.password is None and not re.search(r'[\s\\?#]', site))
        parsed.port  # Reject invalid or out-of-range ports.
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('Set WP_SITE in .env to an HTTPS site URL without login details, a query, or a fragment.')

def wp_request(base,path,username,password,payload=None,content_type='application/json',filename=None):
    validate_wordpress_site(base)
    if not username or not password.replace(' ', ''):
        raise ValueError('Fill in WP_USERNAME and WP_APPLICATION_PASSWORD in the .env file beside app.py.')
    url=base.rstrip('/')+'/wp-json/wp/v2/'+path
    auth=base64.b64encode((username+':'+password.replace(' ','')).encode()).decode()
    headers={'Authorization':'Basic '+auth,'Content-Type':content_type,'User-Agent':'CurrentDraftWorkbench/1.0'}
    if filename:headers['Content-Disposition']='attachment; filename="'+filename+'"'
    req=urllib.request.Request(url,data=payload if isinstance(payload,bytes) else json.dumps(payload).encode() if payload is not None else None,headers=headers)
    try:
        with urllib.request.build_opener(NoRedirect).open(req,timeout=30) as resp: return json.load(resp)
    except urllib.error.HTTPError as err:
        try: message=json.load(err).get('message','Request rejected.')
        except Exception: message='Request rejected.'
        raise WordPressError(err.code, message) from None

def terms(base,kind,names,user,password):
    result=[]
    connection = dict(site=base, username=user, password=password)
    for name in names:
        matches = matching_term_ids(connection, kind, name)
        if len(matches)!=1: raise ValueError(f'Choose an existing {kind[:-1]} name or slug: {name}. No draft was created.')
        result.append(matches[0])
    return result

def wp_read(connection, resource, **params):
    return wp_request(connection['site'], resource+'?'+urllib.parse.urlencode(params),
                      connection['username'], connection['password'])

def normalized_name(value):
    return ' '.join(html.unescape(value).casefold().split())

def matching_term_ids(connection, kind, name):
    found = wp_read(connection, kind, per_page=100, search=name, _fields='id,name,slug')
    return [term['id'] for term in found
            if normalized_name(term['name']) == normalized_name(name) or term['slug'].casefold() == name.strip().casefold()]

def prepare_issue(project, connection):
    pending = [a for a in project['articles'] if not a.get('wordpress_draft')]
    errors = []
    missing_sections = [a for a in pending if a.get('source') == 'INDD' and 'source_section' not in a]
    if missing_sections:
        recipe = extraction_recipe(project.get('source_hash'))
        if recipe:
            sections = {str(i): item.get('section', '') for i, item in enumerate(recipe['items'], 1)}
        else:
            source = folder(project['id'])/'source.indd'
            sections = {}
            if source.is_file():
                items = read_indd(source.read_bytes(), ROOT/'tools'/'indd.exe')
                sections = {item['native_key']: item.get('source_section', '') for item in items}
        for a in missing_sections:
            a['source_section'] = sections.get(a.get('native_key'), '')

    category_targets = [a for a in pending if a.get('source_section') and not a.get('categories')
                        and not a.get('categories_edited') and not a.get('suggested_category')]
    sections = {}
    for section in dict.fromkeys(a['source_section'] for a in category_targets):
        try:
            found = wp_read(connection, 'categories', search=section, per_page=100, _fields='name,slug')
            names = {normalized_name(section)}
            if normalized_name(section) == 'science':
                names.update(('science and health', 'science & health', 'health and science'))
            matches = [html.unescape(term['name']) for term in found
                       if normalized_name(term['name']) in names or term['slug'] == author_slug(section)]
            if len(matches) == 1:
                sections[section] = matches[0]
        except (ValueError, OSError) as error:
            errors.append(str(error))

    suggested = 0
    for a in category_targets:
        section = a['source_section']
        if section in sections:
            a['categories'] = [sections[section]]
            a['suggested_category'] = sections[section]
            a['reviewed'] = False
            suggested += 1
    save(project)
    return dict(project=project, suggested=suggested, warning=errors[0] if errors else '')

def draft_article(project, aid, require_reviewed=True):
    article = next((a for a in project['articles'] if a['id'] == aid), None)
    if not article or not is_article(article):
        raise ValueError('Only articles can be drafted to WordPress.')
    if require_reviewed and not article.get('reviewed'):
        raise ValueError('Review this article before creating a draft.')
    return article

def draft_history():
    path = DATA/'wordpress-drafts.json'
    return json.loads(path.read_text('utf8')) if path.exists() else {}

def draft_preflight(project, aid, connection, cache, require_reviewed=False):
    a = draft_article(project, aid, require_reviewed)
    title = a.get('title', '').strip()
    errors = []
    if not title or title.casefold() == 'untitled article':
        errors.append('Enter a headline.')
    if not a.get('body', '').strip():
        errors.append('Enter the article text.')
    key = draft_key(connection['site'], project, a.get('native_key', aid))
    if a.get('wordpress_draft') or key in cache['history']:
        errors.append('This article was already sent or has an unresolved attempt. Check WordPress before retrying.')
    if any(not str(author.get('name','')).strip() or not str(author.get('slug','')).strip()
           for author in a.get('authors', [])):
        errors.append('Enter both a name and WordPress author slug for each byline author, or remove the blank author row.')
    payload = dict(title=title, content=post_text(a,connection['site']), status='draft', categories=[], tags=[])
    if a.get('slug'):payload['slug']=a['slug']
    for kind in ('categories', 'tags'):
        for name in a.get(kind, []):
            term_key = kind, name
            if term_key not in cache:
                cache[term_key] = matching_term_ids(connection, kind, name)
            matches = cache[term_key]
            if len(matches) == 1:
                payload[kind].extend(matches)
            else:
                label = 'category' if kind == 'categories' else 'tag'
                reason = 'is ambiguous' if matches else 'does not exist'
                errors.append(f'{label.capitalize()} “{name}” {reason} in WordPress.')
    duplicates = []
    if title and title.casefold() != 'untitled article':
        posts = wp_read(connection, 'posts', search=title, search_columns='post_title', context='edit',
                        status='publish,draft,pending,future,private', per_page=100, _fields='id,title,status')
        for post in posts:
            existing = post['title'].get('raw') or post['title'].get('rendered', '')
            if normalized_name(existing) == normalized_name(title):
                duplicates.append(dict(id=post['id'], status=post['status'],
                                       url=draft_edit_url(connection['site'], post['id'])))
    signature = hashlib.sha256(json.dumps(a, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return payload, dict(id=aid, title=title or 'Untitled article', errors=errors,
                         duplicates=duplicates, signature=signature)

def create_draft(project,aid,connection,payload=None):
    a = draft_article(project, aid)
    if not a.get('title','').strip() or not a.get('body','').strip(): raise ValueError('Title and article text are required.')
    if any(not str(author.get('name','')).strip() or not str(author.get('slug','')).strip()
           for author in a.get('authors', [])):
        raise ValueError('Enter both a name and WordPress author slug for each byline author, or remove the blank author row.')
    base=connection['site'].rstrip('/'); user=connection['username']; password=connection['password']
    key=draft_key(base,project,a.get('native_key',aid))
    logpath=DATA/'wordpress-drafts.json'
    history=draft_history()
    if key in history: raise ValueError(f'This article was already sent or has an unresolved attempt ({history[key]}). Check WordPress before retrying.')
    if payload is None:
        cats=terms(base,'categories',a.get('categories',[]),user,password)
        tags=terms(base,'tags',a.get('tags',[]),user,password)
        payload=dict(title=a['title'],content=post_text(a,base),status='draft',categories=cats,tags=tags)
    if a.get('slug'):payload['slug']=a['slug']
    # Persist intent before sending. A timeout must never silently produce duplicates.
    history[key]='attempt pending; inspect WordPress if the result is unknown'
    write_json(logpath, history)
    try:
        response=wp_request(base,'posts',user,password,payload)
    except WordPressError as error:
        if error.status in (400, 401, 403, 422):
            del history[key]
            write_json(logpath, history)
        raise
    if response.get('status')!='draft': raise ValueError('The server did not confirm draft status. Inspect WordPress immediately.')
    if not isinstance(response.get('id'),int) or isinstance(response['id'],bool) or response['id']<=0:
        raise ValueError('The server did not confirm a valid draft ID. Inspect WordPress before retrying.')
    record=dict(id=response['id'],status='draft',site=base,edit_url=draft_edit_url(base,response['id']),
                source_hash=project.get('source_hash',''),native_key=a.get('native_key',aid))
    history[key]=record;write_json(logpath, history)
    a['wordpress_draft']=record.copy();save(project)
    return dict(id=response['id'],status=response['status'],edit_url=record['edit_url'],project=project,
                note='Check the Authors panel manually. Core REST does not assign multiple coauthors.')

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,status,data,ctype='application/json',extra=None):
        if isinstance(data,(dict,list)):data=json.dumps(data,ensure_ascii=False).encode()
        elif isinstance(data,str):data=data.encode()
        self.send_response(status)
        for k,v in {'Content-Type':ctype,'Content-Length':str(len(data)),'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
            'Content-Security-Policy':content_security_policy(),**(extra or {})}.items():self.send_header(k,v)
        self.end_headers()
        try:self.wfile.write(data)
        except (ConnectionAbortedError,ConnectionResetError,BrokenPipeError):pass
    def trusted(self):return self.headers.get('Host','') in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
    def do_GET(self):
        if not self.trusted():return self.send(403,{'error':'Local access only.'})
        path=urllib.parse.urlsplit(self.path).path
        try:
            if path=='/':return self.send(200,(ROOT/'index.html').read_text('utf8').replace('__TOKEN__',TOKEN),'text/html; charset=utf-8')
            if path in ['/app.js','/style.css']:return self.send(200,(ROOT/path[1:]).read_bytes(),mimetypes.guess_type(path)[0])
            if path.startswith('/fonts/') and re.fullmatch(r'/fonts/[A-Za-z0-9_-]+\.ttf',path):
                font_path=ROOT/path[1:]
                if font_path.is_file():return self.send(200,font_path.read_bytes(),'font/ttf')
            if path=='/api/issue':
                with LOCK:
                    issue_id = active_issue_id()
                    project = load(issue_id) if issue_id else None
                return self.send(200, dict(project=project))
            if path=='/api/wordpress':
                settings = wordpress_settings()
                validate_wordpress_site(settings['site'])
                return self.send(200, dict(site=settings['site'], configured=wordpress_ready(settings)))
            if path=='/api/taxonomy':
                settings=wordpress_settings();result={}
                for kind in ('categories','tags'):
                    values=[]
                    for page in range(1,101):
                        batch=wp_read(settings,kind,per_page=100,page=page,_fields='id,name,slug')
                        values.extend(batch)
                        if len(batch)<100:break
                    result[kind]=values
                return self.send(200,result)
            return self.send(404,{'error':'Not found.'})
        except Exception as ex:self.send(400,{'error':str(ex)})
    def do_POST(self):
        if not self.trusted() or self.headers.get('X-Workbench-Token')!=TOKEN:return self.send(403,{'error':'Reload this local app to continue.'})
        origin=self.headers.get('Origin')
        if origin and origin not in {f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'}:return self.send(403,{'error':'Local requests only.'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=100*1024*1024:raise ValueError('Request must be under 100 MB.')
            raw=self.rfile.read(length)
            with LOCK:
                if self.path=='/api/indd':return self.send(200,import_indd(raw,urllib.parse.unquote(self.headers.get('X-Filename','issue.indd'))))
                data=json.loads(raw)
                if self.path=='/api/save':
                    require_active_issue(data.get('id'))
                    result=save_edits(data)
                elif self.path=='/api/close':
                    require_active_issue(data.get('id'))
                    set_active_issue(None)
                    result = dict(closed=True)
                elif self.path=='/api/new':result=article()
                elif self.path in ('/api/prepare-issue', '/api/preflight', '/api/draft'):
                    require_active_issue(data.get('id'))
                    settings = wordpress_settings()
                    if not wordpress_ready(settings):
                        raise ValueError('Fill in WP_USERNAME and WP_APPLICATION_PASSWORD in the .env file beside app.py.')
                    validate_wordpress_site(settings['site'])
                    project = load(data['id'])
                    if self.path == '/api/prepare-issue':
                        result = prepare_issue(project, settings)
                    elif self.path == '/api/preflight':
                        cache = {'history': draft_history()}
                        findings = []
                        for aid in dict.fromkeys(data['article_ids']):
                            try:
                                _, check = draft_preflight(project, aid, settings, cache, data.get('require_reviewed', False))
                            except (ValueError, OSError) as error:
                                a = next((item for item in project['articles'] if item['id'] == aid), {})
                                check = dict(id=aid, title=a.get('title', 'Article'), errors=[str(error)], duplicates=[])
                            findings.append(check)
                        result = dict(site=settings['site'], checks=findings)
                    else:
                        if data.get('site') != settings['site']:
                            raise ValueError('The WordPress site changed. Reopen the draft confirmation.')
                        payload, check = draft_preflight(project, data['article_id'], settings,
                                                         {'history': draft_history()}, require_reviewed=True)
                        if check['errors']:
                            raise ValueError(' '.join(check['errors']))
                        if check['signature'] != data.get('signature'):
                            raise ValueError('This article changed. Check it again before confirming.')
                        duplicates = sorted(match['id'] for match in check['duplicates'])
                        if duplicates and duplicates != data.get('acknowledged_duplicates'):
                            raise ValueError('WordPress has a possible duplicate. Check the existing post before confirming.')
                        result = create_draft(project, data['article_id'], settings, payload)
                else:return self.send(404,{'error':'Not found.'})
            self.send(200,result)
        except Exception as ex:self.send(400,{'error':str(ex)})

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=DEFAULT_PORT);parser.add_argument('--open',action='store_true');args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'INDD Text Workbench: http://localhost:{args.port}',flush=True)
    if args.open:webbrowser.open(f'http://localhost:{args.port}')
    try:server.serve_forever()
    except KeyboardInterrupt:server.server_close()
