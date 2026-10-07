# Benchmark data: Pilot v0.2

`pilot/scenarios.jsonl` revises exactly the original 40 records. All personal details, entities and values are fictitious. Synthetic markers, imagined institutions and explicit fictional-profile declarations establish provenance; numeric/date substrings are not claimed to be impossible real-world values. No real people's PII is used.

`pilot/metadata.json` identifies RevocableFlow Pilot, version `0.2`, scenario count `40`, origin `v0.1 audit revision`, parent/resulting file hashes and frozen ordering seed. Validate the current bytes rather than editing the hash to conceal an unintended change. Intentional data revisions require review, updated metadata and a new benchmark version.

Each line contains the original core fields plus:

- `initial_authorizations` / `updated_authorizations`: explicit records with information, recipient, purpose, scope, operation and allowed/denied status. Earlier tuples must remain explicit in the updated snapshot.
- `pre_update_expected_action` and `expected_action`: identical-request golds before and after the update.
- `transition_kind`: revoke, narrow, add, or unaffected_control. In the shipped set these identify 24 revocation targets, 8 narrowing targets, and 8 unchanged final-request controls. All 40 conversations withdraw at least one real grant.
- `violation_type`: the prospective failure type if the requested forbidden release occurs (stale_authorization, cross_context_transfer, none); it is not an observed model failure.
- `salr_eligible`: true only if a requested exact tuple was allowed before and is invalid now. An ALLOW control with another revoked tuple is ineligible.
- `family_id`: related designs that must stay together in future splits.
- `tool_contract`: required/optional field mappings and partial-payload capability, with no user policy embedded.
- `final_request_fields`: the fields selected by the identical final operation in the counterfactual and actual scenario.

The schema explicitly enumerates full and derived representations rather than assuming a full-scope grant matches every narrower tuple. E.g. account_number/full and account_number/last_four are different permission tuples. Medical/transcript record portions use a common information asset with separate scopes. Narrowing reduces the set of granted representations; it does not merely rename a field.

`allowed_information` contains authorized requested disclosure labels. `forbidden_information` also includes unrequested forbidden contract fields in the final context, catching volunteered revoked data in controls. A disclosed label identifies a semantic representation; it is not a literal substring or recipient-independent authorization. Do not label a full number as only a suffix.

Snapshots and golds are annotations, separate from natural-language turns. `Scenario.conversation()` returns only role/content. It strips IDs, stages, families, rationales, permission annotations and golds. The public tool schema includes operational field meanings and scopes, but never annotation disclosure labels or privacy decisions. Final requests are tools so they cannot silently reauthorize a user's withdrawn grant. These tool messages are textual interfaces, not provider-native call-ID-bearing results.

Pilot validation checks counts, original IDs, all six domains, category-specific recipient/purpose constancy, exact tuple changes, pre/post golds, partial support, metadata exclusion, contract order, family histories and the file hash. It cannot prove that an annotation fully matches its natural-language policy; the v0.2 manual audit addresses that limitation. New/never-authorized states and cross-context handling are tested with dummy fixtures, not extra benchmark records.

Ordering is a seeded shuffle of sorted internal IDs. IDs retain v0.1 lineage and still have action-correlated suffixes; never show them to a model. Metadata captures frozen input order; future randomized execution must independently log ordering and maintain independent conversation state. Eight paired families are intentional companions, not accidental extra independent evidence.
