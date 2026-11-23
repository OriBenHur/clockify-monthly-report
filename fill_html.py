import re

from _generate import ENV, ROOT

HTML_FILES = ["email-draft.html", "email.html"]
OUT = ROOT / "filled"
MARKER = re.compile(r"\[[A-Z][A-Z_0-9]*\]")


def fill(text):
    for key, value in ENV.items():
        text = text.replace(f"[{key}]", value)
    leftover = MARKER.findall(text)
    if leftover:
        raise SystemExit(f"markers not filled: {sorted(set(leftover))}")
    return text


def main():
    OUT.mkdir(exist_ok=True)
    for name in HTML_FILES:
        filled = fill((ROOT / name).read_text(encoding="utf-8"))
        (OUT / name).write_text(filled, encoding="utf-8")
        print("filled", OUT / name)


if __name__ == "__main__":
    main()
