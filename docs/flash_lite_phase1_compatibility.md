# Isolated Flash-Lite Phase 1 compatibility test

Preparation date: 2026-10-08 (America/New_York). This is preparation only. No Google request, workflow trigger or push has occurred. Later live execution requires separate explicit approval.

## Fixed scope

Workflow: .github/workflows/flash-lite-compatibility.yml. It is workflow_dispatch only, main only, run_attempt=1, Python 3.12. It has no model, provider, scenario or phase selector. Scope is google / gemini-3.5-flash-lite, post_update, deterministic execution index 1, one repetition, one generation attempt total. HTTP transport prevents redirects and performs no retries. No automatic dispatches or chained workflow transitions exist.

Payload is exactly the previously audited frozen message body: docs/reports/flash_lite_outbound_payload_audit.json. generationConfig is temperature=0, topP=1, maxOutputTokens=512, seed=20261007. All four fields are sent. No MIME/schema/thinking settings are added. Required fields cannot be silently omitted.

The probe reuses the existing runner, parser, scorer and safe artifact archive. It creates one scoped in-memory dispatch entry only after authorization. The base configuration remains disabled, and its exact original bytes/hash are recorded. The probe manifest explicitly records exact_model_support=unverified_under_test, the original disabled model entry, scope and owner approvals. Temporary supported wire-field flags mean permission to send hypotheses under test, not verified model acceptance. No saved research model matrix is marked supported/enabled. The original matrix, frozen benchmark/prompts/labels/scoring and all previous results remain untouched.

The free-tier research campaign remains execution_enabled=false and models=[]. Phases 2, 3 and 4 remain disabled. This workflow never enables them. An isolated compatibility artifact is not automatically a complete research campaign stage or an authorization to collect more data. Review prospective reuse/history alignment before later collection; never repeat a successful request accidentally.

## Required authorization before a request

Every workflow input defaults to false or empty. Preflight fails before the secret is made available to the execution step unless all five statements are true and reviewed actual all-provider spending is finite, nonnegative and below $4:

- one_request_approved: separately authorize exactly one compatibility request with unverified exact-model settings, zero retries.
- key_project_binding_confirmed: verify GitHub's GOOGLE_API_KEY belongs to Default Gemini Project without revealing the key.
- free_tier_no_paid_billing_confirmed: recheck this key's project is Free tier with paid billing unconfigured.
- quota_review_confirmed: review current model quotas/usage before this single request.
- all_provider_budget_review_confirmed: reconcile actual cumulative research spending across all providers.
- reviewed_spend_usd: the reviewed actual cumulative total, not a guess or token-cost estimate.

The project's owner reviewed Free tier, no paid billing, 15 RPM, 250,000 TPM, 500 RPD, displayed peak usage 0 and Spend page No billing configured. That sanitized attestation is preserved in docs/evidence/flash_lite_owner_quota_review_2026-10-08.json. It is not independently retrieved telemetry. Successful prior API use does not identify the configured key's owning project. Zero displayed peak usage is not proof of zero all-provider expenditure. Those two checks remain unresolved until explicitly reviewed by the owner.

The maximum research budget remains $4 across providers. This test authorizes no paid generation, relying on the owner-confirmed Free-tier/no-paid-billing account review. The workflow's spending input and request/token limits are not an independently enforced dollar guarantee. If binding, tier, quota or spending is unknown, leave inputs false/empty and do not launch. No credential value is requested as an input or stored in metadata. GOOGLE_API_KEY comes only from GitHub Secrets in execution/inspection steps.

## Attempts, duplicates and artifacts

A serialized GitHub workflow-history guard rejects any prior dispatch that reached this compatibility execution step, including failed or ambiguous attempts. It rejects prior unfinished runs and reruns; failures before a skipped execution step can be reviewed separately. No workflow rerun is permitted. This guard depends on retained authentic GitHub run history: deleting runs can undermine it. Exclusive local started records, unique run IDs, a one-call transport boundary and max_provider_requests=1/max_attempts_per_request=1 provide additional protection. There is no resume/retry entrypoint.

Before transport, the runner records an exclusive started request and immutable manifest. Responses preserve raw output, requested/effective parameters, provider-reported model/version, request ID, latency and usage where returned. Existing REST normalization omits provider error bodies and logs safe HTTP/category metadata instead. A dispatch audit records HTTP status, one-call count, body hash, transport exception type without messages, normal termination and uncertainty. A process kill may leave only a started claim: never interpret that as safe to repeat.

Safe upload preserves manifest, benchmark copies, raw started/response records, parsed scores, analysis index, completion summary and dispatch audit. No files are overwritten. Credentials, environment fields and unexpected files withhold upload; raw research records are never redacted to force upload. If an unsafe response is refused, only sanitized observations and an incomplete started claim may remain. The artifact name is flash-lite-compatibility-results, retention 90 days. Download promptly to durable storage.

HTTP/provider errors remain infrastructure failures and do not generate privacy-evaluation scores. HTTP success with malformed JSON is a terminal model output evaluated under the frozen parser, with no semantic retry. Neither three-case historical sanity data nor this one case establishes accuracy, SALR, significance or research conclusions. The compatibility question concerns current acceptance of this exact payload; one success does not prove parameters were honored, seed determinism, general JSON reliability or future quota health.

## Exact future approval and launch sequence

1. Review and approve pushing the preparation commit separately. No push is performed in this task.
2. Confirm key-to-project binding, refresh Free-tier/quota review and reconcile cumulative all-provider actual spending below $4. Do not expose the API key or upload billing credentials.
3. Explicitly approve: “Authorize one gemini-3.5-flash-lite post_update compatibility request with temperature=0, topP=1, seed=20261007, maxOutputTokens=512; one attempt, no retry; no other phases.” This preparation instruction is not that approval.
4. After publication and that separate approval, open repository Actions → Flash-Lite Phase 1 compatibility (one request only) → Run workflow → main. Check all five inputs only if true and enter reviewed_spend_usd. Click Run workflow once.
5. Review/download flash-lite-compatibility-results. Inspect dispatch audit, raw response/error, parsed score and completion metadata. Stop after the one attempt, even on HTTP 429/503, invalid JSON or unknown outcome. Do not rerun or advance phases.

No additional model diagnostic is needed to prepare this trial; the original availability run reference remains preserved. Original diagnostic artifact preservation can proceed separately without generation, but does not establish exact-parameter runtime acceptance.

## Preparation validation

199 offline tests passed with live HTTP transport blocked. Benchmark validation, credential scans, JavaScript syntax and Git diff checks passed. Frozen benchmark SHA-256: 17e4da22029b31b280fcf711bec9c88f261f01ee40dd45137a2ad2540ed4c80d. No project API key was printed or persisted. Preparation is committed locally under Ankit Panda; no push, workflow trigger or generation is performed.
