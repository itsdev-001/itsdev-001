"""Unit tests for Agent 1: Repository Health Agent."""

from pathlib import Path
from unittest.mock import patch

from agents.repo_health_agent import (
    check_baseline_structure,
    check_broken_links,
    check_readme,
    check_syntax_validation,
    extract_markdown_links,
    generate_markdown_report,
)
from datetime import datetime, timezone


def test_check_readme_missing(tmp_path: Path):
    findings = check_readme(tmp_path)
    assert len(findings) == 1
    assert "Missing `README.md`" in findings[0]


def test_check_readme_valid(tmp_path: Path):
    readme = tmp_path / "README.md"
    readme.write_text(
        "# My Project\n\n## Setup\nRun install.\n\n## Usage\nRun agent.\n\n## License\nMIT License.",
        encoding="utf-8",
    )
    findings = check_readme(tmp_path)
    assert len(findings) == 0


def test_extract_markdown_links(tmp_path: Path):
    md_file = tmp_path / "doc.md"
    md_file.write_text(
        "Here is a [link](https://github.com) and a local [file](./sub/test.py).",
        encoding="utf-8",
    )
    links = extract_markdown_links(md_file)
    assert len(links) == 2
    assert links[0][1] == "link"
    assert links[0][2] == "https://github.com"
    assert links[1][1] == "file"
    assert links[1][2] == "./sub/test.py"


def test_check_broken_local_links(tmp_path: Path):
    md_file = tmp_path / "README.md"
    md_file.write_text("See [missing](non_existent_file.md)", encoding="utf-8")

    findings = check_broken_links(tmp_path, check_remote=False)
    assert len(findings) == 1
    assert "Broken local link" in findings[0]


def test_check_baseline_structure(tmp_path: Path):
    # Initially all missing
    findings = check_baseline_structure(tmp_path)
    assert len(findings) == 3

    # Add baseline files
    (tmp_path / "LICENSE").write_text("MIT", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("*.pyc\n", encoding="utf-8")
    (tmp_path / "CONTRIBUTING.md").write_text("# Contributing", encoding="utf-8")

    findings_after = check_baseline_structure(tmp_path)
    assert len(findings_after) == 0


def test_check_syntax_validation(tmp_path: Path):
    valid_yml = tmp_path / "valid.yml"
    valid_yml.write_text("name: test\nversion: 1\n", encoding="utf-8")

    invalid_json = tmp_path / "invalid.json"
    invalid_json.write_text("{ unquoted_key: 123 ", encoding="utf-8")

    findings = check_syntax_validation(tmp_path)
    assert len(findings) == 1
    assert "Invalid JSON syntax" in findings[0]


def test_generate_markdown_report_clean():
    now = datetime.now(timezone.utc)
    report, actionable = generate_markdown_report([], [], [], [], [], now)
    assert actionable == 0
    assert "🟢 Healthy" in report
    assert "All checks passed!" in report

