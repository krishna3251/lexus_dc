# 🤖 Lexus Discord Bot

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Discord.py](https://img.shields.io/badge/discord.py-2.3%2B-blueviolet)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-teal)
![MongoDB](https://img.shields.io/badge/MongoDB-Motor-green)
![License: MIT](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/status-active-success)

Lexus is a modular, multipurpose Discord bot built with **discord.py 2.x**, backed by **MongoDB (Motor)** for persistence and featuring an integrated **FastAPI** service for health checks and real-time server statistics.

---

## ✨ Features

- 🛡️ **Lexus V3 Security Engine**
  - **Decoupled Architecture**: Strictly separates detection from decision and decision from action (`Event -> Normalize -> Evidence -> Tracker -> Correlation -> Risk -> Policy -> Action -> Incident -> Recovery`).
  - **Multi-Window Anti-Spam**: Detects rapid message bursts, exact repeats, near-duplicate text via token signatures, mention floods, invite/link bursts, and channel hopping.
  - **Guild-Scope Raid Detection**: Tracks join velocity and distributed multi-actor coordinated spam with automatic hysteresis state transitions (`NORMAL <-> ELEVATED <-> RAID <-> PANIC <-> RECOVERY`).
  - **Anti-Nuke & Permission Guard**: Detects mass channel/role deletions, @everyone privilege escalation, Administrator grants, unauthorized bot joins, and rapid webhook creation with cross-action risk scoring.
  - **Idempotent Quarantine & Lockdown**: Secure role-based containment with role history preservation and reversible emergency lockdowns.
  - **Structural Baseline & Recovery**: Captures trusted server configurations and performs damage analysis against baselines with safe reconstruction.
  - **Audit Mode vs Enforce Mode**: Supports non-destructive monitoring/simulation (`audit`) or active automated containment (`enforce`).

- 💬 **AI & Coding Assistance**
  - **Lexus AI Chat** (`cogs/chat_lex.py`): Behaviorally-aware conversational AI with emotion and intent analysis (OpenRouter / NVIDIA AI APIs)
  - **Lexus Coder** (`cogs/coder_lex.py`): Intelligent code generation, explanation, debugging, and review with code-continuation support

- 🔧 **Server Administration & Utilities**
  - Interactive channel permissions console (`cogs/channel_perms.py`)
  - Mass role assignment with execution controls (`cogs/mass_role_add_cog.py`)
  - User and channel message purge protocols (`cogs/purge_member_cog.py`, `cogs/slash_commands_cog.py`)
  - Multi-channel command broadcasting (`cogs/broadcast.py`)
  - Configurable server prefix management (`cogs/prefix_cog.py`)
  - Welcome and goodbye messages with customizable embeds and join DMs (`cogs/welcome.py`)
  - Auto-role assignment on member join and persistent reaction-role buttons (`cogs/autorole.py`)
  - Comprehensive audit logging for edits, deletions, joins, leaves, bans, and role changes (`cogs/logging_cog.py`)

- 🎟️ **Community & Engagement**
  - Private thread-based support tickets with transcripts (`cogs/tickets.py`)
  - XP leveling system with rank cards and server leaderboards (`cogs/leveling.py`)
  - Reaction-based polls with optional auto-close timer (`cogs/polls.py`)
  - Persistent reminders stored in MongoDB (`cogs/reminders.py`)
  - Multi-engine search for YouTube, weather, Wikipedia, and Google (`cogs/search.py`)
  - Smart pinger with contextual messages and GIF integration (`cogs/gif_cog.py`)
  - Detailed server and member information cards (`cogs/serverinfo.py`, `cogs/minfo.py`)

- 🌐 **Web API & Hosting**
  - Built-in FastAPI server for hosting platform health checks (`/health`, `/`)
  - Real-time bot and server metrics endpoint (`/stats`) secured by optional API key
  - Wavelink/Lavalink audio node integration

---

## 🏗️ Architecture Overview

```text
lexus_dc/
├── core/               # Centralized config, structured logging, errors, permissions, events
│   ├── config.py
│   ├── logging.py
│   ├── errors.py
│   ├── permissions.py
│   ├── events.py
│   └── lifecycle.py
├── services/           # Persistent data & bounded memory infrastructure
│   ├── database.py     # Resilient MongoDB service with in-memory fallback
│   ├── cache.py        # Bounded LRU/TTL caches
│   └── snapshots.py    # Structural guild snapshots & diffing engine
├── security/           # Lexus V3 Security Engine
│   ├── engine.py       # Central pipeline orchestrator
│   ├── models.py       # Normalized event models, evidence, and states
│   ├── scoring.py      # Exponential heat decay, risk scoring, state machine
│   ├── event_tracker.py# Sliding windows and token-bucket rate limiters
│   ├── dedup.py        # Event deduplication cache
│   ├── spam.py         # Multi-window spam detector
│   ├── raid.py         # Guild join velocity & distributed raid detector
│   ├── join_gate.py    # Account age & join threat analysis
│   ├── anti_nuke.py    # Structural nuke & cross-action risk detector
│   ├── permission_guard.py # Dangerous permission diff engine
│   ├── bot_guard.py    # Unauthorized bot addition guard
│   ├── webhook_guard.py# Webhook abuse detector
│   ├── quarantine.py   # Isolated quarantine & role preservation
│   ├── lockdown.py     # Reversible public channel lockdown
│   ├── baseline.py     # Safe structural baselines
│   ├── recovery.py     # Post-incident recovery analysis
│   ├── audit.py        # Budgeted audit log correlation
│   ├── actions.py      # Rate-limited idempotent action engine
│   ├── incidents.py    # Incident correlation & lifecycle tracking
│   ├── policies.py     # Policy evaluation matrix (audit vs enforce)
│   └── simulator.py    # Offline attack testing harness
├── cogs/
│   ├── security.py     # /security administration slash commands
│   └── ...             # Existing feature extensions
├── tests/              # 47 unit, integration, failure & benchmark tests
├── main.py             # Bot initialization, cog loader, and lifecycle
├── mongo_helper.py     # Centralized async MongoDB database interface
└── requirements.txt    # Production dependencies
```

---

## 🛡️ Lexus Security Engine (V3)

### Security Modes
- **`audit`**: Detects events, calculates risk scores, correlates incidents, and logs simulated responses without punishing members or altering channels. Ideal for initial deployment and threshold calibration.
- **`enforce`**: Actively applies containment policies (Timeout, Quarantine, Channel Lock, Lockdown) when risk and confidence thresholds are crossed.

### Administration Commands (`/security`)
- `/security status` — Displays real-time server security state, protection modules, active telemetry, and incidents.
- `/security setup` — Guided setup to establish a quarantine role, log channel, and trusted baseline.
- `/security config [mode] [profile]` — Configure operation mode (`audit`/`enforce`) and strictness (`standard`/`strict`).
- `/security logs` — Review recent security incident history.
- `/security trust [action] [user/role]` — Whitelist trusted administrators or roles from automated punishment.
- `/security quarantine [action] [member]` — Manually quarantine or release an actor, restoring original roles on release.
- `/security lockdown [action]` — Manually trigger or release emergency public channel lockdowns.
- `/security baseline [action]` — Capture trusted server structure or view structural diffs.
- `/security recovery` — Inspect structural changes following an attack.

### Technical Limitations & Discord Boundaries
- **Role Hierarchy**: Lexus cannot modify or discipline members whose highest role is above or equal to Lexus's highest role.
- **Platform Scope**: Lexus cannot inspect private user DMs, view IP addresses, or bypass Discord permissions.
- **Action Budget**: An automated circuit breaker restricts mutations per time window to prevent API storms and avoid compounding Discord rate limit delays.

---

## 🚀 Getting Started

### 1. Prerequisites
- Python **3.10** or higher
- A Discord Bot Token (from the [Discord Developer Portal](https://discord.com/developers/applications))
- (Optional) A MongoDB cluster (e.g., free MongoDB Atlas M0 cluster)
- (Optional) A Lavalink server instance for music

### 2. Installation
Clone the repository and install dependencies:

```bash
git clone https://github.com/krishna3251/lexus_dc.git
cd lexus_dc
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Required minimum configuration:
```env
DISCORD_TOKEN=your_discord_bot_token_here
```

### 4. Running the Bot
Start Lexus:

```bash
python main.py
```

The bot will:
1. Start the background FastAPI service on `$PORT` (default: `10000`)
2. Connect to MongoDB (if configured)
3. Dynamically discover and load all cogs from `cogs/`
4. Connect to Discord and synchronize application slash commands
5. Establish Lavalink connection (if configured)

---

## 📡 Web Endpoints

When running, Lexus serves a lightweight FastAPI server:

| Endpoint | Method | Description |
| -------- | ------ | ----------- |
| `/` | `GET`, `HEAD` | Root health status |
| `/health` | `GET` | Service liveness check |
| `/stats` | `GET` | Member, channel, role, and boost statistics (secured by `API_SECRET_KEY` if set) |

---

## 📜 License

Distributed under the [MIT License](file:///c:/Users/krish/Downloads/lexus_dc-main/lexus_dc-main/LICENSE).

## 💡 Author

Created by **Krishna** ([@krishna3251](https://github.com/krishna3251))
