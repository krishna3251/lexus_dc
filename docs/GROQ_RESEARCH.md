# Groq-only research reports

14 November 2026. This supersedes the previous Gemini fallback and brief-search
behavior. Rukiya and Discord moderation policy are unchanged.

## Conversation behavior

Use `/research query:<question>` or `lx research <question>`. Explicit natural
requests such as `Lxeus research Discord API changes` also work. Ordinary search,
price and news routes use this research path; normal casual chat stays separate.

After admission, safety and external-processing checks, the bot posts a short
notice explaining that it is checking live sources. The notice is removed on
completion or cancellation. Slash interactions are deferred first. No artificial
waiting period is added: the time is spent collecting evidence and writing the
report. Private/external opt-out requests do not announce or start a search.

Default research performs up to three query formulations: the original question,
a primary-source pass, and an independent evidence/comparison pass. It then makes
a separate Groq request to synthesize the report. The report instructions request
a direct answer, detailed findings, practical comparisons or steps, citations,
dates, uncertainty and coverage gaps. This is model guidance, not a guarantee of
accuracy or exhaustive coverage.

Research has its own 2,400-token output allowance and a 150-second whole-request
deadline. The saved casual-chat brevity preference does not truncate the report
to 220 tokens. Explicit quick/brief/one-line requests use one search pass and a
450-token synthesis allowance instead. A deadline is a maximum, not a promised
wait time or completion time. Provider/token availability can still prevent a
completed report.

## Evidence and providers

- Groq is the unified engine's only hosted generation provider. Its existing
  `GROQ_API_KEY` enables native browser-search research without a second search key.
- If `TAVILY_API_KEY` is provided, Tavily advanced search supplies structured
  excerpts for detailed requests; basic search handles explicit quick requests.
  News queries use the news topic and explicit current/today requests apply a
  recent time range. At least two deduplicated source URLs are required before
  skipping native browser search.
- Native Groq browser passes request factual evidence plus actual source URLs.
  These URLs are provider-reported, not independently fetched or verified by the
  Discord process. Tavily excerpts likewise remain untrusted external data.
- The existing Google CSE integration remains an optional evidence fallback for
  already configured operators; it is not a Gemini model or a new recommendation.
- Sources are URL-validated, deduplicated and assigned application-owned source
  IDs. Private-address/credential URLs are rejected. Unknown standard `[S99]`
  citation IDs are tagged unverified. This checks citation identifiers, not whether
  every generated factual claim is supported by its citation.
- Failed passes and single-domain coverage are disclosed. Without usable live
  source links, no completed sourced report is claimed. A final-model failure also
  produces an error rather than a fabricated result. Cached knowledge is available
  only through the existing explicit `knowledge:` route.
- Reports, query strings and fetched excerpts are not cached globally. Research
  synthesis is tool-free; returned Discord tool calls are rejected.

Gemini generation, Google grounding and external embedding requests have been
removed. Existing SQLite knowledge remains usable through lexical retrieval.
Old Gemini keys have no effect on model selection; the logging redactor still
protects a leftover key if present in the environment. Legacy NVIDIA/OpenRouter
feature integrations and explicit Jev evaluations are separate from the unified
generation/research path and were not migrated in this change.

## Limits and cost

| Setting | Default | Bound or purpose |
| --- | --- | --- |
| `AI_RESEARCH_TIMEOUT` | 150 seconds | 30–240 seconds |
| `AI_RESEARCH_OUTPUT_TOKENS` | 2,400 | 1,000–4,096 tokens for detailed reports |
| `AI_RESEARCH_QUERIES` | 3 | 1–3 evidence queries |
| `TAVILY_API_KEY` | unset | Optional structured search backend |

Every Tavily/CSE HTTP attempt and Groq model attempt reserves the existing shared
external-call budget. Budget exhaustion stops further requests. Rate-limit retries
honor numeric `Retry-After` values up to 60 seconds; a larger requested delay does
not trigger an early retry. The whole research deadline can cancel a wait.
This is process-local attempt accounting, not a currency or search-credit ledger.
Groq native tools may make multiple provider-side search/visit calls within one
model request; those internal calls are not separate application reservations.

Long reports show a visible preview and attach the complete Markdown report.
Shorter prose is split at readable boundaries. Attachment-permission fallback
preserves text delivery. Mentions remain suppressed.

## Free API options checked on 14 November 2026

| API | Published allowance | Notes |
| --- | --- | --- |
| [Tavily](https://www.tavily.com/pricing) | 1,000 credits each month; no card | Basic search uses 1 credit; advanced uses 2. Three advanced queries cost 6 credits, so about 166 such research runs fit before other usage. Groq synthesis is separate. |
| [Exa](https://exa.ai/pricing) | $10 credits each month plus a $10 onboarding bonus; no payment method | Web search and content retrieval; endpoint/options determine consumption. Listed for comparison, not integrated here. |
| [Brave Search](https://api-dashboard.search.brave.com/documentation/resources/help-feedback) | $5 monthly credits | Card verification required. At the published Search rate, equivalent to 1,000 queries. No standalone free plan. Not integrated here. |
| [Serper](https://serper.dev/) | 2,500 free signup queries; no card | Google-style web/news/shopping results. The offer is not advertised as a recurring monthly allowance. Not integrated here. |

Primary technical references: [Tavily Search](https://docs.tavily.com/documentation/api-reference/endpoint/search),
[Tavily credits](https://docs.tavily.com/documentation/api-credits),
[Groq browser search](https://console.groq.com/docs/tool-use/built-in-tools/browser-search),
and [Groq rate limits](https://console.groq.com/docs/rate-limits).
Free allowances can change; none is an unlimited search guarantee.

## Verification

150 local tests passed on Python 3.12 with discord.py 2.7.1, including all 29 cogs
loading/unloading without external network access. New coverage exercises detailed
versus brief planning, three-pass research and synthesis, source deduplication,
partial failures, missing sources, invalid citation IDs, blocked tool output,
privacy/progress sequencing, the dedicated research timeout, cleanup on cancellation,
the hybrid command interaction, Groq retry delays, oversized HTTP responses and
actual loopback Tavily HTTP requests with shared budget reservations. Compilation
and diff validation also passed.

No real Groq/Tavily key, live report quality, provider bill, production Discord
interaction, MongoDB or Lavalink session was tested. Additional search keys are
optional; no account or paid plan was created.
