"""Offline boundary tests. No provider, credential file, or external network access."""

import copy
import http.client
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error

import server

# These tests pin the DeepSeek path; HermesTests below switch to the default Hermes backend.
server.AI_BACKEND = "deepseek"


def fixture():
    dataset = {
        "asOf": "2026-11-12",
        "accounts": [{"id": "demo", "name": "Demo Firm", "strategy": "Private markets",
                      "fundContext": "Public fund context", "sourceIds": ["demo-source", "demo-fiction"],
                      "motion": "net_new", "motionSynthetic": True, "holdReason": None},
                     {"id": "other", "sourceIds": ["other-source"]}],
        "sources": [{"id": "demo-source", "accountId": "demo", "text": "Public firm strategy.",
                     "date": None, "kind": "public"},
                    {"id": "demo-fiction", "accountId": "demo", "text": "Fictional scenario for demonstration.",
                     "date": "2026-11-01", "kind": "scenario"},
                    {"id": "other-source", "accountId": "other", "text": "Other account.",
                     "date": None, "kind": "public"}],
    }
    request = {
        "account_id": "demo", "as_of": dataset["asOf"],
        "evidence": [{key: dataset["sources"][0][key] for key in ("id", "text", "date", "kind")}],
        "context": {"name": "Demo Firm", "strategy": "Private markets", "fundContext": "Public fund context",
                    "product": server.PRODUCT},
    }
    plan = {
        "account_id": "demo",
        "fields": [{"id": field_id, "label": field_id.replace("_", " ").title(),
                    "value": "Hypothesis: Ask whether this workflow needs attention.",
                    "basis": "hypothesis", "source_ids": ["demo-source"]} for field_id in server.FIELD_IDS],
        "questions": ["How are side letter obligations tracked today?"],
        "actions": ["Review the public context before discovery."],
    }
    return dataset, request, plan


class FakeResponse:
    status = 200

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, size):
        return self.body[:size]


class FakeOpener:
    def __init__(self, body=None, error=None):
        self.body = body
        self.error = error
        self.request = None
        self.timeout = None

    def open(self, request, timeout):
        self.request = request
        self.timeout = timeout
        if self.error:
            raise self.error
        return FakeResponse(self.body)


def envelope(plan, finish="stop"):
    return json.dumps({"choices": [{"finish_reason": finish, "message": {"content": json.dumps(plan)}}],
                       "usage": {"prompt_tokens": 52, "completion_tokens": 140}}).encode()


class RequestTests(unittest.TestCase):
    def setUp(self):
        self.dataset, self.request, self.plan = fixture()

    def assert_rejected(self, request, message=None):
        with self.assertRaises(server.ApiError) as caught:
            server.validate_request(request, self.dataset)
        self.assertEqual(caught.exception.status, 400)
        if message:
            self.assertIn(message, caught.exception.message)

    def test_exact_bundled_public_request_is_accepted(self):
        self.assertEqual(server.validate_request(self.request, self.dataset), self.request)

    def test_private_text_injection_and_cross_account_source_are_rejected(self):
        self.request["evidence"][0]["text"] = "Private pasted notes"
        self.assert_rejected(self.request, "match")
        self.request = fixture()[1]
        self.request["evidence"][0]["id"] = "other-source"
        self.assert_rejected(self.request, "belong")

    def test_context_date_unknown_id_and_arbitrary_provider_are_rejected(self):
        changes = [lambda x: x["context"].update(name="Private name"),
                   lambda x: x.update(as_of="2026-02-30"),
                   lambda x: x.update(as_of="2026-11-13"),
                   lambda x: x.update(account_id="other-unknown"),
                   lambda x: x.update(base_url="http://example.test")]
        for mutate in changes:
            with self.subTest(mutate=mutate):
                request = copy.deepcopy(self.request)
                mutate(request)
                self.assert_rejected(request)

    def test_duplicate_evidence_missing_evidence_and_oversize_are_rejected(self):
        request = copy.deepcopy(self.request)
        request["evidence"].append(request["evidence"][0])
        self.assert_rejected(request)
        request["evidence"] = []
        self.assert_rejected(request)
        request["evidence"] = [{**self.request["evidence"][0], "text": "x" * 12001}]
        self.assert_rejected(request)

    def test_duplicate_json_keys_and_nonfinite_numbers_are_rejected(self):
        for text in ('{"account_id":"a","account_id":"b"}', '{"n":NaN}'):
            with self.assertRaises(ValueError):
                server.parse_json(text)

    def test_motion_policy_is_canonical_and_cannot_be_supplied_by_the_caller(self):
        self.dataset["accounts"][0].update(motion="customer_hold", holdReason="Fictional unresolved hold")
        self.assertEqual(server.canonical_motion_policy("demo", self.dataset), {
            "motion": "customer_hold", "hold_reason": "Fictional unresolved hold"})
        self.request["account_policy"] = {"motion": "net_new"}
        self.assert_rejected(self.request)


class ResponseTests(unittest.TestCase):
    def setUp(self):
        self.dataset, self.request, self.plan = fixture()

    def assert_rejected(self, plan):
        with self.assertRaises(server.ApiError) as caught:
            server.validate_model_response(plan, self.request)
        self.assertEqual(caught.exception.status, 502)

    def test_valid_plan_and_explicit_unknown_fields(self):
        self.plan["fields"][1].update(basis="unknown", value="Unknown: Current pain needs discovery.", source_ids=[])
        self.assertEqual(server.validate_model_response(self.plan, self.request), self.plan)

    def test_wrong_account_unknown_sources_missing_citation_and_fact_basis(self):
        changes = [lambda x: x.update(account_id="other"),
                   lambda x: x["fields"][0].update(source_ids=["other-source"]),
                   lambda x: x["fields"][0].update(source_ids=[]),
                   lambda x: x["fields"][0].update(basis="fact"),
                   lambda x: x["fields"][0].update(value="This firm has a known buying need."),
                   lambda x: x["fields"][0].update(id="invented"),
                   lambda x: x["fields"].pop(),
                   lambda x: x.update(actions=["x"] * 6),
                   lambda x: x.update(extra="untrusted output")]
        for mutate in changes:
            with self.subTest(mutate=mutate):
                plan = copy.deepcopy(self.plan)
                mutate(plan)
                self.assert_rejected(plan)

    def test_disabled_source_not_present_in_request_cannot_be_cited(self):
        self.plan["fields"][0]["source_ids"] = ["demo-fiction"]
        self.assert_rejected(self.plan)

    def test_account_record_citations_are_allowed_but_demo_wording_is_rejected(self):
        # HGGC's draft once said "illustrative service escalation in this fictional scenario" and still passed.
        self.request["evidence"].append({key: self.dataset["sources"][1][key] for key in ("id", "text", "date", "kind")})
        self.plan["fields"][0]["source_ids"] = ["demo-fiction"]
        server.validate_model_response(copy.deepcopy(self.plan), self.request)
        leaks = ["Hypothesis: In this fictional scenario, ask about the trigger.",
                 "Hypothesis: Ask about the illustrative service escalation.",
                 "Hypothesis: No demo hold applies; do not invent permission barriers.",
                 "Hypothesis: As a net_new account, ask about the trigger."]
        for leak in leaks:
            with self.subTest(leak=leak):
                plan = copy.deepcopy(self.plan)
                plan["fields"][0]["value"] = leak
                self.assert_rejected(plan)
        plan = copy.deepcopy(self.plan)
        plan["questions"] = ["What does the account owner know about the illustrative escalation?"]
        self.assert_rejected(plan)
        plan = copy.deepcopy(self.plan)
        plan["actions"] = ["Book a product demo with the CFO."]  # a real demo is fine
        server.validate_model_response(plan, self.request)


class EmailTests(unittest.TestCase):
    """A draft for an account with sourced contacts must carry a short email to one of them."""

    def setUp(self):
        self.dataset, self.request, self.plan = fixture()
        self.request["evidence"].append({"id": "CT-0123456789ab-profile", "date": None, "kind": "public",
                                         "text": "Rachel Stock \u2014 General Counsel. The employer's public profile identifies this professional."})
        self.plan["email"] = {"contact_id": "CT-0123456789ab-profile", "subject": "Side letter tracking",
                              "body": "Hi Rachel, your Fund V close likely added new side letters. How do you track those obligations today?"}

    def rejected(self, plan):
        with self.assertRaises(server.ApiError) as caught:
            server.validate_model_response(plan, self.request)
        self.assertEqual(caught.exception.status, 502)

    def test_valid_email_passes_and_missing_email_is_rejected(self):
        server.validate_model_response(copy.deepcopy(self.plan), self.request)
        missing = copy.deepcopy(self.plan); del missing["email"]
        self.rejected(missing)

    def test_email_must_go_to_a_sourced_contact_and_greet_them(self):
        cases = {"unknown contact": {"contact_id": "CT-ffffffffffff-profile"}, "not a contact": {"contact_id": "demo-source"},
                 "generic greeting": {"body": "Hello, how do you track side letter obligations today?"},
                 "wrong name": {"body": "Hi Heather, how do you track side letter obligations today?"},
                 "too long": {"body": "Hi Rachel, " + "word " * 120}, "extra key": {"cc": "someone"}}
        for label, change in cases.items():
            with self.subTest(label):
                plan = copy.deepcopy(self.plan); plan["email"].update(change)
                self.rejected(plan)

    def test_the_actual_hggc_failure_is_rejected_everywhere(self):
        # These exact phrases passed every check on 2026-11-15 and reached the seller.
        hggc_email = "Hi Rachel, can you describe the illustrative service escalation in this fictional scenario?"
        hggc_next = "Unknown: actual customer relationship and health. Fictional demo hold policy: Review the fictional hold with the account owner."
        angle = "Hypothesis: No demo hold applies; do not invent permission barriers or expansion limits."
        plan = copy.deepcopy(self.plan); plan["email"]["body"] = hggc_email
        self.rejected(plan)
        for field_id, value in (("next_action", hggc_next), ("strategy", angle)):
            with self.subTest(field_id):
                plan = copy.deepcopy(self.plan)
                target = next(f for f in plan["fields"] if f["id"] == field_id)
                target["value"] = value
                if value.startswith("Unknown"):
                    target.update(basis="unknown", source_ids=[])
                self.rejected(plan)
        plan = copy.deepcopy(self.plan); plan["questions"] = ["What does the account owner understand about the illustrative service escalation?"]
        self.rejected(plan)
        # Ordinary seller language still passes.
        plan = copy.deepcopy(self.plan)
        plan["actions"] = ["Schedule a demo with the General Counsel."]
        plan["email"]["body"] = "Hi Rachel, would a short demo of side letter tracking be useful before your MFN election process starts?"
        server.validate_model_response(plan, self.request)

    def test_buyer_vocabulary_is_enforced(self):
        for phrase in ("investor commitments", "fund obligations"):
            with self.subTest(phrase):
                plan = copy.deepcopy(self.plan); plan["questions"] = [f"How do you track {phrase} today?"]
                self.rejected(plan)

    def test_filler_wording_is_rejected_in_every_seller_visible_field(self):
        # Phrases real drafts produced on 2026-11-16 before the rule existed.
        for phrase in ("I imagine keeping side letter obligations straight gets harder each fund.",
                       "I wanted to reach out directly.", "We offer a seamless, robust way to track them.",
                       "Let's touch base next week.", "I hope this note finds you well.",
                       "I am curious how you track them.", "I'm curious how you track them."):
            with self.subTest(phrase):
                plan = copy.deepcopy(self.plan)
                plan["email"]["body"] = "Hi Rachel, " + phrase + " How do you track them today?"
                self.rejected(plan)
        plan = copy.deepcopy(self.plan); plan["questions"] = ["Would a bespoke report help?"]
        self.rejected(plan)
        plan = copy.deepcopy(self.plan); plan["fields"][0]["value"] = "Hypothesis: They may want to streamline side letter tracking."
        self.rejected(plan)
        # Finance words that only look like filler still pass.
        plan = copy.deepcopy(self.plan); plan["questions"] = ["How does the leveraged buyout fund track its side letter obligations?"]
        server.validate_model_response(plan, self.request)

    def test_the_email_goes_to_the_contact_the_seller_chose(self):
        other = {"id": "CT-aaaaaaaaaaaa-profile", "date": None, "kind": "public", "text": "Cecilia Kwan — Chief Financial Officer."}
        request = copy.deepcopy(self.request); request["evidence"].append(other)
        request["context"]["recipient"] = "CT-0123456789ab-profile"
        server.validate_model_response(copy.deepcopy(self.plan), request)
        request["context"]["recipient"] = "CT-aaaaaaaaaaaa-profile"
        with self.assertRaises(server.ApiError):
            server.validate_model_response(copy.deepcopy(self.plan), request)

    def test_a_recipient_must_be_an_active_contact_profile_of_this_account(self):
        dataset, request, _ = fixture()
        dataset["sources"].append({"id": "CT-0123456789ab-profile", "accountId": "demo", "date": None, "kind": "public", "text": "Rachel Stock — General Counsel."})
        dataset["accounts"][0]["sourceIds"].append("CT-0123456789ab-profile")
        request["evidence"].append({"id": "CT-0123456789ab-profile", "date": None, "kind": "public", "text": "Rachel Stock — General Counsel."})
        request["context"]["recipient"] = "CT-0123456789ab-profile"
        self.assertEqual(server.validate_request(request, dataset), request)
        for bad in ("demo-source", "CT-ffffffffffff-profile", 7, None):
            with self.subTest(bad):
                wrong = copy.deepcopy(request); wrong["context"]["recipient"] = bad
                with self.assertRaises(server.ApiError):
                    server.validate_request(wrong, dataset)

class ProviderTests(unittest.TestCase):
    def setUp(self):
        _, self.request, self.plan = fixture()

    def test_fixed_provider_bounded_tokens_disabled_thinking_and_usage(self):
        opener = FakeOpener(envelope(self.plan))
        result = server.call_provider(self.request, "mock-key-never-real", opener=opener)
        self.assertEqual(opener.request.full_url, server.PROVIDER_URL)
        payload = json.loads(opener.request.data)
        self.assertEqual(payload["model"], "deepseek-flash")
        self.assertEqual(payload["max_tokens"], 2000)
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(opener.timeout, 30)
        self.assertEqual(result["usage"], {"prompt_tokens": 52, "completion_tokens": 140})
        self.assertEqual(result["provider"], "deepseek")
        self.assertIsInstance(result["elapsed_ms"], int)
        self.assertNotIn("key", result)

    def test_system_prompt_forbids_extra_keys_and_names_scenario_sources(self):
        # DeepSeek once added a top-level "type" key on held accounts and the draft was rejected.
        scenario_request = {**self.request, "evidence": [{**item, "kind": "scenario"} for item in self.request["evidence"]]}
        for request in (self.request, scenario_request):
            opener = FakeOpener(error=TimeoutError())
            with self.assertRaises(server.ApiError):
                server.call_provider(request, "mock-key", opener=opener)
            system = json.loads(opener.request.data)["messages"][0]["content"]
            self.assertIn("no type, motion, lane or policy key", system)
            self.assertEqual(system, server.SYSTEM_PROMPT + server.hermes_scenario_note(request))
        self.assertIn("own account records", server.hermes_scenario_note(scenario_request))
        self.assertIn("fictional, illustrative, simulated or scenario", server.SYSTEM_PROMPT)

    def test_timeout_has_explicit_safe_504(self):
        for error in (TimeoutError("secret"), urllib.error.URLError(TimeoutError("secret"))):
            with self.subTest(error=type(error)), self.assertRaises(server.ApiError) as caught:
                server.call_provider(self.request, "mock-key", opener=FakeOpener(error=error))
            self.assertEqual(caught.exception.status, 504)
            self.assertNotIn("secret", caught.exception.message)

    def test_unsafe_held_expansion_action_is_replaced_without_disabled_scenario_citations(self):
        dataset = fixture()[0]
        dataset["accounts"][0].update(motion="customer_hold", holdReason="Fictional account-owner pause")
        # demo-fiction is deliberately absent: only the public source is selected.
        server.validate_request(self.request, dataset)
        policy = server.canonical_motion_policy("demo", dataset)
        next_action = next(field for field in self.plan["fields"] if field["id"] == "next_action")
        next_action["value"] = "Hypothesis: Contact the buyer today to propose immediate expansion."
        self.plan["actions"] = ["Approach the buyer today with an immediate expansion proposal."]
        opener = FakeOpener(envelope(self.plan))
        result = server.call_provider(self.request, "mock-key", opener=opener, motion_policy=policy)
        sent = json.loads(json.loads(opener.request.data)["messages"][1]["content"])
        self.assertEqual(sent["account_policy"], policy)
        self.assertEqual([item["id"] for item in sent["evidence"]], ["demo-source"])
        held_action = next(field for field in result["fields"] if field["id"] == "next_action")
        self.assertEqual(held_action["basis"], "unknown")
        self.assertTrue(held_action["value"].startswith("Unknown:"))
        self.assertEqual(held_action["source_ids"], [])
        self.assertIn("Fix the open issue", held_action["value"])
        self.assertIn("first, then agree with the account owner", held_action["value"])
        self.assertNotRegex(held_action["value"].lower(), "fictional|illustrative|scenario")
        self.assertEqual(result["actions"], [
            "Hold expansion outreach until the open service issue is fixed.",
            "Get the account owner and customer success on one plan to fix the issue, with a checkpoint date.",
            "Agree with the account owner when it is OK to raise expansion again.",
        ])
        self.assertNotIn("Contact the buyer today", json.dumps(result))
        # Remove server metadata before checking the same strict public response schema.
        normalized = {key: result[key] for key in ("account_id", "fields", "questions", "actions")}
        server.validate_model_response(normalized, self.request)

    def test_net_new_route_preserves_non_action_ai_fields_without_customer_hold(self):
        # A live net-new run invented a hold; code now owns final action routing in all lanes.
        opener = FakeOpener(envelope(self.plan))
        result = server.call_provider(self.request, "mock-key", opener=opener,
                                      motion_policy={"motion": "net_new", "hold_reason": None})
        self.assertEqual([f for f in result["fields"] if f["id"] != "next_action"],
                         [f for f in self.plan["fields"] if f["id"] != "next_action"])
        self.assertNotIn("fictional customer hold", json.dumps(result).lower())
        self.assertIn("Restore", result["actions"][0])

    def test_provider_error_body_is_not_exposed(self):
        error = urllib.error.HTTPError(server.PROVIDER_URL, 401, "secret provider message", {}, io.BytesIO(b"secret body"))
        with self.assertRaises(server.ApiError) as caught:
            server.call_provider(self.request, "mock-key", opener=FakeOpener(error=error))
        self.assertEqual(caught.exception.status, 502)
        self.assertNotIn("secret", caught.exception.message)

    def test_malformed_truncated_wrong_account_and_oversized_responses_fail(self):
        wrong = copy.deepcopy(self.plan)
        wrong["account_id"] = "other"
        for body in (b"not json", envelope(self.plan, finish="length"), envelope(wrong), b"x" * 65537):
            with self.subTest(size=len(body)), self.assertRaises(server.ApiError) as caught:
                server.call_provider(self.request, "mock-key", opener=FakeOpener(body))
            self.assertEqual(caught.exception.status, 502)

    @patch.dict(os.environ, {}, clear=True)
    def test_absent_and_invalid_keys_are_not_configured(self):
        with patch.object(server.os, "name", "posix"):
            self.assertIsNone(server.get_api_key())
            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "bad\nheader"}):
                self.assertIsNone(server.get_api_key())
            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "mock-valid-key"}):
                self.assertEqual(server.get_api_key(), "mock-valid-key")

    @patch.dict(os.environ, {}, clear=True)
    def test_raw_dpapi_utf8_and_powershell_hex_are_decrypted_internally(self):
        with patch.object(server.os, "name", "nt"), patch.object(server.Path, "read_bytes", return_value=b"\x01\x00\xffraw"), \
                patch.object(server, "_decrypt_dpapi", return_value=b"mock-valid-key") as decrypt:
            self.assertEqual(server.get_api_key(), "mock-valid-key")
            decrypt.assert_called_once_with(b"\x01\x00\xffraw")
        with patch.object(server.os, "name", "nt"), patch.object(server.Path, "read_bytes", return_value=b"0100ff"), \
                patch.object(server, "_decrypt_dpapi", return_value="mock-valid-key".encode("utf-16-le")) as decrypt:
            self.assertEqual(server.get_api_key(), "mock-valid-key")
            decrypt.assert_called_once_with(b"\x01\x00\xff")


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        cls.dataset, cls.request, cls.plan = fixture()
        dataset_path = root / "data.json"
        dataset_path.write_text(json.dumps(cls.dataset))
        static = root / "dist"
        static.mkdir()
        (static / "index.html").write_text("<title>Account Intelligence Workspace</title>")
        (static / "assets").mkdir()
        (root / "private.txt").write_text("secret")
        cls.httpd = server.WorkspaceServer(("127.0.0.1", 0), static_root=static, dataset_path=dataset_path)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=2)
        cls.temp.cleanup()

    def call(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.httpd.server_port, timeout=2)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        result = response.status, response.read(), dict(response.getheaders())
        connection.close()
        return result

    def post(self, request=None, headers=None):
        return self.call("POST", "/api/plan", json.dumps(request or self.request),
                         {"Content-Type": "application/json", **(headers or {})})

    @patch.object(server, "get_api_key", return_value=None)
    def test_status_and_no_key_failure_are_truthful(self, _):
        status, body, _headers = self.call("GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"configured": False, "provider": "deepseek", "model": "deepseek-flash"})
        with patch.object(server, "call_provider") as provider:
            status, body, _headers = self.post()
            self.assertEqual(status, 503)
            self.assertIn("not configured", json.loads(body)["error"])
            provider.assert_not_called()

    def test_nonlocal_host_and_origin_are_rejected(self):
        for headers in ({"Host": "evil.test"}, {"Origin": "https://evil.test"},
                        {"Origin": "null"}, {"Host": "localhost@evil.test"},
                        {"Origin": "http://localhost.evil.test:8765"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.call("GET", "/api/status", headers=headers)[0], 403)

    @patch.object(server, "get_api_key", return_value=None)
    def test_local_vite_origin_is_allowed_without_cors_or_credentials(self, _):
        status, body, headers = self.call("GET", "/api/status", headers={"Origin": "http://localhost:5173"})
        self.assertEqual(status, 200)
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertNotIn(b"mock", body)

    def test_static_app_head_and_path_traversal(self):
        status, body, headers = self.call("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"Account Intelligence", body)
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(self.call("HEAD", "/")[1], b"")
        for path in ("/../private.txt", "/%2e%2e/private.txt", "/%5c..%5cprivate.txt", "/assets/", "/.env"):
            with self.subTest(path=path):
                self.assertEqual(self.call("GET", path)[0], 404)

    @patch.object(server, "get_api_key", return_value="mock-valid-key")
    def test_success_and_provider_failure_are_distinct(self, _):
        with patch.object(server, "call_provider", return_value=self.plan) as provider:
            status, body, _headers = self.post()
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["account_id"], "demo")
            self.assertEqual(provider.call_args.kwargs["motion_policy"], {
                "motion": "net_new", "hold_reason": None})
        with patch.object(server, "call_provider", side_effect=server.ApiError(504, "Model timeout.")):
            status, body, _headers = self.post()
            self.assertEqual(status, 504)
            self.assertEqual(json.loads(body), {"error": "Model timeout."})

    @patch.object(server, "get_api_key", return_value="mock-valid-key")
    def test_concurrent_provider_request_is_rejected(self, _):
        self.httpd.provider_lock.acquire()
        try:
            with patch.object(server, "call_provider") as provider:
                self.assertEqual(self.post()[0], 429)
                provider.assert_not_called()
        finally:
            self.httpd.provider_lock.release()

    def test_oversize_body_and_malformed_json_fail_before_provider(self):
        with patch.object(server, "call_provider") as provider:
            self.assertEqual(self.call("POST", "/api/plan", "x" * 65537, {"Content-Type": "application/json"})[0], 413)
            self.assertEqual(self.call("POST", "/api/plan", "{", {"Content-Type": "application/json"})[0], 400)
            provider.assert_not_called()


class FakeStream(FakeResponse):
    """Ollama-style NDJSON stream."""

    def __iter__(self):
        return iter(self.body.splitlines(keepends=True))


def ndjson(plan, done_reason="stop", chunk=40):
    text = json.dumps(plan)
    lines = [json.dumps({"message": {"content": text[i:i + chunk]}, "done": False}) for i in range(0, len(text), chunk)]
    lines.append(json.dumps({"message": {"content": ""}, "done": True, "done_reason": done_reason,
                             "prompt_eval_count": 900, "eval_count": 700}))
    return ("\n".join(lines) + "\n").encode()


class HermesTests(unittest.TestCase):
    def setUp(self):
        self.dataset, self.request, self.plan = fixture()

    def run_stream(self, body):
        events = []
        opener = FakeOpener(body)
        opener.open = lambda request, timeout: (setattr(opener, "request", request), FakeStream(body))[1]
        result = server.stream_hermes(self.request, lambda name, value: events.append(name), opener=opener)
        return result, events, json.loads(opener.request.data)

    def test_streams_tokens_validates_and_reports_local_usage(self):
        result, events, payload = self.run_stream(ndjson(self.plan))
        self.assertEqual(payload["model"], server.HERMES_MODEL)
        self.assertFalse(payload["think"])
        self.assertTrue(events.count("token") > 3 and events[-1] == "stage")
        self.assertEqual(result["provider"], "hermes")
        self.assertEqual(result["usage"], {"prompt_tokens": 900, "completion_tokens": 700})

    def test_schema_limits_source_ids_to_this_request(self):
        schema = server.hermes_schema(self.request)
        field = schema["properties"]["fields"]["items"]["properties"]
        self.assertEqual(field["source_ids"]["items"]["enum"], ["demo-source"])
        self.assertEqual(field["id"]["enum"], list(server.FIELD_IDS))
        self.assertEqual(schema["properties"]["account_id"]["enum"], ["demo"])

    def test_scenario_evidence_gets_an_explicit_reminder(self):
        self.assertEqual(server.hermes_scenario_note(self.request), "")
        request = copy.deepcopy(self.request)
        request["evidence"].append({k: self.dataset["sources"][1][k] for k in ("id", "text", "date", "kind")})
        self.assertIn("demo-fiction", server.hermes_scenario_note(request))

    def test_invalid_or_truncated_drafts_are_rejected(self):
        bad = copy.deepcopy(self.plan)
        bad["fields"][2]["value"] = "Key contacts include the CFO."
        for body in (ndjson(bad), ndjson(self.plan, done_reason="length")):
            with self.subTest(body=body[-80:]):
                with self.assertRaises(server.ApiError) as caught:
                    self.run_stream(body)
                self.assertEqual(caught.exception.status, 502)

    def test_unreachable_hermes_is_reported_plainly(self):
        error = urllib.error.URLError(ConnectionRefusedError())
        with self.assertRaises(server.ApiError) as caught:
            server.stream_hermes(self.request, lambda *_: None, opener=FakeOpener(error=error))
        self.assertIn("not reachable", caught.exception.message)

    def test_availability_requires_the_hermes_model(self):
        tags = json.dumps({"models": [{"name": server.HERMES_MODEL}]}).encode()
        self.assertTrue(server.hermes_available(opener=FakeOpener(tags)))
        self.assertFalse(server.hermes_available(opener=FakeOpener(json.dumps({"models": [{"name": "llama3"}]}).encode())))
        self.assertFalse(server.hermes_available(opener=FakeOpener(error=OSError("refused"))))

    def test_status_names_hermes_when_it_is_the_backend(self):
        with patch.object(server, "AI_BACKEND", "hermes"), patch.object(server, "hermes_available", return_value=True):
            self.assertEqual(server.backend_status(), {"configured": True, "provider": "hermes", "model": server.HERMES_LABEL})


if __name__ == "__main__":
    unittest.main()
