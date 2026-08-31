#!/usr/bin/env python3
"""Shared GitHub issue reporting and idempotent sync engine.

Provides utility functions to:
1. Ensure reports directory exists and safely write Markdown reports.
2. Synchronize findings idempotently with GitHub Issues via GitHub CLI (`gh`).
   - Opens / reopens and updates tracked issues when actionable findings > 0.
   - Automatically resolves and closes tracked issues when actionable findings == 0.
   - Uses hidden HTML markers to prevent duplicate issues.
"""

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("gh_report")


def find_repo_root(start_path: Optional[Path] = None) -> Path:
    """Find the root directory of the repository starting from start_path."""
    curr = (start_path or Path(__file__)).resolve()
    if curr.is_file():
        curr = curr.parent

    for parent in [curr] + list(curr.parents):
        if (parent / ".git").exists() or (parent / ".github").exists():
            return parent
    return curr


def ensure_reports_dir(repo_root: Optional[Path] = None, dir_name: str = "reports") -> Path:
    """Ensure the target reports directory exists and return its path."""
    root = repo_root or find_repo_root()
    reports_path = root / dir_name
    reports_path.mkdir(parents=True, exist_ok=True)
    return reports_path


def write_report(
    filename: str,
    content: str,
    repo_root: Optional[Path] = None,
    dir_name: str = "reports",
) -> Path:
    """Write the report content to the designated reports file."""
    reports_dir = ensure_reports_dir(repo_root, dir_name)
    target_file = reports_dir / filename
    target_file.write_text(content, encoding="utf-8")
    logger.info("Successfully wrote report to %s", target_file)
    return target_file


def is_gh_available() -> bool:
    """Check if GitHub CLI (gh) is installed and available in PATH."""
    return shutil.which("gh") is not None


def run_gh_command(args: List[str], cwd: Optional[Path] = None) -> Tuple[int, str, str]:
    """Execute a GitHub CLI command safely and return (returncode, stdout, stderr)."""
    if not is_gh_available():
        return (-1, "", "GitHub CLI (gh) is not installed or not in PATH.")

    cmd = ["gh"] + args
    try:
        res = subprocess.run(
            cmd,
            cwd=cwd or find_repo_root(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        return (res.returncode, res.stdout.strip(), res.stderr.strip())
    except Exception as exc:
        return (-1, "", f"Failed to execute gh command: {exc}")


def find_existing_issue(marker: str, cwd: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Find an existing tracked issue by looking for its unique HTML marker."""
    if not is_gh_available():
        logger.warning("GitHub CLI not available. Skipping issue search.")
        return None

    # Query all issues (open and closed)
    code, stdout, stderr = run_gh_command(
        ["issue", "list", "--state", "all", "--json", "number,title,body,state,url,labels", "--limit", "100"],
        cwd=cwd,
    )
    if code != 0:
        logger.warning("Unable to fetch issue list via gh: %s", stderr)
        return None

    try:
        issues = json.loads(stdout)
        for issue in issues:
            body = issue.get("body") or ""
            if marker in body:
                return issue
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse JSON output from gh issue list: %s", exc)

    return None


def sync_issue(
    marker: str,
    title: str,
    report_body: str,
    actionable_count: int,
    labels: Optional[List[str]] = None,
    cwd: Optional[Path] = None,
) -> Dict[str, Any]:
    """Synchronize findings idempotently with GitHub Issues.

    Rules:
    - If actionable_count > 0:
        * If issue exists and closed -> Reopen and update body & title.
        * If issue exists and open -> Update body & title in place.
        * If no issue exists -> Create new issue with specified labels.
    - If actionable_count == 0:
        * If issue exists and open -> Comment resolution note and close it.
        * If issue doesn't exist or is closed -> Do nothing (zero spam).

    Returns a summary dictionary of actions taken.
    """
    labels = labels or ["automated-report"]
    result: Dict[str, Any] = {
        "action": "none",
        "issue_number": None,
        "actionable_count": actionable_count,
        "details": "",
    }

    if not is_gh_available():
        msg = "gh CLI is unavailable; skipping remote issue synchronization."
        logger.info(msg)
        result["details"] = msg
        return result

    # Format full issue body with marker and header
    full_body = (
        f"{marker}\n"
        "> [!IMPORTANT]\n"
        "> **Automated DevOps Report**: This issue is automatically synchronized by your repository's automation agents. "
        "Do not remove the tracking marker above.\n\n"
        f"{report_body.strip()}\n"
    )

    existing_issue = find_existing_issue(marker, cwd=cwd)

    if actionable_count > 0:
        if existing_issue:
            num = existing_issue["number"]
            state = existing_issue.get("state", "OPEN").upper()
            result["issue_number"] = num

            # Reopen if closed
            if state == "CLOSED":
                logger.info("Reopening closed issue #%d due to new actionable findings...", num)
                reopen_code, _, reopen_err = run_gh_command(["issue", "reopen", str(num)], cwd=cwd)
                if reopen_code != 0:
                    logger.warning("Failed to reopen issue #%d: %s", num, reopen_err)

            # Update body and title in place using temporary file to handle multiline content cleanly
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as tf:
                tf.write(full_body)
                temp_path = tf.name

            try:
                edit_code, _, edit_err = run_gh_command(
                    ["issue", "edit", str(num), "--title", title, "--body-file", temp_path],
                    cwd=cwd,
                )
                if edit_code == 0:
                    logger.info("Updated tracked issue #%d with %d actionable findings.", num, actionable_count)
                    result["action"] = "updated"
                    result["details"] = f"Updated issue #{num}"
                else:
                    logger.error("Failed to edit issue #%d: %s", num, edit_err)
                    result["details"] = f"Failed to edit issue #{num}: {edit_err}"
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        else:
            # Create new issue
            logger.info("Creating new tracked issue: %s", title)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as tf:
                tf.write(full_body)
                temp_path = tf.name

            try:
                cmd = ["issue", "create", "--title", title, "--body-file", temp_path]
                for label in labels:
                    cmd.extend(["--label", label])

                code, stdout, stderr = run_gh_command(cmd, cwd=cwd)
                if code != 0 and "label" in stderr.lower():
                    # Retry without label in case the repository has not created the label yet
                    logger.warning("Label creation failed (%s), retrying without label...", stderr)
                    cmd_no_label = ["issue", "create", "--title", title, "--body-file", temp_path]
                    code, stdout, stderr = run_gh_command(cmd_no_label, cwd=cwd)

                if code == 0:
                    logger.info("Created new issue: %s", stdout)
                    result["action"] = "created"
                    result["details"] = f"Created issue: {stdout}"
                else:
                    logger.error("Failed to create issue: %s", stderr)
                    result["details"] = f"Failed to create issue: {stderr}"
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

    else:
        # actionable_count == 0
        if existing_issue:
            num = existing_issue["number"]
            state = existing_issue.get("state", "OPEN").upper()
            result["issue_number"] = num

            if state == "OPEN":
                logger.info("All findings resolved. Adding comment and closing issue #%d...", num)
                comment_msg = (
                    "✅ **All Findings Resolved**: The latest DevOps health check completed with zero actionable findings. "
                    "Closing this issue automatically."
                )
                run_gh_command(["issue", "comment", str(num), "--body", comment_msg], cwd=cwd)
                close_code, _, close_err = run_gh_command(
                    ["issue", "close", str(num), "--reason", "completed"],
                    cwd=cwd,
                )
                if close_code == 0:
                    logger.info("Successfully closed resolved issue #%d.", num)
                    result["action"] = "closed"
                    result["details"] = f"Closed issue #{num}"
                else:
                    logger.warning("Failed to close issue #%d: %s", num, close_err)
                    result["details"] = f"Failed to close issue #{num}: {close_err}"
            else:
                logger.info("Issue #%d is already closed and findings remain clean.", num)
                result["action"] = "clean"
                result["details"] = f"Issue #{num} already closed"
        else:
            logger.info("Healthy state: 0 actionable findings and no existing issue. No action needed.")
            result["action"] = "clean"
            result["details"] = "Healthy state with zero open issues"

    return result

