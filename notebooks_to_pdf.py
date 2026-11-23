#!/usr/bin/env python3
"""Render numbered Jupyter notebooks in this folder into one PDF.

Install with:
    python -m pip install nbformat nbconvert playwright
    python -m playwright install chromium

The script uses saved notebook outputs; it does not execute notebook code.
"""

from __future__ import annotations

import argparse
import asyncio
import re
from pathlib import Path

import nbformat
from nbconvert import HTMLExporter
from playwright.async_api import async_playwright


def natural_key(path: Path) -> tuple[object, ...]:
    """Sort numbered notebooks in human order (01, 02, ..., 10)."""
    return tuple(
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", path.name)
    )


async def convert_notebooks(notebooks: list[Path], output: Path) -> None:
    exporter = HTMLExporter()
    shared_head = None
    rendered_bodies = []

    for notebook_path in notebooks:
        notebook = nbformat.read(notebook_path, as_version=4)
        html, _ = exporter.from_notebook_node(notebook)
        head = re.search(r"<head>(.*?)</head>", html, flags=re.I | re.S)
        body = re.search(r"<body[^>]*>(.*?)</body>", html, flags=re.I | re.S)
        if not head or not body:
            raise ValueError(f"Could not parse rendered HTML for {notebook_path}")
        if shared_head is None:
            shared_head = head.group(1)
        body_html = re.sub(
            r"</h1>",
            "</h1><p class=\"author-line\">Auteurs : Elie Hasbani, "
            "Nour Soliman et Peter Yaacoub</p>",
            body.group(1),
            count=1,
            flags=re.I,
        )
        rendered_bodies.append((notebook_path, body_html))
        print(f"Rendered {notebook_path.name}")

    sections = "\n".join(
        f'<section class="notebook"><h1 class="notebook-title">{path.stem}</h1>{body}</section>'
        for path, body in rendered_bodies
    )
    print_styles = """
    <style>
      @page { size: A4; margin: 16mm 17mm 22mm; }
      html, body { width: auto !important; max-width: none !important; }
      body { margin: 0 !important; padding: 0 !important; }
      .jp-Notebook { width: auto !important; max-width: none !important;
                     margin: 0 !important; padding: 0 !important; }
      .jp-Cell { display: block !important; }
      .jp-InputPrompt, .jp-OutputPrompt { display: none !important; }
      .jp-InputArea, .jp-OutputArea { width: 100% !important; margin: 0 !important; }
      .notebook + .notebook { break-before: page; }
      .notebook-title { font-size: 9pt; font-weight: normal; color: #666;
                        border-bottom: 1px solid #bbb; padding-bottom: 4pt;
                        margin: 0 0 14pt; }
      .author-line { margin: -5pt 0 18pt !important; font-weight: 600; }
      pre, code, .jp-RenderedHTMLCommon pre, .jp-OutputArea-output pre {
        white-space: pre-wrap !important; overflow-wrap: anywhere !important;
        word-break: break-word !important; max-width: 100% !important;
      }
      .jp-CodeCell pre, .jp-OutputArea pre {
        font-size: 7.5pt !important; line-height: 1.25 !important;
      }
      table {
        width: 100% !important; max-width: 100% !important;
        table-layout: fixed !important; border-collapse: collapse !important;
      }
      th, td {
        white-space: normal !important; overflow-wrap: anywhere !important;
        word-break: break-word !important; padding: 3px 4px !important;
      }
      table.dataframe { font-size: 6.5pt !important; }
      table.dataframe td {
        white-space: nowrap !important; overflow-wrap: normal !important;
        word-break: normal !important; padding: 2px 3px !important;
      }
      thead { display: table-header-group; }
      tfoot { display: table-footer-group; }
      tr { break-inside: avoid; page-break-inside: avoid; }
      img, svg { max-width: 100% !important; height: auto; }
      * { box-sizing: border-box; }
    </style>
    """
    document = (
        "<!doctype html><html><head>" + (shared_head or "") + print_styles
        + "</head><body>" + sections + "</body></html>"
    )

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        await page.set_content(document, wait_until="networkidle")
        pdf_bytes = await page.pdf(
            format="A4",
            print_background=True,
            prefer_css_page_size=True,
            display_header_footer=True,
            header_template="<div></div>",
            footer_template=(
                '<div style="width:100%;font:9px Arial,sans-serif;color:#666;'
                'text-align:center;padding-top:4px;">'
                '<span class="pageNumber"></span> / <span class="totalPages"></span></div>'
            ),
            margin={"top": "16mm", "right": "17mm", "bottom": "22mm", "left": "17mm"},
        )
        await browser.close()

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(pdf_bytes)
    print(f"Created {output}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert numbered Jupyter notebooks into one PDF."
    )
    parser.add_argument(
        "--output", type=Path, default=Path("notebooks_compiled.pdf"),
        help="Output PDF path (default: notebooks_compiled.pdf)",
    )
    parser.add_argument(
        "notebooks", nargs="*", type=Path,
        help="Notebook paths; defaults to all .ipynb files in this script's folder.",
    )
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    notebooks = args.notebooks or sorted(
        (path for path in base_dir.glob("*.ipynb")
         if ".ipynb_checkpoints" not in path.parts),
        key=natural_key,
    )
    notebooks = [path.resolve() for path in notebooks]
    if not notebooks:
        parser.error("No .ipynb notebooks found.")
    missing = [path for path in notebooks if not path.is_file()]
    if missing:
        parser.error("Notebook not found: " + ", ".join(map(str, missing)))

    output = args.output if args.output.is_absolute() else base_dir / args.output
    asyncio.run(convert_notebooks(notebooks, output.resolve()))


if __name__ == "__main__":
    main()
