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
<title>{title} — ব্যবসাঘর Docs</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Anek+Bangla:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="glossary.css">
<script src="glossary.js" defer></script>
<style>
  :root {{
    --bg-page: #050814;
    --card-bg: rgba(16, 23, 44, 0.65);
    --card-border: rgba(255, 255, 255, 0.08);
    --card-border-top: rgba(255, 255, 255, 0.14);
    --accent: #00f2a9;
    --accent-light: #34d399;
    --accent-glow: rgba(0, 242, 169, 0.15);
    --accent2: #38bdf8;
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --line: rgba(255, 255, 255, 0.08);
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    font-family: 'Anek Bangla', 'Hind Siliguri', sans-serif;
    background-color: var(--bg-page);
    background-image: 
      radial-gradient(circle at 50% 0%, rgba(99, 102, 241, 0.12), transparent 50%),
      radial-gradient(circle at 100% 100%, rgba(0, 242, 169, 0.08), transparent 50%),
      radial-gradient(rgba(255, 255, 255, 0.04) 1px, transparent 1px);
    background-size: 100% 100%, 100% 100%, 28px 28px;
    color: var(--text-primary);
    line-height: 1.7;
    -webkit-font-smoothing: antialiased;
  }}
  .bar {{
    position: sticky; top: 0; z-index: 50;
    background: rgba(9, 14, 31, 0.85); backdrop-filter: blur(20px);
    border-bottom: 1px solid var(--line); padding: 13px 28px;
    display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
  }}
  .brand {{
    font-weight: 700; color: #fff; font-size: 16.5px;
    display: inline-flex; align-items: center; gap: 8px;
  }}
  .brand-dot {{
    width: 8px; height: 8px; background: var(--accent);
    border-radius: 50%; box-shadow: 0 0 10px var(--accent);
  }}
  .bar a {{
    color: var(--accent2); font-size: 13px; text-decoration: none;
    font-family: 'Plus Jakarta Sans', sans-serif; font-weight: 600;
    transition: color 0.15s;
  }}
  .bar a:hover {{ color: #bae6fd; text-decoration: underline; }}
  .bar button {{
    margin-left: auto; background: var(--accent); color: #04120a;
    border: none; border-radius: 999px;
    padding: 7px 16px; font-family: 'Plus Jakarta Sans', sans-serif;
    font-size: 13px; font-weight: 700; cursor: pointer;
    box-shadow: 0 2px 10px var(--accent-glow); transition: all 0.2s;
  }}
  .bar button:hover {{ filter: brightness(1.1); transform: translateY(-1px); }}
  .content {{
    max-width: 940px; margin: 0 auto; padding: 44px 24px 90px;
  }}
  h1 {{
    font-size: 36px; font-weight: 800; line-height: 1.25; margin: 0 0 20px;
    background: linear-gradient(135deg, #ffffff 40%, #cbd5e1 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    border-bottom: 1px solid var(--line); padding-bottom: 16px;
    letter-spacing: -0.5px;
  }}
  h2 {{
    font-size: 24px; font-weight: 700; color: var(--accent2); margin: 36px 0 14px;
    letter-spacing: -0.2px; display: flex; align-items: center; gap: 8px;
  }}
  h3 {{ font-size: 18px; font-weight: 700; color: #f1f5f9; margin: 24px 0 10px; }}
  p, li {{ font-size: 16px; line-height: 1.75; color: #dbe4f0; }}
  p {{ margin: 12px 0; }}
  ul, ol {{ padding-left: 24px; margin: 12px 0; }}
  li {{ margin: 6px 0; }}
  blockquote {{
    border-left: 4px solid var(--accent);
    background: rgba(0, 242, 169, 0.06);
    padding: 16px 22px; border-radius: 0 12px 12px 0; margin: 18px 0;
    border-top: 1px solid rgba(255, 255, 255, 0.05);
  }}
  blockquote p {{ color: #d1fae5; margin: 4px 0; font-size: 16px; }}
  table {{
    width: 100%; border-collapse: separate; border-spacing: 0;
    margin: 20px 0; font-size: 14.5px;
    border: 1px solid var(--card-border); border-radius: 12px;
    overflow: hidden; background: var(--card-bg); backdrop-filter: blur(12px);
  }}
  th {{
    text-align: left; color: var(--accent); background: rgba(24, 34, 64, 0.85);
    padding: 12px 16px; font-size: 13px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.8px;
    border-bottom: 1px solid var(--card-border);
  }}
  td {{
    padding: 11px 16px; border-bottom: 1px solid var(--line);
    color: #e2e8f0; vertical-align: top;
  }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: rgba(255, 255, 255, 0.02); }}
  code {{
    background: rgba(255, 255, 255, 0.06); border: 1px solid rgba(255, 255, 255, 0.1);
    padding: 2px 8px; border-radius: 6px; font-size: 13.5px; color: #fbbf24;
    font-family: 'Plus Jakarta Sans', monospace;
  }}
  pre {{
    background: #090e1f; border: 1px solid var(--line); border-radius: 12px;
    padding: 18px; overflow-x: auto; margin: 16px 0;
  }}
  pre code {{ background: none; border: none; padding: 0; color: #e2e8f0; font-size: 13.5px; line-height: 1.6; }}
  a {{ color: var(--accent2); text-decoration: none; transition: color 0.15s; }}
  a:hover {{ color: #bae6fd; text-decoration: underline; }}
  hr {{ border: none; border-top: 1px solid var(--line); margin: 30px 0; }}
  strong {{ color: #fff; font-weight: 700; }}
  @media print {{
    .bar {{ display: none; }}
    body {{ background: #fff !important; color: #111 !important; }}
    .content {{ padding: 0; max-width: 100%; }}
    h1, h2, h3, p, li, td, th, blockquote, blockquote p {{ color: #111 !important; }}
    td, th {{ border-color: #ccc !important; }}
    th {{ background: #eee !important; }}
    blockquote {{ background: #f5f5f5 !important; border-left-color: #047857 !important; }}
    a {{ color: #0369a1 !important; }}
  }}
</style>
</head>
<body>
<div class="bar">
  <span class="brand"><span class="brand-dot"></span>ব্যবসাঘর Docs</span>
  <a href="viewer.html">← সব ডকের লিস্ট</a>
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

    # Re-encrypt internal pages so protected content stays locked after rebuilds.
    protect = DOCS_DIR / "protect.py"
    if protect.exists():
        import subprocess
        import sys
        subprocess.run([sys.executable, str(protect)], check=True)

if __name__ == "__main__":
    main()
