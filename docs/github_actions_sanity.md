# Manual Gemini sanity workflow

[gemini-sanity.yml](../.github/workflows/gemini-sanity.yml) is workflow_dispatch only. It never runs on a push, pull request or schedule, and accepts no inputs that can expand the approved scope. Only the main branch is allowed. The workflow is encoded in the JSON subset of YAML, so standard-library tests can validate its exact structure without adding a YAML dependency.

The job uses Python 3.12, checks out full committed history without persisting GitHub credentials, installs the project with `python -m pip install .`, runs offline tests/benchmark validation and checks the exact plan before exposing the secret to the runner. The Google key is read only from GitHub Secrets into the preflight, runner and artifact-inspection steps; it is never echoed or written to research files. Permissions are contents:read and concurrent sanity jobs are queued rather than cancelling a possibly billable request.

Preflight pins the scenario SHA-256 to `17e4da22029b31b280fcf711bec9c88f261f01ee40dd45137a2ad2540ed4c80d` and verifies a clean committed checkout, google / gemini-3.8-flash / post_update, 3 scenarios, 1 repetition and exactly 3 intended requests. It uses existing plan_run logic without making a model call. Gemini temperature/top_p omissions must remain explicit.

The existing CLI executes the run; no generation, transcript, parser or scoring logic is recreated in the workflow. Two optional runner controls are used and recorded in the request manifest:

- `--max-provider-requests 3`: the total dispatch budget includes infrastructure retries and prior claims on resume.
- `--max-attempts-per-request 1`: this engineering sanity run makes at most one call per case, so three planned cases cannot turn into nine attempts. The normal frozen infrastructure retry policy is unchanged for commands without this explicit lower limit.

`--require-complete` marks the job unsuccessful if response collection is incomplete. Invalid model JSON remains a preserved response and is never semantically retried. A failed preflight makes zero requests; a failed or interrupted live run may make fewer than three. A completed run makes three, never more. There are no aggregate full-benchmark accuracy/SALR claims for this subset.

Run IDs use GitHub run_id and run_attempt; no raw artifact is overwritten or implicitly resumed. Runtime secrets, GitHub tokens, environment dumps and repository files are not upload targets. After a run, including an infrastructure failure, artifact_safety inspects only that run's manifest/raw/parsed/summary files. It rejects unexpected files/attempts, symlinks, credential fields, token patterns and current credential/token values (including common encodings), then copies exact bytes into a fresh temporary staging directory. The upload step is permitted only after inspection succeeds. Inspection failure withholds the upload rather than redacting raw data. These checks are conservative safeguards, not a general secret-detection or privacy guarantee.

The artifact is named **gemini-sanity-results**, with 30-day retention. It includes safe failure records as well as successful outputs. Download and preserve it in durable research storage promptly; hosted retention is not a publication archive. Provider aliases/defaults may move and API acceptance has not been demonstrated by static/mock tests. Requested/reported models and requested/effective settings remain in the artifacts.

## Launch in GitHub

1. Open https://github.com/ankitpanda226/revocable-flow/actions.
2. Select **Gemini sanity** in the workflow list.
3. Click **Run workflow**, choose **main**, then click **Run workflow** to start one sanity run.
4. Open that run to inspect preflight and collection status.
5. Under **Artifacts**, download **gemini-sanity-results**. It may also be available for a failed collection if safe staging succeeded.

If Actions are disabled, enable repository Actions before using the manual trigger. GOOGLE_API_KEY must be an Actions repository secret; do not put its value into workflow inputs, files or logs. This workflow was not dispatched or executed from Codex. No Gemini request was made from Codex while implementing it.
