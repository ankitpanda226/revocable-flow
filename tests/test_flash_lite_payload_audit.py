"""Exact outbound JSON audit with synthetic credentials and a mocked HTTP opener."""
from hashlib import sha256
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from revocable_flow.providers import GoogleProvider
from revocable_flow.recovery import recovery_transport
from revocable_flow.runner import plan_run

ROOT = Path(__file__).resolve().parents[1]
MODEL = 'gemini-3.5-flash-lite'
KEY = 'SYN-offline-payload-fixture-not-a-real-key'
ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent'
PARAMETERS = {'temperature': 0, 'top_p': 1, 'max_output_tokens': 512, 'seed': 20261007}


class FlashLitePayloadAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        plan=plan_run(ROOT/'configs/free_tier_pilot_v1.yaml')
        cls.messages=next(p['messages'] for p in plan.manifest['prompt_catalog']
                          if p['execution_index']==1 and p['condition']=='post_update')
        cls.expected={'systemInstruction':{'parts':[{'text':cls.messages[0]['content']}]},
                      'contents':[{'role':'user','parts':[{'text':cls.messages[1]['content']}]}],
                      'generationConfig':{'temperature':0,'topP':1,'maxOutputTokens':512,'seed':20261007}}

    def test_real_serializer_and_campaign_transport_emit_exact_frozen_json_once(self):
        reply=Mock(status=200)
        reply.read.return_value=json.dumps({'modelVersion':'SYN-mock-version',
            'candidates':[{'content':{'parts':[{'text':'{"action":"BLOCK","release_fields":[]}'}]}}]}).encode()
        reply.headers={};reply.__enter__=Mock(return_value=reply);reply.__exit__=Mock(return_value=False)
        opener=Mock();opener.open.return_value=reply
        with patch.dict(os.environ,{'GOOGLE_API_KEY':KEY},clear=True), \
             patch('urllib.request.build_opener',return_value=opener), \
             patch('urllib.request.urlopen',side_effect=AssertionError('live HTTP forbidden')):
            response=GoogleProvider(transport=recovery_transport).generate(
                self.messages,model=MODEL,parameters=PARAMETERS,
                supported_parameters=set(PARAMETERS),execute_live=True)
        opener.open.assert_called_once()
        request=opener.open.call_args.args[0]
        self.assertEqual(request.full_url,ENDPOINT)
        self.assertEqual(request.get_method(),'POST')
        self.assertEqual(request.get_header('Content-type'),'application/json')
        self.assertEqual(request.get_header('X-goog-api-key'),KEY)
        self.assertEqual(request.data,json.dumps(self.expected).encode())
        self.assertNotIn(KEY,request.full_url+request.data.decode())
        self.assertEqual(json.loads(request.data),self.expected)
        self.assertIsNone(response.error)
        self.assertEqual(response.requested_parameters,PARAMETERS)
        self.assertEqual(response.effective_parameters,PARAMETERS)
        self.assertEqual(response.unsupported_parameters,())
        self.assertFalse(response.structured_output_enforced)

    def test_field_types_exceptions_and_saved_body_are_exact(self):
        adapter=GoogleProvider()
        self.assertEqual(adapter.allowed_omissions(MODEL),frozenset())
        self.assertEqual(adapter.endpoint_for(MODEL),ENDPOINT)
        for value in self.expected['generationConfig'].values():
            self.assertIs(type(value),int)  # JSON numbers; no strings or bools.
        self.assertEqual(adapter.payload(self.messages,MODEL,PARAMETERS),self.expected)
        body=(ROOT/'docs/reports/flash_lite_outbound_payload_audit.json').read_bytes()
        self.assertEqual(body,json.dumps(self.expected).encode())
        self.assertEqual(sha256(body).hexdigest(),sha256(json.dumps(self.expected).encode()).hexdigest())
        for forbidden in ('responseMimeType','responseSchema','thinkingConfig','topK','scenario_id','expected_action','rationale'):
            self.assertNotIn(forbidden,body.decode())

    def test_missing_required_support_blocks_dispatch_without_38_exceptions(self):
        for field in ('temperature','top_p','max_output_tokens'):
            transport=Mock(side_effect=AssertionError('dispatch forbidden'))
            with patch.dict(os.environ,{},clear=True):
                response=GoogleProvider(transport=transport).generate(
                    self.messages,model=MODEL,parameters=PARAMETERS,
                    supported_parameters=set(PARAMETERS)-{field},execute_live=True)
            transport.assert_not_called()
            self.assertEqual(response.error.category,'unsupported_required_parameters')
            self.assertIn(field,response.unsupported_parameters)

    def test_seed_is_sent_in_audited_payload_and_generic_omission_is_explicit(self):
        from revocable_flow.providers.base import HTTPReply
        transport=Mock(return_value=HTTPReply(200,{'candidates':[{'content':{'parts':[{'text':'SYN-dummy'}]}}]}))
        with patch.dict(os.environ,{'GOOGLE_API_KEY':KEY},clear=True):
            response=GoogleProvider(transport=transport).generate(
                self.messages,model=MODEL,parameters=PARAMETERS,
                supported_parameters=set(PARAMETERS)-{'seed'},execute_live=True)
        self.assertEqual(response.requested_parameters['seed'],20261007)
        self.assertEqual(response.unsupported_parameters,('seed',))
        self.assertNotIn('seed',response.effective_parameters)
        self.assertNotIn('seed',transport.call_args.args[2]['generationConfig'])
        self.assertIn('seed',self.expected['generationConfig'])
