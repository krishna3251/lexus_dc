# Lxeus Brain V2: implementation and verification

Date: 9 November 2026. Repository: `krishna3251/lexus_dc`. Baseline commit: `826d768504d7c643f7357e8d03b4c4ac776fead4`.
The [14 November conversation/efficiency update](DISCORD_EFFICIENCY.md) supersedes
the legacy-cog budget/style and token-telemetry limitations recorded in this original report.
This is an incremental upgrade of the existing bot. Rukiya and `lexus2` were not modified.
Maintainer configuration and resource notes below are supplied for this requested upgrade; the project remains private in operation.

## Architectural assessment before implementation

The repository already contained a modular monolith: Python, discord.py cogs, an AI service package, a separate deterministic security engine, Motor/MongoDB feature persistence, SQLite AI memory/RAG, optional FastAPI/Uvicorn health service, and a Wavelink/Lavalink connector. `main.py` discovers and loads the cogs. No Python runtime pin, CI workflow, Dockerfile, Render Blueprint, or environment example was present. Existing AI persistence defaults to `/home/container/data/lexus_ai.sqlite3`, consistent with the documented container filesystem. The actual deployed machine's CPU/RAM/GPU limits were not available.

Dependencies and boundaries:

| Entry/component | Existing dependencies and behavior |
| --- | --- |
| `main.py` | discord.py, dynamic cog loading, Mongo lifecycle, health thread, optional Lavalink connection |
| `cogs/ai_engine.py` | Discord adapter → `AIEngine`; other feature cogs retain their own commands |
| `services/ai_engine/engine.py` | Router → safety → planner/context → providers → validator/permission guard → executor/registry |
| `memory.py`, `rag.py` | Same SQLite file; feature/security MongoDB remains separate by existing design |
| `research.py` | Groq search → Gemini grounding → Google CSE; optional RAG/embeddings |
| `security/` | Event normalization, detectors, attribution, policy, guarded actions; independent of generation |
| Legacy AI cogs | `chat_lex`, `coder_lex`, GIF/help features contain separate integrations; legacy chat already yields natural messages to the unified engine |

The [complete static import map](module_dependencies.json) covers 103 Python modules, including tests and optional imports. Runtime extension edges are `main.py → cogs.*`; imports alone do not describe dynamic dispatch.

Observed problems before edits:

- Provider availability was checked before any useful local operation, so even straightforward requests required an LLM.
- Jev could make an external request to decide whether generation should receive tools.
- Expiring/evictable per-user locks were unsuitable for active work; global/guild capacity, total deadlines and user cancellation were absent.
- SQLite history was recorded automatically for seven days. Durable memory primitives had no unified user commands or privacy preferences.
- Memory context could grow without a total input-size limit. Model clients were constructed eagerly.
- RAG initialization, health counts and candidate scoring performed synchronous work on the event loop.
- Personalized Gemini answers and prompts entered shared RAG; this could expose private context across retrievals.
- The AI mutation boundary did not require confirmation, tool argument types were insufficiently validated, private channel names were exposed, and one protected-channel lookup failed open.
- Member mention parsing used `d+` instead of `\d+`.
- Security attribution confidence could be overwritten after it had been reduced for an unknown audit actor.

Baseline: the initial check lacked discord.py. After installing the declared requirements in a local virtual environment, 74 tests ran with 2 failures and 4 errors. Three errors came from the workspace SOCKS proxy dependency being required by eager SDK construction; one was a test file containing literal `\n` separators. The failures were the unknown-tool test using a chat route with zero allowed tool calls, and the security attribution bug. The updated test now exercises unknown tools within a tool-enabled route; chat tool execution is separately tested as forbidden. Retry assertions were updated for the new bounded retry behavior.

## What changed and why

The existing `AIEngine` is the Brain entry point. No parallel bot, replacement database, inference framework, or microservice was introduced.

1. **Admission:** reject empty/oversized prompts, enforce a 12-request/minute user window, one active request per user, global and guild capacity, and a total deadline. Capacity is held in non-evictable active state, with no unbounded waiting queue. DM users have separate guild-capacity buckets.
2. **Local selection:** existing router/safety rules run without inference. Arithmetic uses a bounded AST interpreter, never `eval`. Exact requests for server/member identifiers and the registered command list use local application facts. Only deterministic arithmetic is cached; cache size 256, TTL 300 seconds.
3. **Knowledge:** `knowledge: <query>` returns relevant excerpts from the existing shared, curated knowledge store, explicitly marked as potentially outdated. It never invents a synthesized answer or calls an embedding API. Retrieval is bounded and runs database/scoring work in a worker thread.
4. **Context:** recent addressed turns live in a bounded RAM session, isolated by user + guild + channel. Opted-in history may survive restarts in SQLite. Approved key/value memories are isolated by user + guild, ranked lexically within the existing small per-owner bound, and assembled as untrusted context. FTS/mandatory embeddings would add complexity for at most 12 approved records per owner; they were not needed here.
5. **Style:** stable context cues and an optional user preference guide casual/friendly/playful/sarcastic/serious/technical/helpful/concise output. Serious cues override playful preferences. Output budgets vary by task; empty model output is a failure. This is guidance to a language model, not a collection of simulated conversations.
6. **Models:** an optional text-only loopback backend handles suitable conversation first. Longer/explicitly complex requests prefer external generation when permitted. Local failure can fall back to Groq, then Gemini. Without permission for external processing, no external fallback occurs. Tools and live search are not entrusted to an untested local model.
7. **Actions:** model-generated mutations produce an exact pending preview. A one-use 60-second token is bound to user + guild + channel. Confirmation rechecks permissions, hierarchy, protected targets/channels and schemas at execution. Native moderation commands retain their existing path. No new autonomous destructive behavior is enabled.
8. **Lifecycle:** active requests support cancellation and shutdown. SQLite worker transactions finish under their operation lock before cancellation releases it, preventing deletion races that could restore erased history. AI failure remains separate from essential feature cogs.

Jev's explicit typed-evaluation interface is retained, but normal Brain routing no longer invokes an API to choose another API. Global external-off mode also blocks the engine's explicit evaluation entry point.

## Memory, privacy and user controls

Only messages addressed to the bot, direct DMs, or replies to the user's own recent bot response enter unified conversation handling. General server conversation is not silently collected by Brain. Coding triggers owned by `coder_lex` are excluded from the natural-chat gateway to prevent duplicate replies.

| Command | Behavior |
| --- | --- |
| `/aimemory status` / `lx aimemory` | Show private choices for the current guild or DM scope |
| `/aimemory settings history:false external:false` | Disable persistent chat history and external Brain processing; disabling persistence removes saved history |
| `/aimemory remember key:language value:Hinglish` | Explicitly approve a memory; same key replaces the prior value |
| `/aimemory recall` | Privately list only your approved records in the current scope |
| `/aimemory forget key:language` | Delete one record and clear temporary/persisted conversation context in this scope |
| `/aimemory clear` | Cancel active requests; erase your RAM history, SQLite history, approved memories, feedback and pending actions in this scope; retain privacy choices |
| `/aimemory style style:technical` | Save style preference; `adaptive` clears it |
| `/aicancel` | Stop your active Brain requests in this server; already accepted Discord actions may have completed |
| `/aiconfirm token:…` | Execute the exact pending preview once, with renewed permission checks |
| `/aifeedback helpful:false` | Save an explicit usefulness signal without message contents |

All memory responses use ephemeral slash replies or DMs for prefix commands. They never fall back to posting memory contents in a public channel. AI-generated output suppresses Discord mentions. Saved personal memories can inform the requesting user's conversation replies; those replies follow the visibility of the channel where that user asks.

Defaults: persistent history off; external generation allowed when configured; temporary RAM session 15 minutes; opted-in persisted history 24 hours; approved records 90 days. History is bounded per conversation and globally at 20,000 rows; approved records remain bounded at 12 per user/guild. Feedback keeps at most 1,000 metadata-only records for 30 days on cleanup. Expired history/memories are excluded immediately and removed opportunistically during store operations; this is not a continuously running erasure scheduler. SQLite/WAL files and host backups require the maintainer's normal filesystem/backup controls; deletion is logical, not a secure disk wipe.

A privacy-preference read failure fails closed for external processing. No new database is required: preferences and feedback use the existing AI SQLite file. Prior `source_type='research'` shared RAG entries are removed on initialization because they could contain personal data. New personalized answers, prompts and queries are not cached globally. Shared knowledge must be curated public material; there is no user-upload ingestion endpoint in this change.

These controls apply to unified Brain routes. Existing legacy coder, GIF, help, message logging and other cogs keep their independent behavior and provider settings. They have not been silently claimed to share the new privacy or budget policy.

## Configuration and hosting

See the secret-free [environment reference](../.env.example). Existing Discord, MongoDB, Lavalink and health-service configuration names remain unchanged. No dependency was added to `requirements.txt`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `AI_EXTERNAL_ENABLED` | `true` | Global permission for unified external generation/research; user preferences can restrict it further |
| `AI_EXTERNAL_CALL_LIMIT` | `200` | Maximum charged external generation/research attempts per monotonic hour per manager/process, including failed attempts/retries |
| `AI_PROVIDER_RETRIES` | `1` | Additional transient-error attempts before provider fallback; range 0–2, short exponential backoff |
| `GROQ_API_KEY`, `GEMINI_API_KEY` | unset | Existing optional external credentials |
| `GROQ_MODEL`, `GEMINI_MODEL` | existing defaults | Operator-selected models; live availability was not verified with credentials |
| `AI_PROVIDER_COOLDOWN_SECONDS` | `300` | Existing health telemetry; external generation retains strict Groq-first ordering rather than skipping it on cooldown |
| `AI_LOCAL_ENABLED` | `false` | Opt in to a separately operated runtime; requires `AI_LOCAL_MODEL` |
| `AI_LOCAL_URL` | `http://127.0.0.1:11434/v1` | Loopback OpenAI-compatible base URL; non-loopback hosts/embedded credentials are rejected |
| `AI_LOCAL_MODEL` | unset | Explicit runtime model identifier; no automatic model download or selection |
| `AI_LOCAL_TIMEOUT` | `15` | Local attempt including admission to the single-inference semaphore; 1–60 seconds |
| `AI_MAX_CONCURRENT`, `AI_GUILD_CONCURRENT` | `8`, `3` | Active Brain request caps; one active request per user, plus fixed 12/minute user rate bound |
| `AI_REQUEST_TIMEOUT` | `65` | Whole unified request deadline, 1–180 seconds; cleanup may wait for a bounded SQLite worker |
| `AI_CONTEXT_CHARS` | `10000` | Serialized model-message size bound, 4,000–32,000 from environment; tool-loop growth is checked before each generation |
| `AI_PROMPT_CHARS` | `8000` | Additional prompt cap; effective maximum is the smaller of this and half the context bound |
| `AI_SESSION_TTL`, `AI_SESSION_COUNT` | `900`, `1000` | RAM session TTL in seconds and LRU capacity |
| `AI_SQLITE_PATH` | `/home/container/data/lexus_ai.sqlite3` | Existing AI memory and curated RAG database |
| `AI_HISTORY_TTL` | `86400` | Retention for newly opted-in history, seconds; 60–604,800 |
| `AI_MEMORY_TTL` | `7776000` | Approved-record retention, seconds; 60–31,536,000 |
| `AI_EMBEDDINGS_ENABLED` | `false` | Explicit opt-in for knowledge ingestion embeddings; conversation/knowledge query paths still use lexical retrieval |
| `GOOGLE_API_KEY`, `GOOGLE_CSE_ID`, `GEMINI_RESEARCH_MODEL` | existing optional settings | Existing live-research fallback configuration |

Numeric environment inputs are clamped, with invalid/nonfinite values falling back to defaults. Restart for Brain policy/limit changes. `aireload` retains its existing provider credential/model refresh role. Budgets reset on process/manager restart and are call caps, not currency accounting or provider billing enforcement. Legacy/explicit Jev paths have separate accounting. Do not use the counter as a multi-worker shared spend ledger.

Without a local model, the bot needs no GPU and retains the existing Python/Discord/SQLite architecture. The offline benchmark process peaked around 64 MiB RSS; this is not a production sizing guarantee for every cog, server membership, voice session or long history. SQLite requires a writable persistent directory. A single bot process is the supported operational shape for these in-process admission/budget controls. Shared SQLite dedupe helps when the same gateway event reaches more than one process; degraded storage cannot guarantee cross-process deduplication.

Local inference is operated outside the Discord process through an asynchronous HTTP adapter, serialized to one local inference at a time. It does not load weights on the event loop. Actual model selection depends on deployed RAM, CPU, GPU, context length, model quantization, disk and measured latency. The development workspace reported about 9.7 GiB host RAM and 9 logical CPUs; this does not establish the production allocation. No model was downloaded, no GPU was assumed, and no local-model performance claim is made. On small shared hosting, leave local inference off. Use only a model/runtime combination the operator has measured within that machine's limits.

The adapter targets the documented OpenAI-compatible chat-completion endpoints of [Ollama](https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx) and [llama.cpp](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md). It sends ordinary text chat parameters only, rejects runtime tool calls, disables redirects/proxy forwarding for loopback, bounds response bytes and applies deadlines. It has been verified against a simulated loopback server, not an installed inference runtime.

## Security and reliability

Model output, history, retrieved knowledge and tool arguments remain untrusted. Typed arguments, request scope, user permissions, role hierarchy and security policy are checked by application code. Read-only security incidents now require Manage Guild; channel lists omit channels the requester cannot view. Unknown policy during protected mutations fails closed. Mutating registry calls require an application-owned confirmation flag. The member-mention parser and overwritten audit-attribution confidence were corrected with regression coverage.

Provider exceptions no longer include raw service error bodies. Logging filters redact configured credentials, bearer tokens and formatted exception text. Research failure logs omit user queries. No logs intentionally record Brain chat contents. Prompt checks are defense in depth, not a proof of prompt-injection immunity; deterministic execution checks provide the permission boundary.

Normal requests cannot create timers, background autonomy, shell commands, arbitrary HTTP destinations, new tools, or self-modifying code. Existing admin-configured security alerts and reminder commands remain independent. Feedback is stored for evaluation; it does not train or modify a model.

## Verification and measurements

Commands actually executed:

```text
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
.venv/bin/python -m compileall -q services cogs core security tests main.py
.venv/bin/python -m tests.benchmark_brain
git diff --check
```

Final full suite: **111 tests passed**; the recorded validation run completed in 1.207 seconds.

The test suite covers intent routing, bounded context, user/guild/channel isolation, explicit consent, deletion/correction/TTL, worker cancellation races, concurrent users/guild limits, offline operation, external opt-out, local failure/fallback, real loopback HTTP protocol, budget/retry behavior, confirmations/expiry/revoked permissions, forbidden tools, schema checks, private channel filtering, styles, credential redaction and all existing security tests. A network-disabled integration test loads and unloads all 29 cogs. The separate smoke run registered 54 prefix commands and 64 slash-command roots with zero load failures. No Discord login, real moderation, live MongoDB, live provider call or Lavalink playback was attempted. The repository has a Lavalink connector but no dedicated music-playback cog in this checkout; no music implementation is claimed as added or verified.

The malformed RAG test file was repaired. Existing security coverage now catches the corrected audit-attribution confidence. The unknown-tool test was adjusted to use its intended tool-enabled route; a separate test ensures chat cannot execute unadvertised tools.

Measured on Linux / Python 3.12.14, sequential offline samples, without tracing timing measurements:

| Metric | Baseline median / p95 ms | Updated median / p95 ms | Samples |
| --- | --- | --- | --- |
| Lightweight router | 0.0111 / 0.0167 | 0.0110 / 0.0177 | 2,000 |
| Approved-memory lookup | 0.3288 / 0.5369 | 0.3951 / 0.6067 | 100 |
| Retrieval over 100 curated documents | unmeasured | 1.9266 / 2.3033 | 25 |
| Deterministic Brain end-to-end | unavailable as local path | 0.0235 / 0.1036 | 200 |

The memory lookup has a small added cost from retention and cancellation-safe execution; no speedup is claimed there. Deterministic run: zero external calls, zero errors, 99.5% cache hits for a repeated arithmetic expression. Allocation peak for 1,000 short RAM sessions: 687,352 bytes; whole-process peak RSS: 65,648 KiB. These are workload-specific, not worst-case bounds or production throughput estimates. First-token and real model latency are unmeasured, represented as `null`. No fabricated percentage improvement or API savings relative to production traffic is reported.

The machine-readable [benchmark output](brain_benchmarks.json) and executable benchmark are included. Telemetry exposes bounded routing/memory/retrieval/model durations, whole-request duration, error rate, deterministic cache hits/misses, active requests and charged provider attempts. Existing `telemetry.provider_calls` counts completed request outcomes; actual attempt counts are in `provider_metrics`. Synthetic external calls per deterministic conversation are zero; production conversation-level billing attribution and streaming first-token telemetry are not implemented.

## Limitations and next improvements

- No model weights were trained, downloaded or fine-tuned. Natural chat quality, Hindi/Hinglish fluency and judgment depend on the selected language model. Static routing and retrieval do not supply unrestricted intelligence.
- Local inference is text-only, with heuristic capability selection. Tool-enabled requests require external models unless fulfilled deterministically. No claim of semantic local-confidence calibration is made.
- Memory is bounded lexical recall, not automatic extraction of private facts. There is no cross-channel history merge. Approved records may expire or be evicted by the per-owner bound. Database contents/backups are not encrypted by this change.
- Basic response checks catch empty/oversized output and constrain style; they cannot prove factual accuracy or detect every unsupported action claim in free text.
- Proactive autonomy was not expanded. Existing reminders/security automation remain available through their original admin/permission paths.
- Feedback metadata and tests enable controlled iteration; no automatic online learning or self-modification was implemented. A richer consented conversation-evaluation dataset is a useful next step.
- Recommended future work: migrate remaining legacy AI routes deliberately, add shared durable spend accounting if multiple workers become necessary, instrument optional streaming first-token latency, benchmark an actual CPU-sized local model on the deployed machine, and evaluate retrieval quality on a curated dataset before adding FTS or semantic infrastructure.

## File inventory

No files were removed. Existing feature cogs other than the unified AI adapter were left intact.

| Change | Files |
| --- | --- |
| Added | `.env.example` |
| Added | `docs/LXEUS_BRAIN_V2.md` |
| Added | `docs/brain_benchmarks.json` |
| Added | `docs/module_dependencies.json` |
| Added | `services/ai_engine/brain.py` |
| Added | `services/ai_engine/config.py` |
| Added | `tests/benchmark_brain.py` |
| Added | `tests/test_brain.py` |
| Modified | `README.md` |
| Modified | `cogs/ai_engine.py` |
| Modified | `core/logging.py` |
| Modified | `docs/LEXUS_DOCUMENTATION.md` |
| Modified | `main.py` |
| Modified | `security/permission_guard.py` |
| Modified | `services/ai_engine/embeddings.py` |
| Modified | `services/ai_engine/engine.py` |
| Modified | `services/ai_engine/memory.py` |
| Modified | `services/ai_engine/models.py` |
| Modified | `services/ai_engine/permissions.py` |
| Modified | `services/ai_engine/personality.py` |
| Modified | `services/ai_engine/providers.py` |
| Modified | `services/ai_engine/rag.py` |
| Modified | `services/ai_engine/research.py` |
| Modified | `services/ai_engine/telemetry.py` |
| Modified | `services/ai_engine/tools.py` |
| Modified | `services/ai_engine/validator.py` |
| Modified | `services/cache.py` |
| Modified | `tests/test_ai_engine.py` |
| Modified | `tests/test_ai_rag.py` |
