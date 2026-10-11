# Offline preparation: Flash-Lite requests 010–013

During offline preparation, no generation or diagnostic requests, workflow
dispatches, commits, or pushes were performed. This prepares a fixed batch for separate approval, not broader pilot
execution.

Workflow: `.github/workflows/flash-lite-010-013.yml`, displayed as
**Flash-Lite requests 010–013 (manual only)**.
Pinned configuration: `configs/flash_lite_requests_010_013_v1.json`.

| Request key | Frozen scenario |
| --- | --- |
| model-01/post_update/010 | scope_change-08 |
| model-01/post_update/011 | scope_change-01 |
| model-01/post_update/012 | consent_revocation-10 |
| model-01/post_update/013 | recipient_change-08 |

## Provenance verification

The source is the locally preserved owner-uploaded artifact attributed to GitHub
Actions run **38108369312, attempt 1**, ZIP SHA-256
`5bbf9d941b5a79dd003aeef8a48213f3b00c0d6699e460739ef708b10b800230`.
Its manifest canonical hash is
`d6e171d481188b3ec3835c8f441f48b0a6d0c8c650605b33a47af56b8f1e6bdb`.
The scope pins all **48** scientific files byte-for-byte, including the inherited
28 files. Recursive verification reproduces each predecessor bridge and manifest,
checks payload, response and score hashes, started claims, dispatch audits,
completion records and scope claims. Source ZIP attribution to GitHub remains
owner-provided until the future workflow's read-only run-provenance gate executes.
No GitHub API request was needed for this offline preparation.

The bridge contains exactly nine unique terminal identities, 001–009, including
invalid responses 001, 002, 006 and 008. These are completed attempts and cannot be
redispatched. Primary privacy-violation and over-refusal values for invalid
responses remain unknown. Fence removal remains exploratory only. The new bridge
canonical hash is
`9df3a0effb65cc7b848542826937f28cf23fc1463857b5224285569ccd757736`.

## Safety and unchanged protocol

The existing fixed-batch bridge, CLI, runner and artifact safety infrastructure
are reused. A third explicitly enumerated scope is added; no arbitrary index or
phase selector is introduced. Historical manifest reconstruction tolerates its
already-existing dispatch claim only in private read-only source validation.
Every actual dispatch still performs fresh overlap checks and an exclusive atomic
claim. The previous batch workflows and scope pins remain unchanged.

The workflow is `workflow_dispatch` only, main branch, attempt 1 only, with the
shared campaign concurrency lock. Read-only history guards require the exact
completed predecessor runs and reject previously entered execution steps,
including failed or invalid-output attempts. Missing, repeated or unfinished
execution-step history now stops instead of being treated as an unused slot.
Local claims and overlapping manifests provide additional fail-closed checks. There are at most four new calls,
one attempt per identity, zero retries, no follow-up dispatch and no later phase
selection. Rate limiting, consecutive service failures and uncertain transport
outcomes stop the batch; records are preserved and not automatically retried.

Model remains Google `gemini-3.5-flash-lite`, post_update, repetition 1. Outbound
`generationConfig` remains `temperature=0`, `topP=1`, `seed=20261007`,
`maxOutputTokens=512`. No `responseMimeType`, prompt edits or fence normalization
are added. The original model matrix and campaign enablement stay disabled.
Benchmark SHA-256 remains
`17e4da22029b31b280fcf711bec9c88f261f01ee40dd45137a2ad2540ed4c80d`.
Frozen labels, strict parser, scoring and all preceding results remain unchanged.

## Offline validation and execution blockers

230 offline unit tests passed, including new recursive-chain, exact identity,
unknown invalid-score outcomes, byte preservation, duplicate/overlap rejection,
fixed wire parameters, four-call limit, quota/approval rejection, HTTP/transport
failure handling, safe archive and mocked GitHub history tests. Benchmark
validation passed for all 40 scenarios. Diff whitespace, frozen-file integrity
and credential scans passed.

A separate temporary mock simulation used the actual 48-file source, generated
four explicitly synthetic responses, preserved the nine-entry prefix exactly,
archived the source byte-for-byte and rejected repeat dispatch. Synthetic outputs
were confined to a temporary directory and deleted; they are not research results.
The computed conservative byte-based quota-review floor is **12,434** tokens.

Execution remains unauthorized. Before any future run, the owner must freshly
confirm key-project binding, Free tier/no paid billing, current shared RPM/TPM/RPD
headroom, actual cumulative all-provider spending below $4, and approval for only
010–013. Quota fields require individual integer values, not ranges or formatted
numbers; RPM must be 4–15, RPD 4–500, TPM 12,434–250,000. These historical upper
limits must agree with the freshly reviewed account; changes require review.
Neither quotas nor request caps guarantee the $4 dollar limit. Account billing,
secret-to-project binding and spending cannot be independently established by
local artifact verification. The source artifact must still be downloadable by
GitHub Actions; expiry or inconsistent run history stops execution.

At the offline preparation checkpoint, these changes were uncommitted and
unpublished. Publication authorization is separate from live execution approval. All other post-update and
pre-update identities remain unavailable through this workflow. Any continuation
needs separate review and authorization.
