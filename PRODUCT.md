# The Current — WordPress Drafts

## Platform

web

## Users

The Current's editors and production staff who turn a finished newspaper issue into WordPress drafts.

## Product Purpose

Let an editor open one InDesign issue, verify each headline, byline, and article body, and create WordPress drafts without retyping the issue. Success means completed drafts leave the review queue, anything needing attention stays available for review, and editors can close the app and resume their saved work later.

## Operating Context

The application runs locally on Windows through a browser. Editors work with one INDD issue at a time and compare recovered text with the finished issue before sending it to WordPress.

The existing implementation uses a Python local server and plain HTML, CSS, and JavaScript. `start.cmd` starts the application at `http://localhost:3000`; `app.py` supports a configurable port. App screens and documents are built directly in code.

## Capabilities and Constraints

- Read INDD files locally on Windows without requiring Adobe InDesign.
- Keep only one issue open at a time.
- Support review and editing of headlines, bylines, and article bodies.
- Require editorial review and explicit confirmation before sending anything to WordPress.
- Create drafts with article HTML. Never publish.
- Keep byline names and slugs, category suggestions, and tags editable.
- Use existing WordPress categories and tags.
- Preserve saved progress and review queues across closing and reopening the app.
- Prevent duplicate submissions. Articles needing attention remain in the review queue.
- Keep WordPress credentials in `.env` and out of browser code and version control.

## Brand Commitments

The existing product name is The Current — WordPress Drafts. Its interface supports an editorial production task; future changes must preserve the confirmed workflow and terminology.

## Evidence on Hand

- `README.md` documents installation, local INDD import, author lookup, editable metadata, review, draft confirmation, persistence, and duplicate prevention.
- `index.html`, `app.js`, and `style.css` contain the incumbent interface.
- `app.py`, `indd_reader.py`, and `indd_text.py` implement the local server and import workflow.
- `issue-recipes/current-vol37-issue4.json` is an existing issue-specific import recipe. The README records a verified Vol. 37, Issue 4 import with 15 article entries; this is not a guarantee for other files.
- `tests/test_workbench.py` covers application behavior with WordPress writes mocked.

## Product Principles

- Recover issue text to eliminate retyping while keeping editors responsible for verifying it.
- Keep editorial review and explicit confirmation ahead of every WordPress submission.
- Preserve recoverable progress so interruptions do not discard editorial work.
- Make automation suggestions editable and keep unresolved work visible.
- Limit WordPress output to drafts and protect against duplicate submissions.

## Accessibility & Inclusion

- Make the full workflow keyboard-operable.
- Provide visible focus and clear field labels.
- Communicate review status and errors through text as well as color.
- Keep the editor usable at narrow viewport widths and high zoom.

## Open Decisions

No formal accessibility conformance level or numeric zoom target has been specified. The functional accessibility requirements above remain binding.
