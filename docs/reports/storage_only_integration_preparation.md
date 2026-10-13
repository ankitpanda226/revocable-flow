# Storage-only owner-authorization integration preparation

Status: prepared for review, uncommitted and not dispatched. This is a synthetic
storage test, not a research experiment. Production batch 014–023 remains disabled
in both policy and workflow. No production or test authorization file was created.

## Exact isolation boundary

- Workflow: `.github/workflows/storage-only-integration.yml`.
- Display name: **RevocableFlow storage-only authorization integration (SYN test)**.
- Helper: `.github/scripts/storage_only_integration.py`, using only Python's
  standard library. It imports no project modules, provider adapters, scoring,
  runner or campaign ledger implementation.
- Test identities: `SYN-STORAGE-ONLY-001` and `SYN-STORAGE-ONLY-002`.
- Namespace: `SYN-STORAGE-ONLY-v1`; nonce prefix: `storage-only-v1:` followed by
  256 freshly generated random bits. Neither matches production authorization.
- Test authorization path: `checkpoints/storage_tests/authorizations/run-<GITHUB_RUN_ID>.json`.
- Artifact name: `SYN-storage-only-integration-results`.
- Output locations: runner temporary `storage-only-results` and
  `storage-only-readback`, never the scientific campaign or checkpoint directory.

The workflow is manual-only, main-only and attempt-one-only. It supplies no
provider secret, installs no project package, and runs only the standalone
storage-test unit suite. It checks the unchanged production disable controls and
absence of the production authorization file before starting its handshake.
The helper also refuses to proceed if a known provider key is present.

The only custom HTTP operation is a GET to allowlisted GitHub run/job metadata,
the exact test authorization path on main and that path's commit history.
Redirects, arbitrary paths and provider destinations are rejected. Standard
checkout/setup/upload/download Actions need their usual GitHub/toolchain network
access; this test is not a claim that it has no network access at all.
`GITHUB_TOKEN` has contents-read/actions-read. No runtime repository writes, App,
Administration permission, approval environment or provisioned cloud backend is
needed. No Google, OpenAI or Anthropic credential is bound to any step.

The synthetic executor can only write two fixed deterministic fixtures. Every
manifest/audit explicitly states zero provider requests, no scientific observation,
zero campaign ledger writes and no production activation. There are no model
responses, labels, privacy scores or protocol request keys. No scientific importer
or ledger updater is invoked. The bundle's namespace and filenames differ from
the scientific artifact formats, and its records cannot satisfy the existing
frozen campaign verifier.

## Authorization handshake

The initial Actions dispatch grants permission to run a storage test, not model
generation. After checking GitHub's actual run ID, head SHA, workflow path,
attempt and current job, the helper creates an exclusive invocation record with
`generation_authorized: false`. It prints a template and waits up to ten minutes.
No synthetic result is created until the owner approval is verified.

The template binds repository, actual run/attempt/job/runner IDs, exact execution
commit, fresh nonce, test-only workflow and scope hash. The owner must create it
once on main, set `storage_only_approved` to true and supply the current Unix
timestamp. GitHub content readback and the path's one-entry history must agree
with its Git blob hash and introduction commit. Approval must be at most five
minutes old when accepted. The execution checkout remains its original SHA while
the owner's ordinary approval commit advances main.

Wrong run/nonce/job/commit/scope, reused or edited paths, wrong namespace,
malformed/duplicate-key/nonfinite JSON and stale/future timestamps fail closed.
Reruns are skipped by the attempt-one guard; process restart cannot overwrite an
existing invocation. Failure or timeout creates no synthetic execution artifacts
eligible for upload. A new test run needs a new run-specific test-only approval.
Never reuse an old approval or repoint production authorization to this test.

This copies the relevant service-binding protocol without importing the
production executor. A successful test establishes storage-handshake integration,
not permission to generate, exact-model compatibility or production readiness.

## Expected manual GitHub procedure — only after separate approval

1. Review and separately approve publication of these four preparation files.
   Publish them without changing the production disable controls. No approval
   record should be included in that preparation commit.
2. Separately approve dispatch of this storage-only integration test. In GitHub
   Actions choose **RevocableFlow storage-only authorization integration (SYN test)**,
   select main and click Run workflow once. Do not select the production workflow.
3. Open the current job's **Wait for test-only owner commit then create SYN storage
   records** log. Copy its exact template and displayed run-specific path.
4. While that invocation is waiting, create only that test authorization file.
   Set the timestamp to the current Unix time and `storage_only_approved: true`;
   leave the binding and scope hash exactly as printed. Commit/push with normal
   owner credentials as Ankit Panda, without co-author trailers. Do not dispatch
   a second workflow to deliver approval, edit/reuse an existing test record,
   or create a production authorization. This preparation did none of these actions.
5. Confirm the run verifies approval, creates the SYN fixtures, uploads the test
   bundle, downloads it into a separate directory and verifies the manifest and
   every record against the original manifest SHA-256. Record run URL, attempt,
   execution SHA, test authorization commit and manifest SHA-256 from its output.
6. Download the original ZIP immediately and perform the archival procedure below.
   GitHub's 90-day retention is not permanent archival storage.

Negative authorization cases are exercised offline with mocks. Do not intentionally
edit an approval file in a successful integration run to demonstrate rejection.
Any separately approved live negative test must use its own synthetic run/path.

## Artifact verification and two-copy readback

The bundle has seven fixed JSON files: invocation, authorization evidence, scope,
audit, two synthetic fixtures and `test-manifest.json`. The manifest authenticates
each other file's SHA-256 and a canonical tree hash. Its own SHA-256 is printed by
the creating job and supplied to the later readback step; do not trust a hash
invented from an unverified replacement artifact. The verifier also checks exact
synthetic content, authorization evidence and zero-call/no-production audit fields.

Keep the downloaded ZIP unchanged and copy it to two independent owner-controlled
storage locations. Two directories on one disk or aliases to one file are not
independent archives. For example, once the script is published, run locally:

```sh
python .github/scripts/storage_only_integration.py extract \
  --archive '/archive-A/SYN-storage-only-integration-results.zip' \
  --root '/temporary/new-storage-test-extraction' \
  --manifest-sha256 "$EXPECTED_MANIFEST_SHA256"

python .github/scripts/storage_only_integration.py archives \
  --root '/temporary/new-storage-test-extraction' \
  --copy-a '/archive-A/SYN-storage-only-integration-results.zip' \
  --copy-b '/archive-B/SYN-storage-only-integration-results.zip' \
  --manifest-sha256 "$EXPECTED_MANIFEST_SHA256"
```

Set `EXPECTED_MANIFEST_SHA256` to the digest recorded from the creating run.
Extraction accepts only the known, bounded JSON records, rejects unsafe ZIP
paths/duplicates/encryption/symlinks and never executes archived content.
The archive command reads back both whole ZIPs, requires matching SHA-256s and
checks every archived scientific-free test record against the verified file tree.
Aliases/hard links are rejected. Physical independence is explicitly an owner
verification requirement, not a claim that the helper can inspect storage topology.
Record both non-sensitive archive references, ZIP hash, manifest/tree hashes and
run/test-authorization provenance in separate **test** archival bookkeeping, not
the campaign ledger. Do not put ZIPs, credentials or test outputs in project Git.
Read back both copies again before relying on this archived integration evidence.

## Existing scientific predecessor availability

The local original `flash-lite-010-013-results.zip` is available and its SHA-256
was checked against the committed predecessor receipt:
`6143b4d1afd1d8f69d5301df0e670440171618fa61e12a83bb252bba11ef191d`.
The extracted 68 scientific records and thirteen-entry ledger passed the existing
provenance verifier again, including unchanged strict invalid responses.

Current remote availability of the Actions artifact from run 38110745024 was not
checked; no GitHub API was called during this offline preparation. Do not assume
Actions retention has preserved it. Use the verified local original for archival
backup if the remote copy is unavailable. Preserve it unchanged in two independent
locations, run `sha256sum` on each copy after readback and require both digests to
match the receipt above. Verify the extracted scientific tree/ledger with the
existing checkpoint verifier. Only then may the owner record true independent
archival confirmation in the scientific checkpoint summary under separate approval.
The existing attestation remains false. Scientific backups are still required
before production continuation, but are not a generation prerequisite for this
independent synthetic storage test, which performs no generation.

## Validation and remaining blockers

Eight new offline tests cover positive waiting/commit readback, stale and malformed
approval, wrong binding/scope, reused/edited authorization, timeouts, blocked
provider credentials/network destinations, immutable writes, copied-artifact
readback/tampering, safe archive extraction and dual-archive validation.
All network/service responses in those tests are mocked; no service integration
has yet been demonstrated.

The full offline suite passed **253 tests**, including the eight storage-only
tests. Benchmark validation, actual predecessor provenance verification, a mocked
batch-preservation simulation and credential/whitespace scans passed. The scan
covered 128 publication files with no findings. Tracked HEAD comparison passed;
only the four new storage-test preparation files are untracked. The frozen benchmark hash is
`17e4da22029b31b280fcf711bec9c88f261f01ee40dd45137a2ad2540ed4c80d`.
No frozen results, prompts, parameters, scores or production controls were edited.

Remaining blockers: separate publication and storage-test dispatch approval,
actual GitHub run/job/content-history integration, a future test-only owner commit
while the approved invocation waits, and owner-verified archive independence.
Storage success never satisfies the production live-authorization, tier/key/quota
or $4 all-provider spending gates. No commits, pushes, workflows, model/API requests
to providers, credentials or cloud resources were created by this preparation.
