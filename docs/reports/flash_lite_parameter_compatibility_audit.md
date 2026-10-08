# Flash-Lite parameter compatibility audit

Offline source audit, 2026-10-08. Model: gemini-3.5-flash-lite. No provider/workflow requests or generation calls. This audit establishes adapter behavior, not provider acceptance.

## Account and billing observations

Researcher-supplied availability observation: https://github.com/ankitpanda226/revocable-flow/actions/runs/37854150199, verification date 2026-10-08 UTC. Requested models/gemini-3.5-flash-lite; success; listed; generateContent advertised; one read-only request; zero generation. Raw diagnostic artifact remains unavailable locally.

Researcher attests Default Gemini Project is Free tier, displays Set up billing and has no paid billing enabled. Saved in docs/evidence/flash_lite_free_tier_attestation_2026-10-08.json; policy stores its SHA-256. This records an owner statement, not independently retrieved billing evidence. Binding of GOOGLE_API_KEY to that project is not yet confirmed. All-provider cumulative spend remains unreconciled; remaining $4 budget is unknown.

## Requested and prospective effective parameters

| Requested setting | Google wire field | Offline adapter finding | Exact-model acceptance |
|---|---|---|---|
| temperature=0 | temperature | Passed through only when declared supported; required | Unverified; blocked |
| top_p=1 | topP | Passed through only when declared supported; required | Unverified; blocked |
| max_output_tokens=512 | maxOutputTokens | Passed through only when declared supported; required | Unverified; blocked |
| seed=20261007 | seed | Passed through when supported; omission must be explicitly documented in metadata | Unverified; blocked pending review |
| Strict JSON schema | No responseMimeType/responseSchema sent | Frozen prompt requests action/release_fields; parser validates afterward | Provider-enforced structured output not tested or enabled |

Source: src/revocable_flow/providers/google_provider.py and providers/base.py. The adapter maps fields but does not prove that this model accepts those settings. Effective live parameters remain undetermined. Mock tests can verify wire serialization and metadata only. Candidate parameter_support remains unresolved; no supported setting is invented.

GoogleProvider.allowed_omissions returns an empty set for this candidate. The temperature/top_p exception applies only to gemini-3.8-flash. Required unverified sampling/output parameters cannot be silently dropped. Missing support fails before credentials or transport dispatch. The campaign blocks readiness for unresolved required generation parameters, missing hashed diagnostic/pricing records and unverified project binding. API-enforced JSON capability is not required for this frozen prompt/parser-only condition.

The researcher explicitly states model-specific temperature, top_p, seed, maxOutputTokens and structured JSON compatibility has not been independently verified. json_output_verified is therefore false; this supersedes the earlier broad documentation claim for activation purposes. No change to frozen prompts, parser/scoring or structured-output enforcement is proposed. Adding REST schema/MIME parameters would require a separately reviewed condition/configuration, rather than silently modifying this pilot.

## Evidence required before phase 1 approval

1. Supply the safe diagnostic artifact from the recorded run, preserving original bytes and hash.
2. Obtain saved official candidate/model and GenerationConfig documentation establishing acceptance and any restrictions for temperature=0, topP=1, maxOutputTokens=512 and seed. Record URLs/date/hash and the candidate-specific support matrix. If seed is unsupported, document an explicit prospective omission; if a required setting cannot be supported, leave blocked and review a separately versioned proposal. Do not inherit 3.8 exceptions. Clarify documented JSON-output capability without introducing a new API-enforced output condition.
3. Confirm the configured secret belongs to Default Gemini Project; review Free tier and current quotas immediately before dispatch. Reconcile cumulative all-provider actual spending and confirm the $4 maximum. The limits do not independently guarantee dollar spending.
4. Review/approve the evidence and disabled-to-enabled configuration change. Only after that review, explicitly authorize one Phase 1 post-update request, one attempt, no automatic retry. Do not authorize phases 2–4 implicitly.

All four phases are offline implemented and tested; all four remain live disabled. No new run, model outcome, cost or research result is claimed. These evidence updates are authorized for a local read-only verification commit; generation remains unapproved.

## Google API-level specification and exact-model distinction

Official references:

- GenerationConfig REST schema: https://ai.google.dev/api/generate-content#v1beta.GenerationConfig
- Structured output: https://ai.google.dev/gemini-api/docs/structured-output
- Candidate page: https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite

The following is an API-level reference summary, not a newly retrieved or archived quotation. Current official pages were inaccessible in this environment; the access-failure record is preserved. These generic field descriptions do not establish exact-model compatibility or candidate-specific bounds/defaults.

| REST field | API-level specification summary | Frozen pilot use | Remaining verification |
|---|---|---|---|
| temperature | Numeric sampling control | 0 | Exact model accepts value and combined configuration |
| topP | Numeric nucleus-sampling control | 1 | Exact model accepts value and combined configuration |
| seed | Integer sampling seed; reproducibility is not a deterministic guarantee | 20261007 | Exact-model support; explicit documented omission only if unsupported |
| maxOutputTokens | Integer output-token limit | 512 | Exact-model acceptance and model/output-limit restrictions |
| responseMimeType | Output MIME selector; application/json requests JSON output | Not sent | Not required for unchanged pilot; candidate compatibility unverified |
| responseSchema | Schema-constrained output, with JSON MIME and provider-supported schema restrictions | Not sent | Optional separate condition; adding it needs review |

The adapter sends generationConfig with the four requested generation settings once evidence permits them. It does not send responseMimeType or responseSchema. The frozen prompt requires action/release_fields and the parser judges returned text. Removing the unused API-JSON capability from readiness requirements does not modify payloads, scoring or JSON validation, and does not declare that capability verified. The corresponding policy flag remains false.

## Essential, optional and live-only checks

**Essential before Phase 1:** preserve available diagnostic provenance/evidence; establish required parameter compatibility or obtain separate explicit approval for an unverified compatibility probe; confirm the configured secret's project binding and current Free-tier/quota status; review cumulative spending against $4; explicitly approve exactly one request/attempt. Original parameter values, messages, labels and scoring cannot be silently changed.

**Optional research documentation:** immutable archival copies of every generic API guide, independent billing screenshots beyond a reviewed owner attestation, and unused API-enforced schema/JSON capability. Existing conservative file/hash gates still require saved diagnostic/pricing/parameter/tier evidence before the production pilot runner can be enabled; review those gates explicitly rather than forging evidence. The owner-reported availability result is preserved even if the original artifact is unavailable.

**Can only be observed in a live request:** whether this exact model/version/account accepts the combined payload now, actual provider-reported version/usage, output validity and latency. One request cannot establish statistical reliability, seed repeatability, general JSON adherence, ongoing quota health or all-provider spend.

If documentation remains unavailable, a separately approved compatibility probe could send exactly one frozen Phase 1 payload, one attempt, preserving raw/error/metadata. This is a proposal, not implemented or enabled here. It requires project/tier/quota/spending review first and explicit authorization to test unverified parameters. The current evidence-gated runner will not launch it by merely setting parameters to supported. A successful HTTP response establishes acceptance only for that request/version; an HTTP 400 may identify a parameter problem, while 429/503 do not establish incompatibility. Do not silently retry, drop fields, change models, add MIME/schema settings or reinterpret failures as privacy violations. Any reuse as Phase 1 data would require a reviewed prospective provenance decision and must not cause a duplicate call.
