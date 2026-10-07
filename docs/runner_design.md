# Provider runner design

## Boundaries and present status

`providers/base.py` defines ModelProvider, ProviderResponse, ProviderError and an injected HTTP transport. OpenAI Responses, Anthropic Messages and Google generateContent adapters translate the exact two frozen messages into REST requests, then normalize returned text and metadata. Standard-library REST avoids SDK dependencies entirely. The legacy evaluator re-exports the shared interface; offline annotation scoring remains unchanged. Transcript construction, strict parsing, exact-tuple scoring and SALR remain in protocol.py and do not depend on an SDK.

ProviderResponse includes provider, requested_model, reported_model, untouched returned final text in raw_output, request_id, latency_ms, usage, finish_reason, error, requested_parameters, effective_parameters, unsupported_parameters and structured_output_enforced. Missing returned versions remain null. Text segments are concatenated in order without trimming or repair; Google thought-marked parts are not final release output. Arbitrary upstream error bodies, headers and exception strings are never logged. Error metadata retains safe categories, HTTP status, Retry-After and retry eligibility. Only numeric token-usage fields are retained. These are mock-tested wire shapes, not evidence of live provider compatibility.

The runner is implemented and the three researcher-verified aliases are enabled; see [model matrix](model_matrix.md). No paid model request, benchmark experiment, defense or ablation was executed. Frozen benchmark/prompt/scoring decisions are unchanged. Milestone 2 documents record implementation status at their freeze; this document updates implementation status while preserving benchmark, prompt and scoring semantics. The researcher-authorized Gemini sampling compatibility exception is documented below. Confidence-interval computation and durable archive integration are still future work.

## Gates and local commands

From the repository root:

```sh
PYTHONPATH=src python -m revocable_flow.cli pilot-run --dry-run
PYTHONPATH=src python -m revocable_flow.cli pilot-run --provider openai --scenario-limit 3 --dry-run
PYTHONPATH=src python -m revocable_flow.cli pilot-run --provider google --condition post_update --dry-run
PYTHONPATH=src python -m revocable_flow.cli pilot-run --dry-run --manifest-preview
```

Dry-run validates configuration, frozen benchmark hash/metadata, provider registry/capabilities, deterministic scenario order, both prompt conditions, hashes, safe artifact layout and request counts. It constructs prompts even when model IDs are unresolved. It neither requires keys, creates result directories nor invokes a provider. Network-call count is zero, verified by tests that fail on socket/HTTP access. Currently: 40 scenarios, 80 distinct prompts, 3 enabled models and 240 intended requests. A provider filter may select an unresolved entry for preview; an unconfigured exact model selector fails.

`--dry-run` and `--execute-live` are mutually exclusive; one is required. Omitting both fails before any provider call. The runner and adapters also require the literal boolean execute_live=True at their programmatic boundary. An explicit live flag alone cannot bypass unresolved model IDs, required-parameter incompatibility, missing environment credentials, altered manifest identity or uncommitted/dirty code. A unique safe --run-id is required for execution/persistence. Live mode prints a count/token/cost preview before execution and creates its manifest before any call.

Future approved sanity command, **not run now**, from a clean committed freeze:

```sh
PYTHONPATH=src python -m revocable_flow.cli pilot-run \
  --provider openai --scenario-limit 3 --condition post_update \
  --run-id approved-sanity-001 --execute-live
```

This selection is at most 3 scenarios, one model, post only. The general runner also supports full pilots; --scenario-limit is not a universal three-scenario cap. Analogous commands use --provider anthropic or --provider google with their configured aliases. A sanity/subset run is marked non-primary and cannot produce full-pilot headline metrics. Live execution still requires the researcher's explicit authorization; no key or explicit flag was used for a real call here.

## Credentials and parameter policy

Credentials come only from OPENAI_API_KEY, ANTHROPIC_API_KEY and GOOGLE_API_KEY. They enter HTTP authentication headers, never URLs, configuration, prompts, console output or artifacts. `.env`, `.env.*`, secrets/, credentials/ and results/ are ignored. No .env template or real key is committed. Do not paste values into commands or YAML.

Both requested and effective canonical settings are logged. Wire names differ (for example Anthropic max_tokens and Google maxOutputTokens), but values stay frozen. Responses REST and Messages adapters omit seed and declare it unsupported; generateContent can send a verified supported seed. An incompatible required setting refuses execution rather than approximating it, except the expressly authorized sampling omissions for the exact gemini-3.8-flash alias. That adapter never sends temperature/top_p, retains their requested values and records both effective values as unsupported; max_output_tokens remains required. Matrix assertions conflicting with an adapter's wire capability also fail. No native structured-output enforcement is used (always false); all providers receive the frozen JSON instruction without extra semantic guidance, tools or external context.

All artifact writes check for literal current credential values before serialization/persistence. If a provider unexpectedly echoes a credential, persistence fails without altering the text or printing it; the started attempt remains ambiguous and must be reconciled securely. Raw preservation is subordinate to the explicit prohibition on saving keys. This guard is not a general secret scanner, and no privacy guarantee is claimed. Upstream error messages are excluded rather than scrubbed heuristically.

## Manifest, artifacts and integrity

A deterministic plan contains run_id, benchmark identity, execution Git commit/dirty state, Python version, exact configuration UTF-8 bytes/hash, matrix, conditions, seed, anonymous-index-to-ID order, requested settings, prompt catalog/hashes, every enabled request and expected counts. Its manifest_hash covers the canonical content excluding that hash itself. It contains no gold labels; IDs are for local provenance and never enter provider messages. Timing belongs in individual attempt records, not in the deterministic plan.

Default dry-run previews the plan without writing. `--manifest-preview` prints it locally; `--write-manifest --run-id NAME` explicitly persists only the manifest without calling a provider. A persisted preparation can later be executed with --resume only if its entire plan still matches (including Git/config); changed plans require a new run ID. No research artifact is created by the ordinary dry-run.

Layout extends the frozen raw/parsed/summaries structure with immutable request manifests:

```text
results/
  manifests/<run_id>.json
  raw/<run_id>/model-<matrix-index>/<condition>/<anonymous-index>/
    attempt-<number>.started.json
    attempt-<number>.response.json
  parsed/<run_id>/model-<matrix-index>/<condition>/<anonymous-index>.json
  parsed/<run_id>/benchmark.jsonl
  parsed/<run_id>/benchmark_metadata.json
  parsed/<run_id>/analysis_index.json
  summaries/<run_id>/completion-<content-hash>.json
```

Manifest and exact frozen benchmark/metadata copies precede provider calls. Gold data and index mapping belong to offline parsed provenance, never raw provider request/response artifacts. Raw records preserve anonymous index, condition, provider, requested/reported model, benchmark version/hash/commit, exact messages/prompt hash, generation settings, UTC timestamp, latency, request ID, exact raw output, decoded JSON/parse status, safe provider error, finish reason, usage and attempt number. Invalid text remains unchanged. Parsed records link to raw content hashes and use the unchanged rubric. Summaries preserve prior versions using content-derived names.

Writes use exclusive creation and fsync; raw responses are never overwritten. Frozen copies and derived records must match on resume. Unsafe run IDs and symlink artifact paths are rejected. These checks do not constitute tool-execution security or an adversarial filesystem guarantee. Results are deliberately ignored; archive them in an approved durable research store before publication. Git history and hashes support identity, not proof of model execution.

## Retry, interruption and resume

Each request claims an exclusive started artifact before a possible billable call. A saved success or invalid model response is terminal: resume regenerates a missing parsed sidecar locally and never repeats the provider request. For an uncompleted started attempt or corrupt/inconsistent artifacts, stop/mark ambiguous rather than silently duplicate an unknown upstream outcome. No automatic stale-claim removal. Reconcile such cases against provider request/billing records under separate approval; preserve the original files and do not edit raw outcomes to force a retry.

Safe error attempts remain separate from malformed model JSON. Infrastructure retries use at most 3 total attempts, delays 2 then 4 seconds, identical prompt/model/settings, and only timeout, connection reset or HTTP 429/500/502/503/504. No authentication, other status, configuration or semantic retries. Retry-After up to 60 seconds is honored using the greater delay; longer values defer the request. Resume after the recorded delay expires may use the next remaining attempt, retaining history and the fixed backoff. Exhausted attempts never reset on resume. Timeout retries can represent duplicated upstream work; request IDs/attempts expose that uncertainty.

Use exactly the original selection/config/run ID plus --resume. Changed selections or hashes are rejected. Incomplete runs report planned/completed counts, infrastructure-missing and ambiguous keys without primary metrics/rankings. Only a complete 40-scenario, both-condition design receives the frozen paired summaries, grouped separately by enabled model. No confidence intervals or significance tests are computed by the runner.

## Cost preview and limitations

Preview estimates input tokens as UTF-8 transcript/message character count divided by four (rounded up) and output budget as requests × 512. The character heuristic is not a provider tokenizer, and the budget is not a billing guarantee for provider-specific reasoning/usage. Report enabled request counts separately from hypothetical all-selected counts. Optional manually configured pricing.input_per_million/output_per_million applies one uniform rate pair to the selected models for a rough illustration; use an individual model selection when entering model-specific rates and record rate source/date in run notes. No permanent prices are hard-coded. Missing rates report `cost estimate unavailable` and do not block reproducibility. Pricing is not a spending authorization or a hard billing cap.

Outstanding: live parameter-acceptance checks under explicit approval, provider-default review, independent gold review and durable storage. Exact alias IDs were independently verified by the researcher; immutable dated snapshots are not selected. The 40-case short synthetic benchmark cannot establish real-world safety, hidden-use safety, security, population-wide behavior, significance or privacy guarantees.
