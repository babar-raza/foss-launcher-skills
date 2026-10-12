# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **GitHub Issues**: Open a security advisory via GitHub's private vulnerability reporting
2. **Email**: Contact the repository maintainer directly

Please include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact assessment

We aim to acknowledge reports within 48 hours and provide a fix within 7 days for critical issues.

## Security Scanning

This project employs automated security scanning in CI:

- **SAST (Static Analysis)**: [bandit](https://bandit.readthedocs.io/) scans all Python code in `scripts/` for HIGH severity security issues. See [`scripts/ci/checks/check_sast_bandit.py`](scripts/ci/checks/check_sast_bandit.py).
- **Dependency Vulnerability Scanning**: [pip-audit](https://pypi.org/project/pip-audit/) checks all installed dependencies against known vulnerability databases. See [`scripts/ci/checks/check_dependency_audit.py`](scripts/ci/checks/check_dependency_audit.py).
- **Secrets Detection**: [`scripts/ci/checks/check_metrics_no_secrets.py`](scripts/ci/checks/check_metrics_no_secrets.py) scans for hardcoded credentials and API keys.

Security scans run in both GitHub Actions (`.github/workflows/pipeline-tests.yml`) and GitLab CI (`.gitlab-ci.yml`).

## Path Guard

The project enforces write-path restrictions via `scripts/path_guard.py` (S-01), preventing unauthorized writes to governance files (`AGENTS.md`, `CLAUDE.md`), configuration directories (`themes/`, `layouts/`, `configs/`), and skill definitions (`skills/`).

## Responsible Disclosure

We follow responsible disclosure practices. Please allow us reasonable time to address reported vulnerabilities before public disclosure.
