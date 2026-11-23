# Clockify monthly report

You open `upload.html` in any browser.

The form posts to same-origin `/api/upload` (a Cloudflare Pages Function that forwards to Make).

Success and error HTML stay under the form — the browser never navigates to the webhook URL, and the webhook URL is not in the page HTML.

Make, running under the Gmail account you connect once on a desktop, has Google Drive turn the PDF into text, appends a row, creates a draft, and saves the file.

A second scenario starts from a Custom Webhook.

Call that webhook with header `Authorization: Bearer <reminder-token>` (already filled in the Check token filters; different from the upload form password).

Body may be JSON such as `{"trigger":"end_of_month"}`.

The webhook must have Advanced → Get request headers = Yes.

A wrong or missing Authorization value gets HTTP 403 and stops.

The ICS file `clockify-monthly-reminder.ics` is only a calendar reminder; it does not trigger Make by itself.

That run walks Drive PDFs (or a no-op slot if the folder is empty), waits until they are all processed, then checks every spreadsheet tab.

A reminder email is sent only when Sheets returns HTTP 200 with a body and the month value is confirmed missing after trim/lower match.

A Sheets error is treated as unknown (no email), not as missing.

## Create these first

1. A Google Sheet whose first row is exactly these headers, left to right:

   Month/Year, Start Date, End Date, Total Hours, Hourly Rate, Approver, To, CC, VAT

   The blueprint writes columns A–I in that order.

   Each company has its own tab named exactly like the Clockify client (e.g. `<CLIENT_NAME>`).

   Rename or add tabs to match; the processing scenario uses `{{30.company}}` for the tab.

   The reminder lists every tab and mails once per company missing this month.

2. Drive folders: `Clockify Reports` (inbox the reminder picks up from) and `Clockify Reports/Processed` (finished PDFs).

   You can also upload with the web form.

3. In Clockify, set the profile date format to `DD/MM/YYYY`.

   The Total line must be `HH:MM` or `HH:MM:SS`.

   Drive reads that text when it converts the PDF to a Google Doc.

   A scanned PDF with no text layer will not work.

   The Detailed report must include a line like `Client - Project - Task`; the client name before the first ` - ` becomes the company in the PDF filename.

## Replace these placeholders

| Placeholder | Where | Replace with |
| --- | --- | --- |
| Webhook URL | `upload.html` and the reminder’s HTTP module | `<PROCESS_WEBHOOK_URL>` |
| Form password | Process password filters, and the reminder’s HTTP module to process | `<FORM_PASSWORD>` |
| Reminder Authorization | Reminder Check token filters | `<REMINDER_TOKEN>` |
| Spreadsheet id | Both “Read logged months” modules | `<SPREADSHEET_ID>` |
| Drive folder IDs | Upload into Processed, and Rename/move if used | `<CLOCKIFY_REPORTS_FOLDER_ID>`, `<PROCESSED_FOLDER_ID>` |
| Form URL | Reminder email | `<UPLOAD_FORM_URL>` |
| Reminder inbox | Reminder email To | `<YOUR_EMAIL>` |
| Hourly rate and VAT | Make formulas, Append row, and the draft email | `<HOURLY_RATE_ILS>`, `<VAT_PERCENT>` |
| Recipients | Append row and Create Gmail draft | `<TO_EMAIL_1>`, `<TO_EMAIL_2>`, `<CC_EMAIL_1>` to `<CC_EMAIL_4>` |
| Your name and approver | PDF filename, reminder email, draft email | `<YOUR_NAME>`, `<YOUR_FIRST_NAME>`, `<APPROVER_NAME>`, `<CLIENT_NAME>` |
| Overtime note | Draft email | `<OVERTIME_RATE_NOTE>`, or delete that paragraph |

Notes on the table:

- Do not commit `upload.html`.

- Set `<FORM_PASSWORD>` in both places.

- Type the form password into the form’s Password field.

- Do not put the form password in `upload.html`.

- Set `<REMINDER_TOKEN>` as `Bearer <REMINDER_TOKEN>`.

- Send the same header when calling the reminder webhook.

- Do not put the reminder token in `upload.html`.

Host `upload.html` on Cloudflare Pages.

The generator writes the form to `pages/index.html` and a same-origin proxy to `functions/api/upload.js` (webhook URL stays server-side only).

From this repo:

```
npx wrangler login
npx wrangler pages deploy pages --project-name clockify-upload
```

Deploy from the repo root so Wrangler picks up the sibling `functions/` folder.

Do not put the form behind Google sign-in.

The form asks for a password; that value is what Make already checks.

Deploy only `pages` + `functions` so the blueprints (and the form password) stay out of the public site except for the server-side webhook forwarder.

## Import the processing scenario

1. In Make, create a scenario and set the timezone to `Asia/Jerusalem`.
2. Open the three-dot menu and choose Import blueprint.

   Select `blueprints/process-report.blueprint.json`.

3. In the first module (Custom webhook, Clockify report), select or create a webhook.

   Leave JSON pass-through off.

   Scheduling stays Immediately, as data arrives, with a maximum of **5** runs per minute.

   Do not switch it to an interval.

4. Open Read the PDF in Drive and PDF text, and connect the restricted Drive account.

   The first uploads the PDF as a temporary Google Doc in Processed.

   The second downloads that Doc as plain text.

   Delete the temporary Doc removes it.

   If a module did not import, add Google Drive → Upload a file (Convert a file: Yes, target Google Docs) and Google Drive → Download a file (advanced settings: Google Docs as plain text).

5. Open Read logged months and connect Google.

   Replace `<SPREADSHEET_ID>` with your spreadsheet id.

   If that module did not import, add Google Sheets → Make an API call, method GET, URL `spreadsheets/<SPREADSHEET_ID>/values/'{{30.company}}'!A2:A` (quotes around the tab name).

6. Open Append the month, connect the same Google account.

   Search Method is **Enter manually** (`mode: map`).

   Replace `<SPREADSHEET_ID>` with your spreadsheet id, and set Sheet Name to `{{30.company}}`.

   Confirm the nine Values in columns are still mapped.

   `85:30` is written as plain text so Sheets does not turn it into a time of day.

7. Open Create Gmail draft and pick the new Gmail connection (Gmail app v4, not the restricted Google one).

   Folders can stay empty; drafts go to Drafts.

   If the module is missing, add Gmail → Create a draft email, Body type Raw HTML, and paste `email-draft.html` into Content.

   Map the attachment data from `report` → `Data` on the webhook.

   The filename is `<YOUR_NAME>_Time_Report_[Company]_[Month]_[Year].pdf`, with company taken from the PDF text (spaces become `_`).

8. Open Upload into Processed, connect Drive, and choose `Clockify Reports/Processed` (form path).
9. Open both Rename and move into Processed modules if present; they run only when `driveFileId` is set.
10. Save, then turn the scenario on.

    The browser waits for this scenario to finish.

    Make’s webhook response limit is about 40 seconds.

An entry whose duration is longer than 9:00:00 stops the run.

Nothing is logged and no client draft is created.

The page shows that duration.

Tick “An entry over 9 hours is correct.” and upload the same PDF to continue.

A file from Drive sends the same warning to `<YOUR_EMAIL>` instead.

Submit one PDF with the password so the webhook learns `password` and `report`.

If pills are red, re-select `password` and `report` → Data on Read the PDF in Drive.

A failed run can leave a Google Doc named Clockify_extract in Processed; delete it before trying again.

## Import the reminder scenario

1. Create a second scenario, timezone `Asia/Jerusalem`.
2. Import `blueprints/monthly-reminder.blueprint.json`.
3. Open Reminder trigger (Custom webhook).

   It must be the **first** module.

   Select or create the webhook, and paste its URL wherever you call it from.

   Edit the webhook → Advanced settings → **Get request headers = Yes**.

   Scheduling: Immediately.

   Maximum runs to start per minute: **5**.

4. Open Check token.

   Filters read header `authorization` via `__IMTHEADERS__` and compare to `Bearer ` + reminder token.

   Bad path Reject the token returns 403.

   Call once with `Authorization: Bearer …` so Make sees headers in the bundle.

   Calendar / Apps Script HTTP must send that header.

5. Connect the restricted Drive account on **Look in Clockify Reports** and **Download from Clockify Reports**.

   Connect Google on **List sheet tabs** and **Read logged months**.

6. Open Send the reminder (Gmail v4).

   One module only.

   To is `<YOUR_EMAIL>`.

   Filter **Confirmed missing month after Sheets OK**: Read logged months statusCode 200, body exists, and Month missing = 1.

   Month year is exact `MMMM YYYY` (e.g. `October 2026`); matching trims and lowercases both sides.

   There must be no filters that reference a deleted Calendar module.

7. Optional: import `clockify-monthly-reminder.ics` into your calendar so you get a 19:30 last-day ping, and have that (or another Make scenario) HTTP-call the reminder webhook with `Authorization: Bearer …`.

When the reminder webhook runs with a valid token:

- Every real PDF in Clockify Reports is processed first (company from PDF text).

- An empty Drive uses a no-op slot so the flow continues.

- Then sheet tabs are checked once.

- Reminder emails go only when Sheets OK and the month is confirmed missing.

- After the reminder, upload via `<UPLOAD_FORM_URL>` (Drive will not be checked again that night).

For a September 2026 `<CLIENT_NAME>` report the Processed filename is `<YOUR_NAME>_Time_Report_<CLIENT_NAME>_September_2026.pdf`.

## Regex

Dates, first match.

Groups `start` and `end`:

```
(?<start>\d{2}/\d{2}/\d{4})\s*[-–—]\s*(?<end>\d{2}/\d{2}/\d{4})
```

Total duration.

The match is the line that starts with Total, so a “Project Total” row is ignored.

Group `hours` is `HH:MM`; a trailing `:SS` is not part of the group.

```
(?:^|\n)\s*Total:?\s*(?<hours>\d{1,4}:\d{2})(?::\d{2})?
```

Company (client) name.

First `Client - Project - Task` line; group `company` is the text before the first ` - `.

Spaces become `_` in the PDF filename.

```
(?:^|\n)\s*(?<company>[^\r\n\-]+?)\s*-\s*[^\r\n]+?\s*-\s*[^\r\n]+
```

All three parsers read the plain text from PDF text, module 5, field `data`.

After a test run, if that field is a file pill and the parser text is empty, map Data from PDF text into the parsers.

## Amounts

Minutes are `hours * 60 + minutes`.

Decimal hours are those minutes divided by 60 (`85:30` → `85.5`).

The subtotal is billable minutes times `<HOURLY_RATE_ILS>`, divided by 60.

VAT is the subtotal in agorot times `<VAT_PERCENT>`, divided by 100, rounded half up, then added back.

The note is included only when minutes are greater than 4800:

> This month's total exceeds 80 hours.

> <OVERTIME_RATE_NOTE>

## What the browser sees

`confirmation.html` is the webhook body after a new month is logged.

The live page substitutes the month where it says `{{12.value}}`.

The other replies are `already-processed.html`, `unreadable.html`, and `unauthorized.html`.

The draft is not sent.

You review it in Gmail and send it yourself.
