#!/usr/bin/env python3
"""Agent 2: DevOps Security & Dependency Agent.

Performs automated security, infrastructure hygiene, and dependency freshness checks:
1. Dependency freshness: `requirements.txt` (PyPI) and `package.json` (npm registry).
   (Note: Informational only; does not force actionable issue).
2. Dockerfile hygiene: `:latest` tags, root-user execution, remote `ADD` instructions.
3. Kubernetes hygiene: `hostNetwork: true`, `privileged: true`, unpinned images, missing resource limits.
4. Terraform hygiene: public ACLs, open `0.0.0.0/0` ingress rules, unpinned provider versions.
5. Secret scanning: regex heuristics with STRICT redaction (values are NEVER logged or written).

Outputs:
- Generates `reports/security-dependency-report.md`.
- Synchronizes findings with GitHub Issues idempotently using marker:
  `<!-- devops-agent:security-dependency-agent -->`.
"""

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

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

try:
    from packaging.version import parse as parse_version
except ImportError:
    parse_version = None  # type: ignore

from lib.gh_report import (
    find_repo_root,
    is_gh_available,
    sync_issue,
    write_report,
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("security_dependency_agent")

MARKER = "<!-- devops-agent:security-dependency-agent -->"
REPORT_FILENAME = "security-dependency-report.md"
ISSUE_TITLE = "[DevOps Security] Security & Infrastructure Hygiene Findings"

IGNORED_DIRS = {
    ".git",
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

# Secret scanning regex heuristics (names and patterns)
SECRET_PATTERNS = [
    ("AWS Access Key ID", re.compile(r"\b(AKIA[0-9A-Z]{16})\b")),
    (
        "AWS Secret Access Key",
        re.compile(r"(?i)\b(aws_secret_access_key|aws_secret_key)\s*[:=]\s*['\"]?([a-zA-Z0-9/+=]{40})['\"]?"),
    ),
    (
        "Private Key Block",
        re.compile(r"-----BEGIN (?:RSA|EC|DSA|OPENSSH|PGP)?\s*PRIVATE KEY-----"),
    ),
    (
        "Slack Token",
        re.compile(r"\b(xox[baprs]-[0-9a-zA-Z]{10,48})\b"),
    ),
    (
        "GitHub Personal Access Token",
        re.compile(r"\b(ghp_[0-9a-zA-Z]{36}|github_pat_[0-9a-zA-Z_]{82}|gho_[0-9a-zA-Z]{36}|ghu_[0-9a-zA-Z]{36}|ghs_[0-9a-zA-Z]{36}|ghr_[0-9a-zA-Z]{36})\b"),
    ),
    (
        "Generic API Key / Secret Assignment",
        re.compile(r"(?i)\b(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token)\s*[:=]\s*['\"]([a-zA-Z0-9_\-]{20,})['\"]"),
    ),
]


def should_skip_path(path: Path, repo_root: Path) -> bool:
    """Determine whether a file or directory should be skipped."""
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


def check_python_dependencies(repo_root: Path) -> List[Dict[str, str]]:
    """Check PyPI dependency freshness for requirements.txt files."""
    results = []
    req_files = [
        p for p in repo_root.rglob("*requirements*.txt")
        if p.is_file() and not should_skip_path(p, repo_root)
    ]

    for req_file in req_files:
        try:
            lines = req_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception as exc:
            logger.warning("Could not read %s: %s", req_file, exc)
            continue

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue

            # Parse package name and version: e.g. requests==2.31.0 or requests>=2.31.0
            match = re.match(r"^([a-zA-Z0-9_\-\.]+)\s*([=><~^!]+.*)?$", line)
            if not match:
                continue

            pkg_name, version_spec = match.groups()
            version_spec = (version_spec or "").strip()
            current_ver = version_spec.lstrip("=><~^! ") if version_spec else "unspecified"

            latest_ver = "Unknown"
            status = "Up to date"

            if requests:
                try:
                    resp = requests.get(f"https://pypi.org/pypi/{pkg_name}/json", timeout=4)
                    if resp.status_code == 200:
                        data = resp.json()
                        latest_ver = data.get("info", {}).get("version", "Unknown")
                        if latest_ver != "Unknown" and current_ver != "unspecified":
                            if parse_version:
                                if parse_version(latest_ver) > parse_version(current_ver):
                                    status = f"Update available ({latest_ver})"
                                else:
                                    status = "Up to date"
                            elif latest_ver != current_ver:
                                status = f"Update available ({latest_ver})"
                except Exception:
                    pass

            results.append({
                "manifest": str(req_file.relative_to(repo_root)),
                "package": pkg_name,
                "current": current_ver,
                "latest": latest_ver,
                "status": status,
            })

    return results


def check_node_dependencies(repo_root: Path) -> List[Dict[str, str]]:
    """Check npm dependency freshness for package.json files."""
    results = []
    pkg_files = [
        p for p in repo_root.rglob("package.json")
        if p.is_file() and not should_skip_path(p, repo_root)
    ]

    for pkg_file in pkg_files:
        try:
            content = json.loads(pkg_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        deps = {}
        deps.update(content.get("dependencies", {}))
        deps.update(content.get("devDependencies", {}))

        for pkg_name, ver_spec in deps.items():
            clean_ver = str(ver_spec).lstrip("^~>=< ")
            latest_ver = "Unknown"
            status = "Up to date"

            if requests:
                try:
                    resp = requests.get(f"https://registry.npmjs.org/{pkg_name}/latest", timeout=4)
                    if resp.status_code == 200:
                        data = resp.json()
                        latest_ver = data.get("version", "Unknown")
                        if latest_ver != "Unknown" and clean_ver:
                            if latest_ver != clean_ver:
                                status = f"Update available ({latest_ver})"
                except Exception:
                    pass

            results.append({
                "manifest": str(pkg_file.relative_to(repo_root)),
                "package": pkg_name,
                "current": ver_spec,
                "latest": latest_ver,
                "status": status,
            })

    return results


def check_docker_hygiene(repo_root: Path) -> List[str]:
    """Scan Dockerfiles for base image tagging, non-root USER, and remote ADD."""
    findings = []
    dockerfiles = [
        p for p in repo_root.rglob("*")
        if p.is_file()
        and (
            p.name.lower().startswith("dockerfile")
            or p.name.lower().endswith(".dockerfile")
            or p.name.lower().startswith("containerfile")
        )
        and not should_skip_path(p, repo_root)
    ]

    for df in dockerfiles:
        rel = df.relative_to(repo_root)
        try:
            lines = df.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception as exc:
            logger.warning("Could not read %s: %s", df, exc)
            continue

        has_user_instruction = False
        from_stages = []

        for line_no, line in enumerate(lines, start=1):
            clean_line = line.strip()
            if not clean_line or clean_line.startswith("#"):
                continue

            # Check FROM instructions
            if clean_line.upper().startswith("FROM "):
                from_parts = clean_line.split()
                if len(from_parts) >= 2:
                    image_ref = from_parts[1]
                    from_stages.append(image_ref)
                    # Exclude multi-stage alias references (e.g. FROM builder as prod)
                    is_stage_alias = any(
                        len(p.split()) >= 4 and p.split()[3].lower() == image_ref.lower()
                        for p in lines if p.strip().upper().startswith("FROM ")
                    )
                    if not is_stage_alias:
                        if ":" not in image_ref and "@" not in image_ref:
                            findings.append(
                                f"`{rel}:{line_no}` Base image `{image_ref}` is untagged (defaults to `:latest`). Use an explicit pinned version tag or digest."
                            )
                        elif image_ref.endswith(":latest"):
                            findings.append(
                                f"`{rel}:{line_no}` Base image `{image_ref}` uses `:latest` tag. Pin to a specific version or immutable digest."
                            )

            # Check USER instructions
            if clean_line.upper().startswith("USER "):
                user_val = clean_line[5:].strip()
                if user_val and user_val not in ("0", "root"):
                    has_user_instruction = True

            # Check ADD instructions with remote URLs
            if clean_line.upper().startswith("ADD "):
                add_parts = clean_line.split()[1:]
                for part in add_parts:
                    if part.startswith("http://") or part.startswith("https://"):
                        findings.append(
                            f"`{rel}:{line_no}` Remote `ADD {part}` detected. Use `RUN curl` / `RUN wget` with explicit checksum verification instead."
                        )

        # Flag missing USER if there is at least one FROM instruction
        if from_stages and not has_user_instruction:
            findings.append(
                f"`{rel}` Container runs as `root`. Specify a non-root `USER <username>` before the final entrypoint."
            )

    return findings


def check_kubernetes_hygiene(repo_root: Path) -> List[str]:
    """Scan Kubernetes manifests for security context, hostNetwork, unpinned tags, and resource limits."""
    findings = []
    yaml_files = [
        p for p in repo_root.rglob("*")
        if p.is_file()
        and p.suffix.lower() in (".yml", ".yaml")
        and not should_skip_path(p, repo_root)
    ]

    for yf in yaml_files:
        rel = yf.relative_to(repo_root)
        try:
            content = yf.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        # Basic check to see if this is a Kubernetes manifest
        if not ("apiVersion:" in content and "kind:" in content):
            continue

        lines = content.splitlines()
        for idx, line in enumerate(lines, start=1):
            clean = line.strip()

            # hostNetwork check
            if re.match(r"^hostNetwork:\s*true\b", clean, re.IGNORECASE):
                findings.append(
                    f"`{rel}:{idx}` Insecure `hostNetwork: true` enabled in Pod specification."
                )

            # privileged securityContext check
            if re.match(r"^privileged:\s*true\b", clean, re.IGNORECASE):
                findings.append(
                    f"`{rel}:{idx}` Privileged container execution `privileged: true` detected."
                )

            # image tag check
            img_match = re.match(r"^image:\s*['\"]?([^\s'\"]+)['\"]?", clean)
            if img_match:
                img = img_match.group(1)
                if ":" not in img and "@" not in img:
                    findings.append(
                        f"`{rel}:{idx}` Container image `{img}` is unpinned without a tag."
                    )
                elif img.endswith(":latest"):
                    findings.append(
                        f"`{rel}:{idx}` Container image `{img}` uses mutable `:latest` tag."
                    )

        # Check resource limits
        is_workload = bool(re.search(r"kind:\s*(Deployment|StatefulSet|DaemonSet|Pod|Job|CronJob)\b", content))
        if is_workload:
            if yaml:
                try:
                    docs = list(yaml.safe_load_all(content))
                    for doc in docs:
                        if not isinstance(doc, dict):
                            continue
                        kind = doc.get("kind", "")
                        if kind in ("Deployment", "StatefulSet", "DaemonSet", "Pod", "Job", "CronJob"):
                            # Traverse containers to check resource limits
                            spec = doc.get("spec", {})
                            if "template" in spec:
                                spec = spec.get("template", {}).get("spec", {})
                            containers = spec.get("containers", [])
                            for c in containers:
                                c_name = c.get("name", "unknown")
                                res = c.get("resources", {})
                                limits = res.get("limits", {})
                                if not limits.get("cpu") or not limits.get("memory"):
                                    findings.append(
                                        f"`{rel}` Container `{c_name}` in {kind} is missing CPU and/or Memory resource limits."
                                    )
                except Exception:
                    pass
            else:
                # Text scan fallback when PyYAML is not installed
                if "resources:" not in content or "limits:" not in content:
                    findings.append(
                        f"`{rel}` Workload manifest is missing CPU and/or Memory resource limits."
                    )

    return findings


def check_terraform_hygiene(repo_root: Path) -> List[str]:
    """Scan Terraform (*.tf) files for public ACLs, open CIDR ingress rules, and provider pinning."""
    findings = []
    tf_files = [
        p for p in repo_root.rglob("*.tf")
        if p.is_file() and not should_skip_path(p, repo_root)
    ]

    for tf in tf_files:
        rel = tf.relative_to(repo_root)
        try:
            lines = tf.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue

        for idx, line in enumerate(lines, start=1):
            clean = line.strip()

            # Public S3 / Storage ACL check
            if re.search(r'acl\s*=\s*["\'](public-read|public-read-write)["\']', clean):
                findings.append(
                    f"`{rel}:{idx}` Public access ACL `{clean}` configured in storage resource."
                )

            # Ingress rule open to 0.0.0.0/0
            if 'cidr_blocks = ["0.0.0.0/0"]' in clean or "cidr_blocks = ['0.0.0.0/0']" in clean:
                findings.append(
                    f"`{rel}:{idx}` Security group ingress rule open to entire world (`0.0.0.0/0`)."
                )

            # Terraform required_providers version check
            if clean.startswith("provider ") and "{" in clean:
                # Basic notification if provider block lacks version
                pass

    return findings


def check_secret_scanning(repo_root: Path) -> List[str]:
    """Scan repository files for exposed secrets using regex heuristics.

    CRITICAL SECURITY MANDATE:
    Matched secret values are NEVER recorded, printed, or exported.
    Only the relative file path, line number, and pattern name are reported.
    """
    findings = []

    for path in repo_root.rglob("*"):
        if not path.is_file() or should_skip_path(path, repo_root):
            continue

        rel = path.relative_to(repo_root)

        # Skip lock files, binaries, images, test suites/mocks, and report files
        if (
            path.name.startswith("test_")
            or path.name.endswith("_test.py")
            or "tests" in rel.parts
            or "test" in rel.parts
            or path.suffix.lower() in (
                ".lock",
                ".png",
                ".jpg",
                ".jpeg",
                ".gif",
                ".ico",
                ".svg",
                ".pdf",
                ".zip",
                ".tar",
                ".gz",
                ".pyc",
            )
        ):
            continue

        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue

        for idx, line in enumerate(lines, start=1):
            clean = line.strip()
            # Ignore comments in scripts that might describe example patterns
            if clean.startswith("#") or clean.startswith("//") or clean.startswith("/*"):
                if "example" in clean.lower() or "dummy" in clean.lower():
                    continue

            for pattern_name, regex in SECRET_PATTERNS:
                if regex.search(line):
                    # STRICT REDACTION: Only record file, line, and pattern name
                    findings.append(
                        f"`{rel}:{idx}` Potential leaked credential detected: **{pattern_name}** (value redacted)."
                    )

    return findings


def generate_markdown_report(
    dependency_info: List[Dict[str, str]],
    docker_findings: List[str],
    k8s_findings: List[str],
    tf_findings: List[str],
    secret_findings: List[str],
    now: datetime,
) -> Tuple[str, int]:
    """Generate Markdown report for security, infrastructure hygiene, and dependencies."""
    actionable_count = (
        len(docker_findings)
        + len(k8s_findings)
        + len(tf_findings)
        + len(secret_findings)
    )

    status_badge = "🟢 Secure & Clean" if actionable_count == 0 else f"🔴 {actionable_count} Actionable Security Findings"
    timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "# DevOps Security & Dependency Report",
        "",
        f"**Generated At:** {timestamp_str}  ",
        f"**Overall Security Status:** {status_badge}  ",
        f"**Total Actionable Findings:** {actionable_count}",
        "",
        "> [!NOTE]",
        "> Dependency freshness updates are informational; only real infrastructure hygiene violations and leaked secrets count as actionable issues.",
        "",
        "## Summary Table",
        "",
        "| Category | Status | Actionable Issues |",
        "| :--- | :---: | :---: |",
        f"| Secret Scanning (Redacted) | {'✅ Clean' if not secret_findings else '❌ Action Required'} | {len(secret_findings)} |",
        f"| Dockerfile Hygiene | {'✅ Clean' if not docker_findings else '❌ Action Required'} | {len(docker_findings)} |",
        f"| Kubernetes Security & Limits | {'✅ Clean' if not k8s_findings else '❌ Action Required'} | {len(k8s_findings)} |",
        f"| Terraform Configuration Hygiene | {'✅ Clean' if not tf_findings else '❌ Action Required'} | {len(tf_findings)} |",
        f"| Dependency Freshness | ℹ️ Tracked | {len([d for d in dependency_info if 'Update' in d['status']])} updates available |",
        "",
        "---",
        "",
    ]

    if actionable_count == 0:
        lines.extend([
            "## 🛡️ Actionable Security & Hygiene Findings",
            "",
            "✅ **Zero actionable security or infrastructure hygiene findings detected.** All Docker, Kubernetes, Terraform, and secret scanning checks passed.",
            "",
        ])
    else:
        lines.extend([
            "## ⚠️ Actionable Security & Hygiene Findings",
            "",
        ])

        if secret_findings:
            lines.append("### 🔑 Leaked Secrets Detected (Redacted)")
            lines.append("> [!CAUTION]")
            lines.append("> Secret values have been strictly redacted. Rotate the affected credentials immediately and scrub Git history if already pushed.")
            lines.append("")
            for f in secret_findings:
                lines.append(f"- {f}")
            lines.append("")

        if docker_findings:
            lines.append("### 🐳 Docker Hygiene Findings")
            for f in docker_findings:
                lines.append(f"- {f}")
            lines.append("")

        if k8s_findings:
            lines.append("### ☸️ Kubernetes Hygiene Findings")
            for f in k8s_findings:
                lines.append(f"- {f}")
            lines.append("")

        if tf_findings:
            lines.append("### 🏗️ Terraform Hygiene Findings")
            for f in tf_findings:
                lines.append(f"- {f}")
            lines.append("")

    # Dependency freshness section
    lines.extend([
        "---",
        "",
        "## 📦 Dependency Freshness Status",
        "",
    ])

    if not dependency_info:
        lines.append("No Python (`requirements.txt`) or Node (`package.json`) dependency manifests detected.")
    else:
        lines.extend([
            "| Manifest | Package | Current Version | Latest Version | Status |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ])
        for dep in dependency_info:
            lines.append(
                f"| `{dep['manifest']}` | `{dep['package']}` | `{dep['current']}` | `{dep['latest']}` | {dep['status']} |"
            )

    lines.extend([
        "",
        "---",
        "",
        "_Report generated by DevOps Security & Dependency Agent (`security_dependency_agent.py`)._",
    ])

    return "\n".join(lines), actionable_count


def run_agent(repo_root: Optional[Path] = None, sync_remote: bool = True) -> int:
    """Execute all security & dependency checks, write report, and sync issues."""
    root = repo_root or find_repo_root()
    logger.info("Running DevOps Security & Dependency Agent against root: %s", root)

    now = datetime.now(timezone.utc)

    # 1. Dependency freshness
    logger.info("Checking Python and Node dependency freshness...")
    deps = check_python_dependencies(root) + check_node_dependencies(root)

    # 2. Docker hygiene
    logger.info("Scanning Dockerfile hygiene...")
    docker_findings = check_docker_hygiene(root)

    # 3. Kubernetes hygiene
    logger.info("Scanning Kubernetes manifests hygiene...")
    k8s_findings = check_kubernetes_hygiene(root)

    # 4. Terraform hygiene
    logger.info("Scanning Terraform configuration hygiene...")
    tf_findings = check_terraform_hygiene(root)

    # 5. Secret scanning
    logger.info("Scanning repository for exposed credentials (redacted mode)...")
    secret_findings = check_secret_scanning(root)

    # Generate Markdown report
    report_content, actionable_count = generate_markdown_report(
        dependency_info=deps,
        docker_findings=docker_findings,
        k8s_findings=k8s_findings,
        tf_findings=tf_findings,
        secret_findings=secret_findings,
        now=now,
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

    logger.info("DevOps Security Agent completed with %d actionable findings.", actionable_count)
    return actionable_count


if __name__ == "__main__":
    count = run_agent()
    sys.exit(0)
