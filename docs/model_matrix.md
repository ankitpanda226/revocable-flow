# Exploratory pilot model matrix

The intended design uses one representative family from each of OpenAI, Google and Anthropic. This is a small exploratory comparison, not exhaustive provider coverage, a ranking of all models, or evidence that one family is objectively better. These family names are the researcher's intended candidates, not verified availability claims.

## Verification status on 2026-10-07

| Provider | Intended display family | Exact API ID | Status | Official documentation source | Snapshot classification |
|---|---|---|---|---|---|
| OpenAI | GPT-5.6 Sol | Unresolved; null | Disabled / unresolved | [Official model catalog](https://developers.openai.com/api/docs/models) | Unknown |
| Google | Gemini 3.8 Flash | Unresolved; null | Disabled / unresolved | [Official model catalog](https://ai.google.dev/gemini-api/docs/models) | Unknown |
| Anthropic | Claude Sonnet 5.5 | Unresolved; null | Disabled / unresolved | [Official model overview](https://platform.claude.com/docs/en/about-claude/models/overview) | Unknown |

Read-only HTTPS attempts to all three official sources on 2026-10-07 failed with `Tunnel connection failed: 403 Forbidden`. No official page content was obtained. Therefore **no exact API identifier has been verified**, and no candidate identifier is inserted into configuration. The proposed `gpt-5.6-sol` and `gemini-3.8-flash` identifiers are user-supplied candidates only; they have not been validated. No Anthropic identifier was guessed or substituted.

In [pilot_eval.yaml](../configs/pilot_eval.yaml), verification_date records this unsuccessful attempt date for unresolved entries; status and notes explicitly distinguish it from successful verification. All model_id and immutable_snapshot values are null, all parameter-support fields unresolved, and `models: []`. This matrix is a reproducible record of an unresolved selection, **not a completed executable model freeze**. The dry-run previews 40 × 2 × 3 = 240 hypothetical requests, with 0 enabled requests.

## Requirements before enabling

Obtain current official documentation for each intended family. Record the exact API ID, successful verification date, official source URL, immutable_snapshot boolean and availability/parameter notes. Prefer immutable dated/versioned snapshots where the provider offers them. If only a moving/stable alias exists, record the alias and its limitation; raw response metadata records reported_model/modelVersion when exposed, otherwise null. A reported version is provenance, not proof that the provider is fully reproducible.

Verify model support for temperature 0 **and** top_p 1 together, max_output_tokens 512, the chosen REST endpoint and generation seed. Individual parameter support does not prove that their combination is accepted. Set each parameter_support value to supported or unsupported only after verification. Required temperature/top_p/token settings cannot be silently omitted or changed: incompatible models are blocked pending a prospective protocol revision. A generation seed may be unsupported, as allowed by the frozen protocol; then it is omitted and logged explicitly. No reasoning-effort, thinking-budget, tool, browsing, retrieval or structured-output settings are added by these adapters. Review provider defaults and token-budget implications before enabling a reasoning model.

Set status verified only after identifier and compatibility verification; the config's models list must exactly project the verified matrix entries in matrix order. Disabled/unresolved entries never become requests. Configuration validation checks consistency and official URL hosts, but cannot authenticate a maintainer's verification assertion. Commit the completed matrix and execution code before collecting model outputs, and obtain explicit approval for live calls. No adapter compatibility claim for these intended families has yet been demonstrated.

Model availability, aliases, API schemas, defaults and pricing can change. Reverify and prospectively version changes; do not replace a model mid-run. The three REST adapters have only synthetic mock tests. A later approved sanity test should select one verified model, at most 3 scenarios and post_update only. No such test was run in this milestone.
