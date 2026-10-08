# Proposed two-request Gemini recovery

Status: locally validated against the user-supplied original artifact on 2026-10-08; no live recovery is authorized or executed. The supplied run is 37728642241, attempt 2. Its manifest and all original request files passed preflight. The complete 144-test suite and a separate real-artifact recovery simulation passed with mocked responses and zero provider calls. See [artifact diagnostic](reports/gemini_sanity_diagnostic.md).

## Proposed workflow

`.github/workflows/gemini-recovery.yml` is manual-only on main. It requires the failed source GitHub run ID, its attempt number, and explicit confirmation that the owner reviewed spending under the $4 total research budget and has not already recovered this source. The default confirmation is false. Workflow reruns (run_attempt greater than 1) are blocked. Separate new manual dispatches are still possible: concurrency serializes them but is not a durable cross-run spending ledger. Review existing recovery runs before authorizing another dispatch.

Using read-only GitHub permissions, it verifies that the source was a completed, failed, manual main-branch run of gemini-sanity.yml, retrieves its head commit, and downloads only its existing gemini-sanity-results artifact. It does not regenerate missing artifacts. Missing/expired artifacts, mismatched source attempts, or unverified evidence stop before any provider call.

The recovery preflight checks:

- The original manifest's self-hash and source commit against GitHub run metadata, and its exact experimental inputs against the current frozen three-case plan. Git commit and Python version may differ between original and recovery; both remain separately recorded. Config bytes, model matrix, benchmark hash/copies, prompts, parameters, scenario order, condition and request keys must match.
- Exactly three original started/response pairs, indices 1 and 2 with terminal HTTP 503/http_error records and no parsed response, and index 3 with a completed model response. Missing outcomes, timeouts, 429s, extra attempts, or deferred Retry-After values are not authorized for recovery.
- The third raw response's parse metadata and saved score against the existing frozen parser/scorer. An incorrect or invalid but terminal model response is preserved, never repaired or retried. The summary must show one completion, two infrastructure failures, three original dispatches, and no ambiguity. The analysis mapping must match the frozen benchmark.

The original archive is copied without changing any bytes. A new, linked recovery manifest includes original manifest/file hashes and a different execution commit/run identity. It contains only the original requests for execution indices 1 and 2, with identical model, messages, settings and request keys. Each is the second dispatch for that original trial, recorded as attempt 1 in a separate recovery run with explicit lineage; the original attempt-01 files are never edited or renamed. This is a targeted recovery, not a repetition or fresh three-case sanity run.

The existing execute_plan, Google adapter, parser and scorer perform execution. Optional transport injection disables redirects only for recovery, retaining the existing transport normalization and avoiding credential forwarding or extra HTTP requests. Two new requests maximum, one attempt per case, no automatic infrastructure or semantic retries, no third request, no other provider, and no automatic model switch. A failure/interrupt can yield fewer than two calls and is preserved; an ambiguous recovery dispatch must not be replayed automatically.

The original three-call cap remains unchanged. Plain --resume of that exhausted manifest would make no new calls, so the recovery uses its own explicit two-call budget and linked manifest. The historical cap is not silently increased. No benchmark, gold label, prompt, scoring rule or frozen model/config file is changed.

## Artifacts and cost

After collection, the workflow verifies original file hashes again and inspects both source and new recovery records for credentials/unexpected files before upload. The artifact gemini-recovery-results includes `source/` (original raw third response, original failures and metadata) and `recovery/` (new raw/parsed records, manifest, completion summary and dispatch audit). Paths and attempts are allowlisted; no environment dumps or tokens are upload targets. Unsafe data withholds upload rather than altering raw responses. Recovery is reported separately; no aggregate benchmark accuracy or SALR is calculated.

Pricing is unverified in the frozen config. Two calls is a request cap, not a dollar cap. The workflow cannot establish or enforce a $4 billing balance across providers. Before any later authorization, the owner must verify cumulative spending, applicable prices/tier and sufficient remaining budget; use provider billing controls where available. This proposal does not authorize spending.

## Review and eventual manual launch

Publication is authorized only after successful local validation. Publishing the workflow does not authorize live calls. After separately approving two recovery calls and verifying the remaining budget:

1. Verify the failed run's artifact is still available and record its run ID/attempt.
2. Check billing and prior recovery runs; do not recover the same source twice.
3. In GitHub Actions select **Gemini two-request recovery**, then **Run workflow** on main.
4. Enter source run ID **37728642241** and attempt **2**. Confirm the budget review only after completing it and separately approving recovery, then dispatch once.
5. Download **gemini-recovery-results** and review source/recovery provenance and individual outcomes. Do not rerun failures automatically.

This workflow was not launched during validation. The request cap is per recovery invocation; do not create multiple manual dispatches for the same source.
