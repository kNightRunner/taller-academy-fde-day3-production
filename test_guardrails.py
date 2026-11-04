"""
Deterministic tests for the safety layer. No model, no API, no network.

Run:  python test_guardrails.py
"""

import sys
import types

# Install a stub 'anthropic' BEFORE importing guardrails, so the module-level
# client construction succeeds with no key — and so any actual API call raises.
_stub = types.ModuleType("anthropic")


class _Blocked:
    def create(self, **kw):
        raise AssertionError("a test reached the API — tests must stay offline")

    def count_tokens(self, **kw):
        raise AssertionError("a test reached the API — tests must stay offline")


_stub.Anthropic = lambda *a, **k: types.SimpleNamespace(messages=_Blocked())
sys.modules["anthropic"] = _stub

import guardrails as G  # noqa: E402  -- must come after the stub


passed = failed = 0
failures = []


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ok   {name}")
    else:
        failed += 1
        failures.append(name)
        print(f"  FAIL {name}" + (f"   <- {detail}" if detail else ""))


# --- validation: every argument is untrusted input -------------------------
print("\nVALIDATION")
check("rejects refund above what was charged",
      G.validate("issue_refund", {"order_id": "4473", "amount_usd": 99999,
                                  "reason": "r"}) is not None)
check("rejects negative amount",
      G.validate("issue_refund", {"order_id": "4471", "amount_usd": -5,
                                  "reason": "r"}) is not None)
check("rejects amount as string, not int",
      G.validate("issue_refund", {"order_id": "4471", "amount_usd": "840",
                                  "reason": "r"}) is not None)
check("rejects missing reason",
      G.validate("issue_refund", {"order_id": "4471", "amount_usd": 100,
                                  "reason": ""}) is not None)
check("rejects unknown order",
      G.validate("issue_refund", {"order_id": "0000", "amount_usd": 10,
                                  "reason": "r"}) is not None)
check("allows a legitimate refund",
      G.validate("issue_refund", {"order_id": "4471", "amount_usd": 840,
                                  "reason": "duplicate charge"}) is None)

# --- the approval threshold is a boundary, so test both sides of it --------
print("\nAPPROVAL THRESHOLD")
check("USD 499 runs automatically",
      not G.is_high_stakes("issue_refund", {"amount_usd": 499}))
check("USD 500 requires a human",
      G.is_high_stakes("issue_refund", {"amount_usd": 500}))
check("reads never require approval",
      not G.is_high_stakes("get_order", {"order_id": "4471"}))

# --- least privilege: the strongest guardrail is an absent tool ------------
print("\nLEAST PRIVILEGE AND LIMITS")
state = {"refunds": 0, "refunded_usd": 0}
result = G.guarded_call("delete_account", {"customer": "Northwind"}, state)
check("a tool that does not exist cannot be called",
      "BLOCKED" in result.get("error", ""), result)

G.REFUNDS_ISSUED.clear()
state = {"refunds": 0, "refunded_usd": 0}
G.guarded_call("issue_refund", {"order_id": "4472", "amount_usd": 120, "reason": "a"}, state)
G.guarded_call("issue_refund", {"order_id": "4472", "amount_usd": 120, "reason": "b"}, state)
third = G.guarded_call("issue_refund", {"order_id": "4472", "amount_usd": 120,
                                        "reason": "c"}, state)
check("refund COUNT cap is enforced", "BLOCKED" in third.get("error", ""), third)

state = {"refunds": 0, "refunded_usd": 1900}
over = G.guarded_call("issue_refund", {"order_id": "4471", "amount_usd": 840,
                                       "reason": "a"}, state)
check("refund TOTAL cap is enforced", "BLOCKED" in over.get("error", ""), over)

# --- fail closed: anything that is not an explicit yes must be a no --------
print("\nFAIL CLOSED")
import builtins  # noqa: E402

original_input = builtins.input
for answer, label, should_execute in [
    ("y", "explicit yes -> executes", True),
    ("n needs manager sign-off", "no with reason -> blocked", False),
    ("", "empty input -> blocked", False),
    ("maybe later", "unrecognised input -> blocked", False),
]:
    builtins.input = lambda _prompt="", _a=answer: _a
    G.REFUNDS_ISSUED.clear()
    state = {"refunds": 0, "refunded_usd": 0}
    outcome = G.guarded_call("issue_refund", {"order_id": "4471", "amount_usd": 840,
                                             "reason": "duplicate"}, state)
    executed = "refunded" in outcome
    check(label, executed == should_execute, outcome)
builtins.input = original_input

print(f"\n{'=' * 60}\n{passed} passed, {failed} failed")
for name in failures:
    print(f"  FAILED: {name}")
sys.exit(1 if failed else 0)
