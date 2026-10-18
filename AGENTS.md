# AGENTS.md — Lexus (lexus_dc)

## Project boundaries
- Read `README.md`, `SECURITY.md`, and relevant files under `docs/` before changing architecture, security behavior, or public-facing documentation.
- This repository describes a modular Discord bot with separate AI and security systems. Preserve the principle that AI can interpret or recommend, while deterministic policy and permission checks decide whether actions are allowed.
- Respect the README's stated documentation/reference scope. Do not add self-hosting, deployment, credential-setup, or installation guidance unless Krishna explicitly changes that project boundary.
- Treat existing source code as authoritative. Do not assume a subsystem exists just because it is described in a document.

## Architecture
- Inspect the relevant parts of `core/`, `cogs/`, `services/`, `security/`, and `api.py` before editing.
- Keep Discord command/event adapters, business logic, AI-provider calls, and security decisions separated where the current design supports it.
- Permission checks and security policies must not be bypassed by an AI response. Fail closed when a security decision cannot be established.
- Keep provider-specific behavior behind existing interfaces; avoid adding a new provider or dependency without a concrete requirement.
- Preserve established interfaces and behavior across cogs. Avoid circular imports and import-time network/database side effects.

## Security and data
- Never hardcode, log, or reproduce Discord tokens, API keys, database URLs, or other secrets. Use the existing configuration patterns and safe examples only.
- Treat model output, user input, attachments, and external API responses as untrusted.
- Validate inputs and authorization at the action boundary; do not rely only on prompts or UI checks.
- Avoid logging message contents or personal data unless the existing documented behavior explicitly requires it.

## Validation
- Inspect `tests/` and existing CI/configuration before choosing checks.
- Run focused tests first, then the broader available checks if practical. Report commands and actual results.
- If a check cannot run because credentials, services, or dependencies are unavailable, state that limitation rather than claiming success.
- Keep changes small and review the final diff for unrelated edits, security regressions, and inaccurate documentation.