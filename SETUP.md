# Clockify monthly report

This guide sets up a monthly time report.

Each month you export a Clockify summary as a PDF and upload it on a web page.

The upload creates a Gmail draft with the PDF attached and adds a row to a Google Sheet.

If a month is still missing near its end, a reminder email is sent to you.

## What you need

- A Google account with Gmail, Google Drive, and Google Sheets.
- A Make.com account.
- A Cloudflare account, for the upload page.
- A Google account for Apps Script, which can be the same account.
- Python 3 and Node.js on your computer.
- Access to the monthly report in Clockify.

## Step 1: Configure the values

1. Copy `clockify.env.example` to `clockify.env`.

   Keep `clockify.env` private, because it holds passwords and IDs.

2. Fill in every key with your own value.

   | Key | Where to get it |
   | --- | --- |
   | `TO_RECIPIENTS` | Comma-separated addresses, chosen by you, that receive the Gmail draft. |
   | `CC_RECIPIENTS` | Comma-separated addresses, chosen by you, to copy on the draft. |
   | `APPROVER_NAME` | The name the draft asks to approve the report, which you choose. |
   | `YOUR_NAME` | Your full name, used in the PDF filename. |
   | `YOUR_FIRST_NAME` | Your first name, used in the reminder greeting. |
   | `YOUR_EMAIL` | Your own address, which receives the reminder. |
   | `CLIENT_NAME` | The client name exactly as Clockify shows it, used in the PDF filename. |
   | `UPLOAD_FORM_URL` | The address Cloudflare prints after the deploy in Step 6. |
   | `PROCESS_WEBHOOK_URL` | The URL Make shows for the custom webhook you create in Step 5. |
   | `FORM_PASSWORD` | A long, unique password that you choose. |
   | `REMINDER_TOKEN` | A long random string that you choose, for example from `openssl rand -hex 24`. |
   | `SPREADSHEET_ID` | The part of the Google Sheet URL between `/d/` and `/edit`. |
   | `CLOCKIFY_REPORTS_FOLDER_ID` | The part of the Drive folder URL after `/folders/` for the `Clockify Reports` folder. |
   | `PROCESSED_FOLDER_ID` | The same, for the `Processed` folder inside it. |
   | `PROCESS_HOOK_ID` | Not looked up, any whole number that differs from `REMINDER_HOOK_ID`. |
   | `REMINDER_HOOK_ID` | Not looked up, any whole number that differs from `PROCESS_HOOK_ID`. |
   | `HOURLY_RATE` | Your hourly rate in ILS as a whole number, for example `330`. |
   | `VAT_PERCENT` | The VAT percentage you charge, for example `18`. |
   | `OVERTIME_THRESHOLD_HOURS` | The hours a month can reach before the draft shows the overtime box, where leaving it empty turns the box off. |
   | `OVERTIME_RATE_NOTE` | The text shown in the overtime box, under the threshold line. |

   When you import a blueprint in Make, you pick the webhook yourself, so the hook IDs are never typed into Make.

   The generator uses the hook IDs only to build the blueprint, then replaces them with placeholders in the shared files.

## Step 2: Generate the files

1. Open a terminal in the repo folder.
2. Run these two commands:

```
python3 _generate.py
python3 fill_html.py
```

3. The first command prints `ALL_PASS` when every check succeeds.
4. The second command writes `filled/email-draft.html` and `filled/email.html` with your values.

   Use the files in `filled/` for anything you paste into Make.

Run both commands again every time you change `clockify.env`.

`filled/`, `functions/`, and `clockify.env` hold your values, so keep them private.

## Step 3: Set up the Google Sheet and Drive folders

1. Create a Google Sheet.
2. In row 1, put these headers from left to right: `Month/Year`, `Start Date`, `End Date`, `Total Hours`, `Hourly Rate`, `Approver`, `To`, `CC`, `VAT`.

   The processing scenario writes columns A to I in that order.

3. Create one tab for each client, named exactly like the client in Clockify.
4. Copy the spreadsheet ID from the sheet URL, which is the part between `/d/` and `/edit`, into `SPREADSHEET_ID`.
5. In Google Drive, create a folder named `Clockify Reports`.
6. Inside it, create a folder named `Processed`.
7. Copy the ID of each folder from its URL, which is the part after `/folders/`, into `CLOCKIFY_REPORTS_FOLDER_ID` and `PROCESSED_FOLDER_ID`.
8. Run Step 2 again.

## Step 4: Set up Clockify

1. In your Clockify profile, set the date format to `DD/MM/YYYY`.
2. The Total line in the PDF must read `HH:MM` or `HH:MM:SS`.
3. The detailed report must include a line like `Client - Project - Task`.

   The client name before the first ` - ` becomes the company name, the Sheet tab, and the PDF filename.

4. Export the monthly report as a PDF that contains selectable text.

   A scanned PDF without text will not work.

## Step 5: Import the processing scenario in Make

### Create a Google OAuth client for Make

Make needs its own OAuth client to reach your Google Drive, Sheets, and Gmail.

1. Open the Google Cloud Console at console.cloud.google.com, and create a project or pick an existing one.
2. Enable the Google Drive API, the Google Sheets API, and the Gmail API.
3. Set up the OAuth consent screen, and if the app stays in testing, add your Google account under Test users.
4. Open Credentials, click Create credentials, and choose OAuth client ID.
5. Choose Web application as the application type.
6. Copy the redirect URI that Make shows in its Google connection dialog, and add it under Authorized redirect URIs.
7. Click Create, then copy the client ID and client secret into the Make connection.

Keep the client secret only in Make, never in `clockify.env` or the repo.

### Import the scenario

1. In Make, create a scenario with the timezone you report in, for example `Asia/Jerusalem`.
2. Open the three-dot menu and choose Import Blueprint.
3. Select `blueprints/process-report.blueprint.json`.
4. Connect the Google Drive and Google Sheets modules with the OAuth client from the section above, using a Google account that can open your folders and sheet.
5. Connect the Gmail module with the Gmail app, version 4, using the account that should create the drafts.
6. In the first module, a custom webhook, select or create a webhook.

   Copy its URL into `PROCESS_WEBHOOK_URL`, then run Step 2 again.

7. Keep the first module's scheduling on Immediately, with a maximum of 5 runs per minute.
8. Replace the placeholders as described in "Replace the placeholders in Make" below.
9. Save the scenario, then turn it on.

If a Google module did not import, add a Google Drive module that uploads a file with Convert set to Yes and the target Google Docs, and a Google Drive module that downloads the file as Google Docs in plain text.

## Step 6: Deploy the upload page on Cloudflare Pages

1. Open a terminal in the repo folder.
2. Run these two commands, and replace `YOUR-PROJECT-NAME` with a name you choose:

```
npx wrangler login
npx wrangler pages deploy pages --project-name YOUR-PROJECT-NAME
```

3. Copy the address Cloudflare shows for the deployment into `UPLOAD_FORM_URL`, then run Step 2 again.
4. Deploy from the repo root, so the `functions/` folder is deployed with the page.

The upload page asks for the PDF and the password.

The page never shows the webhook URL or the password.

The function forwards uploads to the value of the `MAKE_WEBHOOK_URL` variable in Cloudflare if you set one, and otherwise to the URL in `functions/api/upload.js`.

## Step 7: Import the reminder scenario in Make

1. Create a second scenario with the same timezone as Step 5.
2. Import `blueprints/monthly-reminder.blueprint.json`.
3. In the first module, a custom webhook, select or create a webhook.

   Copy its URL, because Step 8 needs it.

4. In that module's advanced settings, turn on Get request headers.
5. Connect the Google Drive, Google Sheets, and Gmail modules as in Step 5.
6. Replace the placeholders as described below.
7. Save the scenario, then turn it on.

The Check token module rejects any call whose `Authorization` header is not `Bearer` followed by your `REMINDER_TOKEN`, with HTTP 403.

## Replace the placeholders in Make

The imported scenarios contain placeholders written in capital letters inside angle brackets, such as `<SPREADSHEET_ID>`.

Replace each placeholder with the value of the same key in `clockify.env`.

Two groups are handled differently.

- Webhook fields: select the webhook in Make instead of typing an ID.
- Recipients: `<TO_EMAIL_1>` and `<TO_EMAIL_2>` take the first and second entries of `TO_RECIPIENTS`, and `<CC_EMAIL_1>` to `<CC_EMAIL_4>` take the entries of `CC_RECIPIENTS` in order.

`<HOURLY_RATE_ILS>` takes the value of `HOURLY_RATE`.

## Step 8: Schedule the reminder with Apps Script

1. Go to script.google.com, and click New project.
2. In the editor, select the default `Code.gs` file, delete its contents, paste the contents of `apps-script/Code.gs`, and press Cmd+S.
3. In the left menu, click the gear icon to open Project Settings.
4. Set the time zone to `Asia/Jerusalem`.

   The script stops with an error in any other time zone.

5. Scroll down to Script Properties, and click Add script property.
6. Add `MAKE_URL` with the reminder webhook URL from Step 7.
7. Add `MAKE_TOKEN` with the value of `REMINDER_TOKEN`.

   Keep both values in Script Properties only, and never paste them into `Code.gs`.

   The script stops with "Missing configuration properties." if either one is missing.

8. Go back to the editor, choose `scheduleLastDayTrigger` in the function dropdown in the toolbar, click Run, and approve the permissions it asks for.

The script then runs on the first day of each month at 09:00, and schedules that month's reminder.

The reminder runs at 19:00 on the last working day of the month.

When the last day is a Friday, a Saturday, or a holiday, the reminder moves to an earlier day.

Before a holiday, the reminder runs at 15:00.

The script reads the Jewish holidays from hebcal.com.

## Step 9: Test the setup

1. Upload one monthly PDF on your upload page with your `FORM_PASSWORD`.
2. Expect these results:

   - The page says the report was processed.
   - A row appears in the Sheet tab for the client.
   - A Gmail draft appears in Drafts with the PDF attached.
   - The PDF moves to the `Processed` folder.

3. Nothing is sent to the client.

   You review the draft in Gmail and send it yourself.

4. Check that the reminder rejects a wrong token with HTTP 403:

```
curl -X POST "REMINDER_WEBHOOK_URL" -H "Authorization: Bearer wrong-token" -H "Content-Type: application/json" -d '{"trigger":"end_of_month"}'
```

Replace `REMINDER_WEBHOOK_URL` with the URL from Step 7.

Calling the reminder with the correct token sends the reminder email when the month is missing, so only do that when you want the email.

## Troubleshooting

- The reminder returns 403: the token in Make does not match `REMINDER_TOKEN`.
- The Apps Script stops with a time zone error: set the project time zone to `Asia/Jerusalem`.
- A mapped field in Make shows a red pill: select the field again from the module's output.
- A run stopped and left a Google Doc named `Clockify_extract` in Processed: delete it before you upload the PDF again.
- The page asks you to confirm an entry longer than 9 hours: tick the box and upload the same PDF again.
- The page says the month is already logged: no second row or draft is created.

## How the amounts are calculated

- Minutes are hours times 60, plus the minutes.
- The subtotal is the month's minutes times `HOURLY_RATE`, divided by 60.
- VAT is the subtotal times `VAT_PERCENT`, divided by 100, rounded half up.
- The overtime box appears only when the month passes `OVERTIME_THRESHOLD_HOURS` hours, and only when that value is set.
