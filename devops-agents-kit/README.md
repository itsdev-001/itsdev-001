# DevOps Automation Kit

[![CI](https://github.com/granth-alpha2/devops-agents-kit/actions/workflows/ci.yml/badge.svg)](.github/workflows/ci.yml)
[![Infra Validation](https://github.com/granth-alpha2/devops-agents-kit/actions/workflows/infra-validation.yml/badge.svg)](.github/workflows/infra-validation.yml)
[![Scheduled Health Check](https://github.com/granth-alpha2/devops-agents-kit/actions/workflows/scheduled-health-check.yml/badge.svg)](.github/workflows/scheduled-health-check.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Two intelligent automation agents and three GitHub Actions workflows that keep this repository's health, CI, and infrastructure configuration honest — with a hard rule against fake activity: **nothing ever gets committed or opened unless it reflects a real, actionable finding.**

---

## 🤖 Agents

### 1. Repository Health Agent
**File:** [`.github/scripts/agents/repo_health_agent.py`](.github/scripts/agents/repo_health_agent.py)

**Automated Checks:**
- **README Integrity:** Ensures `README.md` exists and covers setup, usage, agents, workflows, and licensing.
- **Broken Link Detection:** Recursively scans all `*.md` files for broken local paths and failing remote URLs.
- **Baseline Project Structure:** Enforces standard repository hygiene (`LICENSE`, `.gitignore`, `CONTRIBUTING.md`).
- **Syntax Validation:** Validates that every `*.yml`, `*.yaml`, and `*.json` file in the repo parses without errors.
- **Workflow Health:** Queries the default branch's latest workflow run status via GitHub CLI/API.

**Output:** `reports/repo-health-report.md`. Opens/updates a single tracked GitHub issue (labeled `automated-report`) only when real actionable issues are found, updates that same issue in place on later runs, and auto-closes it once every finding is resolved.

---

### 2. DevOps Security & Dependency Agent
**File:** [`.github/scripts/agents/security_dependency_agent.py`](.github/scripts/agents/security_dependency_agent.py)

**Automated Checks:**
- **Dependency Freshness (Informational):** Inspects `requirements.txt` against PyPI JSON API and `package.json` against npm registry.
- **Docker Hygiene:** Detects `:latest` or unpinned base images, containers running as root (missing `USER`), and unverified remote `ADD` instructions.
- **Kubernetes Hygiene:** Detects `hostNetwork: true`, `privileged: true`, unpinned container image tags, and containers missing CPU/memory limits.
- **Terraform Hygiene:** Scans for public ACLs (`public-read`), overly permissive ingress rules (`0.0.0.0/0`), and unpinned providers.
- **Secret Scanning (Strict Zero-Leakage Redaction):** Regex heuristics for AWS keys, private key blocks, Slack tokens, GitHub tokens, and generic API keys.

**Security Policy on Secret Scanning:**
Matched secret values are **never printed, written to reports, or transmitted to issues**. Only the file path, line number, and pattern name are reported.

**Output:** `reports/security-dependency-report.md`. Opens/updates a tracked GitHub issue when actionable hygiene violations or potential secrets are detected. Dependency version freshness findings are reported informatively in Markdown tables without creating false alarms.

---

### 🛠️ Shared Behavior (Both Agents)
- **Non-Interactive & Zero-Secrets:** Operates seamlessly with GitHub CLI (`gh`) and standard `GITHUB_TOKEN`.
- **Idempotent Issue Sync:** Hidden HTML markers (`<!-- devops-agent:... -->`) prevent duplicate issues and allow seamless auto-reopening and auto-closing.
- **Zero-Noise Commit Engine:** Diff checks ensure commits are created **only** when report contents actually change.

---

## ⚡ Workflows

### `ci.yml` — Continuous Integration
- **Trigger:** `push` to `main`, and every `pull_request`.
- **Permissions:** `contents: read` (Least Privilege).
- **Execution:** Runs Python test suite (`pytest`), validates YAML/JSON syntax, and posts a rich Markdown summary to GitHub Actions Step Summary.

### `infra-validation.yml` — Infrastructure Validation
- **Trigger:** `pull_request` modifying Terraform files (`*.tf`), Dockerfiles (`Dockerfile*`), or Kubernetes manifests (`k8s/**`, `kubernetes/**`, `manifests/**`).
- **Permissions:** `contents: read`.
- **Execution:** Runs `terraform fmt` and `terraform validate`, Dockerfile linting with `hadolint`, and Kubernetes validation with `kubeconform`.

### `scheduled-health-check.yml` — Scheduled DevOps Health Check
- **Trigger:** Daily cron schedule (`0 4 * * *`) and manual trigger (`workflow_dispatch`).
- **Permissions:** `contents: write` (for report commits) + `issues: write` (for issue synchronization).
- **Execution:** Runs both agents, updates reports, and:
  - Commits updated reports **only if content actually changed**.
  - Opens/updates issues **only if** actionable findings exist.
  - Otherwise finishes green with **zero commits and zero issues**.

---

## 🔒 Design Rules

- **Least Privilege:** Each workflow requests only the permissions it needs (`contents: read` for CI/Infra validation; write permissions reserved for the scheduled job).
- **No Secret Exposure:** Strict redaction guarantees no sensitive tokens or keys appear in logs or issue bodies.
- **No Meaningless Commits:** Commits are made only when findings change. Zero contribution-graph spam.
- **Issue Hygiene:** At most one open issue per agent, maintained idempotently and auto-closed upon resolution.

---

## 🚀 Setup & Installation

1. Copy `.github/` (scripts, lib, and workflows) into your repository.
2. In your repository settings, ensure `GITHUB_TOKEN` has read/write permissions for workflows that create issues (Settings → Actions → General → Workflow permissions → **Read and write permissions**).
3. Install script dependencies locally:
   ```bash
   pip install -r .github/scripts/requirements.txt
   ```
4. Run agent scripts locally:
   ```bash
   python .github/scripts/agents/repo_health_agent.py
   python .github/scripts/agents/security_dependency_agent.py
   ```
5. Run the test suite:
   ```bash
   pytest .github/scripts/tests/ -v
   ```

---

## 📖 Usage

### Running Locally
You can run individual agent checks anytime to verify your repository status before pushing:
```bash
# Verify repo structure, links, syntax, and workflows
python .github/scripts/agents/repo_health_agent.py

# Verify Docker, K8s, Terraform hygiene, and dependencies
python .github/scripts/agents/security_dependency_agent.py
```

### GitHub Actions Automation
Once pushed to GitHub, the workflows will run automatically:
- On every pull request to validate code and infrastructure syntax.
- On a scheduled daily cadence to audit repository health and security posture.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE) - see the LICENSE file for details.

Developed with inspiration from [granth-alpha2 (Granth Chauhan)](https://github.com/granth-alpha2).
