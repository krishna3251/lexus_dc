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
