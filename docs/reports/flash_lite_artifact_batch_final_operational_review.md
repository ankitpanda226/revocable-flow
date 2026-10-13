# Final offline operational review: artifact batch 014–023

The simplified implementation is ready for owner review and publication **with
live execution disabled**. It is suitable for this trusted, manually operated
research campaign. The privileged Git journal can be abandoned for this scope.
The tradeoff is deliberate: interruptions quarantine the reserved batch; this
implementation does not offer automatic recovery or guaranteed completion.

## Authorization bootstrap and exact owner procedure

An authorization cannot contain a future, unknown GitHub run ID. It must precede
the provider request, not the GitHub workflow dispatch. The implementation resolves
this by waiting in the dispatched invocation, without generating model content.

| Step | Owner action and enforced boundary |
| --- | --- |
| 1. Publish preparation | After separate approval, commit and push the reviewed preparation in its disabled state. Both the workflow execution step and configuration currently disable live execution. No authorization file exists. Publishing does not authorize generation. |
| 2. Preserve predecessor | Retain the original thirteen-result ZIP in two independent locations, read back both copies, verify their hashes and complete scientific provenance, and record the verified archival attestation in a normal owner commit. |
| 3. Approve activation | Obtain separate approval for live activation of only 014–023. Review the activation diff; no later identities may become selectable. No activation was performed in this review. |
| 4. Dispatch once | In Actions, select the fixed artifact-batch workflow and main, then dispatch once. Tests, predecessor verification and dispatch-history checks run first. GitHub supplies the run/job IDs. |
| 5. Wait for authorization | The same executor generates a fresh 256-bit invocation nonce, records exclusive initialization, and prints a public authorization template. It waits up to ten minutes. No provider request occurs during this wait. |
| 6. Owner commits approval | Recheck Free tier/no paid billing, key-project binding, shared quotas and actual cumulative all-provider spend below $4. Fill the exact template and current Unix timestamp; create `checkpoints/authorizations/post_update_014_023.json` once, commit as Ankit Panda and push normally while this invocation waits. Do not dispatch another workflow to deliver approval. |
| 7. Read-only verification | The waiting executor reads main using contents-read/actions-read, checks the file's single introduction commit and Git blob hash, exact run/attempt/job/runner/nonce/execution-commit binding, pinned scope and predecessor hashes, and approval freshness of at most five minutes. Missing or inconsistent approval prevents provider calls. |
| 8. Execute and preserve | Only after verification, the same process may serially attempt the ten pinned identities once each, at least twelve seconds apart. Raw outputs, strict scores, request audits and cumulative ledger snapshots are written with create-only local files. Sealing checks provenance and credentials before artifact upload. |
| 9. Confirm archives | Download the original uploaded ZIP promptly; validate the complete sealed chain independently, retain two verified copies, then commit a small append-only checkpoint summary. A future batch needs its own separately reviewed scope and authorization. No follow-up workflow is dispatched. |

The execution checkout remains the original execution commit while the owner's
authorization commit advances main. The runner does not check out new execution
code from that authorization commit. Use ordinary owner Git credentials for
these commits; the workflow has no repository-write credential.

If the wait expires, the runner is lost, or the authorization is incorrect, do
not edit/delete/repoint the authorization to another invocation. Quarantine and
review the scope offline. A reservation is not evidence that ten calls occurred.

## Dispatch and interruption safeguards

The pinned policy and reconstructed schedule must match exactly: post-update
014–023, Google `gemini-3.5-flash-lite`, repetition one, maximum ten transport
entries, one attempt per identity, zero retries and zero follow-up dispatches.
The bounded transport also checks the exact endpoint and frozen JSON payload.
There is no range input, resume switch or later-phase selector.

The authorization binds the whole scope to one invocation. A different run, job,
attempt, execution commit or nonce cannot reuse it. Exclusive initialization and
started records block same-filesystem restarts. The read-only history guard
rejects overlapping runs, reruns, prior execution, missing/repeated/unfinished
execution steps and uncertain histories. Concurrency is an additional safeguard,
not the persistent reservation mechanism.

| Condition | Required handling |
| --- | --- |
| Invalid JSON | Terminal attempted identity; retain original score and unknown privacy/over-refusal outcomes. Never retry it as unattempted. |
| Confirmed provider error or quota failure | Record failure, consume the attempted identity and stop the batch. Do not assign a model privacy failure. |
| Uncertain transport or claim without response | Preserve available evidence and mark ambiguity. Stop; never infer permission to redispatch. |
| Crash before/after request or before scoring | Keep available immutable records; seal a partial bundle when possible. Partial bundles cannot pass the next-batch verification gate. |
| Lost runner, failed upload or missing artifact | The owner-committed invocation reservation remains. Quarantine the entire scope, including identities whose attempt status cannot be established. No automatic resume. |

This is conservative at-most-once operation under trusted owner/repository
maintenance. It is not an adversarial exactly-once service: an administrator
rewriting authorization history or changing approved code could defeat either
design. Partial-batch closure/recovery requires separate offline review and is
not implemented as an automatic pathway.

## Dual-archive validation

The original predecessor ZIP SHA-256 is
`6143b4d1afd1d8f69d5301df0e670440171618fa61e12a83bb252bba11ef191d`.
Its manifest hash is
`d8d0f646d5f5cbec68262921f9c7a8d0bcb4632db06d93a878a69ae6c54a0af2`.

For each completed batch:

1. Independently verify the seal, all scientific file hashes, raw/parsed scores,
   predecessor bytes, ledger uniqueness, authorization evidence and dispatch audit.
2. Preserve the downloaded ZIP unchanged in two independent owner-controlled
   storage locations. Hash each copy **after reading it back**; both must equal
   the original downloaded ZIP SHA-256. Two paths on one disk, links to one file
   or hashes without retained raw bytes do not establish independent archives.
3. Check each archive's contents against the verified scientific tree. The
   `archival_summary` helper checks the ZIP entries against the sealed files and
   produces ZIP, tree, seal and ledger hashes. Run scientific seal verification
   as well; a ZIP checksum alone does not validate scientific provenance.
4. Store only a small checkpoint summary and non-sensitive archive references in
   Git. Keep receipts append-only and raw ZIPs outside the project repository.
   Mark the two-copy attestation true only after the checks above succeed.
5. Before approving a subsequent batch, retrieve and read back both copies again,
   check both ZIP hashes against the committed receipt, and verify the predecessor
   tree/ledger against its committed hashes. Missing/mismatched copies stop approval.

The runtime checks matching predecessor hashes, the true owner attestation and
two distinct references. It cannot independently prove the physical independence
of storage locations or fetch arbitrary private archival systems. Those checks
are explicit owner responsibilities. The current thirteen-result attestation
remains false; two verified independent copies have not been established here.
Actions' 90-day retention is a download window, not permanent archival storage.

## Offline verification results

- Complete publication unit suite: **245 tests passed**, including mocked interruption,
  duplicate-dispatch, authorization, tamper, provider-error and workflow checks.
  The preceding review passed 256 tests including eleven privileged-journal draft
  tests. Those drafts and tests are preserved outside the checkout and excluded
  from this publication; no simplified-executor tests were removed.
- Actual predecessor verification and mock batch: all **68 original records**
  and **13 terminal attempts** preserved; ten mocked calls, zero duplicate calls
  under a replacement invocation; sealed scientific chain reproduced. These
  mock outputs are not experiment results and temporary simulation files were removed.
- Original strict outcomes remain six valid/joint-correct and seven invalid JSON;
  invalid-response privacy and over-refusal outcomes remain unknown.
- Forty-scenario benchmark validation passed. SHA-256 remains
  `17e4da22029b31b280fcf711bec9c88f261f01ee40dd45137a2ad2540ed4c80d`.
- Tracked HEAD comparison and whitespace checks passed: original prompts, model
  matrix, parameters, labels, parser, scoring and prior tracked results unchanged.
- Credential/content checks passed; no credentials or scientific ZIPs are added
  to the publication files. Original scientific files remain in ignored storage.
- Runtime permissions are contents-read/actions-read; checkout does not persist
  credentials. No GitHub App, Administration permission, privileged checkpoint
  branch, repository-write token or new cloud resource is required.

## Remaining blockers and publication scope

Publication in a disabled state is ready for separate approval. Existing legacy
privileged-journal drafts should remain unpublished unless separately reviewed;
they are not dependencies of the simplified artifact executor. No authorization
record, live enablement or generated mock results should enter that publication.

Live execution remains blocked by both disabled execution controls, absent
run-specific authorization, false dual-archive attestation, and fresh owner
tier/key/quota/spend confirmations. Read-only GitHub polling and service-context
binding have been mocked, not demonstrated in a live Actions invocation. Any
integration discrepancy must fail closed before generation. Shared quota can
change after review; the runner stops on quota/provider failures.

The current byte-based quota headroom floor is 29,372 with at least ten available
RPM/RPD requests required. Inputs must be actual integer availability values, not
ranges or formatted strings. These limits do not establish dollar spending.
Actual all-provider spend and Free-tier/key-project binding remain owner evidence;
the adapter cannot independently enforce account billing. The $4 ceiling remains
a separate approval gate, with no paid-cost authorization for this batch.

No model requests, workflow dispatches, resources or live activation were
performed during this review. Publication of the disabled preparation was
subsequently authorized; no run-specific authorization record is included.

## Next separately approved storage-only integration test

The current disabled executor does not have a storage-only integration mode.
Before testing real GitHub authorization polling, separately review a test harness
that uses a distinct non-experimental authorization path and synthetic identities,
keeps the production execution controls false, excludes the Google secret and
permits no provider transport. Mocked binding tests do not substitute for that
service integration test.

After approving only this storage-only scope, dispatch the harness once, obtain
its GitHub run/job/commit/nonce template, and create its test-only owner approval
record while that invocation waits. Verify content/history/binding readback,
stale/reused-approval rejection, create-only test records and artifact sealing.
Download, verify and retain two read-back-verified archival copies. Record the
integration outcome without adding experimental attempts to the campaign ledger.
No production authorization or activation is needed for this test. Actual batch
generation remains subject to a later, separate approval and all live gates.
