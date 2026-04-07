# Dependency Security Audit — Are-Self

**Audit Date:** April 5, 2026
**Scope:** All Python packages in `requirements.txt`
**Method:** Cross-referenced against NVD, GitHub Security Advisories, OSV.dev, and Snyk databases
**Total Packages:** 43

Are-Self takes supply chain security seriously. This document catalogs every Python dependency, its known
vulnerabilities, and our remediation status. We publish this openly because transparency is the foundation
of trust in open-source software.

## Critical Findings

### Django (>=6.0) — PATCH REQUIRED

| CVE | Severity | Description | Fixed In |
|-----|----------|-------------|----------|
| CVE-2025-64459 | **CRITICAL (9.1)** | SQL injection via `QuerySet.filter()`, `exclude()`, `get()` — attackers can inject `_connector` and `_negated` parameters | Django 6.0.2+ |
| CVE-2025-14550 | **HIGH** | ASGIRequest header DoS via duplicate headers — causes resource exhaustion | Django 6.0.2+ |

**Status:** Update to Django >=6.0.2. Are-Self's install script should pin this.

### Redis (>=5.0) — INFRASTRUCTURE UPDATE REQUIRED

| CVE | Severity | Description | Fixed In |
|-----|----------|-------------|----------|
| CVE-2025-49844 | **CRITICAL (10.0)** | Remote Code Execution via Use-After-Free in Lua scripting engine. Existed for 13 years. | Redis 7.22.2-20+ |
| CVE-2025-62507 | **HIGH (8.8)** | Stack buffer overflow via XACKDEL command | Redis 8.3.2+ |

**Status:** This affects the Redis *server*, not the Python `redis` client library. Are-Self uses Redis
via Docker. Update the Docker Compose Redis image to a patched version. Are-Self does not use Redis Lua
scripting, but the RCE is exploitable if Redis is exposed to untrusted networks. The default Docker
configuration binds Redis to localhost only — this is correct and should not be changed.

### LiteLLM — SUPPLY CHAIN INCIDENT

| CVE | Severity | Description | Fixed In |
|-----|----------|-------------|----------|
| Supply chain attack (March 2026) | **CRITICAL** | Versions 1.82.7 and 1.82.8 contained malicious code that stole cloud credentials, SSH keys, and Kubernetes secrets | Versions after 1.82.8 |
| CVE-2024-6825 | **HIGH** | Remote code execution via `post_call_rules` callback | Patched in later versions |
| CVE-2024-8984 | **HIGH** | Denial of Service via multipart boundary manipulation | Patched in later versions |

**Status:** LiteLLM is Are-Self's LLM routing layer. We use it to talk to Ollama (local) and OpenRouter
(cloud failover). The supply chain compromise was real and serious. **Pin LiteLLM to a verified-safe
version in requirements.txt.** Verify the SHA256 hash of the installed package. Are-Self's default
configuration (Ollama-only, no cloud) limits exposure — stolen credentials only matter if you've configured
cloud API keys.

**Recommendation:** Consider vendoring LiteLLM or pinning with hash verification (`pip install litellm==X.Y.Z --hash=sha256:...`).

## High Severity Findings

### Playwright — UPDATE REQUIRED

| CVE | Severity | Description | Fixed In |
|-----|----------|-------------|----------|
| CVE-2025-59288 | **HIGH (8.8)** | SSL certificate validation bypass in browser downloads (uses `curl -k`) | 1.55.1+ |
| CVE-2025-9611 | **HIGH** | DNS rebinding attack via MCP server | MCP 0.0.40+ |
| CVE-2026-2441 | **CRITICAL** | Actively exploited Chromium use-after-free in CSS handling | Chromium 145.0.7632.75+ |

**Status:** Playwright is used for browser automation tools in the Parietal Lobe. Update to latest.
Playwright is a dev/tool dependency — not required for core Are-Self operation.

### Asgiref — PATCHED VIA DJANGO UPDATE

| CVE | Severity | Description | Fixed In |
|-----|----------|-------------|----------|
| CVE-2025-14550 | **HIGH** | Resource exhaustion via duplicate HTTP headers in WsgiToAsgi adapter | Updated asgiref with `duplicate_header_limit` parameter |

**Status:** Resolved by updating Django to 6.0.2+ (pulls patched asgiref).

### Aiosmtpd — UPDATE RECOMMENDED

| CVE | Severity | Description | Fixed In |
|-----|----------|-------------|----------|
| CVE-2024-27305 | **MEDIUM (5.3)** | SMTP smuggling — spoofed sender addresses | 1.4.5+ |
| CVE-2024-34083 | **MEDIUM** | STARTTLS unencrypted command injection (MitM risk) | 1.4.6+ |

**Status:** Aiosmtpd is not used in Are-Self's core operation. If it can be removed from requirements,
remove it. Otherwise update to >=1.4.6.

## Medium Severity Findings

### Pydantic

| CVE | Severity | Description | Fixed In |
|-----|----------|-------------|----------|
| CVE-2024-3772 | **MEDIUM (5.9)** | ReDoS via email validation | 2.4.0+ |

**Status:** If using latest Pydantic (v2.x), this is already patched.

### Django REST Framework

| CVE | Severity | Description | Fixed In |
|-----|----------|-------------|----------|
| CVE-2024-21520 | **MEDIUM** | XSS in `break_long_headers` filter | 3.15.2+ |

**Status:** Update to DRF >=3.15.2. Pin in requirements.

### Pytest

| CVE | Severity | Description | Fixed In |
|-----|----------|-------------|----------|
| CVE-2025-71176 | **MEDIUM (6.8)** | Temporary directory privilege escalation on UNIX | 9.0.3+ |

**Status:** Dev-only dependency. Update to latest.

### Ruff

| CVE | Severity | Description | Fixed In |
|-----|----------|-------------|----------|
| CVE-2025-4574 | **MEDIUM** | Double free in crossbeam-channel dependency | 0.11.5+ |

**Status:** Dev-only dependency. Update to latest.

### Django-Celery-Results (>=2.5)

| CVE | Severity | Description | Fixed In |
|-----|----------|-------------|----------|
| CVE-2020-17495 | **HIGH (7.5)** | Stores sensitive information in cleartext | 2.4.0+ |

**Status:** Version >=2.5 specified in requirements is NOT affected. No action needed.

### IPython (>=8.12)

| CVE | Severity | Description | Fixed In |
|-----|----------|-------------|----------|
| CVE-2024-43805 | **MEDIUM (6.1)** | Jupyter notebook markdown code execution | Updated versions |
| CVE-2025-53000 | **HIGH** | Jupyter nbconvert arbitrary code execution | Updated versions |

**Status:** Dev-only dependency (interactive shell). Update to latest. Not used in production.

## No Known Vulnerabilities

The following packages have no known CVEs as of this audit date:

| Package | Version | Role in Are-Self |
|---------|---------|-----------------|
| celery | >=5.3 | Task queue (PNS heartbeat, spike execution) |
| channels | >=4.0 | WebSocket support (Synaptic Cleft) |
| daphne | >=4.0 | ASGI server |
| channels-redis | latest | WebSocket channel layer |
| django-celery-beat | latest | Periodic task scheduler (PNS metronome) |
| psycopg2-binary | >=2.9.9 | PostgreSQL adapter |
| pgvector | >=0.3.2 | Vector embeddings (Hippocampus) |
| django-filter | latest | API query filtering |
| django-cors-headers | latest | CORS middleware |
| django-htmx | >=1.17 | Frontend interactivity (legacy, candidate for removal) |
| django-extensions | >=3.2 | Admin utilities |
| requests | >=2.31 | HTTP client |
| scapy | >=2.5 | Network scanning (PNS auto-discovery) |
| psutil | >=5.9 | System/process management |
| tenacity | latest | Retry logic |
| html2text | latest | HTML to text conversion |
| Markdown | >=3.10 | Markdown rendering |
| aiofiles | latest | Async file I/O |
| watchfiles | >=1.1.1 | File watching |
| colorlog | >=6.7 | Console output formatting |
| pydantic | latest | Data validation (patched if latest) |
| piper-tts | latest | Text-to-speech (local, no GPU) |
| isort | >=7.0.0 | Import sorting (dev only) |
| yapf | >=0.43.0 | Code formatting (dev only) |
| pytest-django | >=4.11.1 | Django test runner (dev only) |
| pytest-asyncio | latest | Async test support (dev only) |
| coverage | latest | Code coverage (dev only) |
| celery-types | >=0.24.0 | Type stubs (dev only) |
| django-stubs | >=5.2.8 | Type stubs (dev only) |
| djangorestframework-stubs | latest | Type stubs (dev only) |
| django-rest-framework-mcp | latest | MCP integration for DRF |

## Deprecated / Unmaintained Packages

| Package | Status | Recommendation |
|---------|--------|---------------|
| **pygtail** | Deprecated (noted in requirements.txt) | Remove. Not imported anywhere in production code. |
| **piper-tts** | Repository archived Oct 2025 | Monitor. Functional but no longer receiving updates. Consider alternatives if security issues emerge. |
| **django-htmx** | Active, but Are-Self migrated to React | Candidate for removal. Listed in TASKS.md as deprecated. |
| **scapy** | Active, but may be unused | Verify import usage. Listed in TASKS.md as potentially unused. |
| **yapf** | Active, but Are-Self uses Ruff | Redundant with Ruff. Candidate for removal. |

## Recommended Actions for Release

### Before Tuesday (Ship-Blocking)

1. **Pin Django to >=6.0.2** in requirements.txt
2. **Pin LiteLLM to a verified-safe version** with hash
3. **Update Docker Compose Redis image** to patched version
4. **Pin DRF to >=3.15.2**
5. **Remove pygtail** from requirements.txt

### Soon After Release

6. Remove django-htmx, scapy, yapf if confirmed unused
7. Update Playwright to >=1.55.1
8. Update aiosmtpd to >=1.4.6 or remove if unused
9. Separate dev dependencies into `requirements-dev.txt`
10. Add `pip-audit` to CI pipeline

### Ongoing

11. Run `pip-audit` monthly or integrate into GitHub Actions
12. Subscribe to Django security mailing list
13. Monitor LiteLLM releases closely given supply chain history
14. Pin all production dependencies to exact versions before 1.0

## External Runtime Dependencies (Not in requirements.txt)

### Ollama — LOCAL LLM RUNTIME

Are-Self depends on Ollama for local LLM inference but does **not** bundle or distribute it. Ollama is
installed separately by the user (our install script handles this automatically). Because Ollama runs
as a local HTTP server on the operator's machine, its security posture directly affects Are-Self's
attack surface.

**Known Ollama Vulnerabilities:**

| CVE | Severity | Description | Fixed In |
|-----|----------|-------------|----------|
| CVE-2024-37032 ("Probllama") | **CRITICAL** | Path traversal → Remote Code Execution via file overwrite | Patched in 2024 |
| CVE-2024-39720/39721/39722/39719 | **HIGH** | Multiple: DoS, model poisoning, model theft | Patched in 2024 |
| CVE-2024-12886 | **HIGH** | Denial of Service | Patched |
| CVE-2025-51471 | **HIGH** | Authentication bypass | Patched |
| CVE-2025-48889 | **HIGH** | Arbitrary file copy | Patched |
| CVE-2025-0312 | **HIGH** | Out-of-bounds write via malicious model files | Fixed in 0.7.0+ |
| CVE-2025-63389 | **CRITICAL** | Missing authentication on API endpoints | Fixed in 0.12.3+ |
| Installer hijack (2026) | **HIGH** | Command injection in install path verification | Check for latest patch |

**Are-Self's Mitigation Posture:**

- Are-Self does not expose Ollama to the network. The default configuration talks to `localhost:11434`.
- We do not bundle Ollama — users install it independently, meaning they receive Ollama's own updates.
- Our install script (`are-self-install.bat`) installs Ollama if not present but does not pin a version.
- **Recommendation for operators:** Keep Ollama updated. Run `ollama --version` and compare against
  the [Ollama releases page](https://github.com/ollama/ollama/releases). The authentication bypass
  (CVE-2025-63389) is particularly relevant if Ollama is exposed beyond localhost.

**Are-Self does not control Ollama's security.** We depend on it the way a web app depends on a database
server — it's infrastructure the operator must maintain. We document this clearly because pretending
otherwise would be dishonest.

### Docker (PostgreSQL + Redis)

Are-Self uses Docker Compose for PostgreSQL and Redis. Both run as containers bound to localhost by
default. Operators should keep Docker images updated independently of Are-Self releases.

## How to Run This Audit

```bash
# Install pip-audit
pip install pip-audit

# Audit against requirements
pip-audit -r requirements.txt

# Audit installed packages directly
pip-audit

# Output as JSON for CI integration
pip-audit -r requirements.txt --format json --output audit-results.json
```
