import copy
import unittest
import server
from test_server import fixture

class NetNewRoutingTests(unittest.TestCase):
    def test_model_cannot_invent_hold_for_net_new(self):
        _, request, plan = fixture()
        request["account_id"] = "demo"
        request["evidence"][0]["id"] = "demo-context"
        plan["actions"] = ["Pause all pursuit until an imaginary hold is resolved."]
        result = server.constrain_net_new_plan(plan, {"motion":"net_new"}, request)
        field = next(f for f in result["fields"] if f["id"] == "next_action")
        self.assertEqual(field["basis"], "hypothesis")
        self.assertEqual(field["source_ids"], ["demo-context"])
        self.assertIn("Work the champion first", field["value"])
        self.assertFalse(any("imaginary hold" in a for a in result["actions"]))

    def test_missing_firm_context_routes_to_research(self):
        _, request, plan = fixture()
        result = server.constrain_net_new_plan(plan, {"motion":"net_new"}, request)
        field = next(f for f in result["fields"] if f["id"] == "next_action")
        self.assertEqual(field["basis"], "unknown")
        self.assertEqual(field["source_ids"], [])
        self.assertIn("Restore", result["actions"][0])

    def test_held_policy_is_not_replaced_by_net_new_route(self):
        _, request, plan = fixture()
        held = server.constrain_held_plan(plan, {"motion":"customer_hold"})
        result = server.constrain_net_new_plan(held, {"motion":"customer_hold"}, request)
        self.assertEqual(result, held)
        self.assertIn("Hold expansion outreach", result["actions"][0])
