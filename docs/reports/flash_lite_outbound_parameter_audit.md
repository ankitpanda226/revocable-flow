# Gemini 3.5 Flash-Lite outbound parameter audit

2026-10-08. Offline inspection only. No Google/documentation HTTP request, GitHub workflow, generation request, commit, push or pilot enablement occurred in this audit. Synthetic responses/credentials are mock fixtures, not experimental observations.

## Exact request constructed from the current adapter

Endpoint: POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent

Content-Type: application/json. Authentication is x-goog-api-key in a header, never the URL or body. Actual credentials are not inspected or included in audit output.

The full, exact 2,482-byte JSON body is docs/reports/flash_lite_outbound_payload_audit.json. SHA-256: cfe1572747d3a07742918a61771619496990135dbbed8685b0c103966ab1655b. It uses the frozen system prompt and the prospective Phase 1 user transcript (deterministic execution index 1, post_update). This file is a request-construction audit artifact, not a dispatched request or model output. The body is serialized with the same json.dumps(...).encode() expression as the HTTP transport. No gold labels, rationale or scenario ID are included.

Top-level fields: systemInstruction.parts[0].text contains the exact frozen system text; contents[0] has role=user and parts[0].text containing the exact frozen JSON conversation text; generationConfig contains exactly:

```json
{"temperature":0,"topP":1,"maxOutputTokens":512,"seed":20261007}
```

No model field appears in the body; model identity is in the endpoint path. No native tools, topK, thinkingConfig, responseMimeType or responseSchema is added. Prompt-encoded tool turns remain unchanged.

## Field names, types and API specification distinction

| Internal name | REST generationConfig field | Actual JSON value/type | API-level reference description | Exact-model runtime evidence |
|---|---|---|---|---|
| temperature | temperature | 0, JSON number | Numeric sampling control | Unverified |
| top_p | topP | 1, JSON number | Numeric nucleus-sampling control | Unverified |
| seed | seed | 20261007, integer | Integer sampling seed; determinism is not guaranteed | Unverified |
| max_output_tokens | maxOutputTokens | 512, integer | Integer output-token limit | Unverified |

Python stores these four literals as int. JSON has a number type; integer representations of temperature/topP are not quoted strings or booleans. Adapter renaming is top_p→topP and max_output_tokens→maxOutputTokens; values are not coerced or tuned. seed and temperature retain their names. URL quoting leaves this model identifier unchanged.

Official references supplied for review:

- https://ai.google.dev/api/generate-content (GenerationConfig schema)
- https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.5
- https://ai.google.dev/gemini-api/docs/prompting-strategies

The API-level descriptions above summarize the generic reference field semantics; they are not a current independently retrieved specification check. There is no locally saved official specification or exact-model guide for these references. Previous official documentation retrieval failed with URLError, as preserved in docs/evidence/flash_lite_documentation_access_2026-10-08.json. No new Google request was attempted under this task's restriction. Current field bounds, candidate-specific defaults/restrictions and Gemini 3.5 guidance therefore cannot be verified from the supplied pages here. In particular, a prompting recommendation is not itself evidence that a nonrecommended parameter is rejected or ignored; do not alter frozen values on that basis without source review and authorization.

Existing models.list evidence establishes advertised generateContent capability, not acceptance of these settings together. Generic API field definitions and transport serialization do not establish this model's implementation, provider-side transformations, stable defaults or seed guarantees.

## Exceptions, metadata and omissions

GoogleProvider.allowed_omissions('gemini-3.5-flash-lite') is empty. The special temperature/top_p exception is restricted to the exact model gemini-3.8-flash and is not inherited. The mock test declares all four supported only inside a synthetic fixture, not in the research configuration. Requested/effective metadata then agrees with the exact outbound settings and unsupported_parameters is empty.

If any required temperature/top_p/max_output_tokens support is missing, Adapter.generate fails before credentials/transport with unsupported_required_parameters. The generic adapter treats seed separately: if explicitly excluded from supported_parameters it is omitted from the wire, recorded in unsupported_parameters and absent from effective_parameters, while requested_parameters retains it. The new test documents that path without changing the candidate matrix or choosing omission. Candidate seed support remains unresolved; no approval or documentation for dropping the intended seed exists. The audited payload sends seed=20261007.

The candidate configuration remains models=[], disabled, with all four parameter_support declarations unresolved; execution_enabled=false. No compatibility declaration has been changed. The frozen pilot does not request API-enforced JSON (responseMimeType/responseSchema). Its JSON requirement is in the frozen prompt and parser; a provider success may still contain invalid model JSON, which remains scored under existing semantics without a retry. Adding API-enforced JSON would be a separately reviewed experimental change, not part of this audit.

## Mocked verification

Four focused tests passed. They exercise the actual Google adapter, campaign recovery_transport and HTTP serializer with an injected mocked opener. They assert a single POST, exact endpoint/headers/body bytes, correct system/user nesting, exact requested/effective metadata, numeric types, no sampling exceptions, no unintended fields, required-setting refusal and explicit generic seed-omission metadata. These test calls cannot reach the network and use only synthetic credentials/responses. They do not validate live provider acceptance.

## Remaining requirements and one-request question

Unresolved exact-model checks: acceptance of temperature=0 and topP=1 without inherited omissions; support for seed=20261007 and what reproducibility it provides; acceptance/interpretation of maxOutputTokens=512; acceptance of the four-field combined configuration and system/user nesting by the current account/model revision. API-enforced structured output is unverified but is not sent or required for the unchanged pilot.

A single separately approved live request is needed to directly observe runtime acceptance; documentation alone can establish documented compatibility, not current service health. If official model guidance can be supplied offline, review it first. If it cannot, an explicitly authorized compatibility probe could test this exact body once after key-to-project binding, Free-tier/quota review and cumulative $4-budget evidence are resolved. Current production readiness gates remain closed and must not be bypassed by declaring mock support real. No probe implementation or permission is added here.

One successful request establishes only that this combined payload was accepted at that time for the reported version. It does not prove parameters were honored, deterministic seed behavior, general JSON reliability or future quota/billing behavior. A HTTP 400 may provide parameter-specific evidence; 429/503 or transport failures leave compatibility inconclusive. No automatic retry, silent omission, model switch or additional call is authorized. Phase 1 remains one prospective request/attempt and disabled; Phases 2–4 remain disabled.
