"""Unit tests for Agent 2: DevOps Security & Dependency Agent."""

from pathlib import Path
from agents.security_dependency_agent import (
    check_docker_hygiene,
    check_kubernetes_hygiene,
    check_secret_scanning,
    check_terraform_hygiene,
    generate_markdown_report,
)
from datetime import datetime, timezone


def test_docker_hygiene_violations(tmp_path: Path):
    df = tmp_path / "Dockerfile"
    df.write_text(
        "FROM python:latest\n"
        "ADD https://example.org/binary /app/bin\n"
        "CMD [\"python\", \"app.py\"]\n",
        encoding="utf-8",
    )
    findings = check_docker_hygiene(tmp_path)
    # Should catch :latest, remote ADD, and missing USER (running as root)
    assert len(findings) >= 3
    assert any("uses `:latest` tag" in f for f in findings)
    assert any("Remote `ADD" in f for f in findings)
    assert any("Container runs as `root`" in f for f in findings)


def test_docker_hygiene_clean(tmp_path: Path):
    df = tmp_path / "Dockerfile"
    df.write_text(
        "FROM python:3.11.8-slim\n"
        "WORKDIR /app\n"
        "RUN useradd -m appuser\n"
        "USER appuser\n"
        "CMD [\"python\", \"app.py\"]\n",
        encoding="utf-8",
    )
    findings = check_docker_hygiene(tmp_path)
    assert len(findings) == 0


def test_kubernetes_hygiene_violations(tmp_path: Path):
    manifest = tmp_path / "deployment.yaml"
    manifest.write_text(
        "apiVersion: apps/v1\n"
        "kind: Deployment\n"
        "metadata:\n"
        "  name: nginx\n"
        "spec:\n"
        "  template:\n"
        "    spec:\n"
        "      hostNetwork: true\n"
        "      containers:\n"
        "      - name: nginx\n"
        "        image: nginx:latest\n"
        "        securityContext:\n"
        "          privileged: true\n",
        encoding="utf-8",
    )
    findings = check_kubernetes_hygiene(tmp_path)
    assert any("hostNetwork: true" in f for f in findings)
    assert any("privileged: true" in f for f in findings)
    assert any("mutable `:latest` tag" in f for f in findings)
    assert any("missing CPU and/or Memory resource limits" in f for f in findings)


def test_terraform_hygiene_violations(tmp_path: Path):
    tf = tmp_path / "main.tf"
    tf.write_text(
        'resource "aws_s3_bucket" "b" {\n'
        '  bucket = "my-bucket"\n'
        '  acl    = "public-read"\n'
        '}\n'
        'resource "aws_security_group_rule" "ingress" {\n'
        '  type        = "ingress"\n'
        '  cidr_blocks = ["0.0.0.0/0"]\n'
        '}\n',
        encoding="utf-8",
    )
    findings = check_terraform_hygiene(tmp_path)
    assert any("Public access ACL" in f for f in findings)
    assert any("open to entire world (`0.0.0.0/0`)" in f for f in findings)


def test_secret_scanning_with_strict_redaction(tmp_path: Path):
    # Create file with test secret patterns
    secret_val_aws = "AKIAIOSFODNN7EXAMPLE"
    secret_file = tmp_path / "config.py"
    secret_file.write_text(
        f"AWS_KEY = '{secret_val_aws}'\n",
        encoding="utf-8",
    )

    findings = check_secret_scanning(tmp_path)
    assert len(findings) == 1
    assert "AWS Access Key ID" in findings[0]
    assert "value redacted" in findings[0]
    # STRICT REDACTION VERIFICATION: The raw secret value must NEVER be in findings text
    assert secret_val_aws not in findings[0]


def test_generate_markdown_report_clean():
    now = datetime.now(timezone.utc)
    report, actionable = generate_markdown_report([], [], [], [], [], now)
    assert actionable == 0
    assert "🟢 Secure & Clean" in report
    assert "Zero actionable security" in report

