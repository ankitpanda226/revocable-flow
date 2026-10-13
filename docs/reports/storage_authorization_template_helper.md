# Offline helper: copy the whole storage-test template

Prepared for review; no new authorization, commit, push or workflow dispatch was
performed. Production Gemini execution remains disabled. This helper creates
only a synthetic storage-test file after explicit owner confirmation.

## What changes, and what does not

`.github/scripts/prepare_storage_authorization.py` reads the complete JSON template
copied from the waiting job. It changes only `approved_at_epoch` to a current
numeric Unix timestamp and `storage_only_approved` to true. It preserves all other
values and types, including every digit of runner/job IDs, nonce, scope hash and
execution commit. JSON whitespace and key order may change; field meaning does not.
There are no per-field binding overrides, credential requirements or network calls.
It reuses the existing standard-library-only synthetic authorization validator.

The helper accepts only the untouched draft with the exact timestamp placeholder
and approval false. Duplicate keys, invalid namespace/workflow/scope, invalid
binding types and recycled approvals are rejected. It requires the run ID to
match the copied template and explicit owner confirmation of the live waiting
state. File creation is exclusive: an existing file is never replaced. The three
known completed runs are blocked. The check command compares the created file to
the original copied template and checks timestamp freshness before commit.

Offline validation cannot authenticate the copied values against GitHub or detect
a valid integer already mistyped in the input template. For example, `100000016`
is an integer, just as `1000000016` is. The protection is copying the **entire
untouched original**, never reconstructing individual fields, and letting the
waiting runner's exact service-binding verification remain authoritative.
The owner must verify the run is still waiting immediately before committing;
the helper's flag is an attestation, not an independently verified run status.

## Failed-run evidence remains intact

| Completed test | Available evidence | Preservation |
| --- | --- | --- |
| 38342458965 | Owner-reported failed handshake; no authorization in Git | No authorization created; original failure remains historical evidence |
| 38345162374 | Existing approval has incorrect scope and quoted timestamp | SHA-256 `3f93421f730347fe11bb284f57f879dfef802895938a1965132f00bb0ef8ff5d`, unchanged |
| 38348238334 | Existing approval has runner ID `100000016`; owner reports logs expected `1000000016` | SHA-256 `0d63a93a906ec8baee0567f209d70196e4bc63aa7dd897ee16f09ef5e0068358`, unchanged |

Read-only Git fetch and fast-forward synchronized the already existing third
authorization commit; no approval was generated or changed. Original log
templates for these runs are **not independently available**. Tests use the two
actual stored failed records and explicitly labeled in-memory draft reconstructions,
including the expected runner ID supplied by the owner. These reconstructions
are not claimed to be retrieved log templates. The third stored record fails
exact binding comparison against that owner-supplied runner ID. The helper preserves
the larger integer without truncation, rounding or manual re-entry.

## Exact local procedure for the NEXT separately approved fresh test

First separately review/publish this helper and its tests. Obtain separate approval
for a **new** storage-only workflow dispatch; do not rerun a failed run. Keep the
new job's waiting log open in the browser. No Gemini workflow or provider key is
needed. The following are owner commands for a later approved run, not commands
executed by this preparation.

Start from a clean local main and obtain the reviewed helper:

```sh
git switch main
git pull --ff-only origin main
git status --short
```

Stop if the working tree is not clean. In the browser confirm the fresh run is in
progress in **Wait for test-only owner commit then create SYN storage records**.
Copy only its entire printed JSON object, with no log prefixes or Markdown fences.
Save it outside Git using the terminal below: after `cat`, paste the JSON once
and press Ctrl-D. Do not type or edit any binding values.

```sh
storage_template=$(mktemp /tmp/revocable-storage-template.XXXXXX)
cat > "$storage_template"
read -r -p 'New GitHub run ID from the run URL: ' storage_run_id
read -r -p 'Recheck the browser: run is still waiting? Type WAITING: ' storage_status
if [ "$storage_status" != WAITING ]; then exit 1; fi

python .github/scripts/prepare_storage_authorization.py create \
  --template "$storage_template" --run-id "$storage_run_id" \
  --confirm-run-still-waiting
```

If preparation fails, stop. Do not manually repair or reuse an old authorization.
The helper derives the path from the copied run ID and prints it without printing
the nonce or approval contents. It does not commit. Recheck the browser once more
and validate the generated file immediately before staging:

```sh
read -r -p 'Recheck now: the SAME run is still waiting? Type WAITING: ' storage_status
if [ "$storage_status" != WAITING ]; then exit 1; fi

python .github/scripts/prepare_storage_authorization.py check \
  --template "$storage_template" --run-id "$storage_run_id" \
  --confirm-run-still-waiting
```

Stop if check fails, the run has ended, or the ten-minute wait has expired.
Do not commit a stale file. Prepare no approval for any completed run. Stage
**only** the one test file and confirm the index has exactly that path:

```sh
storage_auth="checkpoints/storage_tests/authorizations/run-${storage_run_id}.json"
git add -- "$storage_auth"
python - "$storage_auth" <<'PY'
import subprocess, sys
paths = subprocess.check_output(['git', 'diff', '--cached', '--name-only']).decode().splitlines()
assert paths == [sys.argv[1]], 'Stop: other staged files or missing approval'
PY
```

Do not proceed if the assertion fails. Commit/push only after the successful
check and live browser confirmation, using the exact Git identity:

```sh
GIT_AUTHOR_NAME='Ankit Panda' GIT_AUTHOR_EMAIL='ankitpanda226@gmail.com' \
GIT_COMMITTER_NAME='Ankit Panda' GIT_COMMITTER_EMAIL='ankitpanda226@gmail.com' \
git commit -m "Authorize synthetic storage test run ${storage_run_id}"
git log -1 --format=fuller
git push origin main
```

Verify no co-author trailer was added and the commit contains only the test file.
Never force-push if the remote changed. Return to the same run and confirm
approval acceptance, synthetic artifact creation/upload and download/readback
verification. Retain the original copied template outside Git as test evidence,
along with the run URL, approval commit and manifest digest. Archive synthetic
results in two independent read-back-verified locations as documented in
`storage_only_integration_preparation.md`. Do not modify the scientific ledger.

## Offline checks and remaining limitations

Five new tests cover exact two-field transformation, schema/type/namespace and
scope rejection, known completed-run blocking, owner confirmation, exclusive
creation, post-creation transcription/expiry detection and historical runner-ID
regression. Temporary synthetic fixture files are deleted after tests. The actual
failed authorization files are only read and remain unchanged.

Exact original log-template comparison remains unavailable without owner-provided
logs. No compatibility, billing, production activation or live-status guarantee
is inferred from these tests. A successful storage test remains independent of
all frozen Gemini campaign permissions and scoring.

Validation completed: **261 offline tests passed**, including the five new helper
tests. Benchmark validation and the existing 68-record/13-attempt scientific
provenance check passed. A 134-file credential/generated-output/whitespace scan
found no issues. Both existing authorization hashes match their original Git
bytes, no first-run approval exists, and no new authorization was created. The
frozen benchmark SHA-256 remains
`17e4da22029b31b280fcf711bec9c88f261f01ee40dd45137a2ad2540ed4c80d`.
