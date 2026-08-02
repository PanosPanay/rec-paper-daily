#!/usr/bin/env python3
"""Build a small static archive from the Obsidian daily-report folder."""

from __future__ import annotations

import argparse
import html
import re
import shutil
from pathlib import Path


DEFAULT_SOURCE = Path("/Users/wangbaojiang/Nutstore Files/我的坚果云/日常/推荐论文日报")
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = SCRIPT_DIR.parent / "site"


def inline_markdown(value: str) -> str:
    value = html.escape(value, quote=False)
    value = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', value)
    value = re.sub(r"`([^`]+)`", r"<code>\1</code>", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", value)
    return value


def markdown_to_html(markdown: str) -> str:
    output: list[str] = []
    paragraph: list[str] = []
    in_list = False

    def flush_paragraph() -> None:
        if paragraph:
            output.append(f"<p>{'<br> '.join(paragraph)}</p>")
            paragraph.clear()

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            output.append("</ul>")
            in_list = False

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            close_list()
            continue
        if line.startswith("# "):
            flush_paragraph()
            close_list()
            output.append(f"<h1>{inline_markdown(line[2:])}</h1>")
        elif line.startswith("## "):
            flush_paragraph()
            close_list()
            output.append(f"<h2>{inline_markdown(line[3:])}</h2>")
        elif line.startswith("### "):
            flush_paragraph()
            close_list()
            output.append(f"<h3>{inline_markdown(line[4:])}</h3>")
        elif line.startswith("> "):
            flush_paragraph()
            close_list()
            output.append(f"<blockquote>{inline_markdown(line[2:])}</blockquote>")
        elif re.match(r"^(?:[-*]|\d+\.)\s+", line):
            flush_paragraph()
            if not in_list:
                output.append("<ul>")
                in_list = True
            item = re.sub(r"^(?:[-*]|\d+\.)\s+", "", line)
            output.append(f"<li>{inline_markdown(item)}</li>")
        else:
            close_list()
            paragraph.append(inline_markdown(line))
    flush_paragraph()
    close_list()
    return "\n".join(output)


def page(title: str, body: str, back_link: str = "") -> str:
    back = f'<a class="back" href="{back_link}">← 返回日报列表</a>' if back_link else ""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root {{ color-scheme: light dark; font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif; }}
body {{ margin: 0; background: #f5f7fb; color: #18202a; line-height: 1.65; }}
main {{ max-width: 920px; margin: 0 auto; padding: 42px 20px 72px; }}
article, .report-list {{ background: white; border: 1px solid #e3e8ef; border-radius: 12px; padding: 28px clamp(20px, 5vw, 48px); box-shadow: 0 8px 28px rgba(25, 45, 70, .06); }}
h1 {{ line-height: 1.25; margin-top: 0; }} h2 {{ margin-top: 2em; border-bottom: 1px solid #e8edf3; padding-bottom: .35em; }}
a {{ color: #1769d1; }} li {{ margin: .45em 0; }} code {{ background: #eef2f7; padding: .1em .3em; border-radius: 4px; }}
blockquote {{ border-left: 4px solid #4c9ffe; margin: 1em 0; padding: .4em 1em; color: #536171; background: #f4f8ff; }}
.back {{ display: inline-block; margin-bottom: 18px; text-decoration: none; }} .meta {{ color: #657384; }}
@media (prefers-color-scheme: dark) {{ body {{ background: #11161c; color: #e8edf3; }} article, .report-list {{ background: #1a2129; border-color: #303b48; }} blockquote {{ background: #182b40; color: #b7c4d2; }} code {{ background: #2b3540; }} h2 {{ border-color: #303b48; }} }}
</style>
</head>
<body><main>{back}{body}</main></body>
</html>"""


def build(source_dir: Path, output_dir: Path) -> int:
    reports = sorted(source_dir.glob("daily-*.md"), reverse=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    for child in output_dir.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()

    links = []
    for report in reports:
        slug = report.stem.removeprefix("daily-")
        target = output_dir / f"{slug}.html"
        target.write_text(page(report.stem, markdown_to_html(report.read_text(encoding="utf-8")), "index.html"), encoding="utf-8")
        links.append(f'<li><a href="{target.name}">{html.escape(slug)}</a></li>')
    body = "<h1>推荐算法研究日报</h1><p class=\"meta\">Obsidian 日报归档 · 自动同步到 GitHub Pages</p>"
    body += "<section class=\"report-list\"><h2>日报归档</h2><ul>"
    body += "".join(links) or "<li>暂无日报</li>"
    body += "</ul></section>"
    (output_dir / "index.html").write_text(page("推荐算法研究日报", body), encoding="utf-8")
    return len(reports)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(f"Built {build(args.source_dir, args.output_dir)} report pages in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
