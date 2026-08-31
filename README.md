<h1 align="center">Hi there, I'm Dev Singh 👋</h1>
<h3 align="center">🚀 Aspiring DevOps & Cloud Engineer | Linux | Docker | Kubernetes | AWS | Terraform | CI/CD | Python</h3>

<p align="center">
  <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=20&duration=3000&pause=1000&color=38BDF8&center=true&vCenter=true&width=600&lines=Building+Intelligent+DevOps+Systems;Automating+CI%2FCD+Pipelines;Managing+Cloud+Infrastructure+with+Terraform;Containerizing+Apps+with+Docker+%26+K8s;Securing+Cloud+Environments" alt="Typing SVG" />
</p>

<p align="center">
  <img src="https://komarev.com/ghpvc/?username=itsdev-001&label=Profile%20Views&color=0e75b6&style=flat-square" alt="Profile Views" />
  <img src="https://img.shields.io/badge/Focus-DevOps%20%26%20Cloud%20Automation-success?style=flat-square" alt="Focus" />
</p>

---

### 🛠️ Tech Stack & Skills

<p align="center">
  <!-- Cloud & IaC -->
  <img src="https://img.shields.io/badge/AWS-%23FF9900.svg?style=for-the-badge&logo=amazon-web-services&logoColor=white" />
  <img src="https://img.shields.io/badge/Terraform-%235835CC.svg?style=for-the-badge&logo=terraform&logoColor=white" />
  <!-- Containers & Orchestration -->
  <img src="https://img.shields.io/badge/Docker-%230db7ed.svg?style=for-the-badge&logo=docker&logoColor=white" />
  <img src="https://img.shields.io/badge/Kubernetes-%23326ce5.svg?style=for-the-badge&logo=kubernetes&logoColor=white" />
  <!-- CI/CD & Linux -->
  <img src="https://img.shields.io/badge/GitHub_Actions-%232671E5.svg?style=for-the-badge&logo=github-actions&logoColor=white" />
  <img src="https://img.shields.io/badge/Linux-%23FCC624.svg?style=for-the-badge&logo=linux&logoColor=black" />
  <img src="https://img.shields.io/badge/Bash-%23121011.svg?style=for-the-badge&logo=gnu-bash&logoColor=white" />
  <!-- Languages -->
  <img src="https://img.shields.io/badge/Python-%2314354C.svg?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Java-%23ED8B00.svg?style=for-the-badge&logo=openjdk&logoColor=white" />
  <img src="https://img.shields.io/badge/Git-%23F05033.svg?style=for-the-badge&logo=git&logoColor=white" />
</p>

---

# 🤖 DevOps Automation Kit

[![CI](https://img.shields.io/badge/CI-Automated-blue?logo=githubactions)](.github/workflows/ci.yml)
[![Infra Validation](https://img.shields.io/badge/Infra--Validation-Terraform%20|%20Docker%20|%20K8s-orange?logo=terraform)](.github/workflows/infra-validation.yml)
[![Scheduled Health Check](https://img.shields.io/badge/Health--Check-Daily%20Audit-green?logo=github)](.github/workflows/scheduled-health-check.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

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

1. Clone this repository:
   ```bash
   git clone https://github.com/itsdev-001/itsdev-001.git
   cd itsdev-001
   ```
2. In your repository settings on GitHub, ensure `GITHUB_TOKEN` has read/write permissions for workflows that create issues (Settings → Actions → General → Workflow permissions → **Read and write permissions**).
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

---

### 📊 GitHub Statistics

<p align="center">
  <img src="https://github-readme-stats.vercel.app/api?username=itsdev-001&show_icons=true&theme=tokyonight&hide_border=true&count_private=true" width="48%" />
  <img src="https://github-readme-stats.vercel.app/api/top-langs/?username=itsdev-001&layout=compact&theme=tokyonight&hide_border=true" width="48%" />
</p>

<p align="center">
  <img src="https://github-readme-streak-stats.herokuapp.com/?user=itsdev-001&theme=tokyonight&hide_border=true" width="97%" />
</p>

---

## 📄 License

This project is licensed under the [MIT License](LICENSE) - see the LICENSE file for details.

Developed with inspiration from [granth-alpha2 (Granth Chauhan)](https://github.com/granth-alpha2).
