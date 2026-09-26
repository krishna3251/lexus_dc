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

- 🛡️ **Moderation & Security**
  - Slash and prefix commands for kick, ban, timeout, and role management
  - Anti-nuke protection monitoring channel deletions, member bans, and role deletions
  - Configurable automod (spam rate limiting, caps filtering, invite link blocking, bad-word filter)
  - Interactive quarantine system with configurable roles and monitored channels
  - Perspective API toxicity analysis with automated punishment thresholds and karma tracking

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
├── .env.example        # Environment variable template
├── .gitignore          # Git exclusion rules
├── LICENSE             # MIT License
├── README.md           # Project documentation
├── SECURITY.md         # Security policy and reporting guidance
├── api.py              # FastAPI endpoints (health checks & stats)
├── main.py             # Bot initialization, cog loader, and lifecycle
├── mongo_helper.py     # Centralized async MongoDB database interface
├── requirements.txt    # Production dependencies
├── stats_store.py      # Shared in-memory stats cache
└── cogs/               # Modular discord.py extensions
```

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
