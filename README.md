# The Current — WordPress Drafts

This app does one job: review an article and create its WordPress draft.

## Run

The editorial workbench follows the selected Stitch design, with a searchable pale-blue article queue, a serif text editor, and a WordPress metadata inspector. Queue rows show the byline, section, review status, and word count. Fonts are bundled locally in `fonts/`. After updating an already-running copy, restart `start.cmd` and refresh the browser to load the local font routes.

Double-click **start.cmd** and open **http://localhost:3000**. Use Python 3.11 or newer and keep the bundled Windows reader in **tools/**. Keep the app running while using it. Port 3000 must be available; use `start.cmd --port 3001` if another app occupies it. Saved work is stored on disk and survives port changes.

Choose an **.indd** file. The app keeps one INDD open across reloads. Choose **Close INDD** to save and return to the file picker. Choosing the same file again resumes your saved review.

The bundled [indd-utils reader](https://github.com/storytold/indd-utils) reads supported native InDesign files locally without Adobe InDesign installed or a separate export from the designer. It uses a temporary IDML package internally and discards it after reading the text. The importer uses article groups and text-frame layout where available. Check headlines, authors, body order and endings in the review screen. Text converted to outlines or embedded in pictures cannot be recovered as text. Very old InDesign 1.x files are unsupported.

## Connect to WordPress

Open **.env** beside **app.py** in a text editor and fill in `WP_USERNAME` with your WordPress username and `WP_APPLICATION_PASSWORD` with your WordPress application password. `WP_SITE` is already set to Mako Media Network. Put one setting on each line, immediately after the equals sign. Spaces in the application password are fine. Save the file as UTF-8. The app picks up changes the next time you open draft confirmation.

## Draft an article

The issue queue has a headline and byline search, plus All, Needs review, and Reviewed filters. Filtering keeps the open article available for editing. Use the previous and next buttons above the editor to move through the filtered queue. The batch action applies to all reviewed articles in the issue, including articles outside the current filter.

1. Select an article or add one manually.
2. Edit its headline. The article body opens as a rendered preview; click the text to edit its HTML source, then click outside the editor to return to the preview.
3. Add as many byline authors as needed. Enter each author’s display name and WordPress author slug; the app uses them to build linked byline HTML. It does not search for or assign WordPress user accounts. WordPress assigns the connected account to each new draft.
4. Check the categories and tags. The app suggests a matching WordPress category from the InDesign section when available. Categories are editable, and removing a suggestion keeps it removed. Tag defaults are **add-about** and **Posts By <name>** for each author. They can be removed and stay removed. Automatic coauthor tags can be disabled.
5. Use **Check article** to look for missing text, missing WordPress categories or tags, and matching titles on WordPress posts you can access. Mark the article reviewed when ready.
6. Choose **Create WordPress draft** for one article or **Create reviewed drafts** for the reviewed articles in this INDD. Review the results of the check and confirm. Unready articles and possible duplicates stay in the queue. If a single article legitimately shares a title with an existing post, open its draft confirmation and explicitly include it.

The draft contains the byline and article HTML. Categories and tags must already exist.

Successful drafts leave the review queue and the next article opens. Failed or unconfirmed attempts remain in review. Draft history prevents duplicate submissions after reopening or reimporting the same issue. After an uncertain network result, check WordPress before retrying. Records are in **native-data/wordpress-drafts.json**.

## Storage and access

Changes save automatically under **native-data/**. Original recovered text and completed draft records remain local. Non-article material from earlier versions is preserved internally but is absent from the article queue and cannot be sent as a draft.

The local server reads credentials from **.env** and keeps them out of the browser. Keep that file private. The server listens only on 127.0.0.1. WordPress access depends on the site’s permissions and application-password policy. There is no publish operation.

The verified Vol. 37, Issue 4 import supplies 15 article entries. Other INDD files are read using the bundled reader and can need manual review to exclude non-article text.

## Verification

Run `python -m unittest discover -s tests -v`. Checks cover native text receipts, removable default tags, plain draft content, exclusion of non-articles, draft confirmation, review queue persistence, and duplicate prevention. WordPress writes are mocked in tests.
