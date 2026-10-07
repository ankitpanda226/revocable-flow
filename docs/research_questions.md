# Research questions and phases

Working title: RevocableFlow: Evaluating Dynamic Privacy and Consent in Tool-Using LLM Agents.

- RQ1: How well do LLM agents obey privacy permissions when those permissions change during a conversation?
- RQ2: Which types of privacy-policy transitions cause the most failures?
- RQ3 (later): Can a runtime privacy-control mechanism reduce these failures?
- RQ4 (later): What utility/task-success cost does privacy enforcement introduce?

Phase 1 implements a synthetic pilot and offline scoring. RQ1/RQ2 motivate it, but neither has been answered. RQ3/RQ4 require later implementation, comparators, and a task-success rubric. FlowGuard is outside current scope.

Tentative hypotheses: agents may retain obsolete grants, generalize grants across recipients or purposes, or over-disclose after scope narrowing. Conversely they may over-refuse unaffected requests. These are untested hypotheses. The 40 cases are a convenience pilot rather than a representative random sample; category score differences would not establish causal effects or general population estimates.

Before model experiments: approve provider access; freeze/version data and prompts; specify model parameters, repeats, ordering, tool semantics, annotation instructions and adjudication; preserve all attempted runs including failures. Decide uncertainty reporting and power requirements before inferential claims. No statistical significance or research conclusion is currently asserted.
