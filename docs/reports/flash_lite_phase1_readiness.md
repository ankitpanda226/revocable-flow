# Flash-Lite Phase 1 readiness review

Date: 2026-10-08. No generation requests or workflow triggers. A local read-only verification commit is authorized; no push is authorized in this turn. Phase 1 and Phases 2–4 remain disabled. This review supplements the prior offline compatibility audit; no frozen research definitions or prior experimental outputs are changed.

## Evidence status

| Check | Status | Evidence and limitation |
|---|---|---|
| Account model availability | Researcher-reported verified | Run https://github.com/ankitpanda226/revocable-flow/actions/runs/37854150199; observation date 2026-10-08 UTC; listed=true and generateContent advertised |
| Original diagnostic artifact | Pending | Not present locally; no GitHub API retrieval attempted from this blocked environment. Prepared manual preservation workflow; not published or triggered |
| Temperature=0 | Unresolved | Candidate-specific acceptance not established; no inherited 3.8 omission |
| top_p=1 (topP) | Unresolved | Candidate-specific acceptance not established |
| seed=20261007 | Unresolved | Must establish support or document a separately reviewed explicit omission under the existing protocol |
| max_output_tokens=512 (maxOutputTokens) | Unresolved | Required output setting; no evidence permits changing it |
| Structured JSON support | Optional; unverified for exact model/adapter | Existing frozen prompt requests JSON; adapter sends no responseMimeType/responseSchema. No API-enforced schema is silently added |
| Project Free tier | Owner attestation preserved | Default Gemini Project displays Free tier/Set up billing; paid billing not enabled. Evidence file hashed in policy |
| GitHub secret-to-project binding | Unresolved | Successful models.list does not report the API key's owning project; secret value is not readable through GitHub Secrets API |
| Current quotas | Unresolved | No project-specific RPM/TPM/RPD usage/limits/reset evidence supplied; official quota documentation inaccessible |
| All-provider spend and remaining budget | Unresolved | $4 maximum; actual spending including errors and other providers has not been reconciled. No dollar guarantee from request caps |
| Phase selection and request caps | Implemented offline | Phase 1 selects one post-update request, one attempt; later phases stay disabled |
| Frozen definitions | Verified locally | Original 40-case benchmark, prompts, labels, scoring and original model matrix remain unchanged |

Official public model, GenerationConfig, structured-output, pricing and rate-limit documentation retrieval all failed with URLError. No HTTP status was available. The sanitized access record is docs/evidence/flash_lite_documentation_access_2026-10-08.json. No exact-model parameter acceptance, quota values, current spending or remaining budget is inferred from inaccessible sources. Generic API field descriptions and essential/optional/live-only distinctions are documented in the compatibility audit. API-enforced JSON settings are not sent and are not a required readiness gate. Previously researcher-verified free standard-text pricing remains recorded with that provenance.

## Prepared artifact preservation

.github/workflows/preserve-flash-lite-diagnostic.yml is workflow_dispatch only, main only, first attempt only, with contents:read/actions:read. It validates the fixed source run's workflow, branch/event, attempt, successful completion and exact head commit 712193f0f48d4154e9fd087ae35a6f869f4e6438. It downloads only flash-lite-availability from run 37854150199. No Google secret or endpoint appears in this workflow; it uses the scoped GitHub token only for GitHub reads.

The offline helper treats downloaded bytes as untrusted data. It rejects unexpected files, symlinks, credential/environment fields, token-like material, unsafe model metadata, mismatched model/method/run/commit and existing output destinations. It preserves diagnostic and source metadata bytes exactly, with SHA-256 provenance. Upload is limited to the inspected directory containing those two files and a preservation manifest. It never imports/executes downloaded content or edits the pilot policy. Artifact: flash-lite-verified-evidence, retention 90 days.

This workflow is a prepared fallback, not completed artifact retrieval. If the original artifact expired or is unavailable, it fails rather than reconstructing or rerunning the diagnostic. Safe direct upload of the original downloaded artifact is also acceptable. After separate push/publication approval, the owner could select Actions → Preserve verified Flash-Lite diagnostic (read-only) → Run workflow on main, then download flash-lite-verified-evidence. Do not trigger or push it as part of this task; only local commit of read-only work is authorized.

## Minimum safe actions before Phase 1 approval

1. Preserve the real availability artifact by safe direct upload or separately approved publication/manual use of the prepared read-only workflow. Inspect its original bytes and hashes locally.
2. Supply official candidate-specific parameter/structured-output documentation or accessible saved copies with source URLs and dates. Resolve each required setting without inventing compatibility, changing frozen prompts/settings, or inheriting 3.8 exceptions.
3. In Google AI Studio, verify that the key used to configure GitHub's GOOGLE_API_KEY belongs to Default Gemini Project. Record only a nonsecret project reference and owner-confirmed binding. Do not paste the key, dump environment variables or include it in artifact metadata. Record the project's current tier and RPM/TPM/RPD limits, remaining usage and reset timing immediately before launch. If binding cannot be established, keep disabled; an owner-controlled secret rotation tied to a known project could be separately approved.
4. Reconcile actual cumulative expenditure across all providers against $4, including uncertain failed-request billing. Preserve a sanitized owner-reviewed spending record and current free-tier/quota evidence. Do not fabricate zero spending or assume free-tier listing establishes all-provider spend.
5. Review a prospective enablement update and explicitly approve only Phase 1: one post-update request, one attempt. Phases 2–4 require separate approvals and fresh budget/quota reviews. None is enabled by this review.

Until those checks pass, no generation approval is requested. The immediate useful action is evidence preservation and review.

## Final validation and scope

The local commit contains completed provenance, attestations, compatibility/readiness documentation, the optional manual read-only artifact-preservation workflow/helper/tests and verification-gate corrections. No generation feature is enabled; no Google endpoint is called by that workflow. It does not rerun the diagnostic. The original artifact remains unavailable locally; prepared retrieval is not completed retrieval.

Required parameters and key-to-project binding remain unresolved. Phase 1 selects only one post-update case/attempt but stays disabled. Phases 2–4 remain disabled. Missing exact-model evidence cannot be replaced by a generic API field list or synthetic tests. All-provider expenditure is unknown; the $4 maximum remains enforced through explicit owner review, not a claimed dollar guarantee from request limits.

Offline validation: 188 tests passed with live HTTP transport blocked. Benchmark validation, credential scanning and diff checks passed. Benchmark SHA-256 remains 17e4da22029b31b280fcf711bec9c88f261f01ee40dd45137a2ad2540ed4c80d. No prior experimental result files were edited. This read-only verification work is committed locally under the owner identity; no push, workflow or generation is authorized or performed.
