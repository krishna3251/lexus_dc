# Security Policy

## Supported Versions

Security updates and bug fixes are applied to the active branch of the Lexus bot:

| Version | Supported          | Notes |
| ------- | ------------------ | ----- |
| 2.x     | :white_check_mark: | Current active release branch |
| < 2.0   | :x:                | Deprecated / Unsupported |

---

## Reporting a Vulnerability

If you discover a security vulnerability within the Lexus codebase, please report it privately:

1. **Do not create public GitHub issues** for security disclosures.
2. Open a private security advisory through the GitHub repository's **Security** tab, or contact the project maintainer via Discord or email.
3. Include clear steps to reproduce the issue, along with any relevant payloads or logs.

Reports will be reviewed and acknowledged promptly, and valid vulnerabilities will be patched in the repository.

---

## Best Practices & Security Guidelines

To run Lexus safely in production, follow these operational best practices:

### 1. Protect Your Secrets
- **Never commit `.env` files** or hardcode API keys, Discord bot tokens, or database connection strings.
- Verify that `.env` is listed in your `.gitignore` before making any commits.
- If a token or key is ever accidentally pushed to a remote repository, **immediately revoke and rotate** the credential in the relevant developer dashboard (Discord, MongoDB Atlas, OpenAI, etc.).

### 2. Configure Discord Bot Permissions Properly
- Avoid granting the `Administrator` permission to the bot unless strictly necessary.
- Use granular permissions (e.g., `Manage Roles`, `Manage Channels`, `Moderate Members`, `Send Messages`) according to the bot's configured features.
- Ensure the bot's highest role is positioned correctly in the server hierarchy: above the roles it manages, but below critical administrative roles.

### 3. Secure MongoDB Access
- Restrict MongoDB network access using IP whitelisting in your database provider (e.g., MongoDB Atlas).
- Use a dedicated database user with least-privilege permissions for the bot's database.

### 4. API Key Protection
- When exposing the FastAPI web server, set `API_SECRET_KEY` in `.env` to prevent unauthorized access to the `/stats` endpoint.

### 5. Dependency Management
- Regularly update Python dependencies to address known upstream vulnerabilities.
- Run the bot in a virtual environment (`venv`).
