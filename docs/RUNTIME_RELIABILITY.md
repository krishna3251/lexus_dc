# Runtime reliability fixes

The November 14 runtime log showed successful cog loading and successful Groq HTTP
requests alongside independent interaction, audio, database and shutdown failures.

## Interactions

Security commands acknowledge before database or administrative work and deliver
their result through an ephemeral followup. A rejected acknowledgement stops the
callback before it performs administrative changes. Known expired interactions and
remote duplicate acknowledgements are logged without attempting another initial
reply. Shared error reporting prevents hybrid and application handlers from
reporting the same failure twice. Other HTTP errors remain visible.

Code 40060 alone does not identify why an interaction was acknowledged elsewhere.
It can still require investigation of overlapping handlers or bot processes. This
change prevents cascading error replies; it does not provide cross-process command
deduplication. Existing permission and security policy behavior is unchanged.

## Resources and shutdown

Lavalink sessions have an explicit owner, including when Wavelink rejects a node
without registering it in its pool. Initial attempts have a 30-second bound.
Repeated READY events reuse an existing connected or connecting node, and slash
commands are synchronized once after success. A node-ready event confirms audio
readiness; merely returning from Pool.connect is no longer treated as success.

The bot's asynchronous context closes Discord before its event loop exits on
cancellation. Owner-command restarts also close resources before replacing the
process. Ordinary service-close failures do not prevent Discord from closing.
Forced process termination cannot run asynchronous cleanup.

Failed MongoDB pings close the allocated client. Connection diagnostics retain the
exception type without printing raw exception text that might contain credentials.
Karma logs one warning per observed database outage, then resumes updates if access
returns; skipped updates are not stored or replayed. This does not add automatic
database reconnection.

## Verification and limits

Offline regression coverage checks initial-response races, expired tokens, early
security acknowledgement, rejected administrative callbacks, failed audio nodes,
HTTP-session cleanup, cancellation, resilient shutdown, and database-client cleanup.
An in-process HTTP endpoint returns 404 to exercise the actual installed Wavelink
failure path. The full suite passes 179 tests locally on Python 3.12.

The external Lavalink endpoint and MongoDB connection were not validated with live
credentials. Their configuration or availability can still prevent music and
database-backed features from working. Successful Groq requests do not prove that
every legacy AI integration or generated report is correct.

## Provider detection and security boundaries — 17 November 2026

Provider reload previously rebuilt clients from an unchanged process environment.
It never reread an edited `.env`, while status incorrectly treated a running
request scheduler as proof that a conversation provider was configured. These
code paths can explain a missing-provider message despite a key in the file;
they do not establish what was present in a particular deployed process.

The shared environment loader now reads only the project's root `.env`, including
UTF-8 BOM files, before service initialization. Nonempty hosting-platform settings
retain priority. A blank Groq credential can fall back to the file; deliberate
empty model settings retain their meaning. Provider refresh updates or removes
values previously loaded from that file, without overwriting process-supplied
credentials or changing the frozen external-inference policy and Brain limits.
The loader respects `PYTHON_DOTENV_DISABLED`.

When conversation providers are missing, an incoming request can refresh their
configuration while the engine is idle, at most once every 30 seconds. This makes
credentials added after startup discoverable without repeated owner commands.
New AI requests and confirmations pause during a reload; active requests prevent
a reload. Provider call budgets and usage counters survive refresh. A hosting
dashboard update that does not change the running process environment still
requires a process restart.

Owner status reports key presence, source and external-inference policy without
revealing credentials. `CONFIGURED` means a client can be selected, not that its
key, account quota or model access was validated. Missing configuration no longer
produces a successful reload message, and disabled external inference no longer
asks for another Groq key.

Two security boundaries were tightened:

- `/stats` returns 503 when its secret is absent or blank, and 403 for a missing
  or incorrect request key. It reads the current process setting at request time
  and compares credentials with `hmac.compare_digest`. Root and health endpoints
  retain their existing public behavior.
- Confirmed AI moderation also checks an administrator's position against the
  target's highest role. Only the guild owner is exempt from the requester's
  hierarchy comparison; bot hierarchy, protected targets and policy checks still
  apply to the owner.

Regression coverage exercises file precedence, rotation and deletion, empty and
BOM values, unrelated working directories, policy preservation, automatic
recovery, status output, HTTP access and AI hierarchy. The full offline suite
passes 228 tests on Python 3.12. Live Discord/Groq credentials and the deployed
process were not available for validation.
