"""Provider wire-shape fixtures are dummy responses, never observed model results."""
import os
import unittest
from unittest.mock import Mock, patch

from revocable_flow.providers import PROVIDER_CLASSES
from revocable_flow.providers.base import HTTPReply, TransportFailure
from revocable_flow.protocol import load_protocol_benchmark, build_messages
from revocable_flow.schema import ValidationError
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARAMETERS = {"temperature": 0, "top_p": 1, "max_output_tokens": 512, "seed": 20261007}
DUMMY_TEXT = ' {"action":"BLOCK","release_fields":[]}\n'
DUMMY_KEY = "SYN-fixture-credential-not-a-real-api-key"


class ProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.messages = build_messages(load_protocol_benchmark(ROOT / "configs/pilot_eval.yaml")[0], "post_update")

    def adapter(self, provider, reply):
        transport = Mock(return_value=reply)
        return PROVIDER_CLASSES[provider](transport=transport), transport

    def call(self, adapter, supported=None):
        with patch.dict(os.environ, {adapter.credential_variable: DUMMY_KEY}):
            return adapter.generate(self.messages, model="dummy-model", parameters=PARAMETERS,
                                    supported_parameters=supported or adapter.wire_supported, execute_live=True)

    def test_openai_normalization_and_request_shape(self):
        adapter, transport = self.adapter("openai", HTTPReply(200, {
            "model": "dummy-returned-version", "status": "completed", "output": [
                {"type": "message", "content": [{"type": "output_text", "text": DUMMY_TEXT}]}],
            "usage": {"input_tokens": 10, "output_tokens": 5, "secret_header": DUMMY_KEY}}, {"x-request-id": "dummy-request"}))
        response = self.call(adapter)
        self.assertEqual(response.raw_output, DUMMY_TEXT)
        self.assertEqual(response.reported_model, "dummy-returned-version")
        self.assertEqual(response.requested_model, "dummy-model")
        self.assertEqual(response.request_id, "dummy-request")
        self.assertEqual(response.usage, {"input_tokens": 10, "output_tokens": 5})
        self.assertEqual(response.finish_reason, "completed")
        self.assertIsNone(response.error)
        self.assertEqual(response.unsupported_parameters, ("seed",))
        self.assertNotIn("seed", response.effective_parameters)
        self.assertEqual(response.requested_parameters, PARAMETERS)
        self.assertFalse(response.structured_output_enforced)
        url, headers, payload = transport.call_args.args
        self.assertEqual(payload["input"], self.messages)
        self.assertNotIn("tools", payload)
        self.assertNotIn("reasoning", payload)
        self.assertNotIn("response_format", payload)
        self.assertNotIn(DUMMY_KEY, str(payload))
        self.assertNotIn(DUMMY_KEY, url)

    def test_anthropic_normalization_and_headers(self):
        adapter, transport = self.adapter("anthropic", HTTPReply(200, {
            "model": "dummy-snapshot", "content": [{"type": "text", "text": DUMMY_TEXT}],
            "stop_reason": "end_turn", "usage": {"input_tokens": 10}}, {"request-id": "dummy-request"}))
        response = self.call(adapter)
        self.assertEqual(response.raw_output, DUMMY_TEXT)
        self.assertEqual(response.reported_model, "dummy-snapshot")
        url, headers, payload = transport.call_args.args
        self.assertEqual(headers["x-api-key"], DUMMY_KEY)
        self.assertEqual(payload["system"], self.messages[0]["content"])
        self.assertEqual(payload["messages"], self.messages[1:])
        self.assertEqual(payload["max_tokens"], 512)
        self.assertNotIn("thinking", payload)
        self.assertEqual(response.unsupported_parameters, ("seed",))

    def test_google_normalization_and_seed(self):
        adapter, transport = self.adapter("google", HTTPReply(200, {
            "modelVersion": "dummy-snapshot", "responseId": "dummy-id", "candidates": [
                {"content": {"parts": [{"text": DUMMY_TEXT}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5}}))
        response = self.call(adapter)
        self.assertEqual(response.raw_output, DUMMY_TEXT)
        self.assertEqual(response.reported_model, "dummy-snapshot")
        self.assertEqual(response.request_id, "dummy-id")
        self.assertEqual(response.unsupported_parameters, ())
        url, headers, payload = transport.call_args.args
        self.assertNotIn(DUMMY_KEY, url)
        self.assertEqual(headers["x-goog-api-key"], DUMMY_KEY)
        self.assertEqual(payload["generationConfig"], {"temperature": 0, "topP": 1, "maxOutputTokens": 512, "seed": 20261007})
        self.assertEqual(payload["contents"][0]["parts"][0]["text"], self.messages[1]["content"])

    def test_frozen_gemini_sampling_omissions_are_explicit_and_never_sent(self):
        adapter, transport = self.adapter("google", HTTPReply(200, {
            "modelVersion": "dummy-runtime-version", "candidates": [
                {"content": {"parts": [{"text": DUMMY_TEXT}]}, "finishReason": "STOP"}]}))
        with patch.dict(os.environ, {"GOOGLE_API_KEY": DUMMY_KEY}):
            response = adapter.generate(self.messages, model="gemini-3.8-flash", parameters=PARAMETERS,
                supported_parameters={"max_output_tokens", "seed"}, execute_live=True)
        self.assertIsNone(response.error)
        self.assertEqual(response.requested_parameters["temperature"], 0)
        self.assertEqual(response.requested_parameters["top_p"], 1)
        self.assertEqual(response.effective_parameters["temperature"], "unsupported")
        self.assertEqual(response.effective_parameters["top_p"], "unsupported")
        self.assertEqual(set(response.unsupported_parameters), {"temperature", "top_p"})
        payload = transport.call_args.args[2]
        self.assertEqual(payload["generationConfig"], {"maxOutputTokens": 512, "seed": 20261007})
        self.assertNotIn("temperature", payload["generationConfig"])
        self.assertNotIn("topP", payload["generationConfig"])
        self.assertNotIn("thinkingConfig", payload["generationConfig"])
        self.assertEqual(response.requested_model, "gemini-3.8-flash")
        self.assertEqual(response.reported_model, "dummy-runtime-version")

    def test_gemini_cannot_accidentally_send_documented_unsupported_sampling(self):
        adapter, transport = self.adapter("google", HTTPReply(200, {"candidates": [
            {"content": {"parts": [{"text": DUMMY_TEXT}]}}]}))
        with patch.dict(os.environ, {"GOOGLE_API_KEY": DUMMY_KEY}):
            response = adapter.generate(self.messages, model="gemini-3.8-flash", parameters=PARAMETERS,
                supported_parameters=adapter.wire_supported, execute_live=True)
        self.assertEqual(response.effective_parameters["temperature"], "unsupported")
        self.assertNotIn("temperature", transport.call_args.args[2]["generationConfig"])
        self.assertNotIn("topP", transport.call_args.args[2]["generationConfig"])

    def test_gemini_sampling_exception_is_not_applied_to_other_google_models(self):
        adapter, transport = self.adapter("google", None)
        response = self.call(adapter, supported={"max_output_tokens", "seed"})
        self.assertEqual(response.error.category, "unsupported_required_parameters")
        transport.assert_not_called()

    def test_all_adapters_refuse_implicit_live_calls(self):
        for provider, cls in PROVIDER_CLASSES.items():
            adapter = cls(transport=Mock())
            with self.subTest(provider=provider), self.assertRaises(ValidationError):
                adapter.generate(self.messages, model="dummy", parameters=PARAMETERS,
                                 supported_parameters=cls.wire_supported)
            adapter.transport.assert_not_called()

    def test_all_missing_credentials_are_local_errors(self):
        with patch.dict(os.environ, {}, clear=True):
            for cls in PROVIDER_CLASSES.values():
                adapter = cls(transport=Mock())
                response = adapter.generate(self.messages, model="dummy", parameters=PARAMETERS,
                                            supported_parameters=cls.wire_supported, execute_live=True)
                self.assertEqual(response.error.category, "missing_credentials")
                self.assertFalse(response.error.retryable)
                self.assertIsNone(response.raw_output)
                adapter.transport.assert_not_called()

    def test_unsupported_required_parameter_does_not_silently_change_request(self):
        adapter, transport = self.adapter("anthropic", None)
        response = self.call(adapter, supported={"max_output_tokens"})
        self.assertEqual(response.error.category, "unsupported_required_parameters")
        self.assertEqual(set(response.unsupported_parameters), {"temperature", "top_p", "seed"})
        self.assertEqual(response.requested_parameters, PARAMETERS)
        transport.assert_not_called()

    def test_provider_errors_do_not_include_upstream_secrets(self):
        adapter, _ = self.adapter("openai", HTTPReply(429, {"error": {"message": DUMMY_KEY}}, {"Retry-After": "4"}))
        response = self.call(adapter)
        self.assertEqual(response.error.http_status, 429)
        self.assertTrue(response.error.retryable)
        self.assertEqual(response.error.retry_after_seconds, 4)
        self.assertNotIn(DUMMY_KEY, repr(response))
        self.assertIsNone(response.raw_output)

    def test_transport_exception_message_is_not_logged(self):
        adapter, transport = self.adapter("openai", None)
        transport.side_effect = RuntimeError(DUMMY_KEY)
        response = self.call(adapter)
        self.assertEqual(response.error.category, "transport_error")
        self.assertNotIn(DUMMY_KEY, repr(response))
        transport.side_effect = TransportFailure("timeout")
        response = self.call(adapter)
        self.assertTrue(response.error.retryable)

    def test_malformed_provider_envelope_is_not_model_invalid_json(self):
        adapter, _ = self.adapter("openai", HTTPReply(200, {}))
        response = self.call(adapter)
        self.assertEqual(response.error.category, "invalid_provider_response")
        self.assertFalse(response.error.retryable)

    def test_http_nonretryable_and_long_retry_after(self):
        adapter, _ = self.adapter("openai", HTTPReply(401, None))
        self.assertFalse(self.call(adapter).error.retryable)
        adapter, _ = self.adapter("openai", HTTPReply(503, None, {"retry-after": "61"}))
        self.assertEqual(self.call(adapter).error.retry_after_seconds, 61)
