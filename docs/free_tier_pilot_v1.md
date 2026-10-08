# Gemini Flash-Lite research pilot v1

Prepared 2026-10-08 for google / gemini-3.5-flash-lite. This is a separately versioned cohort. Original Gemini 3.8 Flash configuration, artifacts, frozen prompts, gold labels and scoring remain unchanged. Stable model names are not immutable snapshots; provider-reported versions must remain recorded.

## Verification record and execution status

The researcher reports that the manually dispatched account diagnostic succeeded with:

```json
{"requested_model":"models/gemini-3.5-flash-lite","status":"success","target_listed":true,"target_supports_generateContent":true}
```

Report received 2026-10-08. The actual diagnostic verification date, GitHub Actions run URL and downloaded safe diagnostic artifact have not been supplied. They remain null in the policy; the receipt date is not substituted for the observation date. Account access and advertised generateContent support are recorded as researcher-reported successful verification, not independently inspected artifact evidence.

The read-only availability workflow is published at commit 712193f0f48d4154e9fd087ae35a6f869f4e6438. It does not enable this pilot. Listing proves advertised access at that observation, not quota, price, account tier or generation health.

The researcher independently verified stable-model documentation, structured output and standard text free-tier pricing at:

- https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite
- https://ai.google.dev/gemini-api/docs/pricing

Codex could not retrieve those pages or the GenerationConfig reference during this preparation (network URLError). These are researcher-supplied documentation claims. No project-specific Free-tier evidence or actual cumulative spend is available. Free pricing documentation does not establish this project's tier.

**All generation remains disabled:** models=[], model status=disabled, execution_enabled=false, parameter_support_verified=false, account_free_tier_eligibility_verified=false. The live implementation review gate remains set. Preparation and offline validation do not approve generation.

## Four manual phases

| Phase input | Condition | Execution indices | New request cap | Readiness |
|---|---|---|---:|---|
| connectivity | post_update | 1 | 1 | Implemented and mock-tested; live blocked |
| small_pilot | post_update | 2–5 | 4 | Implemented and mock-tested; live blocked |
| remaining_post | post_update | 6–40 | 35 | Implemented and mock-tested; live blocked |
| paired_pre | pre_update | 1–40 | 40 | Implemented and mock-tested; live blocked |

These are 80 distinct condition/index requests, one model and one repetition. The first five post-update cases form the cumulative sanity stage; case 1 is not repeated in phase 2. Pre/post conversations remain independent paired conditions. The benchmark contains exactly the original 40 cases, hash 17e4da22029b31b280fcf711bec9c88f261f01ee40dd45137a2ad2540ed4c80d.

The workflow uses workflow_dispatch only, main only, Python 3.12, run_attempt=1, and serialized dispatch. No phases advance automatically. Each later stage requires the immediately prior successful workflow run and its artifact containing all ancestors. Identity, policy/config/model/prompt/benchmark hashes, started records, responses, reproduced scoring, dispatch audit and completion summary are checked before dispatch.

A read-only GitHub workflow-history guard counts earlier runs whose provider execution step was reached. It rejects duplicate campaigns, missing/extra prior stages, earlier unfinished runs and reruns; the immediate predecessor must be a successful manual main run. An attempted failed phase occupies its slot and requires separately reviewed recovery, rather than fresh repetition. A preflight failure with skipped execution does not occupy a generation slot. This protection depends on retained GitHub workflow history and authentic artifacts: do not delete runs/artifacts to bypass it. Deleting runs can defeat a history-based ledger. Offline direct Python use does not have that remote ledger; owner review and committed workflow execution remain required.

Every case has one attempt. No semantic/invalid-output retries. Stop on HTTP 429, two consecutive HTTP 503 failures, or an ambiguous claim. Caps are explicit in manifests. Original infrastructure retry settings are unchanged, overridden prospectively by lower campaign limits. Completed successes and invalid terminal model answers remain final. Incomplete prior stages block progression. No automatic provider/model switch.

Raw outputs, failure records, metadata, requested/effective parameters, reported version, latency and token usage are preserved. Scores reference raw hashes. Unique run IDs and exclusive writes reject overwrites; artifacts preserve ancestors byte-for-byte. Secret scans and allowlists precede upload, including failed stages. Unsafe artifacts withhold upload rather than altering raw research records. Artifact name: flash-lite-pilot-results, retention 30 days; retain durable copies promptly. A crash after provider dispatch can leave an ambiguous started record and unknown billing; review before any recovery.

## Parameter and Free-tier gates

Requested protocol settings are temperature=0, top_p=1, max_output_tokens=512, seed=20261007. Candidate-specific support for all four remains unresolved. Existing Google wire mappings (temperature, topP, maxOutputTokens, seed) demonstrate adapter implementation, not this model's acceptance. Gemini 3.8 Flash sampling exceptions are restricted to that exact model and are not inherited by Flash-Lite.

Before live enablement, preserve official model-specific parameter evidence with source/date and a matching support matrix. The readiness gate hashes and validates that evidence. Required sampling/output settings cannot be silently omitted. Seed omission requires the existing protocol's explicit unsupported metadata. Structured-output support does not silently add responseMimeType/schema settings: frozen prompts/parser remain authoritative.

The readiness gate additionally requires saved diagnostic bytes/hash and observation run URL/date; saved pricing bytes/hash; saved project-specific tier evidence bytes/hash identifying Free tier, model, project reference, verification basis/date; and explicit implementation approval. These evidence records are owner-reviewed assertions, not independent billing/API entitlement audits. Do not store credentials or sensitive billing details in evidence. The Google project must match the secret's project, confirmed by the owner, before generation approval.

## Budget and manual launch prerequisites

Total research budget is $4 across all providers. Actual cumulative expenditure and remaining funds are unknown, including failed-request billing. No cost estimate is fabricated. Token/request caps are not dollar guarantees. Standard text being free does not establish this project's eligibility or prevent charges after a billing/tier change.

Each phase requires explicit review of project Free tier, current model pricing and quotas, all-provider cumulative spending, and prior run history. Supply reviewed_total_spend_usd as a finite actual total below $4 and budget_review_confirmed=true. The manifest records this assertion and price_guarantee=false, estimated_stage_cost_usd=null. Use provider billing controls where available. If spend, account tier or effective parameters cannot be verified, leave execution disabled.

**Next action is evidence review, not a generation launch:** supply the successful availability run URL/date and safe artifact; preserve candidate parameter documentation; verify the key's project is on the Free tier; reconcile actual cumulative spending across providers. Resolve those gates in a separately reviewed update before approving generation.

Once evidence is verified, configuration is enabled and generation is explicitly approved, the owner could open Actions → Gemini Flash-Lite staged pilot, choose Run workflow on main, select exactly one phase, enter the immediate prior run ID (empty only for connectivity), and supply the fresh budget review. Do not perform these steps now. No workflow or generation request was triggered during this preparation.

## Offline validation and research limits

Tests exercise disabled gates, candidate identity, parameter/tier evidence hashes, budget refusal, all 80 unique mock requests, immutable ancestry, no success replay, quota circuit stops, error preservation, workflow-history guard and safe upload. They establish implementation behavior, not provider compatibility or research performance. Original parser/scorer and complete-paired metric semantics remain authoritative. No live aggregate accuracy, SALR, significance or research conclusions are reported. The aggregate assembler/bootstrap extension remains outside this collection implementation.
