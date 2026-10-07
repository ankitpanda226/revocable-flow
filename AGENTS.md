# RevocableFlow research rules

This project uses Pilot v0.2 and is Phase 1: a reproducible benchmark and offline evaluation framework.
Use the existing checkout; each cloud task is isolated. Do not create worktrees unless requested.

- Use only deliberately fictitious personal information, with SYN markers and fictional entities.
- Keep benchmark records in data/, independent from execution code in src/.
- Do not call external model APIs, add provider integrations, or build FlowGuard without explicit approval.
- Do not fabricate runs, outcomes, significance, or scientific conclusions. Label dummy tests as such.
- Preserve raw outputs and configuration/model metadata for any eventual experiment.
- Never commit credentials or real PII. Generated runs belong in ignored runs/.
- Validate ordered turns and annotation consistency after every benchmark edit.
- Keep gold labels, rationale, and permission metadata out of model-visible inputs; use Scenario.conversation().
- Run: PYTHONPATH=src python -m unittest discover -s tests -v
- Run: PYTHONPATH=src python -m revocable_flow.cli validate data/pilot/scenarios.jsonl --pilot

Later provider adapters must implement the ModelProvider interface without coupling benchmark data to provider-specific execution. Changes to metrics require explicit denominator documentation and regression tests.

Pilot v0.2 rules: validate exact permission tuples and counterfactuals, never infer SALR from information overlap, keep tool contracts separate from policy and before updates, preserve the original 40 IDs, keep matched families together, and update version/hash metadata only for reviewed intentional changes. The v0.1 audit is historical; consult docs/pilot_v02_audit.md for current limitations.
