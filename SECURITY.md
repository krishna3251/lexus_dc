# Security Policy

## Supported Versions

Security updates and bug fixes are applied to the active branch of the Lexus bot:

| Version | Supported          | Notes |
| ------- | ------------------ | ----- |
| 3.x     | :white_check_mark: | Lexus V3 Security Engine baseline |
| 2.x     | :white_check_mark: | Maintenance only |
| < 2.0   | :x:                | Deprecated / Unsupported |

---

## Defensive Philosophy & Operational Realities

The Lexus V3 Security Engine provides automated heuristic defense, rate tracking, and structural containment. However, administrators should understand platform constraints:

- **No Absolute Guarantee**: No bot can claim 100% infallible anti-raid or anti-nuke prevention. Platform API latency, network drops, and Discord platform limits mean containment is defensive and probabilistic, not infallible.
- **Discord Role Hierarchy**: Lexus can never manage, timeout, or kick users or roles positioned higher than the bot's own highest role in Discord's server settings.
- **API Outages**: During platform-wide Discord API disruptions, security actions may be queued or delayed by Discord gateway limits.

---

## Reporting a Vulnerability

If you discover a security vulnerability within the Lexus codebase, please report it privately:

1. **Do not create public GitHub issues** for security disclosures.
2. Open a private security advisory through the GitHub repository's **Security** tab, or contact the project maintainer via Discord or email.
3. Include clear steps to reproduce the issue, along with any relevant payloads or logs.

Reports will be reviewed promptly, and valid vulnerabilities will be patched.

---

## Best Practices & Security Guidelines

To run Lexus safely in production, follow these operational best practices:

### 1. Protect Your Secrets & Tokens
- **Never commit `.env` files** or hardcode API keys, Discord bot tokens, or database connection strings.
- Verify that `.env` is listed in your `.gitignore` before making any commits.
- If a token or key is ever accidentally pushed to a remote repository, **immediately revoke and rotate** the credential in the relevant developer dashboard.

### 2. Configure Discord Bot Permissions Properly (Least Privilege)
- Avoid granting the `Administrator` permission to the bot if possible.
- Grant only required operational permissions: `Manage Roles`, `Manage Channels`, `Moderate Members`, `View Audit Log`, `Send Messages`, `Embed Links`.
- Ensure the bot's highest role is positioned correctly in the server hierarchy: above regular members and manageable roles, but below the server owner and trusted senior management.

### 3. Secure MongoDB Access
- Restrict MongoDB network access using IP whitelisting in your database provider (e.g., MongoDB Atlas).
- Use a dedicated database user with least-privilege permissions for the bot's database.

### 4. API Key Protection
- When exposing the FastAPI web server, set `API_SECRET_KEY` in `.env` to prevent unauthorized access to the `/stats` endpoint.

### 5. Dependency Management
- Regularly update Python dependencies to address known upstream vulnerabilities.
- Run the bot in a virtual environment (`venv`).

