---
name: The Current — WordPress Drafts
description: An editorial workbench for reviewing issue text and preparing WordPress drafts.
colors:
  ink: "#161c21"
  muted: "#535f72"
  line: "#e2e9f0"
  control-line: "#bdc9c5"
  accent: "#00685c"
  accent-hover: "#005047"
  selected: "#dff2ee"
  paper: "#fff"
  canvas: "#eef4fb"
  inspector: "#f6faff"
  warning-bg: "#fff4dc"
  warning-ink: "#70501b"
  danger: "#991b1b"
  danger-bg: "#fee2e2"
  review-line: "#f0a3a3"
  reviewed-ink: "#166534"
  reviewed-line: "#86b99a"
  reviewed-bg: "#dcfce7"
  queue-hover: "#e2eaf4"
  author-avatar: "#d6e3fa"
  dialog-backdrop: "#16212ca6"
typography:
  display:
    fontFamily: "Newsreader, Georgia, serif"
    fontSize: "48px"
    fontWeight: 500
    lineHeight: 1.05
    letterSpacing: "-0.025em"
  headline:
    fontFamily: "Newsreader, Georgia, serif"
    fontSize: "20px"
    fontWeight: 600
    lineHeight: 1.3
  title:
    fontFamily: "Newsreader, Georgia, serif"
    fontSize: "16px"
    fontWeight: 600
    lineHeight: 1.375
  body:
    fontFamily: "Inter, Segoe UI, Arial, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
  copy:
    fontFamily: "Newsreader, Georgia, serif"
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 1.6470588235
  label:
    fontFamily: "Inter, Segoe UI, Arial, sans-serif"
    fontSize: "11px"
    fontWeight: 600
  mono:
    fontFamily: "JetBrains Mono, Consolas, monospace"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.3333333333
  micro:
    fontFamily: "Inter, Segoe UI, Arial, sans-serif"
    fontSize: "10px"
    fontWeight: 400
  dialog-body:
    fontFamily: "Inter, Segoe UI, Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 400
  welcome-body:
    fontFamily: "Inter, Segoe UI, Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 400
  loading-title:
    fontFamily: "Inter, Segoe UI, Arial, sans-serif"
    fontSize: "18px"
    fontWeight: 400
  mobile-display:
    fontFamily: "Newsreader, Georgia, serif"
    fontSize: "40px"
    fontWeight: 400
rounded:
  control: "0px"
  copy: "2px"
  dialog: "4px"
spacing:
  tight: "4px"
  compact: "8px"
  small: "12px"
  medium: "16px"
  large: "20px"
  roomy: "24px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.paper}"
    rounded: "{rounded.control}"
    padding: "7px 11px"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "7px 11px"
  button-text:
    backgroundColor: "transparent"
    textColor: "{colors.accent}"
    padding: "7px 5px"
  field:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "9px 10px"
  filter-selected:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.accent}"
    padding: "4px 8px"
  badge-needs-review:
    backgroundColor: "{colors.danger-bg}"
    textColor: "{colors.danger}"
    rounded: "{rounded.control}"
    padding: "1px 5px"
  badge-reviewed:
    backgroundColor: "{colors.reviewed-bg}"
    textColor: "{colors.reviewed-ink}"
    rounded: "{rounded.control}"
    padding: "1px 5px"
  import-panel:
    backgroundColor: "{colors.paper}"
    rounded: "{rounded.control}"
    padding: "36px"
  queue-row:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    padding: "8px 8px 8px 12px"
  category-selected:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.paper}"
    padding: "4px 8px"
  tag-chip:
    backgroundColor: "{colors.line}"
    typography: "{typography.mono}"
    padding: "2px 6px"
  featured-frame:
    backgroundColor: "{colors.canvas}"
    rounded: "{rounded.control}"

---

# Design System: The Current ? WordPress Drafts

## Overview

**Creative North Star: "Editorial Workbench"**

The interface follows the selected Stitch workstation: an issue-only header above a pale blue queue, a proofing surface, and a compact WordPress inspector. Teal controls identify actions; serif stories and monospaced metadata distinguish reading from production work.

The workbench keeps its dense square geometry while supporting editable bylines, categories, tags, and slugs. A visible review gate precedes draft checks and explicit confirmation.

**Key Characteristics:**

- Dense square controls and fine panel rules.
- Newsreader stories, Inter controls, and JetBrains Mono metadata.
- Blue paper tones and white structural surfaces.
- Text-labeled status and a desktop review gate.

## Colors

Frontmatter values are normative. Teal identifies actions and selection; cool paper tones distinguish content and structure.

### Primary

- **Workbench Teal:** accent identifies primary actions, selected categories, links, carets, focus, and active queue markers; accent-hover deepens primary hover and selected supports selection and success notices.

### Neutral

- **Ink and Muted Slate:** primary content and secondary labels.
- **White and Blue Paper:** paper, canvas, and inspector distinguish structural panels, queue, and proof text.
- **Structural and Control Rules:** line separates panels and fills tag chips; control-line outlines controls.
- **Review Status:** red needs-review and green reviewed labels carry explicit text; warning colors support recovered-text cautions.

**The Written Status Rule.** Pair review and error colors with readable state text.

## Typography

Newsreader serves stories, Inter serves controls, and JetBrains Mono serves metadata. All ship locally with Georgia, Segoe UI/Arial, and Consolas fallbacks respectively. Headline, queue title, story copy, and UI roles are specified in frontmatter. Uppercase inspector labels use tracking (0.04em). The issue filename, article position, word counts, author slugs, tags, and article HTML source use monospaced type. The welcome display retains its large serif treatment and reduces to (40px) on mobile.

## Layout

The issue-only top bar is (56px) high and contains the filename and Close Issue action. Desktop uses a quarter-width queue, then editor and inspector at (2:1) across the remaining space. Editor and inspector ribbons are (40px) high. Queue, proofing area, and metadata have separate scroll regions; the desktop review gate remains outside the metadata scroll region.

Below (1024px), panes stack in source order and the page scrolls; the queue list is bounded to (280px). Stacked copy has minimum height (640px), and the text area retains a minimum reading height (480px). At (760px) and below, filename and control spacing adjust while retaining compact geometry. The viewport minimum is (320px).

Inspector sections use (8px) insets, editor paper (12px), proof-stage framing (12px), and story textarea padding (16px). Welcome/import and dialog surfaces retain roomier spacing.

## Elevation & Depth

Fine rules and tonal layers provide most separation. The proof stage uses a small shadow (0 1px 2px #161c2110). The draft dialog uses a diffuse shadow (0 20px 64px #161c2133) and dark backdrop (#16212ca6). The active queue row uses an inset teal marker (3px). Focus uses a teal outline (3px), offset (3px), inset for queue rows.

The busy bar alternates over (1.2s) with ease-in-out timing. Reduced-motion preferences stop it and make correction scrolling instant.

## Shapes

Controls are square (0px radius); the story preview and HTML source editor retain softened corners (2px) and dialog (4px). Most rules are (1px); the review footer has a stronger top rule (2px). Category choices are compact rectangles despite their pill terminology. Tags have an inline removal control.

## Components

### Buttons

Primary buttons use teal, white text, and deeper hover. Secondary buttons use white and a control boundary. Text actions are teal and underlined. The full-width draft action is (40px) high; until reviewed it uses a muted fill, muted text, and opacity (0.75). Other disabled buttons use opacity (0.5). Interactive controls retain visible focus.

### Chips

Red/green review badges carry uppercase status words. Category buttons use aria-pressed, teal fill, white text, and a checkmark when selected. Tags use monospaced type and individually labeled removal buttons. Matching existing tags appear as suggestions; Enter adds a tag from the entry field.

### Cards / Containers

White inspector sections use fine dividers. Byline rows pair author name and slug inputs with an add-author action. The import panel remains a flat bordered welcome container. The proof stage frames a rendered story preview that switches to HTML source on click.

### Inputs / Fields

A single-line serif headline sits above the proof area. Search, tag entry, and slug fields stay compact; the article slug uses monospaced type and blue-gray fill. Visually hidden labels remain available to assistive technology.

### Navigation

Search matches headline or author. Count-bearing review filters expose selection. Queue rows show review state, headline, byline, and monospaced word count; section labels are hidden. Selected rows use white fill and an inset teal rule. PREV/NEXT follow the filtered list and disable at its limits.

### Review Gate and Draft Check

The review checkbox states that the article was verified against print. Edits clear review. The enabled draft action opens checks and explicit confirmation. The native dialog reports errors, duplicates, and results; correction actions focus the relevant field. Busy work makes background regions inert and restores focus afterward.

## Do's and Don'ts

### Do:

- **Do** preserve the issue-only header and compact pane ribbons.
- **Do** use Newsreader for stories, Inter for controls, and JetBrains Mono for metadata.
- **Do** preserve selected categories and removable tags.
- **Do** retain readable status text, visible focus, and draft confirmation.

### Don't:

- **Don't** add a branded masthead above the issue bar.
- **Don't** round square workstation controls into capsules.
- **Don't** replace the author summary with expanded forms by default.
- **Don't** upload selected images to WordPress before draft confirmation.
