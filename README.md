<p align="center">
  <img src="ChatGPT Image Sep 27, 2026, 05_50_05 PM.png" alt="Lexus" width="100%" />
</p>

<p align="center">
  <a href="https://github.com/krishna3251/lexus_dc/stargazers">
    <img src="https://img.shields.io/github/stars/krishna3251/lexus_dc?style=for-the-badge&color=ff2a76&labelColor=080b16" alt="GitHub stars" />
  </a>
  <a href="https://github.com/krishna3251/lexus_dc/network/members">
    <img src="https://img.shields.io/github/forks/krishna3251/lexus_dc?style=for-the-badge&color=35bfff&labelColor=080b16" alt="GitHub forks" />
  </a>
  <a href="https://github.com/krishna3251/lexus_dc/issues">
    <img src="https://img.shields.io/github/issues/krishna3251/lexus_dc?style=for-the-badge&color=ff58c7&labelColor=080b16" alt="GitHub issues" />
  </a>
  <a href="https://github.com/krishna3251/lexus_dc/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/license-MIT-48cfff?style=for-the-badge&labelColor=080b16" alt="MIT License" />
  </a>
</p>

---

## 🧠 What is Lexus?

**Lexus** is a modular Discord bot built around two ideas:

> **AI should reason. Security should decide.**

It combines everyday Discord utilities with a dedicated **V3 Security Engine** and a new **AI Engine** designed around provider abstraction, tool calling, guarded execution, and deterministic application-side policies.

The goal is not to make Lexus look complicated.

The goal is to make the internals **harder to break**.

---

## ⚡ Core Systems

<table>
<tr>
<td width="50%" valign="top">

### 🛡️ Lexus V3 Security Engine

A layered defensive engine for server protection.

- Multi-window anti-spam
- Distributed raid detection
- Join-gate analysis
- Anti-nuke detection
- Dangerous permission monitoring
- Bot addition guard
- Webhook abuse detection
- Quarantine and containment
- Panic / lockdown states
- Structural baselines
- Recovery analysis
- Audit Log correlation
- Incident correlation
- Bounded action budgets
- Audit and enforce modes

</td>
<td width="50%" valign="top">

### 🤖 Lexus AI Engine

A provider-agnostic agent layer for reasoning and controlled Discord tools.

- Gemini primary provider
- Groq fallback provider
- Tool / function calling
- Local request routing
- Context building
- Execution planning
- Safety gate
- Permission guard
- Tool validation
- Bounded tool execution
- Request deduplication
- Provider fallback
- Telemetry
- Discord inspection tools
- Guarded moderation tools

</td>
</tr>
</table>

---

## 🔐 Security Philosophy

Lexus is deliberately built around a strict separation of responsibilities:

```text
Discord Event
     │
     ▼
Normalize
     │
     ▼
Detect / Observe
     │
     ▼
Evidence
     │
     ▼
Correlation
     │
     ▼
Risk / Heat
     │
     ▼
Security Policy
     │
     ├──────────────► LOG / ALERT
     │
     └──────────────► ACTION
                           │
                           ▼
                    Discord API
```

The AI Engine follows the same principle:

```text
User Request
     │
     ▼
Local Router
     │
     ▼
Safety Gate
     │
     ▼
Context Builder
     │
     ▼
Execution Plan
     │
     ▼
Gemini / Groq
     │
     ▼
Tool Validation
     │
     ▼
Permission Guard
     │
     ▼
Tool Executor
     │
     ▼
Discord Result
     │
     ▼
Final Response
```

**The model is never the final authority for Discord mutations.**

Role hierarchy, Discord permissions, protected assets, security policy, and tool limits remain application-controlled.

---

## 🧩 Current AI Tool Surface

Lexus currently exposes a deliberately small, guarded tool set:

### Read

```text
get_server_overview
get_member
list_channels
list_roles
get_bot_status
get_security_status
get_recent_security_incidents
get_recent_audit_logs
```

### Mutating

```text
timeout_member
kick_member
ban_member
lock_channel
```

Every mutation passes application-side checks before a Discord API call is attempted.

That means:

```text
AI: "Ban this member."
        │
        ▼
Requester permission?
        │
        ▼
Target hierarchy?
        │
        ▼
Bot hierarchy?
        │
        ▼
Protected target?
        │
        ▼
Tool policy?
        │
        ▼
Discord API
```

---

## 🏗️ Project Structure

```text
lexus_dc/
│
├── core/
│   ├── config.py
│   ├── logging.py
│   ├── errors.py
│   ├── permissions.py
│   ├── events.py
│   └── lifecycle.py
│
├── services/
│   ├── database.py
│   ├── cache.py
│   ├── snapshots.py
│   └── ai_engine/
│       ├── __init__.py
│       ├── models.py
│       ├── providers.py
│       ├── router.py
│       ├── context.py
│       ├── planner.py
│       ├── permissions.py
│       ├── safety.py
│       ├── validator.py
│       ├── executor.py
│       ├── telemetry.py
│       ├── tools.py
│       └── engine.py
│
├── security/
│   ├── engine.py
│   ├── models.py
│   ├── scoring.py
│   ├── event_tracker.py
│   ├── spam.py
│   ├── raid.py
│   ├── join_gate.py
│   ├── anti_nuke.py
│   ├── permission_guard.py
│   ├── bot_guard.py
│   ├── webhook_guard.py
│   ├── quarantine.py
│   ├── lockdown.py
│   ├── baseline.py
│   ├── recovery.py
│   ├── audit.py
│   ├── actions.py
│   ├── incidents.py
│   ├── dedup.py
│   ├── policies.py
│   └── simulator.py
│
├── cogs/
│   ├── security.py
│   ├── ai_engine.py
│   ├── chat_lex.py
│   ├── coder_lex.py
│   └── ...
│
├── tests/
│   └── ...
│
├── api.py
├── main.py
├── mongo_helper.py
├── stats_store.py
├── requirements.txt
├── .env.example
├── SECURITY.md
└── LICENSE
```

---

## 🛠️ Tech Stack

<p align="center">
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/discord.py-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="discord.py" />
  <img src="https://img.shields.io/badge/Gemini_AI-4285F4?style=for-the-badge&logo=google&logoColor=white" alt="Gemini AI" />
  <img src="https://img.shields.io/badge/Groq-000000?style=for-the-badge&logo=groq&logoColor=white" alt="Groq" />
  <img src="https://img.shields.io/badge/OpenRouter-111827?style=for-the-badge" alt="OpenRouter" />
  <img src="https://img.shields.io/badge/MongoDB-47A248?style=for-the-badge&logo=mongodb&logoColor=white" alt="MongoDB" />
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Uvicorn-499848?style=for-the-badge&logo=gunicorn&logoColor=white" alt="Uvicorn" />
  <img src="https://img.shields.io/badge/Lavalink-5865F2?style=for-the-badge" alt="Lavalink" />
  <img src="https://img.shields.io/badge/GitHub-181717?style=for-the-badge&logo=github&logoColor=white" alt="GitHub" />
</p>

---

## 🚀 Getting Started

### 1. Clone

```bash
git clone https://github.com/krishna3251/lexus_dc.git
cd lexus_dc
```

### 2. Install

```bash
python -m pip install -r requirements.txt
```

### 3. Configure

Create a `.env` file from `.env.example`.

Minimum:

```env
DISCORD_TOKEN=your_discord_bot_token
```

AI Engine credentials:

```env
GEMINI_API_KEY=
GROQ_API_KEY=
```

Provider model IDs are managed by the AI Engine rather than being exposed as deployment configuration.

Optional integrations include MongoDB, Lavalink, OpenRouter, search APIs, media APIs, and the FastAPI health service.

### 4. Run

```bash
python main.py
```

---

## 🎮 Example AI Usage

Ask Lexus something simple:

```text
lx ask how many channels are in this server?
```

Lexus can inspect live server state through a guarded read-only tool.

For an authorized moderation action:

```text
lx ask timeout @user for 5 minutes because they are spamming
```

The AI can request the action, but Lexus still performs the permission and hierarchy checks before Discord is touched.

---

## 🛡️ Security Commands

Lexus V3 exposes server security administration through `/security`.

```text
/security status
/security setup
/security config
/security logs
/security trust
/security quarantine
/security lockdown
/security baseline
/security recovery
```

### Security Modes

| Mode | Behavior |
| --- | --- |
| `audit` | Detect, score, correlate, log and simulate without destructive enforcement |
| `enforce` | Apply configured containment actions when policy thresholds are crossed |

Start with **audit mode** while calibrating a server.

---

## 📡 FastAPI Endpoints

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/` | GET / HEAD | Root health response |
| `/health` | GET | Service health check |
| `/stats` | GET | Bot and server statistics |

The API can bind to the `PORT` environment variable for hosting platforms.

---

## 🧪 Testing

The repository includes security and AI-engine test coverage for areas such as:

```text
✓ Sliding windows
✓ Token buckets
✓ Heat decay
✓ Risk scoring
✓ Permission diffs
✓ Event deduplication
✓ Hysteresis
✓ Spam detection
✓ Raid detection
✓ AI tool loops
✓ AI safety gates
✓ AI routing
✓ Failure isolation
```

Run:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

Also compile the project before deployment:

```bash
python -m compileall .
```

---

## ⚙️ Design Principles

> **Decision ≠ Generation**

> **Detection ≠ Action**

> **AI ≠ Authority**

> **Security must remain deterministic**

> **Failure must be visible**

> **Caches must be bounded**

> **Every mutation needs a policy boundary**

These are not decorative sentences. They are architectural constraints.

---

## 🚧 Development Status

| Component | Status |
| --- | --- |
| Modular Discord bot | 🟢 Active |
| V3 Security Engine baseline | 🟢 Implemented |
| Security event pipeline | 🟢 Implemented |
| Anti-spam / anti-raid | 🟢 Implemented |
| Anti-nuke / permission guard | 🟢 Implemented |
| Quarantine / lockdown | 🟢 Implemented |
| AI provider abstraction | 🟢 Implemented |
| AI tool-calling foundation | 🟢 Implemented |
| AI routing / safety / execution layers | 🟢 Implemented |
| AI long-term memory | 🟡 Planned |
| Advanced planner / reasoning improvements | 🟡 In development |
| Full migration of legacy AI cogs | 🟡 Planned |
| Production-scale AI benchmark suite | 🟡 In development |

**Lexus is under active development.**

The AI Engine is being built incrementally so the existing bot does not have to be sacrificed to the gods of refactoring.

---

## 🔗 Project Links

<p align="center">
  <a href="https://github.com/krishna3251/lexus_dc">
    <img src="https://img.shields.io/badge/Repository-GitHub-181717?style=for-the-badge&logo=github&logoColor=white" alt="Repository" />
  </a>
  <a href="https://github.com/krishna3251/lexus_dc/issues">
    <img src="https://img.shields.io/badge/Issues-Report%20a%20problem-f78166?style=for-the-badge&logo=github" alt="Issues" />
  </a>
  <a href="https://github.com/krishna3251/lexus_dc/security">
    <img src="https://img.shields.io/badge/Security-Policy-2ea043?style=for-the-badge&logo=github" alt="Security" />
  </a>
</p>

---

## 📜 License

Lexus is distributed under the **MIT License**.

See [LICENSE](LICENSE).

---

<p align="center">
  <i>Built with Python, Discord, APIs, too many edge cases, and an unreasonable refusal to let the bot do stupid things.</i>
</p>

<p align="center">
  <sub>© Krishna • Lexus Discord Bot</sub>
</p>
