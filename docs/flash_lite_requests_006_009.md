# Offline preparation: Flash-Lite requests 006–009

Status: prepared for review, **not approved or executed**. No provider request,
GitHub dispatch, commit, or push occurred during this preparation. Later campaign
requests remain disabled.

Workflow name: **Flash-Lite requests 006–009 (manual only)**.
Workflow file: `.github/workflows/flash-lite-006-009.yml`.
Pinned scope: `configs/flash_lite_requests_006_009_v1.json`.

## Exact experimental identities

All four use provider `google`, model `gemini-3.5-flash-lite`, condition
`post_update`, and repetition 1. They are the next eligible identities after
subtracting the five terminal attempts from the frozen ordered campaign schedule.

| Request key | Frozen scenario |
| --- | --- |
| model-01/post_update/006 | purpose_change-07 |
| model-01/post_update/007 | consent_revocation-02 |
| model-01/post_update/008 | purpose_change-03 |
| model-01/post_update/009 | scope_change-04 |

Only these four are selectable. This is an operational slice of the frozen
remaining-post schedule, not a new benchmark or a changed experiment identity.
No remaining request or pre-update phase is enabled.

## Provenance and preservation

The source is the owner-uploaded artifact from run 38080218987, attempt 1, with
ZIP SHA-256 `c5343454121c33376baab87f79111b214264f882689d983214455e246ef7357e`.
The scope pins **all 28 scientific files** under its `source/` and `batch/` trees,
manifest `67bb8f91adb75ddf9b69907db1d233f45bff2aa1e8c9de08b9cd49c4ab5c9ba7`,
and source commit `b7b528fcf17324206bca385e6c05b8fdb3700db8`.
It links to bridge `a0ed2f880c8c234af56050ee088fbc07d4ed73f2773e1b806e2196317f5f6dfa`
and the original one-request compatibility attempt 37891267903, attempt 1.

The new bridge hash is
`8921392c2684ebb3954b31caae69fcf2129d3e8e119f84f3a274fd16b08ed37f`.
An ignored offline snapshot is `results/prepared/flash-lite-006-009-v1/bridge.json`.

The existing framework reconstructs the original bridge and first batch manifest,
accounting for recorded host metadata without changing any scientific setting.
It verifies original source bytes, canonical hashes, exact payload byte hashes,
HTTP audit, one-attempt started claims, normalized response records, strict parsed
scores, completion hash, and five unique terminal ledger entries. Altered bytes,
changed model/parameters/prompts/manifests, duplicates, extra files, uncertain
attempts, or a non-complete predecessor fail before any request.

The first five ledger entries are deep-copied into the new ledger and stay
identical. Original ledger files and every prior artifact are copied byte-for-byte
into the new safe upload, nested under `source/`; current records occupy a separate
`batch/`. No original is overwritten or relabeled. Invalid responses 001 and 002
remain terminal attempts and retain their original strict invalid_json scores,
with unknown privacy-violation and over-refusal outcomes. Exploratory fence removal
stays outside execution and primary scoring.

A temporary simulation using the actual verified chain made four **mocked** calls,
produced a nine-entry synthetic ledger with the unchanged five-entry prefix,
and preserved all 28 source files and the original ledger bytes in safe staging.
Simulation authorization and responses were synthetic, not owner approvals or
research outcomes; all newly generated simulation records were temporary.

## Reused framework and dispatch controls

The existing `four_request_bridge.py`, artifact allowlist, dispatch-history guard,
and `flash_lite_next_four.py` entrypoint are extended. The original 002–005 workflow
and scope files remain unchanged. The new workflow invokes the same entrypoint
with fixed `--scope 006-009`; it has no phase, model, source-run, or scenario input.

The existing runner retains exact messages and generationConfig:
`temperature=0, topP=1, seed=20261007, maxOutputTokens=512`. No responseMimeType,
response schema, prompt suffix, primary fence-removal, or parser/scoring change is
introduced. Provider metadata, raw text, strict scores, and errors are retained.

The workflow is workflow_dispatch-only on main, attempt 1, and shares the existing
`flash-lite-pilot-v1` concurrency group with cancel-in-progress false. Read-only
history checks require exactly the verified previous four-request execution, no
prior attempt of this new workflow, and no broader pilot execution. Missing,
ambiguous, rerun, failed, extra, or active predecessor history blocks dispatch.
GitHub provenance checks pin the predecessor run/commit before downloading its
existing artifact. Missing/expired artifacts fail closed; no rerun is initiated.

Locally, an exclusive claim derived from the full four identities is created
before a possible provider call, independently of run ID. An existing claim or
overlapping manifest blocks dispatch, including for invalid responses or provider
failures. A competing process cannot acquire the same claim. The claim is copied
into safe audit artifacts; generated global claim files stay ignored under results/.

The transport boundary admits each exact frozen payload once and caps four new
provider calls. The runner has one attempt per identity, resume=false, no retries,
and no follow-up workflow dispatch. HTTP 429, two consecutive HTTP 503s, or an
unconfirmed transport outcome stop early. Thus four is the intended maximum,
not a promise to continue after infrastructure failure. Confirmed HTTP failures,
invalid outputs, and uncertain outcomes consume their claimed attempt; none is
automatically repeated. Errors receive no model privacy score. Unknown outcomes
are marked ambiguous and require manual review. Unattempted identities remain
explicitly unattempted in the ledger; this workflow still cannot be restarted to
execute them under a different run ID.

Exclusive artifacts prevent overwrite. Upload staging checks all prior hashes,
current raw-to-score links, scope claim, ledger uniqueness, safe paths, credential
patterns, actual secret values/encodings, and forbidden environment/credential
fields. Only inspected scientific source/current records are uploaded as
`flash-lite-006-009-results`. A hard process kill can leave an incomplete claim or
prevent upload; history and claim guards still block automatic duplicate execution.

## Fresh manual authorization and remaining blockers

All confirmation inputs default false; numeric inputs default empty:

- four_requests_approved: separately approve only these four identities.
- key_project_binding_confirmed: verify the GitHub secret belongs to the reviewed
  project, without revealing the key.
- free_tier_no_paid_billing_confirmed: freshly check Free tier and no paid billing.
- quota_review_confirmed: review current shared project RPM/TPM/RPD headroom.
- all_provider_budget_review_confirmed: reconcile actual cumulative all-provider
  research spending below the $4 overall limit.
- reviewed_spend_usd: known finite actual spend, 0 <= spend < 4.
- available_rpm_requests: at least 4 and at most the attested 15.
- available_rpd_requests: at least 4 and at most the attested 500.
- available_tpm_tokens: at least **12,100** and at most the attested 250,000.

The TPM floor uses outbound JSON byte sizes plus four output caps. It is a
conservative headroom heuristic, not provider token accounting or a quota
reservation. Other project use can consume quota after review. Request caps do
not enforce dollar limits. Historical manifest spend/tier/binding attestations do
not constitute fresh approval, independent billing evidence, or a verified
remaining balance. Unknown spend or key-project binding must block approval.
Paid-cost policy remains zero; code cannot independently enforce Google billing.

Current blockers: review these uncommitted changes, separate publication approval,
fresh owner account/quota/budget confirmations, and explicit live authorization.
GitHub workflow/history execution was mocked locally, not exercised through a
live dispatch. The supplied artifact is internally verified; no external GitHub,
provider, or billing log was consulted during preparation.

## Offline validation

**221 tests passed**, including chained provenance, exact 006–009 dispatch,
unchanged five-entry ledger prefix, atomic claim and cross-run duplicate rejection,
uncertain/duplicate/tampered predecessor refusal, fresh quota/budget gates,
HTTP/transport error preservation, zero retries, safe nested archive preservation,
manual-only workflow restrictions, and exact predecessor history checks.
All 40 benchmark scenarios validate. Frozen SHA-256 remains:
`17e4da22029b31b280fcf711bec9c88f261f01ee40dd45137a2ad2540ed4c80d`.
Credential scanning passed for 104 repository files with zero findings;
provenance integrity and diff checks passed. No frozen definitions or prior
experimental results were modified. These changes remain uncommitted.
