"""Convert all .md files in docs/ to standalone styled .html files.

Usage:  python docs/build.py
Output: <name>.html next to each <name>.md — double-click to open in browser.
Re-run after editing any .md file.
"""

import re
from pathlib import Path

import markdown

DOCS_DIR = Path(__file__).parent

TEMPLATE = """<!DOCTYPE html>
<html lang="bn">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — ByabshaGhor Docs</title>
<link href="https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@400;600;700&family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="glossary.css">
<script src="glossary.js" defer></script>
<style>
  :root {{
    --bg:#0f172a; --card:#1e293b; --accent:#22c55e; --accent2:#38bdf8;
    --text:#f1f5f9; --muted:#94a3b8; --line:rgba(148,163,184,.15);
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:'Hind Siliguri','Inter',sans-serif; background:#0b1120; color:var(--text); }}
  .bar {{
    position:sticky; top:0; z-index:10; background:rgba(15,23,42,.95); backdrop-filter:blur(8px);
    border-bottom:1px solid var(--line); padding:12px 24px;
    display:flex; align-items:center; gap:14px; flex-wrap:wrap;
  }}
  .brand {{ font-weight:700; color:var(--accent); font-size:16px; }}
  .bar a {{ color:var(--accent2); font-size:13.5px; text-decoration:none; }}
  .bar a:hover {{ text-decoration:underline; }}
  .bar button {{
    margin-left:auto; background:rgba(34,197,94,.12); color:var(--accent);
    border:1px solid rgba(34,197,94,.4); border-radius:10px;
    padding:7px 14px; font-family:inherit; font-size:13.5px; font-weight:600; cursor:pointer;
  }}
  .content {{ max-width:960px; margin:0 auto; padding:40px 28px 80px; }}
  h1 {{ font-size:32px; color:var(--accent); margin:0 0 18px; border-bottom:2px solid rgba(34,197,94,.3); padding-bottom:12px; }}
  h2 {{ font-size:23px; color:var(--accent2); margin:34px 0 14px; }}
  h3 {{ font-size:18px; color:#e2e8f0; margin:24px 0 10px; }}
  p, li {{ font-size:15.5px; line-height:1.75; color:#dbe4f0; }}
  p {{ margin:10px 0; }}
  ul, ol {{ padding-left:26px; margin:10px 0; }}
  li {{ margin:5px 0; }}
  blockquote {{
    border-left:4px solid var(--accent); background:rgba(34,197,94,.07);
    padding:14px 18px; border-radius:0 10px 10px 0; margin:14px 0;
  }}
  blockquote p {{ color:#d1fae5; }}
  table {{ width:100%; border-collapse:collapse; margin:16px 0; font-size:14.5px; }}
  th {{ text-align:left; color:var(--accent); background:rgba(34,197,94,.08); padding:10px 12px; font-size:13px; border:1px solid var(--line); }}
  td {{ padding:9px 12px; border:1px solid var(--line); color:#dbe4f0; vertical-align:top; }}
  tr:nth-child(even) td {{ background:rgba(30,41,59,.5); }}
  code {{ background:#0b1120; padding:2px 7px; border-radius:5px; font-size:13.5px; color:#fbbf24; }}
  pre {{ background:#0b1120; border:1px solid var(--line); border-radius:10px; padding:18px; overflow-x:auto; margin:14px 0; }}
  pre code {{ background:none; padding:0; color:#e2e8f0; font-size:13.5px; line-height:1.6; }}
  a {{ color:var(--accent2); text-decoration:none; }}
  a:hover {{ text-decoration:underline; }}
  hr {{ border:none; border-top:1px solid var(--line); margin:26px 0; }}
  strong {{ color:#fff; }}
  @media print {{
    .bar {{ display:none; }}
    body {{ background:#fff; }}
    .content {{ padding:0; }}
    h1, h2, h3, p, li, td, th, blockquote, blockquote p {{ color:#111; }}
    td, th {{ border-color:#ccc; }}
    th {{ background:#eee; }}
    blockquote {{ background:#f5f5f5; }}
    a {{ color:#0369a1; }}
  }}
</style>
</head>
<body>
<div class="bar">
  <span class="brand">ব্যবসাঘর Docs</span>
  <a href="viewer.html">সব ডকের লিস্ট</a>
  <a href="{source}">{source} (markdown)</a>
  <button onclick="window.print()">🖨 Print / PDF</button>
</div>
<div class="content">
{body}
</div>
</body>
</html>
"""

def title_from_md(text: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else fallback

def main() -> None:
    md_files = sorted(DOCS_DIR.glob("*.md"))
    for md_file in md_files:
        text = md_file.read_text(encoding="utf-8")
        body = markdown.markdown(
            text, extensions=["tables", "fenced_code", "sane_lists"]
        )
        out = md_file.with_suffix(".html")
        out.write_text(
            TEMPLATE.format(
                title=title_from_md(text, md_file.stem),
                source=md_file.name,
                body=body,
            ),
            encoding="utf-8",
        )
        print(f"built {out.name}")

if __name__ == "__main__":
    main()
