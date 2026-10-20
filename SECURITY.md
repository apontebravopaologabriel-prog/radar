# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Security Architecture & Threat Model

Radar is designed as a **local-first, single-user** career intelligence tool:
- **Zero Cloud Persistence:** The primary database (`radar.db`), user profiles (`cv_master.json`), photos, and cached jobs are stored solely on your local filesystem under strict file permissions (`0600`/`0700` on POSIX systems).
- **Credentials:** LLM API keys are stored in the OS credential manager (`keyring`) or in a `0600` private file (`secrets.json`). They are never stored in the database or transmitted to any server other than your chosen LLM provider.
- **SSRF Protection:** Outbound requests (such as URL verification and single job imports) are strictly validated against private IP ranges, loopback addresses, and cloud metadata endpoints (`ensure_public_http_url`).
- **Network Boundaries:** By default, the API binds only to loopback (`127.0.0.1`) and enforces strict `Host` and `Origin` headers to protect against DNS rebinding and cross-origin attacks.
- **No Automated Application Submission:** Radar intentionally does not provide automated application submission or messaging tools to prevent unintended actions or violation of platform policies.

For a comprehensive breakdown of security boundaries, refer to [docs/security.md](docs/security.md).

## Reporting a Vulnerability

If you discover a security vulnerability in Radar, please report it responsibly:

1. **GitHub Security Advisory:** Use the "Report a vulnerability" button in the **Security** tab of the GitHub repository.
2. Please provide:
   - A description of the vulnerability and its potential impact.
   - Reproduction steps or a minimal proof of concept (PoC).
   - Any recommended remediation steps.

We appreciate your efforts to responsibly disclose findings and will acknowledge receipt and work promptly on a patch.
