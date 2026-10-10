# Flash-Lite next-four offline preparation

This preparation has **not** been authorized for execution. No generation request,
workflow dispatch, commit, or push was made during preparation. Later pilot phases
remain disabled in the original configuration and policy.

## Verified provenance

The source is compatibility run [37891267903, attempt 1](https://github.com/ankitpanda226/revocable-flow/actions/runs/37891267903).
The owner-uploaded ZIP has SHA-256
`f19ba9b07712a9cb301b2f374d93ecac5d0219bff048f569c810157b80dd59b1`.
The local bridge independently verified all nine scientific records against their
byte hashes, the original canonical manifest hash
`8b79d3e2c75a603e1d1bd5e0490b5132dcf271af20d84189725c44549419a273`,
the exact disabled configuration bytes, benchmark/metadata copies, frozen prompt,
started claim, raw response, parsed scoring record, completion hash, and dispatch
audit. The original HTTP 200 attempt was one request with zero retries.

The bridge hash is
`a0ed2f880c8c234af56050ee088fbc07d4ed73f2773e1b806e2196317f5f6dfa`.
The ignored local snapshot is
`results/prepared/flash-lite-next-four-v1/bridge.json`. Original artifacts and ZIP
remain byte-for-byte preserved under `results/verified/` and outside Git.
MacOS packaging metadata remains preserved with the original ZIP; it is not a
scientific record or an upload candidate.

The ledger contains exactly one terminal compatibility identity:
`google / gemini-3.5-flash-lite / scope_change-09 / post_update / repetition 1`,
request key `model-01/post_update/001`. Its strict primary parse is **invalid_json**
(`parse_status: invalid`), with unknown privacy violation and over-refusal.
It consumes its dispatch slot even though the model output was invalid.
The separately documented fence-removal analysis is excluded from the bridge's
primary scoring and from dispatch eligibility.

## Proposed requests

These are derived by subtracting the completed identity from the frozen ordered
campaign schedule, then taking the next four. They are not selected by assuming
that numeric indices always imply eligibility. All use provider `google`, model
`gemini-3.5-flash-lite`, condition `post_update`, and repetition **1**.

| Execution index | Scenario | Request key |
| --- | --- | --- |
| 2 | purpose_change-04 | model-01/post_update/002 |
| 3 | consent_revocation-03 | model-01/post_update/003 |
| 4 | scope_change-07 | model-01/post_update/004 |
| 5 | consent_revocation-08 | model-01/post_update/005 |

Prompt hashes are recorded in the bridge and checked against frozen messages.
Scenario IDs and gold labels are offline metadata only, never added to outbound
messages. The existing generationConfig is unchanged:
`temperature=0, topP=1, seed=20261007, maxOutputTokens=512`.
No JSON MIME setting or response schema is added. The frozen strict parser and
primary scoring remain authoritative.

## Proposed manual workflow and inputs

`.github/workflows/flash-lite-next-four.yml` accepts only `workflow_dispatch` on
`main`, attempt 1. There is no model, phase, source-run, or scenario selector.
It checks the fixed predecessor's GitHub metadata, downloads its existing artifact,
and validates the pinned records before exposing the Google secret to execution.
Missing or expired source artifacts stop preflight. It does not rerun a diagnostic.

Every dispatch requires a **fresh owner review**, with these booleans defaulting
to false:

- `four_requests_approved`: separately approve exactly the four identities above.
- `key_project_binding_confirmed`: verify that the GitHub secret's key belongs to
  the reviewed Google project. Prior API success does not establish this binding.
- `free_tier_no_paid_billing_confirmed`: recheck that this project is Free tier
  with no paid billing configured.
- `quota_review_confirmed`: review current shared project quota and consumption.
- `all_provider_budget_review_confirmed`: reconcile actual cumulative spending
  across all research providers, below the overall **$4** ceiling.

Required numeric inputs default to empty:

- `reviewed_spend_usd`: known, finite actual cumulative spend, `0 <= spend < 4`.
- `available_rpm_requests`: current headroom, at least 4, at most attested 15.
- `available_rpd_requests`: current headroom, at least 4, at most attested 500.
- `available_tpm_tokens`: at least **12,022**, at most attested 250,000.

The TPM floor is outbound JSON byte length plus four output caps. It is a
conservative operational heuristic, **not** verified provider token accounting.
Concurrent project users can consume quota after review. Request caps and owner
attestations are **not dollar-denominated spending guarantees**; the permitted
paid-cost policy is zero, but this code cannot independently inspect billing,
key-project binding, or all-provider expenditure. Unknown evidence must block
approval. This offline preparation supplies no fresh billing or spending evidence.

## Dispatch and preservation controls

The dedicated workflow shares the existing campaign concurrency group. Its
read-only history guard refuses another dispatch after any earlier execution step
was entered, including HTTP failures and invalid model responses. GitHub reruns
are blocked. Preflight-only failures can be corrected without claiming generation.
It also rejects any prior execution of the broader free-tier pilot workflow,
rather than assuming that another workflow's requests are absent.
History access failure or uncertain prior job state blocks execution.

The Python boundary permits only the four exact frozen payloads and endpoint,
each at most once. The existing runner uses exclusive artifact creation,
`resume=False`, a four-call hard cap, and one attempt per identity. There are zero
automatic retries and no follow-up dispatch. HTTP 429, two consecutive HTTP 503s,
or an unconfirmed transport outcome stop the batch early; therefore four is the
intended count and maximum, not a promise to continue through infrastructure
failure. Provider failures are not privacy-evaluation failures.

The new opt-in runner transport-stop flag applies only to this scope and leaves
existing runs' behavior and frozen parser/scorer untouched. Dispatch observations
and a five-identity campaign ledger are saved even on ordinary exceptions. An
ambiguous started claim consumes its slot and is never automatically retried.
A process kill may prevent the final audit or upload; manual artifact/history
review is then required, and the dispatch guard still blocks a fresh batch.

Only inspected research records are uploaded as `flash-lite-next-four-results`,
with separate `source/` and `batch/` trees. Original primary records are copied
exactly, never relabeled or rewritten. Secret values and common encodings, key
patterns, credential fields, environment dumps, unexpected files, and symlinks
are rejected before upload. Existing destinations and run IDs cannot be overwritten.
The original configuration, model matrix, benchmark, prompts, labels, and scoring
are unchanged; in-memory wire permission is restricted to this bounded continuation.

## Validation and next approval

213 offline tests passed, including mocked four-call dispatch, zero repeats of
index 1, invalid-response terminal handling, preservation, overwrite rejection,
tampered source/config/prompt rejection, quota/budget gates, transport stops, and
workflow/history constraints. All 40 benchmark records validate. Benchmark SHA-256
remains `17e4da22029b31b280fcf711bec9c88f261f01ee40dd45137a2ad2540ed4c80d`.
The credential scan inspected 99 repository files with zero findings; original
source staging passed the safe-artifact scan. Git diff whitespace checks passed.
An additional temporary, actual-source simulation made exactly four **mocked**
transport calls and archived all nine source files byte-for-byte. Its responses
and authorizations were synthetic fixtures, not experiment outcomes or owner approvals.

Before execution: review these uncommitted changes; separately approve any commit
and push; then freshly establish all five owner confirmations and numeric inputs.
Only after separate live approval may an owner launch the fixed-four workflow
from GitHub Actions on main. No remaining-post or pre-update phase is enabled.
Artifact availability in GitHub and enforcement of GitHub runner/history behavior
have been tested with mocks locally, not through a live workflow.
