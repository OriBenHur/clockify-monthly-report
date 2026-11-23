#!/usr/bin/env python3
"""Write the Clockify Make blueprints and check the regex, money, and calendar rules."""

import json
import math
import re
from calendar import monthrange
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_env(path):
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip():
            values[key.strip()] = value.strip()
    return values


ENV = load_env(ROOT / "clockify.env")

DATE_PATTERN = r"(?<start>\d{2}/\d{2}/\d{4})\s*[-–—]\s*(?<end>\d{2}/\d{2}/\d{4})"
HOURS_PATTERN = r"(?:^|\n)\s*Total:?\s*(?<hours>\d{1,4}:\d{2})(?::\d{2})?"
# One entry longer than 9:00:00. The monthly Total line is not an entry.
LONG_ENTRY_PATTERN = (
    r"(?<!Total: )(?<!Total )(?<!Total\n)(?<!Total:\n)"
    r"(?<!otal: )(?<!otal )(?<!otal\n)(?<!otal:\n)"
    r"(?<!OTAL: )(?<!OTAL )(?<!OTAL\n)(?<!OTAL:\n)"
    r"(?<long>(?:[1-9]\d{1,3}:[0-5]\d:[0-5]\d)"
    r"|(?:0?9:(?:0[1-9]|[1-5]\d):[0-5]\d)"
    r"|(?:0?9:00:(?:0[1-9]|[1-5]\d)))"
)
# Detailed report lines: "Client - Project - Task"
COMPANY_PATTERN = r"(?:^|\n)\s*(?<company>[^\r\n\-]+?)\s*-\s*[^\r\n]+?\s*-\s*[^\r\n]+"

TO = ENV["TO_RECIPIENTS"]
CC = ENV["CC_RECIPIENTS"]
HOURLY_RATE = int(ENV["HOURLY_RATE"])
VAT_PERCENT = int(ENV["VAT_PERCENT"])
OVERTIME_NOTE = "This month's total exceeds 80 hours."
OVERTIME_RATE = ENV["OVERTIME_RATE_NOTE"]
SUCCESS = "Report successfully processed and Gmail draft created!"
DEFAULT_SHEET_TAB = ENV["CLIENT_NAME"]
YOUR_NAME = ENV["YOUR_NAME"]
YOUR_FIRST_NAME = ENV["YOUR_FIRST_NAME"]
YOUR_EMAIL = ENV["YOUR_EMAIL"]
APPROVER_NAME = ENV["APPROVER_NAME"]
UPLOAD_FORM_URL = ENV["UPLOAD_FORM_URL"]
REPORT_FILE_PREFIX = YOUR_NAME.replace(" ", "_") + "_Time_Report"
SPREADSHEET_ID = ENV["SPREADSHEET_ID"]
CLOCKIFY_REPORTS_FOLDER = ENV["CLOCKIFY_REPORTS_FOLDER_ID"]
PROCESSED_FOLDER = ENV["PROCESSED_FOLDER_ID"]
WEBHOOK_URL = ENV["PROCESS_WEBHOOK_URL"]
FORM_PASSWORD = ENV["FORM_PASSWORD"]
REMINDER_TOKEN = ENV["REMINDER_TOKEN"]
# Make lowercases incoming header names in __IMTHEADERS__.
REMINDER_TOKEN_HEADER = "authorization"
REMINDER_AUTH_VALUE = "Bearer " + REMINDER_TOKEN
REMINDER_TOKEN_VALUE = (
    '{{get(map(15.`__IMTHEADERS__`; "value"; "name"; "'
    + REMINDER_TOKEN_HEADER
    + '"); 1)}}'
)
DRIVE_FILES = "ifempty(2.body.files; ifempty(2.files; emptyarray))"
DRIVE_FILE_COUNT = "{{length(" + DRIVE_FILES + ")}}"
DRIVE_FILES_ARRAY = "{{" + DRIVE_FILES + "}}"
DRIVE_ITER_ARRAY = (
    "{{if(length(" + DRIVE_FILES + "); "
    + DRIVE_FILES
    + "; add(emptyarray; emptystring))}}"
)
DRIVE_ITEM_ID = "{{12.id}}"
# Sheets A1 needs quotes when the tab name has spaces (or is mapped).
SHEET_READ_URL = (
    f"spreadsheets/{SPREADSHEET_ID}/values/'{{{{30.company}}}}'!A2:A"
)
LIST_SHEETS_URL = (
    f"spreadsheets/{SPREADSHEET_ID}?fields=sheets.properties.title"
)
REMINDER_WEBHOOK = 15
REMINDER_HOOK_ID = int(ENV["REMINDER_HOOK_ID"])
PROCESS_HOOK_ID = int(ENV["PROCESS_HOOK_ID"])
REMINDER_SHEET_URL = (
    f"spreadsheets/{SPREADSHEET_ID}/values/'{{{{10.properties.title}}}}'!A2:A"
)
PDF_NAME = (
    REPORT_FILE_PREFIX + '_{{replace(30.company; " "; "_")}}_'
    '{{replace(12.value; " "; "_")}}.pdf'
)

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

# Module ids in the processing scenario.
WEBHOOK = 1
ROUTER = 2
DENY = 3
UPLOAD = 4
CONVERT = 5
DATES = 6
HOURS = 7
AGG = 8
HOURS_HM = 9
MINUTES = 10
DECIMAL = 11
MONTH = 12
START = 13
END = 14
SUBTOTAL = 15
VAT = 16
TOTAL = 17
SHEET_READ = 18
BRANCH = 19
ALREADY_ROUTER = 20
ADD_ROW = 21
DRAFT = 22
ARCHIVE_ROUTER = 23
OK_UPLOAD = 24
MOVE_NEW = 25
UPLOAD_FILE = 26
OK_MOVE = 27
LOGGED_MONTHS = 28
ALREADY_FLAG = 29
COMPANY = 30
MOVE_DUP = 31
OK_DUP_MOVE = 32
OK_DUP = 33
PDF_FILE = 34
LONG_ENTRY = 36
LONG_ROUTER = 37
LONG_FORM = 38
LONG_MAIL = 39
LONG_DRIVE = 51
LONG_TEXT = 52


def month_switch(source):
    args = [source]
    for index, name in enumerate(MONTHS, start=1):
        args.append(f'"{index}"')
        args.append(f'"{name}"')
    return "switch(" + "; ".join(args) + ")"


def month_year_from_pdf():
    parsed = 'parseDate(6.start; "DD/MM/YYYY")'
    return "{{" + month_switch(f'formatDate({parsed}; "M")') + "}} {{formatDate(" + parsed + '; "YYYY")}}'


def long_date(group):
    parsed = f'parseDate(6.{group}; "DD/MM/YYYY")'
    name = "{{" + month_switch(f'formatDate({parsed}; "M")') + "}}"
    return name + " {{formatDate(" + parsed + '; "D")}}, {{formatDate(' + parsed + '; "YYYY")}}'


def month_year_from_now():
    return "{{" + month_switch('formatDate(now; "M")') + '}} {{formatDate(now; "YYYY")}}'


MINUTES_EXPR = (
    'parseNumber(get(split(9.value; ":"); 1)) * 60 + '
    'parseNumber(get(split(9.value; ":"); 2))'
)
LAST_DAY = 'formatDate(addDays(addMonths(setDate(now; 1); 1); -1); "YYYY-MM-DD")'
TODAY = 'formatDate(now; "YYYY-MM-DD")'

def page(title, heading, *details):
    paras = "\n".join(
        f'<p style="margin:{"0 0 0.75rem" if i < len(details) - 1 else "0"};'
        f'font-size:1rem;line-height:1.5;color:#52606d;">{detail}</p>'
        for i, detail in enumerate(details)
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{title}</title>
</head>
<body style="margin:0;background:#f4f6f8;color:#1f2933;font-family:Segoe UI,Helvetica,Arial,sans-serif;">
<main style="max-width:28rem;margin:0 auto;padding:2.5rem 1.25rem;">
<section style="background:#ffffff;border-radius:16px;padding:1.75rem 1.25rem;">
<h1 style="font-size:1.35rem;line-height:1.35;margin:0 0 0.75rem;">{heading}</h1>
{paras}
</section>
</main>
</body>
</html>
"""


SUCCESS_HTML = page(
    "Report processed",
    "✅ " + SUCCESS,
    "{{12.value}} drafts was created.",
    "Open Gmail drafts, review the attached PDF, and send it when it looks right.",
)
ALREADY_HTML = page(
    "Already processed",
    "This month is already logged.",
    "{{12.value}} is already in the sheet, so no second row or Gmail draft was created.",
)
FAILURE_HTML = page(
    "Report not processed",
    "The report was not processed.",
    "Check that the PDF is a Clockify summary with dates as DD/MM/YYYY and a Total of HH:MM or HH:MM:SS.",
    "Then look at the scenario run in Make.",
)
DENY_HTML = page(
    "Unauthorized",
    "This form is not authorized.",
    "Open the upload link from the reminder email and try again.",
)
LONG_HTML = page(
    "Check this entry",
    "An entry is longer than 9 hours.",
    "{{52.value}} is one continuous log.",
    "Nothing was logged and no client draft was created.",
    "Fix it in Clockify, or tick the box and upload the same PDF again.",
)


def email_html():
    overtime = (
        '{{if(' + MINUTES_EXPR + ' > 4800; "'
        "<div style='margin:20px 0 0;padding:12px 14px;background:#fff8e6;border-left:3px solid #b45309;'>"
        "<p style='margin:0;'>" + OVERTIME_NOTE + "</p>"
        "<p style='margin:8px 0 0;'>" + OVERTIME_RATE + "</p>"
        "</div>\"; \"\")}}"
    )
    row = (
        "<tr>"
        "<td style='padding:10px 0;border-bottom:1px solid #e4e7eb;color:#52606d;'>{label}</td>"
        "<td style='padding:10px 0;border-bottom:1px solid #e4e7eb;text-align:right;font-weight:600;'>{value}</td>"
        "</tr>"
    )
    rows = "\n".join([
        row.format(label="Period", value="{{13.value}} – {{14.value}}"),
        row.format(label="Total hours", value="{{9.value}}"),
        row.format(label="Hourly rate", value=f"{HOURLY_RATE} ILS"),
        row.format(label="Base", value="{{15.value}} ILS"),
        row.format(label=f"VAT {VAT_PERCENT}%", value="{{16.value}} ILS"),
        row.format(label="Total", value="{{17.value}} ILS"),
    ])
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DevOps Consulting Time Report</title>
</head>
<body style="margin:0;padding:0;background:#f4f6f8;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f8;padding:24px 12px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:12px;padding:28px 24px;font-family:Segoe UI,Helvetica,Arial,sans-serif;color:#1f2933;font-size:15px;line-height:1.5;">
<tr><td>
<p style="margin:0 0 8px;font-size:13px;letter-spacing:0.04em;text-transform:uppercase;color:#52606d;">DevOps consulting</p>
<h1 style="margin:0 0 20px;font-size:22px;line-height:1.3;">Time report — {{{{12.value}}}}</h1>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
{rows}
</table>
{overtime}
<p style="margin:20px 0 0;">{APPROVER_NAME}, please approve this time report.</p>
<p style="margin:16px 0 0;color:#52606d;font-size:13px;">The Clockify PDF is attached.</p>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""


UPLOAD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Upload Clockify report</title>
</head>
<body style="margin:0;background:#f4f6f8;color:#1f2933;font-family:Segoe UI,Helvetica,Arial,sans-serif;">
<main style="max-width:28rem;margin:0 auto;padding:2.5rem 1.25rem;">
<form id="upload" method="post" enctype="multipart/form-data" action="/api/upload" style="background:#ffffff;border-radius:16px;padding:1.5rem 1.25rem;">
<h1 style="font-size:1.35rem;line-height:1.3;margin:0 0 0.5rem;">Clockify time report</h1>
<p style="margin:0 0 1.25rem;color:#52606d;font-size:1rem;line-height:1.5;">Upload the monthly summary PDF and enter the password.</p>
<p style="margin:0 0 1.25rem;color:#52606d;font-size:1rem;line-height:1.5;">This page does not ask you to sign in to Google.</p>
<label for="report" style="display:block;font-weight:600;margin:0 0 0.5rem;">PDF file</label>
<input id="report" name="report" type="file" accept="application/pdf,.pdf" required style="display:block;width:100%;font-size:16px;margin:0 0 1rem;">
<label for="password" style="display:block;font-weight:600;margin:0 0 0.5rem;">Password</label>
<input id="password" name="password" type="password" autocomplete="current-password" required style="display:block;width:100%;box-sizing:border-box;font-size:16px;min-height:48px;margin:0 0 1rem;padding:0.75rem;border:1px solid #cbd2d9;border-radius:8px;">
<p style="margin:0 0 0.75rem;color:#52606d;font-size:1rem;line-height:1.5;">Tick this only when an entry over 9 hours is correct.</p>
<label style="display:flex;gap:0.6rem;align-items:flex-start;margin:0 0 1rem;font-size:1rem;line-height:1.4;">
<input type="checkbox" name="confirmLong" value="yes" style="width:1.25rem;height:1.25rem;margin:0.1rem 0 0;">
<span>An entry over 9 hours is correct.</span>
</label>
<input type="hidden" name="driveFileId" value="">
<button type="submit" style="display:block;width:100%;min-height:48px;border:0;border-radius:12px;background:#0f6f4e;color:#ffffff;font-size:16px;font-weight:600;">Upload report</button>
<p id="wait" style="display:none;margin:1rem 0 0;color:#52606d;">Creating the Gmail draft.</p>
<p id="wait-line2" style="display:none;margin:0.35rem 0 0;color:#52606d;">Stay on this page.</p>
<div id="result" style="display:none;margin:1.25rem 0 0;padding:1rem 0 0;border-top:1px solid #e4e7eb;" aria-live="polite"></div>
</form>
</main>
<script>
(function () {
  var form = document.getElementById("upload");
  var wait = document.getElementById("wait");
  var waitLine2 = document.getElementById("wait-line2");
  var result = document.getElementById("result");
  var button = form.querySelector("button");
  function setWaiting(on) {
    wait.style.display = on ? "block" : "none";
    waitLine2.style.display = on ? "block" : "none";
  }
  function breakAfterPeriods(root) {
    Array.prototype.slice.call(root.querySelectorAll("p")).forEach(function (p) {
      var parts = p.textContent.split(/\\.(?:\\s+|$)/).map(function (part) {
        return part.trim();
      }).filter(Boolean);
      if (parts.length < 2) return;
      var frag = document.createDocumentFragment();
      parts.forEach(function (part, i) {
        var next = document.createElement("p");
        next.setAttribute(
          "style",
          i < parts.length - 1
            ? "margin:0 0 0.75rem;font-size:1rem;line-height:1.5;color:#52606d;"
            : "margin:0;font-size:1rem;line-height:1.5;color:#52606d;"
        );
        next.textContent = /[.!?]$/.test(part) ? part : part + ".";
        frag.appendChild(next);
      });
      p.parentNode.replaceChild(frag, p);
    });
  }
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    result.style.display = "none";
    result.innerHTML = "";
    setWaiting(true);
    button.disabled = true;
    button.textContent = "Uploading…";
    fetch("/api/upload", { method: "POST", body: new FormData(form), credentials: "same-origin" })
      .then(function (response) {
        return response.text().then(function (html) {
          return { ok: response.ok, html: html };
        });
      })
      .then(function (payload) {
        var doc = new DOMParser().parseFromString(payload.html, "text/html");
        var section = doc.querySelector("section") || doc.querySelector("main");
        if (section) {
          result.innerHTML = section.innerHTML;
          breakAfterPeriods(result);
        } else if (payload.ok) {
          result.innerHTML = "<p style=\\"margin:0;\\">Report processed.</p>";
        } else {
          result.innerHTML =
            "<p style=\\"margin:0 0 0.75rem;\\">Upload failed.</p>" +
            "<p style=\\"margin:0;\\">Check the file and password, then try again.</p>";
        }
        result.style.display = "block";
      })
      .catch(function () {
        result.innerHTML =
          "<p style=\\"margin:0 0 0.75rem;\\">Upload failed.</p>" +
          "<p style=\\"margin:0;\\">Check the file and password, then try again.</p>";
        result.style.display = "block";
      })
      .finally(function () {
        setWaiting(false);
        button.disabled = false;
        button.textContent = "Upload report";
      });
  });
})();
</script>
</body>
</html>
"""

UPLOAD_FUNCTION_JS = """\
export async function onRequestPost(context) {
  const webhook = context.env.MAKE_WEBHOOK_URL || %s;
  const incoming = await context.request.formData();
  const upstream = await fetch(webhook, { method: "POST", body: incoming });
  const html = await upstream.text();
  return new Response(html, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") || "text/html; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}
""" % (json.dumps(WEBHOOK_URL),)


def scenario_meta(instant):
    return {
        "instant": instant,
        "version": 1,
        "scenario": {
            "roundtrips": 1,
            "maxErrors": 3,
            "autoCommit": True,
            "autoCommitTriggerLast": True,
            "sequential": False,
            "confidential": False,
            "dataloss": False,
            "dlq": False,
            "freshVariables": False,
        },
        "designer": {"orphans": []},
    }


def scheduling(instant, max_runs_per_minute=None):
    if instant:
        spec = {"type": "immediately"}
        if max_runs_per_minute is not None:
            spec["maximum_runs_per_minute"] = max_runs_per_minute
        return spec
    return None


def mod(module_id, module, x, y, name, mapper=None, parameters=None, version=1, filter_=None, onerror=None, routes=None):
    node = {
        "id": module_id,
        "module": module,
        "version": version,
        "parameters": {} if parameters is None else parameters,
        "mapper": {} if mapper is None else mapper,
        "metadata": {"designer": {"x": x, "y": y, "name": name}},
    }
    if filter_ is not None:
        node["filter"] = filter_
    if onerror is not None:
        node["onerror"] = onerror
    if routes is not None:
        node["routes"] = routes
        node["mapper"] = None
    return node


STEP_X = 300
STEP_Y = 220


def chain_width(nodes):
    width = 0
    for node in nodes:
        branch = 0
        for route in node.get("routes") or []:
            branch = max(branch, chain_width(route["flow"]))
        width += STEP_X + branch
    return width


def first_errors(flow):
    if not flow:
        return 0
    return len(flow[0].get("onerror") or [])


def layout(nodes, x0=0, y0=0):
    x = x0
    for node in nodes:
        designer = node["metadata"]["designer"]
        designer["x"] = x
        designer["y"] = y0
        for ei, err in enumerate(node.get("onerror") or []):
            layout([err], x, y0 + (ei + 1) * STEP_Y)
        routes = node.get("routes") or []
        branch = 0
        if routes:
            primary = max(range(len(routes)), key=lambda i: chain_width(routes[i]["flow"]))
            layout(routes[primary]["flow"], x + STEP_X, y0)
            branch = chain_width(routes[primary]["flow"])
            below_next = first_errors(routes[primary]["flow"]) + 1
            above_next = 1
            for ri, route in enumerate(routes):
                if ri == primary:
                    continue
                errs = first_errors(route["flow"])
                if below_next <= above_next:
                    ry = y0 + below_next * STEP_Y
                    below_next += 1 + errs
                else:
                    above_next += errs
                    ry = y0 - above_next * STEP_Y
                    above_next += 1
                layout(route["flow"], x + STEP_X, ry)
                branch = max(branch, chain_width(route["flow"]))
        x += STEP_X + branch


def filt(name, left, right, op):
    return {"name": name, "conditions": [[{"a": left, "b": right, "o": op}]]}


def logged_months_text(module_id):
    # google-sheets:makeAPICall nests the Sheets payload under body.
    # Output is body.values = [["September 2026"], ...].
    return (
        'join(flatten(ifempty('
        + str(module_id)
        + '.body.values; emptyarray)); ",")'
    )


def logged_months_normalized(module_id):
    # Make map() extracts a key; it cannot run trim per cell.
    # Normalize the joined column text and the needle (lower + trim) instead.
    return (
        'lower(join(flatten(ifempty('
        + str(module_id)
        + '.body.values; emptyarray)); ","))'
    )


def month_missing_formula(read_id):
    # 1 = confirmed missing, 0 = found, "" = Sheets failed / unknown.
    return (
        "{{if(" + str(read_id) + ".statusCode = 200; "
        "if(contains(" + logged_months_normalized(read_id)
        + '; lower(trim(1.value))); 0; 1); "")}}'
    )


def logged_months_formula():
    # Materialize column A as plain text.
    # Upload filename is irrelevant.
    return '{{' + logged_months_text(SHEET_READ) + '}}'


def already_logged_formula():
    return '{{if(contains(' + str(LOGGED_MONTHS) + '.value; 12.value); 1; 0)}}'


def html_headers():
    return [{"key": "Content-Type", "value": "text/html; charset=utf-8"}]


def respond(module_id, x, y, name, status, body):
    return mod(
        module_id, "gateway:WebhookRespond", x, y, name, version=1,
        mapper={"status": status, "body": body, "headers": html_headers()},
    )


def failure_handler(x, y, respond_id, rollback_id):
    return [
        respond(respond_id, x, y, "Tell the browser it failed", 422, FAILURE_HTML),
        mod(rollback_id, "builtin:Rollback", x + 300, y, "Roll back", mapper={}),
    ]


def http_request(module_id, x, y, name, url, fields):
    return mod(
        module_id, "http:MakeRequest", x, y, name, version=4,
        parameters={"authenticationType": "noAuth", "tlsType": "", "proxyKeychain": ""},
        mapper={
            "url": url,
            "method": "post",
            "contentType": "multipart",
            "parseResponse": False,
            "stopOnHttpError": True,
            "allowRedirects": True,
            "shareCookies": False,
            "requestCompressedContent": True,
            "timeout": 80,
            "multipartBodyContent": fields,
        },
    )


def variable(module_id, x, name, value):
    return mod(
        module_id, "util:SetVariable2", x, 0, name, version=1,
        mapper={"name": "value", "scope": "roundtrip", "value": value},
    )


def parser(module_id, x, name, pattern, text, global_match, sensitive, onerror=None):
    return mod(
        module_id, "regexp:Parser", x, 0, name, version=1,
        parameters={
            "pattern": pattern,
            "global": global_match,
            "sensitive": sensitive,
            "multiline": False,
            "singleline": False,
            "continueWhenNoRes": False,
            "ignoreInfiniteLoopsWhenGlobal": global_match,
        },
        mapper={"text": text},
        onerror=onerror,
    )


def google_conn(module):
    if module.startswith("google-email"):
        return [{"name": "__IMTCONN__", "type": "account:google-email", "label": "Connection", "required": True}]
    if module.startswith("google-calendar"):
        return [{"name": "__IMTCONN__", "type": "account:google", "label": "Connection", "required": True}]
    if module.startswith("google-drive"):
        account = "account:google-restricted"
    else:
        account = "account:google"
    return [{"name": "__IMTCONN__", "type": account, "label": "Connection", "required": True}]


def drive_api(module_id, x, y, name, mapper):
    node = mod(module_id, "google-drive:makeApiCall", x, y, name, version=4, mapper=mapper)
    node["metadata"]["parameters"] = google_conn("google-drive:makeApiCall")
    return node


def move_pdf(module_id, x, y):
    return drive_api(
        module_id, x, y, "Rename and move into Processed",
        {
            "url": "/v3/files/{{1.driveFileId}}",
            "method": "PATCH",
            "headers": [{"key": "Content-Type", "value": "application/json"}],
            "qs": [
                {"key": "addParents", "value": PROCESSED_FOLDER},
                {"key": "removeParents", "value": CLOCKIFY_REPORTS_FOLDER},
            ],
            "body": '{"name": "{{34.value}}"}',
        },
    )


def process_blueprint(message):
    good = [
        mod(
            UPLOAD, "google-drive:uploadAFile", 600, 0, "Read the PDF in Drive",
            version=4,
            mapper={
                "select": "map",
                "destination": "drive",
                "folderId": PROCESSED_FOLDER,
                "filename": "Clockify_extract.pdf",
                "data": "{{1.report.data}}",
                "convert": True,
                "targetType": "application/vnd.google-apps.document",
            },
            onerror=failure_handler(600, 280, 40, 41),
        ),
        mod(
            CONVERT, "google-drive:getAFile", 900, 0, "PDF text",
            version=4,
            mapper={
                "select": "map",
                "file": "{{4.id}}",
                "formatDocuments": "text/plain",
            },
            onerror=failure_handler(900, 280, 42, 43),
        ),
        drive_api(35, 1050, 0, "Delete the temporary Doc", {
            "url": "/v3/files/{{4.id}}",
            "method": "DELETE",
            "headers": [],
            "qs": [],
            "body": "",
        }),
        parser(
            DATES, 1200, "Start and end dates", DATE_PATTERN, "{{5.data}}",
            False, True, onerror=failure_handler(1200, 280, 44, 45),
        ),
        parser(
            HOURS, 1500, "Total hours", HOURS_PATTERN, "{{5.data}}",
            False, False, onerror=failure_handler(1500, 280, 46, 47),
        ),
        parser(
            COMPANY, 1650, "Company name", COMPANY_PATTERN, "{{5.data}}",
            False, True, onerror=failure_handler(1650, 280, 48, 49),
        ),
        variable(HOURS_HM, 1800, "Hours HH:MM", "{{7.hours}}"),
        variable(MINUTES, 2400, "Billable minutes", "{{" + MINUTES_EXPR + "}}"),
        variable(DECIMAL, 2700, "Decimal hours", "{{10.value / 60}}"),
        variable(MONTH, 3000, "Month year", month_year_from_pdf()),
        variable(START, 3300, "Start date", long_date("start")),
        variable(END, 3600, "End date", long_date("end")),
        variable(
            SUBTOTAL, 3900, "Subtotal",
            f'{{{{formatNumber(10.value * {HOURLY_RATE} / 60; 2; "."; ",")}}}}',
        ),
        variable(
            VAT, 4200, "VAT amount",
            f'{{{{formatNumber(floor(10.value * {HOURLY_RATE} * 100 / 60 * {VAT_PERCENT} / 100 + 0.5) / 100; 2; "."; ",")}}}}',
        ),
        variable(
            TOTAL, 4500, "Total with VAT",
            f'{{{{formatNumber((10.value * {HOURLY_RATE} * 100 / 60 + floor(10.value * {HOURLY_RATE} * 100 / 60 * {VAT_PERCENT} / 100 + 0.5)) / 100; 2; "."; ",")}}}}',
        ),
        variable(PDF_FILE, 4650, "PDF file name", PDF_NAME),
    ]
    long_parser = parser(
        LONG_ENTRY, 4700, "Long entry", LONG_ENTRY_PATTERN, "{{5.data}}",
        False, False,
    )
    long_parser["parameters"]["continueWhenNoRes"] = True
    long_parser["metadata"]["interface"] = [
        {"name": "long", "type": "text", "label": "long"},
    ]
    long_text = variable(LONG_TEXT, 4750, "Long entry text", '{{ifempty(36.long; "")}}')
    branch = mod(
            BRANCH, "builtin:BasicRouter", 5100, 0, "Already logged?",
            routes=[
                {
                    "flow": [
                        mod(
                            ALREADY_ROUTER, "builtin:BasicRouter", 5400, 280, "Move a Drive PDF?",
                            routes=[
                                {
                                    "flow": [
                                        move_pdf(MOVE_DUP, 5700, 420),
                                        respond(OK_DUP_MOVE, 6000, 420, "Already processed", 200, ALREADY_HTML),
                                    ]
                                },
                                {
                                    "flow": [
                                        respond(OK_DUP, 5700, 640, "Already processed", 200, ALREADY_HTML),
                                    ]
                                },
                            ],
                        ),
                    ]
                },
                {
                    "flow": [
                        mod(
                            ADD_ROW, "google-sheets:addRow", 5400, 0, "Append the month",
                            version=2,
                            mapper={
                                "mode": "map",
                                "insertUnformatted": False,
                                "valueInputOption": "RAW",
                                "insertDataOption": "INSERT_ROWS",
                                "spreadsheetId": f"/{SPREADSHEET_ID}",
                                "sheetId": "{{30.company}}",
                                "tableFirstRow": "A1:Z1",
                                "values": {
                                    "0": "{{12.value}}",
                                    "1": "{{13.value}}",
                                    "2": "{{14.value}}",
                                    "3": "{{9.value}}",
                                    "4": str(HOURLY_RATE),
                                    "5": APPROVER_NAME,
                                    "6": TO,
                                    "7": CC,
                                    "8": str(VAT_PERCENT),
                                },
                            },
                        ),
                        mod(
                            DRAFT, "google-email:createADraft", 5700, 0, "Create Gmail draft",
                            version=4,
                            mapper={
                                "to": TO.split(", "),
                                "cc": CC.split(", "),
                                "subject": "DevOps Consulting Time Report - {{12.value}}",
                                "bodyType": "rawHtml",
                                "content": message,
                                "attachments": [{
                                    "filename": "{{34.value}}",
                                    "data": "{{1.report.data}}",
                                }],
                            },
                        ),
                        mod(
                            ARCHIVE_ROUTER, "builtin:BasicRouter", 6000, 0, "Save the renamed PDF",
                            routes=[
                                {
                                    "flow": [
                                        move_pdf(MOVE_NEW, 6300, 0),
                                        respond(OK_MOVE, 6600, 0, "Success page", 200, SUCCESS_HTML),
                                    ]
                                },
                                {
                                    "flow": [
                                        mod(
                                            UPLOAD_FILE, "google-drive:uploadAFile", 6300, 200, "Upload into Processed",
                                            version=4,
                                            mapper={
                                                "select": "map",
                                                "destination": "drive",
                                                "folderId": PROCESSED_FOLDER,
                                                "filename": "{{34.value}}",
                                                "data": "{{1.report.data}}",
                                                "convert": False,
                                            },
                                        ),
                                        respond(OK_UPLOAD, 6600, 200, "Success page", 200, SUCCESS_HTML),
                                    ]
                                },
                            ],
                        ),
                    ]
                },
            ],
        )
    sheet_tail = [
        mod(
            SHEET_READ, "google-sheets:makeAPICall", 4800, 0, "Read logged months",
            version=2,
            mapper={
                "url": SHEET_READ_URL,
                "method": "GET",
                "headers": [],
                "qs": [],
                "body": "",
            },
        ),
        variable(LOGGED_MONTHS, 4875, "Logged months text", logged_months_formula()),
        variable(ALREADY_FLAG, 4950, "Already logged", already_logged_formula()),
        branch,
    ]
    long_mail = mod(
        LONG_MAIL, "google-email:sendAnEmail", 0, 0, "Email the long entry",
        version=4,
        mapper={
            "to": [YOUR_EMAIL],
            "subject": "Clockify entry longer than 9 hours — {{12.value}}",
            "bodyType": "rawHtml",
            "content": (
                "<p style='margin:0 0 12px;'>An entry is longer than 9 hours.</p>"
                "<p style='margin:0 0 12px;'>{{52.value}} is one continuous log.</p>"
                "<p style='margin:0;'>Nothing was logged and no client draft was created.</p>"
            ),
        },
    )
    long_router = mod(
        LONG_ROUTER, "builtin:BasicRouter", 0, 0, "Long entry?",
        routes=[
            {"flow": sheet_tail},
            {"flow": [respond(LONG_FORM, 0, 0, "Ask for confirmation", 200, LONG_HTML)]},
            {"flow": [long_mail, respond(LONG_DRIVE, 0, 0, "Long entry held", 200, LONG_HTML)]},
        ],
    )
    long_router["routes"][0]["flow"][0]["filter"] = {
        "name": "No long entry or already confirmed",
        "conditions": [
            [{"a": "{{52.value}}", "b": "", "o": "notexist"}],
            [{"a": "{{52.value}}", "b": "", "o": "text:equal"}],
            [{"a": "{{1.confirmLong}}", "b": "yes", "o": "text:equal"}],
        ],
    }
    long_router["routes"][1]["flow"][0]["filter"] = {
        "name": "Form upload needs confirmation",
        "conditions": [[
            {"a": "{{52.value}}", "b": "", "o": "text:notequal"},
            {"a": "{{1.confirmLong}}", "b": "yes", "o": "text:notequal"},
            {"a": "{{1.driveFileId}}", "b": "", "o": "text:equal"},
        ]],
    }
    long_router["routes"][2]["flow"][0]["filter"] = {
        "name": "Drive file needs confirmation",
        "conditions": [[
            {"a": "{{52.value}}", "b": "", "o": "text:notequal"},
            {"a": "{{1.confirmLong}}", "b": "yes", "o": "text:notequal"},
            {"a": "{{1.driveFileId}}", "b": "", "o": "text:notequal"},
        ]],
    }
    good.extend([long_parser, long_text, long_router])
    good[0]["filter"] = filt("Form password matches", "{{1.password}}", FORM_PASSWORD, "text:equal")
    branch["routes"][0]["flow"][0]["filter"] = {
        "name": "Month already logged",
        "conditions": [[
            {"a": "{{12.value}}", "b": "", "o": "text:notequal"},
            {"a": "{{29.value}}", "b": "1", "o": "number:equal"},
        ]],
    }
    branch["routes"][0]["flow"][0]["routes"][0]["flow"][0]["filter"] = filt(
        "Came with a Drive file id", "{{1.driveFileId}}", "", "text:notequal",
    )
    branch["routes"][0]["flow"][0]["routes"][1]["flow"][0]["filter"] = filt(
        "Came from the upload form", "{{1.driveFileId}}", "", "text:equal",
    )
    branch["routes"][1]["flow"][0]["filter"] = {
        "name": "Month not logged yet",
        "conditions": [[
            {"a": "{{12.value}}", "b": "", "o": "text:notequal"},
            {"a": "{{29.value}}", "b": "0", "o": "number:equal"},
        ]],
    }
    branch["routes"][1]["flow"][2]["routes"][0]["flow"][0]["filter"] = filt(
        "Came with a Drive file id", "{{1.driveFileId}}", "", "text:notequal",
    )
    branch["routes"][1]["flow"][2]["routes"][1]["flow"][0]["filter"] = filt(
        "Came from the upload form", "{{1.driveFileId}}", "", "text:equal",
    )
    deny = respond(DENY, 600, 420, "Reject the password", 403, DENY_HTML)
    deny["filter"] = filt("Form password does not match", "{{1.password}}", FORM_PASSWORD, "text:notequal")
    hook = mod(
        WEBHOOK, "gateway:CustomWebHook", 0, 0, "Report upload",
        version=1,
        parameters={"hook": PROCESS_HOOK_ID, "maxResults": 1},
    )
    hook["metadata"]["parameters"] = [
        {"name": "hook", "type": "hook:gateway-webhook", "label": "Webhook", "required": True},
        {"name": "maxResults", "type": "number", "label": "Maximum number of results"},
    ]
    hook["metadata"]["restore"] = {
        "parameters": {
            "hook": {
                "label": "Clockify report",
                "data": {"editable": "true"},
            }
        }
    }
    by_id = {node["id"]: node for node in _modules(good)}
    by_id[UPLOAD]["metadata"]["parameters"] = google_conn("google-drive:uploadAFile")
    by_id[CONVERT]["metadata"]["parameters"] = google_conn("google-drive:getAFile")
    by_id[ADD_ROW]["metadata"]["parameters"] = google_conn("google-sheets:addRow")
    by_id[ADD_ROW]["metadata"]["restore"] = {
        "expect": {
            "mode": {"label": "Enter manually"},
            "insertUnformatted": {"mode": "chose"},
            "valueInputOption": {"mode": "chose", "label": "Raw"},
            "insertDataOption": {"mode": "chose", "label": "Insert rows"},
            "tableFirstRow": {"label": "A-Z"},
        },
    }
    by_id[ADD_ROW]["metadata"]["expect"] = [
        {
            "name": "mode",
            "type": "select",
            "label": "Search Method",
            "required": True,
            "validate": {"enum": ["select", "fromAll", "map"]},
        },
        {"name": "insertUnformatted", "type": "boolean", "label": "Unformatted", "required": True},
        {
            "name": "valueInputOption",
            "type": "select",
            "label": "Value input option",
            "required": True,
            "validate": {"enum": ["USER_ENTERED", "RAW"]},
        },
        {
            "name": "insertDataOption",
            "type": "select",
            "label": "Insert data option",
            "validate": {"enum": ["INSERT_ROWS", "OVERWRITE"]},
        },
        {"name": "spreadsheetId", "type": "text", "label": "Spreadsheet ID", "required": True},
        {"name": "sheetId", "type": "text", "label": "Sheet Name", "required": True},
        {
            "name": "tableFirstRow",
            "type": "select",
            "label": "Column range",
            "required": True,
            "validate": {
                "enum": ["A1:Z1", "A1:BZ1", "A1:CZ1", "A1:DZ1", "A1:MZ1", "A1:ZZ1"],
            },
        },
        {
            "name": "values",
            "type": "collection",
            "label": "Values in columns",
            "spec": [
                {"name": str(i), "type": "text", "label": chr(65 + i)}
                for i in range(9)
            ],
        },
    ]
    by_id[DRAFT]["metadata"]["parameters"] = google_conn("google-email:createADraft")
    by_id[LONG_MAIL]["metadata"]["parameters"] = google_conn("google-email:sendAnEmail")
    by_id[UPLOAD_FILE]["metadata"]["parameters"] = google_conn("google-drive:uploadAFile")
    by_id[SHEET_READ]["metadata"]["parameters"] = google_conn("google-sheets:makeAPICall")
    by_id[DATES]["metadata"]["interface"] = [
        {"name": "start", "type": "text", "label": "start"},
        {"name": "end", "type": "text", "label": "end"},
    ]
    by_id[HOURS]["metadata"]["interface"] = [
        {"name": "hours", "type": "text", "label": "hours"},
    ]
    by_id[COMPANY]["metadata"]["interface"] = [
        {"name": "company", "type": "text", "label": "company"},
    ]
    router = mod(
        ROUTER, "builtin:BasicRouter", 300, 0, "Check password",
        routes=[{"flow": [deny]}, {"flow": good}],
    )
    flow = [hook, router]
    layout(flow)
    return {
        "name": "Clockify monthly report",
        "flow": flow,
        "metadata": scenario_meta(True),
        "scheduling": scheduling(True, max_runs_per_minute=5),
    }


def reminder_email_html(company):
    return (
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' "
        "style='background:#f4f6f8;padding:24px 12px;'>"
        "<tr><td align='center'>"
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' "
        "style='max-width:560px;background:#ffffff;border-radius:12px;padding:28px 24px;"
        "font-family:Segoe UI,Helvetica,Arial,sans-serif;color:#1f2933;font-size:15px;line-height:1.5;'>"
        "<tr><td>"
        "<p style='margin:0 0 8px;font-size:13px;letter-spacing:0.04em;text-transform:uppercase;"
        "color:#52606d;'>" + company + "</p>"
        "<h1 style='margin:0 0 12px;font-size:22px;line-height:1.3;'>"
        "Upload needed — {{1.value}}</h1>"
        "<p style='margin:0 0 20px;color:#52606d;'>Hello " + YOUR_FIRST_NAME + ", it is the evening of the last day of the month, "
        "and no hours report for " + company + " was logged yet.</p>"
        "<p style='margin:0 0 20px;color:#52606d;'>Upload the Clockify PDF with the form below.</p>"
        "<p style='margin:0 0 20px;color:#52606d;'>The Gmail draft is created automatically.</p>"
        "<p style='margin:0 0 20px;'>"
        "<a href='" + UPLOAD_FORM_URL + "' "
        "style='display:inline-block;background:#0f6f4e;color:#ffffff;text-decoration:none;"
        "font-weight:600;font-size:16px;padding:14px 22px;border-radius:10px;'>"
        "Upload the report</a></p>"
        "</td></tr></table>"
        "</td></tr></table>"
    )


def sheet_reminder_flow(list_id, feed_id, read_id, missing_id, mail_id):
    list_sheets = mod(
        list_id, "google-sheets:makeAPICall", 0, 0, "List sheet tabs",
        version=2,
        mapper={
            "url": LIST_SHEETS_URL,
            "method": "GET",
            "headers": [],
            "qs": [],
            "body": "",
        },
    )
    list_sheets["metadata"]["parameters"] = google_conn("google-sheets:makeAPICall")
    iterate = mod(
        feed_id, "builtin:BasicFeeder", 0, 0, "Each company tab",
        version=1,
        mapper={"array": "{{" + str(list_id) + ".body.sheets}}"},
    )
    sheet_url = (
        f"spreadsheets/{SPREADSHEET_ID}/values/'{{{{{feed_id}.properties.title}}}}'!A2:A"
    )
    sheets = mod(
        read_id, "google-sheets:makeAPICall", 0, 0, "Read logged months",
        version=2,
        mapper={
            "url": sheet_url,
            "method": "GET",
            "headers": [],
            "qs": [],
            "body": "",
        },
    )
    sheets["metadata"]["parameters"] = google_conn("google-sheets:makeAPICall")
    missing = variable(
        missing_id, 0, "Month missing from sheet",
        month_missing_formula(read_id),
    )
    company = "{{" + str(feed_id) + ".properties.title}}"
    mail = mod(
        mail_id, "google-email:sendAnEmail", 0, 0, "Send the reminder",
        version=4,
        mapper={
            "to": [YOUR_EMAIL],
            "subject": "Upload the Clockify time report — " + company + " — {{1.value}}",
            "bodyType": "rawHtml",
            "content": reminder_email_html(company),
        },
        filter_={
            "name": "Confirmed missing month after Sheets OK",
            "conditions": [[
                {"a": "{{" + str(read_id) + ".statusCode}}", "b": "200", "o": "number:equal"},
                {"a": "{{" + str(read_id) + ".body}}", "b": "", "o": "exist"},
                {"a": "{{" + str(missing_id) + ".value}}", "b": "1", "o": "number:equal"},
            ]],
        },
    )
    mail["metadata"]["parameters"] = google_conn("google-email:sendAnEmail")
    return [list_sheets, iterate, sheets, missing, mail]


def reminder_blueprint():
    hook = mod(
        REMINDER_WEBHOOK, "gateway:CustomWebHook", 0, 0, "Reminder trigger",
        version=1,
        parameters={"hook": REMINDER_HOOK_ID, "maxResults": 1},
    )
    hook["metadata"]["parameters"] = [
        {"name": "hook", "type": "hook:gateway-webhook", "label": "Webhook", "required": True},
        {"name": "maxResults", "type": "number", "label": "Maximum number of results"},
    ]
    hook["metadata"]["advanced"] = True
    hook["metadata"]["interface"] = [
        {
            "name": "__IMTHEADERS__",
            "spec": [
                {"name": "name", "type": "text", "label": "Name"},
                {"name": "value", "type": "text", "label": "Value"},
            ],
            "type": "array",
            "label": "Headers",
        }
    ]
    first = variable(1, 300, "Month year", month_year_from_now())
    look = drive_api(
        2, 600, 0, "Look in Clockify Reports",
        {
            "url": "/v3/files",
            "method": "GET",
            "headers": [{"key": "Content-Type", "value": "application/json"}],
            "qs": [
                {
                    "key": "q",
                    "value": (
                        "(mimeType = 'application/pdf' or name contains '.pdf') and '"
                        + CLOCKIFY_REPORTS_FOLDER
                        + "' in parents and trashed = false"
                    ),
                },
                {"key": "orderBy", "value": "modifiedTime desc"},
                {"key": "pageSize", "value": "50"},
                {"key": "fields", "value": "files(id,name,mimeType)"},
                {"key": "supportsAllDrives", "value": "true"},
                {"key": "includeItemsFromAllDrives", "value": "true"},
            ],
        },
    )
    each_pdf = mod(
        12, "builtin:BasicFeeder", 900, 0, "Each Drive PDF",
        version=1,
        mapper={"array": DRIVE_ITER_ARRAY},
    )
    download = mod(
        4, "google-drive:getAFile", 1200, 0, "Download from Clockify Reports",
        version=4,
        mapper={
            "file": DRIVE_ITEM_ID,
            "select": "map",
            "formatDrawings": "image/jpeg",
            "formatDocuments": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "formatSpreadsheets": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "formatPresentations": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        },
        filter_=filt("Drive file id present", DRIVE_ITEM_ID, "", "text:notequal"),
    )
    download["metadata"]["parameters"] = google_conn("google-drive:getAFile")
    send_pdf = http_request(
        5, 1500, 0, "Send the PDF to the processing scenario",
        WEBHOOK_URL,
        [
            {
                "name": "password",
                "value": FORM_PASSWORD,
                "multipartFieldType": "text",
            },
            {
                "name": "driveFileId",
                "value": DRIVE_ITEM_ID,
                "multipartFieldType": "text",
            },
            {
                "data": "{{4.data}}",
                "name": "report",
                "fileName": "Clockify_Report.pdf",
                "multipartFieldType": "file",
            },
        ],
    )
    skip_empty = variable(14, 1200, "Skip empty Drive slot", "1")
    skip_empty["filter"] = filt("Drive file id missing", DRIVE_ITEM_ID, "", "text:equal")
    pdf_router = mod(
        3, "builtin:BasicRouter", 900, 0, "Process Drive PDF?",
        routes=[
            {"flow": [skip_empty]},
            {"flow": [download, send_pdf]},
        ],
    )
    after_drive = mod(
        13, "builtin:BasicAggregator", 1800, 0, "After all Drive PDFs",
        version=1,
        parameters={"feeder": 12},
        mapper={},
    )
    sheets_flow = sheet_reminder_flow(11, 10, 6, 8, 7)
    first["filter"] = filt(
        "Reminder token matches", REMINDER_TOKEN_VALUE, REMINDER_AUTH_VALUE, "text:equal",
    )
    deny = respond(16, 300, 420, "Reject the token", 403, "Unauthorized")
    deny["filter"] = filt(
        "Reminder token does not match", REMINDER_TOKEN_VALUE, REMINDER_AUTH_VALUE, "text:notequal",
    )
    good = [first, look, each_pdf, pdf_router, after_drive] + sheets_flow
    token_router = mod(
        9, "builtin:BasicRouter", 300, 0, "Check token",
        routes=[{"flow": [deny]}, {"flow": good}],
    )
    flow = [hook, token_router]
    layout(flow)
    return {
        "name": "Clockify monthly report reminder",
        "flow": flow,
        "metadata": scenario_meta(True),
        "scheduling": scheduling(True, max_runs_per_minute=5),
    }



def walk(nodes, found):
    for node in nodes:
        if not isinstance(node["module"], str):
            raise SystemExit(f"module id {node['id']} has a bad module name")
        if node["id"] in found:
            raise SystemExit(f"duplicate module id {node['id']}")
        found.add(node["id"])
        for child in node.get("onerror") or []:
            walk([child], found)
        for route in node.get("routes") or []:
            walk(route["flow"], found)


def _modules(nodes):
    found = []
    for node in nodes:
        found.append(node)
        for child in node.get("onerror") or []:
            found.extend(_modules([child]))
        for route in node.get("routes") or []:
            found.extend(_modules(route["flow"]))
    return found


def js_named(pattern):
    return re.sub(r"\(\?<([A-Za-z0-9_]+)>", r"(?P<\1>", pattern)


def first_long_entry(text):
    match = re.search(js_named(LONG_ENTRY_PATTERN), text, re.IGNORECASE)
    return match.group("long") if match else ""


def last_hours(text):
    matches = list(re.finditer(js_named(HOURS_PATTERN), text, re.IGNORECASE))
    if not matches:
        raise AssertionError("no Total match")
    return matches[-1].group("hours")


def dates_of(text):
    match = re.search(js_named(DATE_PATTERN), text)
    if not match:
        raise AssertionError("no date range")
    return match.group("start"), match.group("end")


def company_of(text):
    match = re.search(js_named(COMPANY_PATTERN), text)
    if not match:
        raise AssertionError("no company line")
    return match.group("company").strip()


def money(hhmm):
    hours, minutes = (int(part) for part in hhmm.split(":"))
    billable = hours * 60 + minutes
    subtotal_agorot = billable * HOURLY_RATE * 100 / 60
    vat_agorot = math.floor(subtotal_agorot * VAT_PERCENT / 100 + 0.5)
    total_agorot = subtotal_agorot + vat_agorot
    return billable, subtotal_agorot / 100, vat_agorot / 100, total_agorot / 100


def english_long(ddmmyyyy):
    parsed = date(int(ddmmyyyy[6:10]), int(ddmmyyyy[3:5]), int(ddmmyyyy[0:2]))
    return f"{MONTHS[parsed.month - 1]} {parsed.day}, {parsed.year}", f"{MONTHS[parsed.month - 1]} {parsed.year}"


def is_last_day(day):
    return day.day == monthrange(day.year, day.month)[1]


def pdf_filename(month_year, company):
    slug = company.replace(" ", "_")
    return (
        REPORT_FILE_PREFIX + "_"
        + slug
        + "_"
        + month_year.replace(" ", "_")
        + ".pdf"
    )


def check(process, reminder, message):
    assert json.loads(json.dumps(process))["name"] == "Clockify monthly report"
    ids = set()
    walk(process["flow"], ids)
    walk(reminder["flow"], set())
    assert SUCCESS in json.dumps(process)
    assert "{{12.value}} drafts was created." in json.dumps(process)
    assert "Open Gmail drafts, review the attached PDF" in json.dumps(process)
    assert OVERTIME_NOTE in message
    assert OVERTIME_RATE in message
    assert "overtime component" not in message
    assert (
        "<p style='margin:0;'>" + OVERTIME_NOTE + "</p>"
        "<p style='margin:8px 0 0;'>" + OVERTIME_RATE + "</p>"
    ) in message
    assert f"{APPROVER_NAME}, please approve this time report." in message
    assert f"@{APPROVER_NAME.split()[0]}" not in message
    assert f"{HOURLY_RATE} ILS" in message
    assert TO.split(", ")[0] in json.dumps(process)
    assert FORM_PASSWORD in json.dumps(process)
    assert FORM_PASSWORD in json.dumps(reminder)
    assert REMINDER_TOKEN in json.dumps(reminder)
    assert REMINDER_TOKEN != FORM_PASSWORD
    assert process["metadata"]["instant"] is True
    assert process["scheduling"] == {"type": "immediately", "maximum_runs_per_minute": 5}
    assert process["flow"][0]["parameters"]["hook"] == PROCESS_HOOK_ID
    for scenario in (process, reminder):
        for node in _modules(scenario["flow"]):
            designer = node["metadata"]["designer"]
            assert designer["x"] % STEP_X == 0, node["id"]
            assert designer["y"] % STEP_Y == 0, node["id"]
        spots = [
            (n["metadata"]["designer"]["x"], n["metadata"]["designer"]["y"])
            for n in _modules(scenario["flow"])
        ]
        assert len(spots) == len(set(spots)), scenario["name"]

    samples = {
        "same line": (
            "Summary report\n01/09/2026 - 30/09/2026\n"
            "Sample Client - Project - Task\n"
            "Project Total\nInternal 10:00:00\nTotal 85:30:00\n"
        ),
        "next line": (
            "Detailed report\n01/09/2026 – 30/09/2026\n"
            "Sample Client - Project - Task\n"
            "Total\n85:30:00\n"
        ),
        "under eighty": "01/09/2026 - 30/09/2026\nSubtotal 40:00:00\nTotal: 79:45:00\n",
        "eighty exactly": "01/09/2026 — 30/09/2026\nTotal 80:00:00\n",
        "one minute over": "01/09/2026 - 30/09/2026\nTotal 80:01\n",
        "acme": "Acme Health - Platform Ops - Retainer\nTotal 10:00:00\n",
    }
    assert first_long_entry("01/10/2026 Task 08:30:00 Me\nTotal: 90:45:00\n") == ""
    assert first_long_entry("01/10/2026 Task 09:00:00 Me\nTotal: 90:45:00\n") == ""
    assert first_long_entry("01/10/2026 Task 09:01:00 Me\nTotal: 90:45:00\n") == "09:01:00"
    assert first_long_entry("01/10/2026 Task 12:00:00 Me\nTotal: 90:45:00\n") == "12:00:00"
    assert first_long_entry("Total\n85:30:00\n01/10/2026 Task 04:00:00\n") == ""
    assert first_long_entry("Subtotal 40:00:00\nTotal: 20:00:00\n") == ""
    assert first_long_entry("Project Total: 40:00:00\n01/10/2026 Task 12:00:00\n") == "12:00:00"
    assert 'name="confirmLong" value="yes"' in UPLOAD_HTML
    assert last_hours(samples["same line"]) == "85:30"
    assert last_hours(samples["next line"]) == "85:30"
    assert dates_of(samples["same line"]) == ("01/09/2026", "30/09/2026")
    assert dates_of(samples["next line"]) == ("01/09/2026", "30/09/2026")
    assert company_of(samples["same line"]) == "Sample Client"
    assert company_of(samples["next line"]) == "Sample Client"
    assert company_of(samples["acme"]) == "Acme Health"
    long_start, month_label = english_long("01/09/2026")
    long_end, _ = english_long("30/09/2026")
    assert long_start == "September 1, 2026"
    assert long_end == "September 30, 2026"
    assert month_label == "September 2026"

    assert HOURLY_RATE * 100 % 60 == 0
    minutes, subtotal, vat, total = money("85:30")
    expected_subtotal = minutes * HOURLY_RATE / 60
    assert (minutes, subtotal, vat, total) == (
        5130,
        expected_subtotal,
        expected_subtotal * VAT_PERCENT / 100,
        expected_subtotal * (100 + VAT_PERCENT) / 100,
    )
    assert money("79:45")[0] == 4785
    assert money("79:45")[0] < 4800
    assert money("80:00")[0] == 4800
    assert money("80:01")[0] == 4801
    one_minute = HOURLY_RATE / 60
    assert money("00:01")[1:] == (one_minute, one_minute * VAT_PERCENT / 100, one_minute * (100 + VAT_PERCENT) / 100)

    assert is_last_day(date(2026, 9, 30))
    assert not is_last_day(date(2026, 9, 29))
    assert is_last_day(date(2026, 2, 28))
    assert is_last_day(date(2024, 2, 29))
    assert is_last_day(date(2026, 1, 31))
    assert is_last_day(date(2026, 4, 30))
    assert is_last_day(date(2026, 12, 31))
    assert LAST_DAY.startswith("formatDate(addDays(addMonths(setDate(now; 1); 1); -1)")
    assert reminder["flow"][0]["module"] == "gateway:CustomWebHook"
    assert reminder["flow"][0]["id"] == REMINDER_WEBHOOK
    assert reminder["flow"][0]["parameters"]["hook"] == REMINDER_HOOK_ID
    assert reminder["flow"][0]["parameters"]["maxResults"] == 1
    assert reminder["metadata"]["instant"] is True
    assert reminder["scheduling"] == {"type": "immediately", "maximum_runs_per_minute": 5}
    assert reminder["flow"][1]["module"] == "builtin:BasicRouter"
    assert reminder["flow"][1]["id"] == 9
    assert reminder["flow"][1]["metadata"]["designer"]["name"] == "Check token"
    deny_token = reminder["flow"][1]["routes"][0]["flow"][0]
    assert deny_token["id"] == 16
    assert deny_token["module"] == "gateway:WebhookRespond"
    assert deny_token["mapper"]["status"] == 403
    assert deny_token["mapper"]["body"] == "Unauthorized"
    assert deny_token["filter"] == filt(
        "Reminder token does not match", REMINDER_TOKEN_VALUE, REMINDER_AUTH_VALUE, "text:notequal",
    )
    rem = reminder["flow"][1]["routes"][1]["flow"]
    assert rem[0]["module"] == "util:SetVariable2"
    assert rem[0]["id"] == 1
    assert rem[0]["filter"] == filt(
        "Reminder token matches", REMINDER_TOKEN_VALUE, REMINDER_AUTH_VALUE, "text:equal",
    )
    assert REMINDER_AUTH_VALUE.startswith("Bearer ")
    assert REMINDER_AUTH_VALUE.endswith(REMINDER_TOKEN)
    assert reminder["flow"][0]["metadata"].get("advanced") is True
    assert any(
        item.get("name") == "__IMTHEADERS__"
        for item in reminder["flow"][0]["metadata"].get("interface") or []
    )
    assert "google-calendar" not in json.dumps(reminder)
    assert "searchEvents" not in json.dumps(reminder)
    assert "ActionGetEvents" not in json.dumps(reminder)
    assert "make:makeApiCall" not in json.dumps(reminder)
    assert "{{9." not in json.dumps(reminder)
    assert rem[1]["module"] == "google-drive:makeApiCall"
    assert rem[1]["metadata"]["designer"]["name"] == "Look in Clockify Reports"
    assert CLOCKIFY_REPORTS_FOLDER in rem[1]["mapper"]["qs"][0]["value"]
    assert rem[2]["module"] == "builtin:BasicFeeder"
    assert rem[2]["id"] == 12
    assert rem[2]["mapper"]["array"] == DRIVE_ITER_ARRAY
    assert rem[3]["module"] == "builtin:BasicRouter"
    assert rem[3]["metadata"]["designer"]["name"] == "Process Drive PDF?"
    pickup = rem[3]["routes"][1]["flow"]
    assert pickup[0]["module"] == "google-drive:getAFile"
    assert pickup[0]["mapper"]["file"] == DRIVE_ITEM_ID
    assert pickup[0]["filter"]["name"] == "Drive file id present"
    assert pickup[1]["module"] == "http:MakeRequest"
    assert pickup[1]["mapper"]["url"] == WEBHOOK_URL
    assert any(
        f.get("name") == "driveFileId" and f.get("value") == DRIVE_ITEM_ID
        for f in pickup[1]["mapper"]["multipartBodyContent"]
    )
    assert "get(get(" not in json.dumps(pickup)
    skip = rem[3]["routes"][0]["flow"]
    assert skip[0]["id"] == 14
    assert skip[0]["filter"]["name"] == "Drive file id missing"
    assert rem[4]["module"] == "builtin:BasicAggregator"
    assert rem[4]["parameters"]["feeder"] == 12
    assert rem[4]["metadata"]["designer"]["name"] == "After all Drive PDFs"
    assert rem[5]["module"] == "google-sheets:makeAPICall"
    assert rem[5]["mapper"]["url"] == LIST_SHEETS_URL
    assert "filter" not in rem[5]
    assert "Combined missing-report check" not in json.dumps(reminder)
    assert rem[6]["mapper"]["array"] == "{{11.body.sheets}}"
    assert rem[7]["mapper"]["url"] == REMINDER_SHEET_URL
    assert rem[8]["mapper"]["value"] == month_missing_formula(6)
    assert rem[9]["module"] == "google-email:sendAnEmail"
    assert rem[9]["id"] == 7

    long_router_node = process["flow"][1]["routes"][1]["flow"][-1]
    assert long_router_node["id"] == LONG_ROUTER
    assert long_router_node["routes"][0]["flow"][0]["filter"]["name"] == "No long entry or already confirmed"
    assert long_router_node["routes"][1]["flow"][0]["filter"]["name"] == "Form upload needs confirmation"
    assert long_router_node["routes"][2]["flow"][0]["module"] == "google-email:sendAnEmail"
    branch_node = long_router_node["routes"][0]["flow"][-1]
    append = branch_node["routes"][1]["flow"][0]
    assert append["module"] == "google-sheets:addRow"
    values = append["mapper"]["values"]
    assert list(values) == ["0", "1", "2", "3", "4", "5", "6", "7", "8"]
    assert values["4"] == str(HOURLY_RATE) and values["5"] == APPROVER_NAME and values["8"] == str(VAT_PERCENT)
    assert values["6"] == TO and values["7"] == CC
    assert append["mapper"]["mode"] == "map"
    assert append["mapper"]["sheetId"] == "{{30.company}}"
    assert append["mapper"]["tableFirstRow"] == "A1:Z1"
    assert append["mapper"]["valueInputOption"] == "RAW"
    assert "from" not in append["mapper"]
    blob = json.dumps(process)
    reminder_blob = json.dumps(reminder)
    assert "Look for this month in Processed" not in blob
    assert '"name": "Logged months text"' in blob
    assert '"name": "Already logged"' in blob
    assert "contains(28.value; 12.value)" in blob
    assert "{{29.value}}" in blob
    assert "18.body.values" in blob
    assert "ifempty(18.values;" not in blob
    assert "{{8.value}}" in reminder_blob
    assert "6.body.values" in reminder_blob
    assert "6.statusCode = 200" in reminder_blob
    assert "lower(trim(1.value))" in reminder_blob
    assert "ifempty(6.values;" not in reminder_blob
    assert REMINDER_SHEET_URL in reminder_blob
    assert "21.body.sheets" not in reminder_blob
    assert rem[2]["mapper"]["array"] == DRIVE_ITER_ARRAY
    assert "emptystring" in reminder_blob
    assert "parseJSON" not in reminder_blob
    assert REPORT_FILE_PREFIX + '_{{replace(30.company; \\" \\"; \\"_\\")}}_' in blob
    assert "Clockify-Report.pdf" not in blob
    assert 'replace(12.value; \\" \\"; \\"_\\")' in blob
    assert "pdf.co" not in blob.lower()
    assert "ActionSendData" not in blob and "ActionSendData" not in reminder_blob
    assert "http:MakeRequest" in reminder_blob
    assert WEBHOOK_URL in reminder_blob
    assert blob.count("{{5.data}}") == 4
    assert "values/'{{30.company}}'!A2:A" in blob
    assert "values/'{{10.properties.title}}'!A2:A" in reminder_blob
    assert LIST_SHEETS_URL in reminder_blob
    assert "builtin:BasicFeeder" in reminder_blob
    assert "{{11.body.sheets}}" in reminder_blob
    move_bodies = [
        node["mapper"]["body"]
        for node in _modules(process["flow"])
        if isinstance(node.get("mapper"), dict) and node["mapper"].get("method") == "PATCH"
    ]
    assert move_bodies == ['{"name": "{{34.value}}"}', '{"name": "{{34.value}}"}']
    filenames = [
        item.get("filename")
        for node in _modules(process["flow"])
        if isinstance(node.get("mapper"), dict)
        for item in (node["mapper"].get("attachments") or [])
    ]
    assert filenames == ["{{34.value}}"]
    assert CLOCKIFY_REPORTS_FOLDER in blob and PROCESSED_FOLDER in blob
    assert "addParents" in blob and "removeParents" in blob
    assert WEBHOOK_URL not in UPLOAD_HTML
    assert 'action="/api/upload"' in UPLOAD_HTML
    assert 'id="result"' in UPLOAD_HTML
    assert "fetch(\"/api/upload\"" in UPLOAD_HTML
    assert WEBHOOK_URL in UPLOAD_FUNCTION_JS
    assert "onRequestPost" in UPLOAD_FUNCTION_JS
    assert "ActionSendEmail" not in reminder_blob and "ActionCreateDraft" not in blob
    assert 'name="driveFileId"' in UPLOAD_HTML
    assert 'name="password" type="password"' in UPLOAD_HTML
    assert 'id="password"' in UPLOAD_HTML
    assert FORM_PASSWORD not in UPLOAD_HTML
    assert FORM_PASSWORD not in UPLOAD_HTML
    assert REMINDER_TOKEN not in UPLOAD_HTML
    assert 'name="token"' not in UPLOAD_HTML
    every = list(_modules(process["flow"])) + list(_modules(reminder["flow"]))
    for node in every:
        mapper = node.get("mapper") if isinstance(node.get("mapper"), dict) else {}
        if node["module"].endswith("makeAPICall") or node["module"].endswith("makeApiCall"):
            assert mapper["method"] in ("GET", "POST", "PATCH", "DELETE"), node["id"]
        if node["module"] == "util:SetVariable2":
            assert mapper["name"] == "value", node["id"]
    draft = next(n for n in every if n["module"] == "google-email:createADraft")
    assert draft["version"] == 4
    assert draft["metadata"]["parameters"][0]["type"] == "account:google-email"
    assert draft["mapper"]["to"] == TO.split(", ")
    assert draft["mapper"]["cc"] == CC.split(", ")
    assert draft["mapper"]["bodyType"] == "rawHtml"
    assert draft["mapper"]["content"] == message
    assert draft["mapper"]["attachments"] == [{"filename": "{{34.value}}", "data": "{{1.report.data}}"}]
    mails = [n for n in _modules(reminder["flow"]) if n["module"] == "google-email:sendAnEmail"]
    assert len(mails) == 1
    sent = mails[0]
    held = next(n for n in _modules(process["flow"]) if n["id"] == LONG_MAIL)
    assert held["mapper"]["to"] == [YOUR_EMAIL]
    assert "{{52.value}}" in held["mapper"]["content"]
    assert sent["id"] == 7
    assert sent["version"] == 4
    assert sent["metadata"]["parameters"][0]["type"] == "account:google-email"
    assert sent["mapper"]["to"] == [YOUR_EMAIL]
    assert sent["mapper"]["bodyType"] == "rawHtml"
    assert UPLOAD_FORM_URL in sent["mapper"]["content"]
    assert "{{1.value}}" in sent["mapper"]["subject"]
    assert "{{10.properties.title}}" in sent["mapper"]["subject"]
    assert "no hours report for {{10.properties.title}}" in sent["mapper"]["content"]
    assert "Clockify Reports" not in sent["mapper"]["content"]
    assert "Google Drive" not in sent["mapper"]["content"]
    assert "Two easy ways" not in sent["mapper"]["content"]
    assert sent["filter"]["name"] == "Confirmed missing month after Sheets OK"
    conds = sent["filter"]["conditions"][0]
    assert len(conds) == 3
    assert {"a": "{{6.statusCode}}", "b": "200", "o": "number:equal"} in conds
    assert {"a": "{{6.body}}", "b": "", "o": "exist"} in conds
    assert {"a": "{{8.value}}", "b": "1", "o": "number:equal"} in conds
    assert rem[1]["metadata"]["designer"]["name"] == "Look in Clockify Reports"
    assert "{{15.token}}" not in reminder_blob
    assert '15.`__IMTHEADERS__`' in reminder_blob
    assert (
        '"name"; "authorization"' in reminder_blob
        or '\\"name\\"; \\"authorization\\"' in reminder_blob
    )
    assert REMINDER_AUTH_VALUE in reminder_blob
    assert "Check token" in reminder_blob
    assert "Reject the token" in reminder_blob
    ics = (ROOT / "clockify-monthly-reminder.ics").read_text(encoding="utf-8")
    assert "SUMMARY:Clockify monthly report" in ics
    assert "UID:clockify-monthly-reminder@clockify-monthly-report" in ics
    assert "SUMMARY:Clockify inbox pickup" not in ics
    assert "20261031T193000" in ics
    assert "20261031T190000" not in ics
    add = next(n for n in every if n["id"] == ADD_ROW)
    assert add["module"] == "google-sheets:addRow"
    assert add["mapper"]["mode"] == "map"
    assert add["mapper"]["spreadsheetId"] == f"/{SPREADSHEET_ID}"
    assert add["mapper"]["sheetId"] == "{{30.company}}"
    assert add["mapper"]["tableFirstRow"] == "A1:Z1"
    assert add["metadata"]["restore"]["expect"]["mode"]["label"] == "Enter manually"
    uploads = [n for n in every if n["module"] == "google-drive:uploadAFile"]
    extract, archive = uploads
    assert extract["mapper"]["convert"] is True
    assert extract["mapper"]["targetType"] == "application/vnd.google-apps.document"
    assert extract["mapper"]["data"] == "{{1.report.data}}"
    assert archive["mapper"]["convert"] is False
    assert archive["mapper"]["folderId"] == PROCESSED_FOLDER
    assert archive["mapper"]["filename"] == "{{34.value}}"
    text = next(n for n in every if n["id"] == CONVERT and n["module"] == "google-drive:getAFile")
    assert text["mapper"]["file"] == "{{4.id}}"
    assert text["mapper"]["formatDocuments"] == "text/plain"
    deleted = next(n for n in every if n["id"] == 35)
    assert deleted["mapper"]["method"] == "DELETE"
    assert any(n["id"] == 5 and n["module"] == "http:MakeRequest" for n in _modules(reminder["flow"]))
    assert pdf_filename("September 2026", DEFAULT_SHEET_TAB) == (
        f"{REPORT_FILE_PREFIX}_{DEFAULT_SHEET_TAB.replace(' ', '_')}_September_2026.pdf"
    )
    assert pdf_filename("September 2026", "Acme Health") == (
        f"{REPORT_FILE_PREFIX}_Acme_Health_September_2026.pdf"
    )


def setup_md():
    return f"""# Clockify monthly report

You open `upload.html` in any browser.

The form posts to same-origin `/api/upload` (a Cloudflare Pages Function that forwards to Make).

Success and error HTML stay under the form — the browser never navigates to the webhook URL, and the webhook URL is not in the page HTML.

Make, running under the Gmail account you connect once on a desktop, has Google Drive turn the PDF into text, appends a row, creates a draft, and saves the file.

A second scenario starts from a Custom Webhook.

Call that webhook with header `Authorization: Bearer <reminder-token>` (already filled in the Check token filters; different from the upload form password).

Body may be JSON such as `{{\"trigger\":\"end_of_month\"}}`.

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

   Rename or add tabs to match; the processing scenario uses `{{{{30.company}}}}` for the tab.

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

   If that module did not import, add Google Sheets → Make an API call, method GET, URL `spreadsheets/<SPREADSHEET_ID>/values/'{{{{30.company}}}}'!A2:A` (quotes around the tab name).

6. Open Append the month, connect the same Google account.

   Search Method is **Enter manually** (`mode: map`).

   Replace `<SPREADSHEET_ID>` with your spreadsheet id, and set Sheet Name to `{{{{30.company}}}}`.

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
{DATE_PATTERN}
```

Total duration.

The match is the line that starts with Total, so a “Project Total” row is ignored.

Group `hours` is `HH:MM`; a trailing `:SS` is not part of the group.

```
{HOURS_PATTERN}
```

Company (client) name.

First `Client - Project - Task` line; group `company` is the text before the first ` - `.

Spaces become `_` in the PDF filename.

```
{COMPANY_PATTERN}
```

All three parsers read the plain text from PDF text, module 5, field `data`.

After a test run, if that field is a file pill and the parser text is empty, map Data from PDF text into the parsers.

## Amounts

Minutes are `hours * 60 + minutes`.

Decimal hours are those minutes divided by 60 (`85:30` → `85.5`).

The subtotal is billable minutes times `<HOURLY_RATE_ILS>`, divided by 60.

VAT is the subtotal in agorot times `<VAT_PERCENT>`, divided by 100, rounded half up, then added back.

The note is included only when minutes are greater than 4800:

> {OVERTIME_NOTE}

> {OVERTIME_RATE}

## What the browser sees

`confirmation.html` is the webhook body after a new month is logged.

The live page substitutes the month where it says `{{{{12.value}}}}`.

The other replies are `already-processed.html`, `unreadable.html`, and `unauthorized.html`.

The draft is not sent.

You review it in Gmail and send it yourself.
"""


def numbered(prefix, addresses):
    return [(address, f"<{prefix}_{index}>") for index, address in enumerate(addresses, start=1)]


SHARED_REDACTIONS = [
    (WEBHOOK_URL, "<PROCESS_WEBHOOK_URL>"),
    (FORM_PASSWORD, "<FORM_PASSWORD>"),
    (REMINDER_TOKEN, "<REMINDER_TOKEN>"),
    (SPREADSHEET_ID, "<SPREADSHEET_ID>"),
    (CLOCKIFY_REPORTS_FOLDER, "<CLOCKIFY_REPORTS_FOLDER_ID>"),
    (PROCESSED_FOLDER, "<PROCESSED_FOLDER_ID>"),
    (f'"hook": {PROCESS_HOOK_ID}', '"hook": "<PROCESS_HOOK_ID>"'),
    (f'"hook": {REMINDER_HOOK_ID}', '"hook": "<REMINDER_HOOK_ID>"'),
    (f'"4": "{HOURLY_RATE}"', '"4": "<HOURLY_RATE_ILS>"'),
    (f'"8": "{VAT_PERCENT}"', '"8": "<VAT_PERCENT>"'),
    (f"* {HOURLY_RATE} / 60", "* <HOURLY_RATE_ILS> / 60"),
    (f"* {HOURLY_RATE} * 100 / 60", "* <HOURLY_RATE_ILS> * 100 / 60"),
    (f"* {VAT_PERCENT} / 100", "* <VAT_PERCENT> / 100"),
    (f"{HOURLY_RATE} ILS", "<HOURLY_RATE_ILS> ILS"),
    (f"VAT {VAT_PERCENT}%", "VAT <VAT_PERCENT>%"),
    (OVERTIME_RATE, "<OVERTIME_RATE_NOTE>"),
    (APPROVER_NAME, "<APPROVER_NAME>"),
    (f"Hello {YOUR_FIRST_NAME},", "Hello <YOUR_FIRST_NAME>,"),
    (YOUR_NAME, "<YOUR_NAME>"),
    (f"{REPORT_FILE_PREFIX}_", "<YOUR_NAME>_Time_Report_"),
    (DEFAULT_SHEET_TAB.replace(" ", "_"), "<CLIENT_NAME>"),
    (DEFAULT_SHEET_TAB, "<CLIENT_NAME>"),
    (UPLOAD_FORM_URL, "<UPLOAD_FORM_URL>"),
    (YOUR_EMAIL, "<YOUR_EMAIL>"),
    *numbered("TO_EMAIL", TO.split(", ")),
    *numbered("CC_EMAIL", CC.split(", ")),
]


def redact(text):
    for real, placeholder in SHARED_REDACTIONS:
        text = text.replace(real, placeholder)
    return text


def assert_redacted(text):
    for real, _ in SHARED_REDACTIONS:
        assert real not in text, real


HTML_MARKERS = [
    (f"{HOURLY_RATE} ILS", "[HOURLY_RATE] ILS"),
    (f"VAT {VAT_PERCENT}%", "VAT [VAT_PERCENT]%"),
    (OVERTIME_RATE, "[OVERTIME_RATE_NOTE]"),
    (APPROVER_NAME, "[APPROVER_NAME]"),
    (f"Hello {YOUR_FIRST_NAME},", "Hello [YOUR_FIRST_NAME],"),
    (UPLOAD_FORM_URL, "[UPLOAD_FORM_URL]"),
]


def redact_html(text):
    for real, marker in HTML_MARKERS:
        text = text.replace(real, marker)
    return text


def main():
    message = email_html()
    # The f-string doubled the month braces.
    # Collapse them back to Make syntax.
    message = message.replace("{{{{12.value}}}}", "{{12.value}}")
    process = process_blueprint(message)
    reminder = reminder_blueprint()
    check(process, reminder, message)

    reminder_mail = next(
        n for n in _modules(reminder["flow"]) if n["module"] == "google-email:sendAnEmail"
    )
    shared = {
        ROOT / "blueprints" / "process-report.blueprint.json":
            json.dumps(process, indent=2, ensure_ascii=False) + "\n",
        ROOT / "blueprints" / "monthly-reminder.blueprint.json":
            json.dumps(reminder, indent=2, ensure_ascii=False) + "\n",
        ROOT / "SETUP.md": setup_md().replace("{{{{12.value}}}}", "{{12.value}}"),
    }
    html_shared = {
        ROOT / "email-draft.html": message,
        ROOT / "email.html": reminder_mail["mapper"]["content"] + "\n",
    }

    (ROOT / "blueprints").mkdir(exist_ok=True)
    (ROOT / "upload.html").write_text(UPLOAD_HTML, encoding="utf-8")
    pages = ROOT / "pages"
    pages.mkdir(exist_ok=True)
    (pages / "index.html").write_text(UPLOAD_HTML, encoding="utf-8")
    functions_api = ROOT / "functions" / "api"
    functions_api.mkdir(parents=True, exist_ok=True)
    (functions_api / "upload.js").write_text(UPLOAD_FUNCTION_JS, encoding="utf-8")
    assert (ROOT / "functions" / "api" / "upload.js").read_text(encoding="utf-8") == UPLOAD_FUNCTION_JS
    (ROOT / "confirmation.html").write_text(SUCCESS_HTML, encoding="utf-8")
    (ROOT / "already-processed.html").write_text(ALREADY_HTML, encoding="utf-8")
    (ROOT / "unreadable.html").write_text(FAILURE_HTML, encoding="utf-8")
    (ROOT / "unauthorized.html").write_text(DENY_HTML, encoding="utf-8")

    for path, text in shared.items():
        redacted = redact(text)
        assert_redacted(redacted)
        path.write_text(redacted, encoding="utf-8")
    for path, text in html_shared.items():
        marked = redact_html(text)
        assert_redacted(marked)
        path.write_text(marked, encoding="utf-8")

    saved = json.loads((ROOT / "blueprints" / "process-report.blueprint.json").read_text(encoding="utf-8"))
    assert saved["flow"][1]["routes"][1]["flow"][3]["parameters"]["pattern"] == DATE_PATTERN
    assert saved["flow"][1]["routes"][1]["flow"][4]["parameters"]["pattern"] == HOURS_PATTERN
    assert saved["flow"][1]["routes"][1]["flow"][5]["parameters"]["pattern"] == COMPANY_PATTERN
    assert saved["flow"][1]["routes"][1]["flow"][6]["mapper"]["value"] == "{{7.hours}}"
    assert "BasicAggregator" not in json.dumps(saved)
    assert (ROOT / "email-draft.html").read_text(encoding="utf-8") == redact_html(message)
    assert (ROOT / "email.html").read_text(encoding="utf-8") == redact_html(reminder_mail["mapper"]["content"] + "\n")
    print("ALL_PASS")


if __name__ == "__main__":
    main()
