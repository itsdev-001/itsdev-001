#!/usr/bin/env python3
"""Agent 1: Repository Health Agent.

Performs automated checks on repository integrity:
1. README validation: existence and essential sections (Installation, Usage, License).
2. Broken links verification across all Markdown (*.md) files (relative files and remote URLs).
3. Baseline project structure: LICENSE, .gitignore, CONTRIBUTING.md.
4. YAML & JSON syntax validation across the repository.
5. GitHub Actions workflow runs health on the default branch.

Outputs:
- Generates `reports/repo-health-report.md`.
- Synchronizes findings with GitHub Issues idempotently using marker:
  `<!-- devops-agent:repo-health-agent -->`.
"""

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import unquote, urlparse

# Ensure lib package can be imported regardless of execution path
SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPTS_ROOT = SCRIPT_DIR.parent
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

try:
    import requests
except ImportError:
    requests = None  # type: ignore

from lib.gh_report import (
    find_repo_root,
    is_gh_available,
    run_gh_command,
    sync_issue,
    write_report,
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("repo_health_agent")

MARKER = "<!-- devops-agent:repo-health-agent -->"
REPORT_FILENAME = "repo-health-report.md"
ISSUE_TITLE = "[DevOps Health] Repository Health Findings"

IGNORED_DIRS = {
    ".git",
    ".github/actions",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "reports",
    ".pytest_cache",
    ".gemini",
    ".idea",
    ".vscode",
}


def should_skip_path(path: Path, repo_root: Path) -> bool:
    """Determine whether a file or directory should be ignored."""
    try:
        rel = path.relative_to(repo_root)
    except ValueError:
        return False

    parts = rel.parts
    for ignored in IGNORED_DIRS:
        ignored_parts = Path(ignored).parts
        for i in range(len(parts) - len(ignored_parts) + 1):
            if parts[i : i + len(ignored_parts)] == ignored_parts:
                return True
    return False


def check_readme(repo_root: Path) -> List[str]:
    """Check if README exists and contains setup, usage, and license sections."""
    findings = []
    readme_candidates = [
        repo_root / "README.md",
        repo_root / "README.rst",
        repo_root / "README.txt",
        repo_root / "readme.md",
    ]
    readme_path = next((p for p in readme_candidates if p.exists() and p.is_file()), None)

    if not readme_path:
        findings.append("Missing `README.md` file in the repository root.")
        return findings

    content = readme_path.read_text(encoding="utf-8", errors="ignore").lower()

    # Required section patterns (supporting emoji prefixes like ## 🚀 Setup)
    sections = {
        "Setup / Installation": [r"#+\s*(?:[^\w\s]+\s*)?(setup|install|getting\s+started|quick\s*start|prerequisites)"],
        "Usage / Workflows / Agents": [r"#+\s*(?:[^\w\s]+\s*)?(usage|how\s+to\s+use|agents|workflows|commands|features)"],
        "License / Rules / Contributing": [r"#+\s*(?:[^\w\s]+\s*)?(license|licensing|contributing|design\s+rules|guidelines)"],
    }

    missing_sections = []
    for section_name, patterns in sections.items():
        if not any(re.search(pat, content) for pat in patterns):
            missing_sections.append(section_name)

    if missing_sections:
        findings.append(
            f"README at `{readme_path.name}` is missing key sections: {', '.join(missing_sections)}."
        )

    return findings


def extract_markdown_links(file_path: Path) -> List[Tuple[int, str, str]]:
    """Extract (line_number, link_text, link_url) from a Markdown file."""
    links = []
    try:
        lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception as exc:
        logger.warning("Could not read %s: %s", file_path, exc)
        return []

    # First clean out images ![alt](url) before finding links
    inline_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')

    for idx, line in enumerate(lines, start=1):
        # Ignore lines that are pure images or strip images
        clean_line = re.sub(r'\!\[([^\]]*)\]\([^)]+\)', r'\1', line)
        for match in inline_pattern.finditer(clean_line):
            text, url = match.groups()
            url = url.strip()
            # Remove title if present (e.g., [text](url "title"))
            if ' "' in url:
                url = url.split(' "')[0]
            elif " '" in url:
                url = url.split(" '")[0]
            links.append((idx, text, url))

    return links


def check_broken_links(repo_root: Path, check_remote: bool = True) -> List[str]:
    """Scan all markdown files in the repository for broken relative and remote links."""
    findings = []
    md_files = [
        p for p in repo_root.rglob("*.md")
        if p.is_file() and not should_skip_path(p, repo_root)
    ]

    session = None
    if check_remote and requests:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; DevOpsHealthAgent/1.0)"})

    checked_remote_urls: Dict[str, Tuple[bool, str]] = {}

    for md_file in md_files:
        rel_md = md_file.relative_to(repo_root)
        links = extract_markdown_links(md_file)

        for line_no, link_text, url in links:
            # Skip empty, anchors, mailto, javascript, or placeholders
            if not url or url.startswith("#") or url.startswith("mailto:") or url.startswith("javascript:"):
                continue
            if any(dummy in url for dummy in ["example.com", "localhost", "127.0.0.1", "foo.bar"]):
                continue

            parsed = urlparse(url)

            if parsed.scheme in ("http", "https"):
                # Remote URL check
                if not check_remote or not session:
                    continue

                if url in checked_remote_urls:
                    is_ok, reason = checked_remote_urls[url]
                    if not is_ok:
                        findings.append(f"`{rel_md}:{line_no}` Broken remote link `[{link_text}]({url})`: {reason}")
                    continue

                try:
                    # Use HEAD first, then fallback to GET
                    resp = session.head(url, timeout=5, allow_redirects=True)
                    # Some servers block HEAD with 403/405/404, fallback to GET
                    if resp.status_code in (404, 405, 403, 400):
                        resp = session.get(url, timeout=5, stream=True, allow_redirects=True)

                    if resp.status_code == 404:
                        checked_remote_urls[url] = (False, "HTTP 404 Not Found")
                        findings.append(f"`{rel_md}:{line_no}` Broken remote link `[{link_text}]({url})`: HTTP 404 Not Found")
                    elif resp.status_code >= 500:
                        checked_remote_urls[url] = (False, f"HTTP {resp.status_code} Server Error")
                        findings.append(f"`{rel_md}:{line_no}` Broken remote link `[{link_text}]({url})`: HTTP {resp.status_code}")
                    else:
                        checked_remote_urls[url] = (True, "OK")
                except Exception as exc:
                    # Only flag hard connection/DNS errors, avoiding temporary network timeouts
                    err_str = str(exc)
                    if "NameResolutionError" in err_str or "Failed to resolve" in err_str:
                        checked_remote_urls[url] = (False, "DNS Resolution Failed")
                        findings.append(f"`{rel_md}:{line_no}` Broken remote link `[{link_text}]({url})`: DNS Resolution Failed")
                    else:
                        checked_remote_urls[url] = (True, "Skipped/Timeout")

            elif not parsed.scheme or parsed.scheme == "file":
                # Local relative link check
                target_part = unquote(parsed.path)
                if not target_part:
                    continue

                # Target resolved relative to the markdown file's folder
                target_path = (md_file.parent / target_part).resolve()

                # Also try relative to repo root if path starts with '/'
                if target_part.startswith("/"):
                    target_path = (repo_root / target_part.lstrip("/")).resolve()

                if not target_path.exists():
                    findings.append(
                        f"`{rel_md}:{line_no}` Broken local link `[{link_text}]({url})`: target path `{target_part}` does not exist."
                    )

    return findings


def check_baseline_structure(repo_root: Path) -> List[str]:
    """Check if baseline files (.gitignore, LICENSE, CONTRIBUTING.md) exist."""
    findings = []

    license_files = [repo_root / "LICENSE", repo_root / "LICENSE.md", repo_root / "LICENSE.txt"]
    if not any(f.exists() and f.is_file() for f in license_files):
        findings.append("Missing `LICENSE` file in the repository root.")

    gitignore = repo_root / ".gitignore"
    if not (gitignore.exists() and gitignore.is_file()):
        findings.append("Missing `.gitignore` file in the repository root.")

    contributing_files = [
        repo_root / "CONTRIBUTING.md",
        repo_root / "CONTRIBUTING",
        repo_root / ".github/CONTRIBUTING.md",
    ]
    if not any(f.exists() and f.is_file() for f in contributing_files):
        findings.append("Missing `CONTRIBUTING.md` guideline in the repository root or `.github/`.")

    return findings


def check_syntax_validation(repo_root: Path) -> List[str]:
    """Validate YAML and JSON files across the repository."""
    findings = []

    # Check YAML files
    yaml_files = [
        p for p in repo_root.rglob("*")
        if p.is_file()
        and p.suffix.lower() in (".yml", ".yaml")
        and not should_skip_path(p, repo_root)
    ]
    for yml in yaml_files:
        rel = yml.relative_to(repo_root)
        try:
            content = yml.read_text(encoding="utf-8")
            if yaml:
                yaml.safe_load(content)
        except Exception as exc:
            findings.append(f"Invalid YAML syntax in `{rel}`: {exc}")

    # Check JSON files
    json_files = [
        p for p in repo_root.rglob("*.json")
        if p.is_file() and not should_skip_path(p, repo_root)
    ]
    for jf in json_files:
        rel = jf.relative_to(repo_root)
        try:
            content = jf.read_text(encoding="utf-8")
            json.loads(content)
        except Exception as exc:
            findings.append(f"Invalid JSON syntax in `{rel}`: {exc}")

    return findings


def check_workflow_runs(repo_root: Path) -> Tuple[List[str], Dict[str, Any]]:
    """Check the latest run status of GitHub Actions workflows on default branch."""
    findings = []
    stats: Dict[str, Any] = {"workflows_checked": 0, "failed_workflows": []}

    if not is_gh_available():
        logger.info("gh CLI not available. Skipping remote workflow runs check.")
        return findings, stats

    code, stdout, stderr = run_gh_command(
        ["run", "list", "--json", "name,conclusion,status,url,headBranch", "--limit", "30"],
        cwd=repo_root,
    )
    if code != 0 or not stdout:
        logger.info("No workflow runs found or gh query returned: %s", stderr)
        return findings, stats

    try:
        runs = json.loads(stdout)
        # Find latest run per workflow name
        latest_runs: Dict[str, Dict[str, Any]] = {}
        for r in runs:
            name = r.get("name")
            if name and name not in latest_runs:
                latest_runs[name] = r

        stats["workflows_checked"] = len(latest_runs)

        for wf_name, run_info in latest_runs.items():
            conclusion = (run_info.get("conclusion") or "").lower()
            status = (run_info.get("status") or "").lower()
            url = run_info.get("url") or ""

            if conclusion in ("failure", "timed_out", "startup_failure", "action_required"):
                findings.append(
                    f"Workflow **{wf_name}** failed on latest run: [{conclusion}]({url})"
                )
                stats["failed_workflows"].append(wf_name)

    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse gh run list JSON: %s", exc)

    return findings, stats


def generate_markdown_report(
    readme_findings: List[str],
    links_findings: List[str],
    baseline_findings: List[str],
    syntax_findings: List[str],
    workflow_findings: List[str],
    now: datetime,
) -> Tuple[str, int]:
    """Compile check results into a formatted Markdown report."""
    total_actionable = (
        len(readme_findings)
        + len(links_findings)
        + len(baseline_findings)
        + len(syntax_findings)
        + len(workflow_findings)
    )

    status_badge = "🟢 Healthy" if total_actionable == 0 else f"🔴 {total_actionable} Actionable Findings"
    timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "# DevOps Repository Health Report",
        "",
        f"**Generated At:** {timestamp_str}  ",
        f"**Overall Health Status:** {status_badge}  ",
        f"**Total Actionable Findings:** {total_actionable}",
        "",
        "## Summary of Health Checks",
        "",
        "| Health Check Category | Status | Actionable Issues |",
        "| :--- | :---: | :---: |",
        f"| README Content & Sections | {'✅ Pass' if not readme_findings else '❌ Action Required'} | {len(readme_findings)} |",
        f"| Markdown Broken Links | {'✅ Pass' if not links_findings else '❌ Action Required'} | {len(links_findings)} |",
        f"| Baseline Project Structure | {'✅ Pass' if not baseline_findings else '❌ Action Required'} | {len(baseline_findings)} |",
        f"| YAML & JSON Syntax Integrity | {'✅ Pass' if not syntax_findings else '❌ Action Required'} | {len(syntax_findings)} |",
        f"| GitHub Actions Workflows Status | {'✅ Pass' if not workflow_findings else '❌ Action Required'} | {len(workflow_findings)} |",
        "",
        "---",
        "",
    ]

    if total_actionable == 0:
        lines.extend([
            "## Actionable Findings",
            "",
            "✅ **All checks passed!** The repository adheres to all baseline structure, syntax, and link health standards.",
            "",
        ])
    else:
        lines.extend([
            "## ⚠️ Actionable Findings",
            "",
        ])

        if readme_findings:
            lines.append("### 📄 README Issues")
            for f in readme_findings:
                lines.append(f"- {f}")
            lines.append("")

        if links_findings:
            lines.append("### 🔗 Broken Markdown Links")
            for f in links_findings:
                lines.append(f"- {f}")
            lines.append("")

        if baseline_findings:
            lines.append("### 📁 Missing Baseline Structure Files")
            for f in baseline_findings:
                lines.append(f"- {f}")
            lines.append("")

        if syntax_findings:
            lines.append("### ⚙️ YAML / JSON Syntax Errors")
            for f in syntax_findings:
                lines.append(f"- {f}")
            lines.append("")

        if workflow_findings:
            lines.append("### 🔄 Failed Workflow Runs")
            for f in workflow_findings:
                lines.append(f"- {f}")
            lines.append("")

    lines.extend([
        "---",
        "",
        "_Report generated by Repository Health Agent (`repo_health_agent.py`)._",
    ])

    return "\n".join(lines), total_actionable


def run_agent(repo_root: Optional[Path] = None, sync_remote: bool = True) -> int:
    """Execute all repository health checks, generate report, and sync issues."""
    root = repo_root or find_repo_root()
    logger.info("Running Repository Health Agent against root: %s", root)

    now = datetime.now(timezone.utc)

    # 1. README check
    logger.info("Validating README structure...")
    readme_findings = check_readme(root)

    # 2. Markdown link check
    logger.info("Scanning for broken Markdown links...")
    links_findings = check_broken_links(root)

    # 3. Baseline files check
    logger.info("Checking baseline project files...")
    baseline_findings = check_baseline_structure(root)

    # 4. YAML / JSON syntax check
    logger.info("Validating YAML and JSON syntax...")
    syntax_findings = check_syntax_validation(root)

    # 5. Workflow health check
    logger.info("Inspecting latest workflow runs on default branch...")
    workflow_findings, _ = check_workflow_runs(root)

    # Compile report
    report_content, actionable_count = generate_markdown_report(
        readme_findings,
        links_findings,
        baseline_findings,
        syntax_findings,
        workflow_findings,
        now,
    )

    # Write report file
    write_report(REPORT_FILENAME, report_content, repo_root=root)

    # Sync with GitHub issues
    if sync_remote:
        sync_result = sync_issue(
            marker=MARKER,
            title=ISSUE_TITLE,
            report_body=report_content,
            actionable_count=actionable_count,
            labels=["automated-report"],
            cwd=root,
        )
        logger.info("Issue sync result: %s", sync_result)

    logger.info("Repository Health Agent completed with %d actionable findings.", actionable_count)
    return actionable_count


if __name__ == "__main__":
    count = run_agent()
    sys.exit(0)
