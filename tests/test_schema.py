import copy
import json
import re
import unittest
from pathlib import Path
from revocable_flow.schema import (Action, Authorization, Permission, PermissionState,
                                  Prediction, Scenario, Status, ValidationError)

DATA = Path(__file__).resolve().parents[1] / "data/pilot/scenarios.jsonl"


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.rows = {s["scenario_id"]: s for s in map(json.loads, DATA.read_text().splitlines())}
        self.data = self.rows["consent_revocation-01"]

    def test_typed_record_and_gold_free_conversation(self):
        scenario = Scenario.from_dict(self.data)
        self.assertIs(scenario.expected_action, Action.BLOCK)
        self.assertTrue(scenario.salr_eligible)
        self.assertTrue(all(isinstance(a, Authorization) for a in scenario.initial_authorizations))
        self.assertEqual(scenario.pre_update_expected_action, scenario.derive_action(before=True))
        self.assertTrue(scenario.tested_invalidated_permissions)
        for turn in scenario.conversation():
            self.assertEqual(set(turn), {"role", "content"})

    def test_every_conversation_excludes_golds_ids_and_metadata(self):
        for data in self.rows.values():
            scenario = Scenario.from_dict(data)
            text = json.dumps(scenario.conversation())
            for token in (scenario.scenario_id, scenario.family_id, scenario.rationale,
                          "expected_action", "salr_eligible", "initial_authorizations",
                          "updated_authorizations", "transition_kind", "violation_type", "disclosure_label"):
                self.assertNotIn(token, text)
            self.assertIsNone(re.search(r"\b(ALLOW|BLOCK|REDACT)\b", text))
            self.assertIn(scenario.synthetic_private_value, scenario.initial_permission)

    def test_missing_unknown_and_wrong_types_fail(self):
        for mutate in (lambda d: d.pop("recipient"), lambda d: d.update(extra="x"),
                       lambda d: d.update(domain="other"), lambda d: d.update(expected_action="LEAK"),
                       lambda d: d.update(salr_eligible="true"), lambda d: d.update(family_id=""),
                       lambda d: d.update(forbidden_information="passport_number"),
                       lambda d: d.update(synthetic_private_value=""), lambda d: d.update(turns=None),
                       lambda d: d.pop("initial_authorizations"), lambda d: d.pop("pre_update_expected_action"),
                       lambda d: d.pop("expected_action")):
            with self.subTest(mutate=mutate):
                data = copy.deepcopy(self.data)
                mutate(data)
                with self.assertRaises(ValidationError): Scenario.from_dict(data)

    def test_bad_turn_order_duplicates_and_text_fail(self):
        for mode in ("order", "id", "text", "role", "missing_context", "missing_update", "late_contract"):
            with self.subTest(mode=mode):
                data = copy.deepcopy(self.data)
                by_stage = {t["stage"]: t for t in data["turns"]}
                if mode == "order": data["turns"].reverse()
                if mode == "id": data["turns"][1]["turn_id"] = "t1"
                if mode == "text": by_stage["policy_update"]["content"] = "different update"
                if mode == "role": by_stage["policy_update"]["role"] = "tool"
                if mode == "missing_context": data["turns"] = [t for t in data["turns"] if t["stage"] != "context"]
                if mode == "missing_update": data["turns"].remove(by_stage["policy_update"])
                if mode == "late_contract":
                    data["turns"].remove(by_stage["tool_contract"])
                    data["turns"].insert(-1, by_stage["tool_contract"])
                with self.assertRaises(ValidationError): Scenario.from_dict(data)

    def test_explicit_metadata_leaks_rejected(self):
        for token in (self.data["scenario_id"], self.data["family_id"], self.data["rationale"], "salr_eligible", "BLOCK", "BLOCK."):
            data = copy.deepcopy(self.data)
            next(t for t in data["turns"] if t["stage"] == "context")["content"] += " " + token
            with self.assertRaises(ValidationError): Scenario.from_dict(data)

    def test_tuple_change_cannot_hide_behind_information_overlap(self):
        for component in ("recipient", "purpose", "scope", "operation"):
            data = copy.deepcopy(self.data)
            data["initial_authorizations"][0][component] = "some other context"
            data["updated_authorizations"].append(data["initial_authorizations"][0] | {"status": "allowed"})
            # Same information label, but the final exact tuple was never allowed.
            with self.assertRaises(ValidationError): Scenario.from_dict(data)

    def test_duplicate_conflicting_or_missing_snapshots_fail(self):
        mutations = (lambda d: d.update(initial_authorizations=[]),
                     lambda d: d["initial_authorizations"].append(d["initial_authorizations"][0] | {"status":"denied"}),
                     lambda d: d.update(updated_authorizations=[]),
                     lambda d: d["updated_authorizations"][0].update(status="allowed"),
                     lambda d: d["updated_authorizations"][0].update(status="revoked"))
        for mutate in mutations:
            data = copy.deepcopy(self.data); mutate(data)
            with self.assertRaises(ValidationError): Scenario.from_dict(data)

    def test_counterfactual_and_salr_annotations_must_match(self):
        for changes in ({"pre_update_expected_action":"BLOCK"}, {"salr_eligible":False},
                        {"expected_action":"ALLOW"}, {"violation_type":"cross_context_transfer"},
                        {"transition_kind":"unaffected_control"}, {"allowed_information":["passport_number"]}):
            with self.assertRaises(ValidationError): Scenario.from_dict(self.data | changes)

    def test_every_redact_requires_partial_contract_before_update(self):
        for data in self.rows.values():
            if data["expected_action"] != "REDACT": continue
            scenario = Scenario.from_dict(data)
            self.assertTrue(scenario.tool_contract.accepts_partial_payload)
            stages = [t.stage for t in scenario.turns]
            self.assertLess(stages.index("tool_contract"), stages.index("policy_update"))
            bad = copy.deepcopy(data)
            bad["tool_contract"]["accepts_partial_payload"] = False
            with self.assertRaises(ValidationError): Scenario.from_dict(bad)

    def test_denied_required_field_prevents_redaction(self):
        data = copy.deepcopy(self.rows["consent_revocation-07"])
        data["tool_contract"]["required"] += data["tool_contract"]["optional"]
        data["tool_contract"]["optional"] = []
        with self.assertRaises(ValidationError): Scenario.from_dict(data)

    def test_unknown_final_fields_and_tool_schema_policy_leak_fail(self):
        data = copy.deepcopy(self.data); data["final_request_fields"] = ["unknown"]
        with self.assertRaises(ValidationError): Scenario.from_dict(data)
        data = copy.deepcopy(self.data)
        next(t for t in data["turns"] if t["stage"] == "tool_contract")["content"] = '{"required": [], "policy": "deny"}'
        with self.assertRaises(ValidationError): Scenario.from_dict(data)

    def test_permission_states_cover_retained_invalidated_new_and_never(self):
        scenario = Scenario.from_dict(self.rows["consent_revocation-09"])
        case, account = [scenario.permission_for(f) for f in scenario.tool_contract.fields]
        self.assertEqual(scenario.permission_state(case), PermissionState.RETAINED)
        self.assertEqual(scenario.permission_state(account), PermissionState.INVALIDATED)
        absent = Permission("account_number", "Fictional Other Desk", "case status lookup", "full", "submit_case_lookup")
        self.assertEqual(scenario.permission_state(absent), PermissionState.NEVER_AUTHORIZED)
        # A synthetic add fixture tests the supported schema seam; it is not a 41st benchmark case.
        data = copy.deepcopy(self.data)
        data["initial_authorizations"][0]["status"] = "denied"
        data["updated_authorizations"][0]["status"] = "allowed"
        data.update(transition_kind="add", violation_type="none", salr_eligible=False,
                    pre_update_expected_action="BLOCK", expected_action="ALLOW",
                    allowed_information=["passport_number"], forbidden_information=[])
        added = Scenario.from_dict(data)
        self.assertEqual(added.permission_state(added.permission_for(added.requested_fields[0])), PermissionState.NEWLY_GRANTED)

    def test_cross_context_fixture_is_not_stale(self):
        data = copy.deepcopy(self.data)
        old = data["initial_authorizations"][0]
        denied = old | {"recipient":"Fictional Never Authorized Recipient", "status":"denied"}
        new = old | {"recipient":"Fictional Newly Authorized Recipient"}
        data["initial_authorizations"] = [old, denied]
        data["updated_authorizations"] = [old, denied, new]
        data.update(recipient=denied["recipient"], transition_kind="add", violation_type="cross_context_transfer",
                    salr_eligible=False, pre_update_expected_action="BLOCK")
        scenario = Scenario.from_dict(data)
        self.assertFalse(scenario.tested_invalidated_permissions)
        self.assertFalse(scenario.salr_eligible)
        self.assertEqual(scenario.permission_state(scenario.permission_for(scenario.requested_fields[0])), PermissionState.NEVER_AUTHORIZED)

    def test_prediction_validation(self):
        prediction = dict(scenario_id="dummy", action="BLOCK", disclosed_information=[], raw_output="dummy raw")
        self.assertIs(Prediction.from_dict(prediction).action, Action.BLOCK)
        for changes in ({"action":"UNKNOWN"}, {"raw_output":""}, {"disclosed_information":[1]}, {"extra":True}):
            with self.assertRaises(ValidationError): Prediction.from_dict(prediction | changes)

    def test_unaffected_control_is_not_eligible_for_other_revoked_field(self):
        data = copy.deepcopy(self.rows["consent_revocation-09"])
        self.assertTrue(Scenario.from_dict(data).invalidated_permissions)
        data["salr_eligible"] = True
        with self.assertRaises(ValidationError): Scenario.from_dict(data)

    def test_narrowing_requires_a_retained_scope_of_the_same_operation(self):
        data = copy.deepcopy(self.rows["scope_change-01"])
        for a in data["updated_authorizations"]:
            a["status"] = "denied"
        data["forbidden_information"] = ["account_full", "account_last_four"]
        with self.assertRaisesRegex(ValidationError, "narrowing"):
            Scenario.from_dict(data)
