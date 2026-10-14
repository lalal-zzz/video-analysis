"""Build a GitHub Pages artifact from explicitly public research assets only."""
from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from urllib.parse import quote, urlparse

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "https://github.com/lalal-zzz/video-analysis/blob/main/"


def build(output: Path, root: Path = ROOT) -> None:
    import markdown

    output = output.resolve()
    if output == root.resolve() or output.exists() and any(output.iterdir()):
        raise ValueError("Use an empty output directory, separate from the checkout")
    files = {Path("README.md"), Path("html/skills/creator-catalog.md"),
             Path("html/skills/creator-catalog.json"), Path("html/skills/daily/index.json")}
    for folder in ("skills/a-share-daily-review", "skills/video-analysis"):
        files.update(path.relative_to(root) for path in (root / folder).rglob("*")
                     if path.is_file() and path.suffix in (".md", ".json"))
    reports = json.loads((root / "html/skills/daily/index.json").read_text(encoding="utf-8"))["reports"]
    for report in reports:
        path = report["path"]
        if not re.fullmatch(r"html/skills/daily/\d{4}-\d{2}-\d{2}/[a-f0-9]{32}\.md", path):
            raise ValueError("Invalid public report path")
        files.add(Path(path))
    output.mkdir(parents=True, exist_ok=True)
    homepage = (root / "github.html").read_text(encoding="utf-8")
    homepage = re.sub(r'(href="[^"#?]+)\.md("|[?#])', r'\1.html\2', homepage)
    # Keep the index's immutable source paths; only change the browser destination.
    homepage = homepage.replace("link.href = report.path;", "link.href = report.path.replace(/\\.md$/, '.html');")
    for name in ("index.html", "github.html"):
        (output / name).write_text(homepage, encoding="utf-8")
    (output / ".nojekyll").write_text("", encoding="utf-8")
    css = "body{max-width:1040px;margin:40px auto;padding:0 20px;color:#203229;font:16px/1.8 system-ui,sans-serif}a{color:#17674b}table{display:block;overflow-x:auto;border-collapse:collapse;font-size:14px}td,th{border:1px solid #dce4da;padding:10px;min-width:100px}pre{overflow:auto;background:#f2f5f0;padding:15px}code{overflow-wrap:anywhere}h1,h2,h3{line-height:1.4}nav{border-bottom:1px solid #dce4da;padding-bottom:18px;margin-bottom:30px}img{max-width:100%}"
    for relative in sorted(files):
        source = root / relative
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"Missing or unsafe public asset: {relative}")
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix != ".md":
            target.write_bytes(source.read_bytes())
            continue
        text = source.read_text(encoding="utf-8")
        body = markdown.markdown(text, extensions=["tables", "fenced_code"])

        def resolve_link(match: re.Match[str]) -> str:
            href = html.unescape(match[1])
            parsed = urlparse(href)
            if parsed.scheme or href.startswith("#"):
                return match[0]
            path = (source.parent / parsed.path).resolve()
            try:
                repo_path = path.relative_to(root.resolve())
            except ValueError:
                return match[0]
            if repo_path in files and path.suffix == ".md":
                href = re.sub(r"\.md(?=$|[?#])", ".html", href)
            elif repo_path not in files:
                href = REPOSITORY + quote(repo_path.as_posix())
            return 'href="' + html.escape(href, quote=True) + '"'

        body = re.sub(r'href="([^"]+)"', resolve_link, body)
        depth = len(relative.parts) - 1
        back = "../" * depth + "index.html#daily"
        title = next((line[2:] for line in text.splitlines() if line.startswith("# ")), relative.stem)
        page = f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(title)}</title><style>{css}</style></head><body><nav><a href="{back}">← 返回研究首页与历史日历</a></nav><main>{body}</main></body></html>'
        target.with_suffix(".html").write_text(page, encoding="utf-8")
    print(f"Public site built: {len(files)} assets plus homepage")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    build(parser.parse_args().output)
