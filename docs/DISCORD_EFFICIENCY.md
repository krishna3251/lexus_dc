# Lxeus Discord conversation and API efficiency update

14 November 2026. Builds on the Brain V2 branch in PR #2. Rukiya is unchanged.

## Reply behavior

The shared voice favors short Discord replies, natural language matching, occasional
humor, and useful follow-up questions only when context is missing. It does not
claim to be human. Explicit requests for detail, technical explanations or brevity
take priority over saved default tone; serious topics still disable playful tone.
This is prompt guidance, not a guarantee of model quality.

Legacy AI-channel conversation and the `chat` command now use the Brain request
path, including scoped conversation state and saved preferences. Native commands,
coding triggers, wake aliases, mentions and scoped bot replies have one owning
adapter. The first legacy chat message no longer starts inside a 15-second cooldown.
Artificial typing delays were removed from ordinary chat.

Research receives the selected style without a second rewriting call. Groq research
uses the request's output cap; the Gemini research fallback receives style guidance
but retains its existing endpoint configuration. Source links are preserved.

Natural, prefix and slash Brain replies share paragraph-aware delivery with a
conservative 1,900 UTF-16-unit bound. Long replies containing code, and prose over
7,600 units, are attached intact as Markdown. If Discord denies attachment
permission, text delivery is attempted instead; code fences may span messages in
that fallback. AI text delivery suppresses all mentions. Configured smart-ping
notifications retain their existing explicit recipient behavior.

## Cost controls and accounting

`GROQ_CHAT_MODEL` defaults to `openai/gpt-oss-20b` for short, tool-free, ordinary
chat. Technical/helpful/serious requests, stronger-reasoning cues and tool requests
keep `GROQ_MODEL`, which defaults to `openai/gpt-oss-120b`. Local inference policy
still applies first. Failed economy requests fall back to the main Groq model,
then Gemini. Set `GROQ_CHAT_MODEL` empty to disable economy routing. No additional
provider or model download is introduced.

Existing OpenRouter coding and NVIDIA help/GIF requests now reserve attempts from
the Brain's process-wide hourly cap and check the relevant user's external-processing
preference. They fail closed if the Brain policy is unavailable. Scheduled AI pings
check the selected recipient's preference; a local message replaces AI generation
when processing is disallowed or the budget is exhausted. Their existing provider
credentials and model choices remain separate. Exact prefix-command help comes
from the live command registry without an AI call.

`AI_CODE_OUTPUT_TOKENS` defaults to 2,048 and is clamped to 256–4,096. Delivering
already generated code no longer requests more generations while splitting it;
the returned remainder is delivered directly. A token-capped generation can still
be incomplete; this update does not claim to automatically finish arbitrary code.

`aistatus` now includes aggregate provider/model input and output token counts and
the count of responses with missing usage metadata. Cached input counts are retained
in provider metrics. No message text, user IDs or per-user billing is recorded in
these metrics. Unknown usage is identified as unreported rather than free. The
credential reload command preserves the current budget and usage and refuses to
interrupt an active Brain request.

These are attempt limits, not a currency budget or a provider billing ledger.
They reset on process restart and do not coordinate multiple workers. Gemini
grounding, CSE, explicit Jev evaluations and optional embeddings do not all expose
token usage through the same response shape; their costs are not inferred as zero.
Jev/embedding accounting and legacy code-memory deletion/retention are not migrated
by this update. The existing CSE per-request reservation was already present and
is preserved.

## Discord compatibility

The supported discord.py floor is now 2.7.1 with a major-version ceiling below 3.
The new GitHub Actions workflow runs the offline suite, compilation and diff checks
on Python 3.12 and 3.13 for pull requests, main pushes and manual runs. This tests
new compatible dependency releases when the workflow runs; it is not a promise of
compatibility with unpublished Discord changes.

Reviewed official references:

- [discord.py changelog](https://discordpy.readthedocs.io/en/stable/whats_new.html)
- [Discord developer changelog](https://docs.discord.com/developers/change-log)
- [Components reference](https://docs.discord.com/developers/components/reference)
- [Privileged intent review](https://docs.discord.com/developers/gateway/getting-started-with-privileged-intent-review)
- [Groq model catalog](https://console.groq.com/docs/models)

Components V2 UI migration, the October 2026 position-audit events and the new
permission-query endpoints are follow-up work. discord.py 2.7.1 does not expose
the position-event enum names, so no guessed audit attribution is added. Existing
deterministic security decisions and confirmation-gated AI mutations are unchanged.

## Verification

Local baseline: 111 tests passed. Updated suite: 130 tests passed on Python 3.12
with discord.py 2.7.1, including registration/unloading of all 29 cogs with network
requests disabled. New coverage exercises concurrent legacy/Brain message dispatch,
economy routing and fallback, shared budgets, privacy opt-out, usage extraction,
budget-preserving reload, code delivery without generation, free exact-command
help, style propagation to research, Unicode bounds and attachment-permission
fallback. Compilation and `git diff --check` passed.

No live Discord login, moderation action, real model response, provider bill,
MongoDB service or Lavalink session was tested. No measured production savings or
natural-language quality score is claimed. Python 3.13 is exercised by CI, not by
the local Python 3.12 run.
