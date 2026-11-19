# Builds the public GitHub Pages copy of the XFFL Record Book Bible into docs/.
# Uses the same page code as the Claude version (page/index.html) and the data
# files refresh.py writes to out/. Managers are shown by short names (NAMES below).
# Run after refresh.py:  python build_public.py
import json, os, re, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(HERE, "docs")

# Public display names. Anyone not listed is shown by first name.
NAMES = {
    "Thomas Moeller": "Moeller",
    "Thomas Dalimonte": "T-Dal",
    "Alex Bensley": "Benz",
    "Adam Weber": "Weber",
    "Brendan Mokler": "Mokler",
}


def short(full):
    return NAMES.get(full, full.split(" ")[0])


def main():
    out = os.path.join(HERE, "out")
    seasons = json.load(open(os.path.join(out, "seasons.json")))["rows"]
    games = json.load(open(os.path.join(out, "games.json")))["rows"]
    full_names = sorted({r["manager"] for r in seasons} | {g["home"] for g in games} | {g["away"] for g in games}, key=len, reverse=True)
    mapping = {n: short(n) for n in full_names}
    dupes = {v for v in mapping.values() if list(mapping.values()).count(v) > 1}
    if dupes:
        raise SystemExit(f"Two managers would share the public name {sorted(dupes)}; add them to NAMES in build_public.py.")

    os.makedirs(os.path.join(DOCS, "data"), exist_ok=True)
    for n in ("games", "seasons", "champions"):
        text = json.dumps(json.load(open(os.path.join(out, n + ".json")))["rows"], separators=(",", ":"))
        for full, s in mapping.items():
            text = text.replace(json.dumps(full)[1:-1], s)
        leftover = [f for f in full_names if f in text]
        if leftover:
            raise SystemExit(f"Full names still present in {n}.json: {leftover}")
        open(os.path.join(DOCS, "data", n + ".json"), "w", encoding="utf-8").write(text)

    page = open(os.path.join(HERE, "page", "index.html"), encoding="utf-8").read()
    page = re.sub(r'<meta name="dash-one-writer">\s*', "", page)
    # In the Claude dashboard each <script> runs in its own scope; give them one here too.
    page = re.sub(r"<script>(.*?)</script>", lambda m: "<script>(() => {" + m.group(1) + "})();</script>", page, flags=re.S)
    summary = json.load(open(os.path.join(out, "summary.json")))
    tpl = open(os.path.join(HERE, "public", "template.html"), encoding="utf-8").read()
    html = tpl.replace("{{PAGE}}", page).replace("{{UPDATED}}", summary["pulled"])
    open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8", newline="\n").write(html)
    shutil.copy(os.path.join(HERE, "public", "dash-lite.js"), os.path.join(DOCS, "dash-lite.js"))
    open(os.path.join(DOCS, ".nojekyll"), "w").close()
    print(json.dumps({"built": "docs/index.html", "updated": summary["pulled"], "names": mapping}))


if __name__ == "__main__":
    main()
