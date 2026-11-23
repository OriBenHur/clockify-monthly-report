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
OVERTIME_HOURS = ENV["OVERTIME_THRESHOLD_HOURS"]
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
        f'            <p style="margin:{"0 0 0.75rem" if i < len(details) - 1 else "0"};'
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


def overtime_block(hours):
    if not hours:
        return ""
    hours = int(hours)
    return (
        '{{if(' + MINUTES_EXPR + f' > {hours} * 60; "'
        "<div style='margin:20px 0 0;padding:12px 14px;background:#fff8e6;border-left:3px solid #b45309;'>"
        f"<p style='margin:0;'>This month's total exceeds {hours} hours.</p>"
        "<p style='margin:8px 0 0;'>" + OVERTIME_RATE + "</p>"
        "</div>\"; \"\")}}"
    )


def overtime_redactions():
    if not OVERTIME_HOURS or not OVERTIME_RATE:
        return []
    hours = int(OVERTIME_HOURS)
    return [
        (f"> {hours} * 60; ", "> <OVERTIME_THRESHOLD_HOURS> * 60; "),
        (f"exceeds {hours} hours.", "exceeds <OVERTIME_THRESHOLD_HOURS> hours."),
        (OVERTIME_RATE, "<OVERTIME_RATE_NOTE>"),
    ]


def overtime_markers():
    if not OVERTIME_HOURS or not OVERTIME_RATE:
        return []
    hours = int(OVERTIME_HOURS)
    return [
        (f"> {hours} * 60; ", "> [OVERTIME_THRESHOLD_HOURS] * 60; "),
        (f"exceeds {hours} hours.", "exceeds [OVERTIME_THRESHOLD_HOURS] hours."),
        (OVERTIME_RATE, "[OVERTIME_RATE_NOTE]"),
    ]


def email_html():
    overtime = overtime_block(OVERTIME_HOURS)
    row = (
        "                                <tr>\n"
        "                                    <td style='padding:10px 0;border-bottom:1px solid #e4e7eb;color:#52606d;'>{label}</td>\n"
        "                                    <td style='padding:10px 0;border-bottom:1px solid #e4e7eb;text-align:right;font-weight:600;'>{value}</td>\n"
        "                                </tr>"
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
        <tr>
            <td align="center">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:12px;padding:28px 24px;font-family:Segoe UI,Helvetica,Arial,sans-serif;color:#1f2933;font-size:15px;line-height:1.5;">
                    <tr>
                        <td>
                            <p style="margin:0 0 8px;font-size:13px;letter-spacing:0.04em;text-transform:uppercase;color:#52606d;">DevOps consulting</p>
                            <h1 style="margin:0 0 20px;font-size:22px;line-height:1.3;">Time report — {{{{12.value}}}}</h1>
                            <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
{rows}
                            </table>
                            {overtime}
                            <p style="margin:20px 0 0;">{APPROVER_NAME}, please approve this time report.</p>
                            <p style="margin:16px 0 0;color:#52606d;font-size:13px;">The Clockify PDF is attached.</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
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
        <form id="upload" method="post" enctype="multipart/form-data" action="/api/upload"
            style="background:#ffffff;border-radius:16px;padding:1.5rem 1.25rem;">
            <h1 style="font-size:1.35rem;line-height:1.3;margin:0 0 0.5rem;">Clockify time report</h1>
            <p style="margin:0 0 1.25rem;color:#52606d;font-size:1rem;line-height:1.5;">Upload the monthly summary PDF and enter the password.</p>
            <p style="margin:0 0 1.25rem;color:#52606d;font-size:1rem;line-height:1.5;">This page does not ask you to sign in to Google.</p>
            <label for="report" style="display:block;font-weight:600;margin:0 0 0.5rem;">PDF file</label>
            <input id="report" name="report" type="file" accept="application/pdf,.pdf" required
                style="display:block;width:100%;font-size:16px;margin:0 0 1rem;">
            <label for="password" style="display:block;font-weight:600;margin:0 0 0.5rem;">Password</label>
            <input id="password" name="password" type="password" autocomplete="current-password" required
                style="display:block;width:100%;box-sizing:border-box;font-size:16px;min-height:48px;margin:0 0 1rem;padding:0.75rem;border:1px solid #cbd2d9;border-radius:8px;">
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
    return f"""<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='background:#f4f6f8;padding:24px 12px;'>
    <tr>
        <td align='center'>
            <table role='presentation' width='100%' cellpadding='0' cellspacing='0'
                style='max-width:560px;background:#ffffff;border-radius:12px;padding:28px 24px;font-family:Segoe UI,Helvetica,Arial,sans-serif;color:#1f2933;font-size:15px;line-height:1.5;'>
                <tr>
                    <td>
                        <p
                            style='margin:0 0 8px;font-size:13px;letter-spacing:0.04em;text-transform:uppercase;color:#52606d;'>
                            {company}</p>
                        <h1 style='margin:0 0 12px;font-size:22px;line-height:1.3;'>Upload needed — {{{{1.value}}}}</h1>
                        <p style='margin:0 0 20px;color:#52606d;'>Hello {YOUR_FIRST_NAME}, it is the evening of the last
                            day of the month, and no hours report for {company} was logged yet.</p>
                        <p style='margin:0 0 20px;color:#52606d;'>Upload the Clockify PDF with the form below.</p>
                        <p style='margin:0 0 20px;color:#52606d;'>The Gmail draft is created automatically.</p>
                        <p style='margin:0 0 20px;'><a href='{UPLOAD_FORM_URL}'
                                style='display:inline-block;background:#0f6f4e;color:#ffffff;text-decoration:none;font-weight:600;font-size:16px;padding:14px 22px;border-radius:10px;'>Upload
                                the report</a></p>
                    </td>
                </tr>
            </table>
        </td>
    </tr>
</table>"""


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
    assert overtime_block(OVERTIME_HOURS) in message
    assert overtime_block("") == ""
    assert "overtime component" not in message
    if OVERTIME_HOURS:
        assert f"> {int(OVERTIME_HOURS)} * 60; " in message
        assert f"exceeds {int(OVERTIME_HOURS)} hours." in message
    else:
        assert "* 60; " not in message
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
    if OVERTIME_HOURS:
        threshold = int(OVERTIME_HOURS) * 60
        assert money(f"{int(OVERTIME_HOURS) - 1}:45")[0] < threshold
        assert money(f"{int(OVERTIME_HOURS)}:00")[0] == threshold
        assert money(f"{int(OVERTIME_HOURS)}:01")[0] == threshold + 1
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
   | `TO_RECIPIENTS` | You choose. Comma-separated addresses that receive the Gmail draft. |
   | `CC_RECIPIENTS` | You choose. Comma-separated addresses to copy on the draft. |
   | `APPROVER_NAME` | You choose. The name the draft asks to approve the report. |
   | `YOUR_NAME` | Your full name. It appears in the PDF filename. |
   | `YOUR_FIRST_NAME` | Your first name. It appears in the reminder greeting. |
   | `YOUR_EMAIL` | Your own address. It receives the reminder. |
   | `CLIENT_NAME` | The client name exactly as Clockify shows it. It appears in the PDF filename. |
   | `UPLOAD_FORM_URL` | The address Cloudflare prints after the deploy in Step 6. |
   | `PROCESS_WEBHOOK_URL` | The URL Make shows for the custom webhook you create in Step 5. |
   | `FORM_PASSWORD` | You choose. Use a long, unique password. |
   | `REMINDER_TOKEN` | You choose. Use a long random string, for example from `openssl rand -hex 24`. |
   | `SPREADSHEET_ID` | The part of the Google Sheet URL between `/d/` and `/edit`. |
   | `CLOCKIFY_REPORTS_FOLDER_ID` | The part of the Drive folder URL after `/folders/` for the `Clockify Reports` folder. |
   | `PROCESSED_FOLDER_ID` | The same, for the `Processed` folder inside it. |
   | `PROCESS_HOOK_ID` | Not looked up. Any whole number that differs from `REMINDER_HOOK_ID`. |
   | `REMINDER_HOOK_ID` | Not looked up. Any whole number that differs from `PROCESS_HOOK_ID`. |
   | `HOURLY_RATE` | Your hourly rate in ILS as a whole number, for example `330`. |
   | `VAT_PERCENT` | The VAT percentage you charge, for example `18`. |
   | `OVERTIME_THRESHOLD_HOURS` | The hours a month can reach before the draft shows the overtime box. Leave it empty to turn the box off. |
   | `OVERTIME_RATE_NOTE` | The text shown in the overtime box, under the threshold line. |

   When you import a blueprint in Make, you pick the webhook yourself, so the hook IDs are never typed into Make.

   The generator uses the hook IDs only to build the blueprint, then replaces them with placeholders in the shared files.

   `HOURLY_RATE` must be a multiple of 3, because the Make formulas need a whole number of agorot per minute.

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
3. Set up the OAuth consent screen. If the app stays in testing, add your Google account under Test users.
4. Open Credentials, click Create credentials, and choose OAuth client ID.
5. Choose Web application as the application type.
6. Copy the redirect URI that Make shows in its Google connection dialog, and add it under Authorized redirect URIs.
7. Click Create, then copy the client ID and client secret into the Make connection.

Keep the client secret only in Make, never in `clockify.env` or the repo.

### Import the scenario

1. In Make, create a scenario and set its timezone to the one you report in. The examples use `Asia/Jerusalem`.
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
3. In the left menu, click the gear icon. This opens Project Settings.
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
curl -X POST "REMINDER_WEBHOOK_URL" -H "Authorization: Bearer wrong-token" -H "Content-Type: application/json" -d '{{\"trigger\":\"end_of_month\"}}'
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
    *overtime_redactions(),
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
    *overtime_markers(),
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
