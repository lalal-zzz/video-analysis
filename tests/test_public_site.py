import json
from pathlib import Path

import pytest

pytest.importorskip("markdown")

from scripts.build_public_site import build


def public_fixture(root: Path) -> str:
    report = "html/skills/daily/2026-10-13/" + "a" * 32 + ".md"
    values = {
        "README.md": "# Readme\n[Skill](skills/a-share-daily-review/SKILL.md)",
        "skills/a-share-daily-review/SKILL.md": "# Skill\n",
        "html/skills/creator-catalog.md": "# Authors\n",
        "html/skills/creator-catalog.json": "{}",
        "html/skills/daily/index.json": json.dumps({"reports": [{"path": report}]}),
        report: "# Daily review\n\n| Author | View |\n|---|---|\n| A | Wait |\n",
        "github.html": '<a href="README.md">Readme</a><script>link.href = report.path;</script>',
        "data/private-research/secret.md": "PRIVATE_SENTINEL",
        "html/skills/daily/unindexed.md": "UNINDEXED_SENTINEL",
    }
    for path, content in values.items():
        file = root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding="utf-8")
    return report


def test_only_public_indexed_assets_are_published(tmp_path):
    root = tmp_path / "repository"
    report = public_fixture(root)
    output = tmp_path / "site"
    build(output, root)
    assert not (output / "data").exists()
    assert not (output / "html/skills/daily/unindexed.html").exists()
    page = (output / Path(report).with_suffix(".html")).read_text(encoding="utf-8")
    assert "<table>" in page
    assert 'href="../../../../index.html#daily"' in page
    home = (output / "index.html").read_text(encoding="utf-8")
    assert 'href="README.html"' in home
    assert "report.path.replace(/\\.md$/, '.html')" in home
    assert 'href="skills/a-share-daily-review/SKILL.html"' in (output / "README.html").read_text(encoding="utf-8")
    assert 'name="description"' in page
    assert 'rel="canonical"' in page
    assert "2026-10-13 A股复盘" in page
    assert 'application/ld+json' in page
    sitemap = (output / "sitemap.xml").read_text(encoding="utf-8")
    assert "PRIVATE_SENTINEL" not in sitemap
    assert "unindexed" not in sitemap
    assert "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.html" in sitemap
    assert "github.html" not in sitemap
    assert "sitemap.xml" in (output / "robots.txt").read_text(encoding="utf-8")


def test_refuses_existing_output_or_repository_root(tmp_path):
    root = tmp_path / "repository"
    public_fixture(root)
    with pytest.raises(ValueError):
        build(root, root)
    output = tmp_path / "existing"
    output.mkdir()
    (output / "keep.txt").write_text("keep")
    with pytest.raises(ValueError):
        build(output, root)
    assert (output / "keep.txt").read_text() == "keep"


def test_report_index_cannot_publish_arbitrary_paths(tmp_path):
    root = tmp_path / "repository"
    public_fixture(root)
    (root / "html/skills/daily/index.json").write_text(json.dumps({"reports": [{"path": "data/private-research/secret.md"}]}))
    with pytest.raises(ValueError):
        build(tmp_path / "site", root)
