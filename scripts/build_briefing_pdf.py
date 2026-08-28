"""Build a single combined PDF from the docs/technical-briefing markdown set.

Usage:
    python scripts/build_briefing_pdf.py                 # combined PDF, default path
    python scripts/build_briefing_pdf.py --out FILE      # custom output path
    python scripts/build_briefing_pdf.py --keep-html     # keep intermediate HTML

Renders docs/technical-briefing/00-INDEX.md .. 07-*.md in reading order into one
HTML document (markdown-it + pygments syntax highlighting, mermaid diagrams from
jsdelivr CDN), then prints it to A4 PDF via headless Chromium (Playwright). The
final PDF is self-contained; only the build step needs network (for mermaid).
If the CDN is unreachable the mermaid blocks degrade to styled source text and
the build still succeeds.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs" / "technical-briefing"
DEFAULT_OUT = DOCS_DIR / "technical-briefing.pdf"
MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"

DOC_FILES = (
    "00-INDEX.md",
    "01-system-overview.md",
    "02-engine-deep-dive.md",
    "03-frontend-deep-dive.md",
    "04-data-sources-registry.md",
    "05-deployment-egress.md",
    "06-glossary-conventions.md",
    "07-opportunities-roadmap.md",
)

PRINT_CSS = """
:root { --ink:#171b16; --dim:#5b6257; --accent:#3FA424; --line:#c8cdc2; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family:'Segoe UI','Helvetica Neue',Arial,sans-serif; font-size:10pt;
       color:var(--ink); line-height:1.5; margin:0; }
header.titleblock { border-bottom:3px solid var(--accent); padding-bottom:8px;
                    margin-bottom:10px; }
header.titleblock h1 { font-size:20pt; margin:0 0 2px; color:#0f2c0c; }
header.titleblock p { color:var(--dim); margin:0; font-size:9pt; }
section.doc { break-before:page; }
section.doc.first { break-before:auto; }
h1 { font-size:16pt; color:#0f2c0c; border-bottom:1px solid #d7dcd2;
     padding-bottom:3px; margin:16px 0 8px; break-after:avoid; }
h2 { font-size:12.5pt; color:#24401f; margin:13px 0 6px; break-after:avoid; }
h3 { font-size:10.5pt; color:#2c4a26; margin:10px 0 4px; break-after:avoid; }
h4 { font-size:10pt; margin:8px 0 3px; break-after:avoid; }
p { margin:5px 0; }
ul,ol { margin:5px 0 8px; padding-left:22px; }
li { margin:2px 0; }
blockquote { border-left:3px solid var(--accent); background:#f3f8f0;
             padding:4px 10px; margin:6px 0; color:#333; }
code { font-family:Consolas,'Cascadia Code',monospace; font-size:8.6pt;
       background:#f1f3ee; padding:1px 3px; border-radius:3px; }
pre { background:#f6f8fa; border:1px solid #e6e8e3; border-radius:5px;
      padding:6px 10px; margin:6px 0; white-space:pre-wrap;
      word-break:break-word; }
pre code { background:none; padding:0; }
pre.mermaid { font-family:Consolas,'Cascadia Code',monospace; font-size:8.6pt; }
pre.mermaid svg { font-family:inherit; }
.highlight pre { margin:0; white-space:pre-wrap; word-break:break-word; }
table { width:100%; border-collapse:collapse; font-size:8.8pt; margin:6px 0;
        break-inside:auto; }
th,td { border:1px solid var(--line); padding:3px 7px; text-align:left;
        vertical-align:top; }
th { background:#eef4e9; font-weight:600; }
tr { break-inside:avoid; }
tr:nth-child(even) td { background:#f8fbf5; }
a { color:#1f5f17; text-decoration:none; }
svg { max-width:100%; height:auto; }
.toc ul { list-style:none; padding-left:0; }
.toc li { margin:5px 0; }
.toc .num { display:inline-block; min-width:40px; color:var(--dim); }
.toc .sep { color:var(--dim); }
hr { border:none; border-top:1px solid var(--line); margin:10px 0; }
"""

FOOTER_TMPL = (
    '<div style="width:100%;text-align:center;font-size:8px;color:#666;">'
    "ResearchHub &middot; Technical Briefing &mdash; "
    '<span class="pageNumber"></span> / <span class="totalPages"></span></div>'
)
HEADER_TMPL = "<span></span>"

MERMAID_BOOT = f"""
(function () {{
  var boot = function () {{
    document.querySelectorAll("pre code.language-mermaid").forEach(function (c) {{
      var p = c.parentNode;
      var n = document.createElement("pre");
      n.className = "mermaid";
      n.textContent = c.textContent;
      if (p && p.parentNode) {{ p.parentNode.replaceChild(n, p); }}
    }});
    if (!window.mermaid) return;   /* CDN unreachable -> degrade gracefully */
    try {{
      mermaid.initialize({{ startOnLoad:false, theme:"default",
                           securityLevel:"loose" }});
      mermaid.run({{ querySelector:"pre.mermaid" }}).then(function () {{
        window.__mmdDone = true;
      }}).catch(function (e) {{
        window.__mmdError = String(e);
        window.__mmdDone = true;
      }});
    }} catch (e) {{
      window.__mmdError = String(e);
      window.__mmdDone = true;
    }}
  }};
  if (document.readyState === "loading") {{
    document.addEventListener("DOMContentLoaded", boot);
  }} else {{ boot(); }}
}})();
"""


def slugify(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9 _-]", "", text).strip().lower()
    s = re.sub(r"\s+", "-", s)
    return s or "section"


def anchor_headings(body: str) -> tuple[str, str]:
    ids: dict[str, int] = {}

    def repl(m: re.Match) -> str:
        lvl, inner = m.group(1), m.group(2)
        base = slugify(re.sub(r"<[^>]+>", "", inner))
        n = ids.get(base, 0)
        ids[base] = n + 1
        slug = f"{base}-{n + 1}" if n else base
        return f'<h{lvl} id="{slug}">{inner}</h{lvl}>'

    out = re.sub(r"<h([1-4])>(.*?)</h\1>", repl, body, flags=re.S)
    m = re.search(r"<h1[^>]*>(.*?)</h1>", out, flags=re.S)
    title = re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else ""
    return out, title


def render_md(md: str):
    from markdown_it import MarkdownIt
    from pygments import highlight as pyg_highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import get_lexer_by_name
    from pygments.util import ClassNotFound

    fmt = HtmlFormatter(style="friendly")

    def highlight(code: str, lang: str, attrs: str) -> str:
        if not lang or lang.lower() == "mermaid":
            return ""
        try:
            lexer = get_lexer_by_name(lang, stripall=False)
        except ClassNotFound:
            return ""
        try:
            return pyg_highlight(code, lexer, fmt)
        except Exception:
            return ""

    md_inst = MarkdownIt("default", {"highlight": highlight})
    return md_inst.render(md)


def build_html() -> tuple[str, int, int]:
    mermaid_blocks = 0
    toc_rows: list[tuple[str, str]] = []
    sections: list[str] = []

    for i, name in enumerate(DOC_FILES):
        path = DOCS_DIR / name
        if not path.exists():
            print(f"ERROR: missing {path}", file=sys.stderr)
            sys.exit(2)
        body, title = anchor_headings(render_md(path.read_text(encoding="utf-8")))
        mermaid_blocks += body.count("language-mermaid")
        slug = f"doc-{name[:2]}"
        toc_rows.append((slug, title or name))
        first = " first" if i == 0 else ""
        sections.append(
            f'<section class="doc{first}" id="{slug}">\n{body}\n</section>'
        )

    toc_items = "\n".join(
        f'<li><a href="#{slug}"><span class="num">{slug[-2:]}</span>'
        f'<span>{title}</span></a></li>'
        for slug, title in toc_rows
    )
    toc = (
        f'<section class="doc" id="toc">\n<h1>Table of Contents</h1>\n'
        f'<p class="toc-note">Reading order for the ResearchHub teams '
        f"(frontend / backend / business analyst), per "
        f"<code>00-INDEX.md</code>.</p>\n<ul class=\"toc\">{toc_items}</ul>\n"
        f"</section>"
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ResearchHub — Technical Briefing</title>
<script src="{MERMAID_CDN}"></script>
<script>{MERMAID_BOOT}</script>
<style>{PRINT_CSS}</style>
</head>
<body>
<header class="titleblock">
<h1>ResearchHub · Technical Briefing</h1>
<p>Research engine + QuickPlot — doc set for the frontend, backend, and BA teams. Generated from the survey-research codebase.</p>
</header>
<main>
{toc}
{chr(10).join(sections)}
</main>
</body>
</html>
"""
    return html, mermaid_blocks, len(sections)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build technical-briefing.pdf")
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help="output PDF path"
    )
    parser.add_argument(
        "--keep-html", action="store_true", help="keep the intermediate HTML"
    )
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "ERROR: playwright not installed — run: pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 1

    print(f"Reading {len(DOC_FILES)} docs from {DOCS_DIR}")
    html, mermaid_blocks, n_sections = build_html()
    total_chars = sum(
        (DOCS_DIR / n).stat().st_size for n in DOC_FILES
    )
    print(f"Rendered {n_sections} sections, {total_chars} bytes of markdown, "
          f"{mermaid_blocks} mermaid diagram(s)")

    tmp_html = ROOT / "build" / "briefing.html"
    tmp_html.parent.mkdir(parents=True, exist_ok=True)
    tmp_html.write_text(html, encoding="utf-8")

    out = args.out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.emulate_media(media="print")
        page.goto(tmp_html.as_uri(), wait_until="domcontentloaded")
        if mermaid_blocks:
            try:
                page.wait_for_function(
                    "window.__mmdDone === true", timeout=25000
                )
            except Exception as e:  # noqa: BLE001 — offline CDN is a soft path
                print(f"WARN: mermaid render skipped ({type(e).__name__}); "
                      "diagram blocks appear as source text")
        page.wait_for_timeout(400)
        page.pdf(
            path=str(out),
            format="A4",
            print_background=True,
            display_header_footer=True,
            header_template=HEADER_TMPL,
            footer_template=FOOTER_TMPL,
            margin={
                "top": "16mm",
                "bottom": "18mm",
                "left": "12mm",
                "right": "12mm",
            },
        )
        browser.close()

    if not args.keep_html:
        try:
            tmp_html.unlink()
        except OSError:
            pass

    size_kb = out.stat().st_size / 1024
    print(f"Wrote {out} ({size_kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())