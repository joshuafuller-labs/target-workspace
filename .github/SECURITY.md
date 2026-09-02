# Security Policy

## Supported versions

This project is pre-release (v0.x). No version is yet supported for production use.

## Reporting a vulnerability

**Please do not open public issues for security vulnerabilities.**

Report security issues privately via GitHub's [private security advisory](https://github.com/joshuafuller/target-workspace/security/advisories/new) channel.

We aim to acknowledge reports within 72 hours and to publish a coordinated advisory + fix within 14 days for high-severity issues.

## What we consider a vulnerability

- Authentication / authorization bypass
- Remote code execution
- SQL injection, command injection, path traversal
- SSRF, XSS, CSRF in the API or web SPA
- Cryptographic flaws or insecure default configurations
- Supply-chain issues in our pinned dependencies that are not already addressed by the audit in `docs/tech-stack.md`
- Sensitive data leakage (audit log, classification handling, secrets)

## What we don't consider in scope (yet)

- Issues in third-party services we integrate with (TAK Server, ATAK clients, etc.) — report to the vendor
- Findings on running deployments you don't own
- DoS-by-resource-exhaustion against the public OpenAPI endpoint that don't constitute a real attack

## Supply-chain expectations

We follow the practices documented in `docs/foundation.md` §5 and `docs/tech-stack.md`:

- SHA-pinned GitHub Actions
- SBOM (CycloneDX) attached to every release
- Cosign-signed container images
- Vuln + license scanning on every PR
- No high/critical CVEs in pinned dependency versions on day 1

If you find a deviation from this posture, please report it the same way.
