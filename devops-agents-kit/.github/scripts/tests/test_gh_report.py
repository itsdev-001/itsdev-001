"""Unit tests for shared GitHub reporting library."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from lib.gh_report import (
    ensure_reports_dir,
    find_existing_issue,
    find_repo_root,
    is_gh_available,
    sync_issue,
    write_report,
)


def test_find_repo_root(tmp_path: Path):
    # Create fake repo structure
    (tmp_path / ".github").mkdir(parents=True, exist_ok=True)
    sub = tmp_path / "sub" / "dir"
    sub.mkdir(parents=True, exist_ok=True)
    f = sub / "test.txt"
    f.write_text("hello", encoding="utf-8")

    root = find_repo_root(f)
    assert root == tmp_path


def test_write_report(tmp_path: Path):
    content = "# Test Report\nEverything is good."
    report_file = write_report("test-report.md", content, repo_root=tmp_path)

    assert report_file.exists()
    assert report_file.parent.name == "reports"
    assert report_file.read_text(encoding="utf-8") == content


def test_sync_issue_when_gh_unavailable(tmp_path: Path):
    with patch("lib.gh_report.is_gh_available", return_value=False):
        res = sync_issue(
            marker="<!-- test -->",
            title="Test Issue",
            report_body="Body",
            actionable_count=2,
            cwd=tmp_path,
        )
        assert res["action"] == "none"
        assert "unavailable" in res["details"]


def test_sync_issue_create_new_when_actionable_findings(tmp_path: Path):
    with patch("lib.gh_report.is_gh_available", return_value=True), \
         patch("lib.gh_report.find_existing_issue", return_value=None), \
         patch("lib.gh_report.run_gh_command", return_value=(0, "https://github.com/org/repo/issues/10", "")) as mock_cmd:
        
        res = sync_issue(
            marker="<!-- marker -->",
            title="[DevOps Health] New Finding",
            report_body="Details here",
            actionable_count=3,
            cwd=tmp_path,
        )
        assert res["action"] == "created"
        assert mock_cmd.called


def test_sync_issue_close_when_zero_actionable_findings(tmp_path: Path):
    existing = {"number": 15, "title": "Old Health Issue", "body": "<!-- marker --> body", "state": "OPEN"}
    with patch("lib.gh_report.is_gh_available", return_value=True), \
         patch("lib.gh_report.find_existing_issue", return_value=existing), \
         patch("lib.gh_report.run_gh_command", return_value=(0, "closed", "")) as mock_cmd:
        
        res = sync_issue(
            marker="<!-- marker -->",
            title="[DevOps Health] Old",
            report_body="Clean now",
            actionable_count=0,
            cwd=tmp_path,
        )
        assert res["action"] == "closed"
        assert res["issue_number"] == 15

