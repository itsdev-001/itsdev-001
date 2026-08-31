# Contributing to DevOps Automation Kit

Thank you for your interest in contributing to **devops-agents-kit**! This toolkit is built to keep repository health, CI pipelines, and infrastructure configurations honest, secure, and clean.

## Core Design Principles

When contributing or extending agents, adhere to our strict design rules:

1. **Zero Fake Activity**: Nothing is ever committed or opened unless it reflects a real, actionable finding.
2. **Least Privilege**: Workflows declare only the exact GitHub Actions permissions they require (`contents: read` for validation; `contents: write` + `issues: write` only for scheduled health updates).
3. **Strict Zero-Leakage Credential Security**: Matched secret values are never printed to logs, saved in reports, or pushed to GitHub issues.
4. **No Meaningless Commits**: The health check workflow diffs the generated reports and skips the commit entirely if nothing changed.
5. **Issue Hygiene**: At most one tracked issue per agent at a time, updated in place via HTML marker tags and auto-closed when resolved.

---

## Local Development & Testing

### 1. Prerequisites
- Python 3.10+
- `git`
- GitHub CLI (`gh`) (optional for local mock testing)

### 2. Install Dependencies
```bash
pip install -r .github/scripts/requirements.txt
```

### 3. Run Test Suite
```bash
pytest .github/scripts/tests/ -v
```

### 4. Run Agents Locally
```bash
# Agent 1: Repository Health
python .github/scripts/agents/repo_health_agent.py

# Agent 2: Security & Dependencies
python .github/scripts/agents/security_dependency_agent.py
```

Generated reports will be placed in `reports/repo-health-report.md` and `reports/security-dependency-report.md`.

---

## Adding New Checks

### Adding a check to Agent 1 (`repo_health_agent.py`)
- Implement a check function returning `List[str]` of actionable findings.
- If no issue is found, return an empty list `[]`.
- Include unit tests in `.github/scripts/tests/test_repo_health_agent.py`.

### Adding a check to Agent 2 (`security_dependency_agent.py`)
- Infrastructure hygiene (Docker/K8s/Terraform) and secret leaks are **actionable**.
- Dependency version notices are **informational** and added to the dependency table without incrementing actionable issue counts.
- Always redact any secret pattern match.
- Include unit tests in `.github/scripts/tests/test_security_dependency_agent.py`.

---

## Submitting Pull Requests

1. Fork the repository and create a feature branch (`git checkout -b feat/my-new-check`).
2. Verify all tests pass locally.
3. Ensure YAML and JSON files are formatted and valid.
4. Submit a Pull Request targeting `main`.

