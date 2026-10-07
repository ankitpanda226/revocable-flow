# Frozen exploratory pilot model matrix — 2026-10-07

The exploratory pilot uses one intended representative family from OpenAI, Anthropic and Google. This is not exhaustive provider coverage, a ranking of all models, or evidence that one family is objectively better. No live model output has been observed.

## Enabled identifiers and verification provenance

| Provider | Display family | Enabled API ID | Official source | Immutable snapshot |
|---|---|---|---|---|
| OpenAI | GPT-5.6 Sol | `gpt-5.6-sol` | [Official model page](https://developers.openai.com/api/docs/models/gpt-5.6-sol) | false |
| Anthropic | Claude Sonnet 5.5 | `claude-sonnet-5-5` | [Official model page](https://www.anthropic.com/claude-sonnet-5-5) | false |
| Google | Gemini 3.8 Flash | `gemini-3.8-flash` | [Official model documentation](https://ai.google.dev/gemini-api/docs/latest-model) | false |

The researcher independently verified these exact identifiers against the linked official sources on **2026-10-07** and supplied that verification for this freeze. The environment's earlier documentation requests were blocked with HTTP 403; this update relies on researcher-provided verification, not a claim that the environment retrieved those pages. Config status is enabled for exactly these three entries, and `models` lists those entries in existing matrix order (OpenAI, Google, Anthropic).

These identifiers are provider aliases rather than frozen dated snapshots. Availability, alias targets, API defaults and schemas may change. Every eventual raw response preserves requested_model and reported_model/modelVersion when returned (null otherwise). A returned name is not automatically an immutable snapshot; interpret provider version metadata before making reproducibility claims. Never substitute a model mid-run or silently replace an unavailable alias.

## Requested versus effective settings

The frozen requested settings stay temperature=0, top_p=1, max_output_tokens=512, seed=20261007 and repetitions=1. No provider-specific reasoning-effort or thinking-budget settings are supplied; use provider defaults. No tools, browsing, retrieval, extra context or native structured-output enforcement is enabled.

| Provider | Sent sampling parameters | Seed handling | Recorded difference |
|---|---|---|---|
| OpenAI Responses | temperature=0, top_p=1 | Omitted by this REST adapter | requested seed retained; unsupported_parameters includes seed |
| Anthropic Messages | temperature=0, top_p=1 | Omitted by this REST adapter | requested seed retained; unsupported_parameters includes seed |
| Google Gemini 3.8 Flash | Neither temperature nor top_p sent | Sent using existing generateContent adapter contract | requested temperature=0/top_p=1 retained; effective values are `unsupported`; both names recorded as unsupported |

The researcher supplied current official Gemini guidance to remove temperature and top_p. This explicitly authorizes a model-specific compatibility exception to Milestone 3's general rejection of unsupported sampling settings. It changes effective API settings, not requested settings, prompts, benchmark labels or scoring. Only the exact Gemini alias receives this exception; unrelated models and unsupported output-token limits remain blocked. Missing controls mean provider defaults apply; the runner does not invent numeric effective sampling values. Comparisons cannot claim identical effective sampling or deterministic generation across providers.

OpenAI/Anthropic parameter handling and token/seed mappings follow the existing REST contracts encoded in the repository and are verified with synthetic adapter tests. Google token-limit/seed mappings also use that existing contract. No live test or independent in-environment documentation retrieval has established model-specific acceptance, joint parameter compatibility or provider default behavior. Later approved sanity tests must check acceptance; incompatible requests are recorded as provider errors, never silently retuned or semantically retried.

## Freeze and next step

Full plan: 40 scenarios × 2 conditions × 3 enabled models = **240 intended requests**. Full and filtered dry-runs validate configuration, hashes, ordering and prompts while making zero network calls. The alias matrix is frozen; live execution still needs explicit research approval, environment-only credentials, a clean committed checkout and a unique run ID. No live sanity test, benchmark experiment, ablation or experimental result is included in this freeze. Pricing remains unconfigured, so cost estimate is unavailable.
