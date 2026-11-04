"""
A guardrail gate in front of an agent's actions.

The agent here handles refund requests. It can read freely and refund with
limits, but a large refund stops for human approval, and it cannot touch
anything not on its allow-list.

This script prompts you at the terminal. Run it interactively.

Run:  python guardrails.py
"""

import json

from runtime import make_client

client = make_client()
MODEL = "claude-opus-5"


# ---------------------------------------------------------------------------
# POLICY — the whole safety configuration in one readable place. Being able
# to read your policy at a glance is itself a safety property.
# ---------------------------------------------------------------------------

POLICY = {
    # LEAST PRIVILEGE: only these tools exist for this agent. Note what is
    # absent — there is no delete_order, no edit_customer, no send_email.
    # A tool you did not provide cannot be misused.
    "allowed_tools": {"get_order", "get_charge_history", "issue_refund"},

    # Actions above this amount require a human.
    "approval_threshold_usd": 500,

    # Hard caps on a single run.
    "max_steps": 8,
    "max_refunds_per_run": 2,
    "max_total_refund_usd": 2000,
}

ORDERS = {
    "4471": {"customer": "Northwind Ltd", "total_usd": 840, "status": "paid"},
    "4472": {"customer": "Acme Corp", "total_usd": 120, "status": "paid"},
    "4473": {"customer": "Zephyr Inc", "total_usd": 9500, "status": "paid"},
}

CHARGES = {
    "4471": [{"date": "2026-03-03", "usd": 840}, {"date": "2026-03-03", "usd": 840}],
    "4472": [{"date": "2026-03-18", "usd": 120}],
    "4473": [{"date": "2026-03-20", "usd": 9500}],
}

REFUNDS_ISSUED = []
AUDIT_LOG = []


# ---------------------------------------------------------------------------
# TOOLS
# ---------------------------------------------------------------------------

def get_order(order_id: str) -> dict:
    order = ORDERS.get(order_id)
    if order is None:
        return {"error": f"No order {order_id}. Known: {sorted(ORDERS)}."}
    return {"order_id": order_id, **order}


def get_charge_history(order_id: str) -> dict:
    if order_id not in ORDERS:
        return {"error": f"No order {order_id}. Known: {sorted(ORDERS)}."}
    return {"order_id": order_id, "charges": CHARGES.get(order_id, [])}


def issue_refund(order_id: str, amount_usd: int, reason: str) -> dict:
    """The only tool with side effects. Everything above it is a read."""
    REFUNDS_ISSUED.append({"order_id": order_id, "amount_usd": amount_usd,
                           "reason": reason})
    return {"refunded": {"order_id": order_id, "amount_usd": amount_usd},
            "reference": f"rf-{len(REFUNDS_ISSUED)}"}


TOOL_FUNCTIONS = {
    "get_order": get_order,
    "get_charge_history": get_charge_history,
    "issue_refund": issue_refund,
}


# ---------------------------------------------------------------------------
# VALIDATION — treat every argument as untrusted input, because it is.
# ---------------------------------------------------------------------------

def validate(tool: str, args: dict) -> str | None:
    """Return an error string if the call is not acceptable, else None."""
    if tool in ("get_order", "get_charge_history"):
        if not isinstance(args.get("order_id"), str) or not args["order_id"].strip():
            return "order_id must be a string."
        return None

    if tool == "issue_refund":
        amount = args.get("amount_usd")
        order_id = args.get("order_id")
        if not isinstance(order_id, str) or order_id not in ORDERS:
            return f"issue_refund needs a known order_id. Known: {sorted(ORDERS)}."
        if type(amount) is not int or amount <= 0:
            return f"amount_usd must be a positive integer, got {amount!r}."
        # SCOPE LIMIT: cannot refund more than was charged.
        charged = sum(c["usd"] for c in CHARGES.get(order_id, []))
        if amount > charged:
            return (f"Refund of {amount} exceeds total charged ({charged}) for "
                    f"order {order_id}. Refuse and re-check the charge history.")
        if not isinstance(args.get("reason"), str) or not args["reason"].strip():
            return "issue_refund requires a reason describing why."
        return None

    return f"No validation rule for tool {tool}."


def is_high_stakes(tool: str, args: dict) -> bool:
    """Irreversible AND high impact -> a person decides."""
    return tool == "issue_refund" and args.get("amount_usd", 0) >= POLICY["approval_threshold_usd"]


def request_approval(tool: str, args: dict) -> tuple[bool, str]:
    """Ask a human. Shows enough context to actually judge — a bare
    'approve? y/n' produces a rubber stamp, not a checkpoint."""
    order = ORDERS.get(args.get("order_id"), {})
    print("\n" + "!" * 72)
    print("APPROVAL REQUIRED")
    print("!" * 72)
    print(f"  Action:    {tool}")
    print(f"  Order:     {args.get('order_id')} ({order.get('customer', '?')})")
    print(f"  Amount:    USD {args.get('amount_usd')}")
    print(f"  Order total: USD {order.get('total_usd', '?')}")
    print(f"  Charges on record: {CHARGES.get(args.get('order_id'), [])}")
    print(f"  Agent's reason: {args.get('reason')}")
    print("!" * 72)

    answer = input("Approve? [y/N, or 'n <reason>']: ").strip()
    if answer.lower() in ("y","yes"):
        return True, "approved by reviewer"
    # FAIL CLOSED: anything that is not an explicit yes is a no.
    reason = answer[1:].strip() or "no reason given"
    return False, reason


# ---------------------------------------------------------------------------
# THE GATE — every action passes through here, in this order.
# ---------------------------------------------------------------------------

def guarded_call(tool: str, args: dict, run_state: dict) -> dict:
    AUDIT_LOG.append({"proposed": tool, "args": args})

    # 1. Least privilege
    if tool not in POLICY["allowed_tools"]:
        blocked = {"error": f"BLOCKED: tool '{tool}' is not permitted for this agent."}
        AUDIT_LOG.append({"blocked": tool, "why": "not permitted"})
        return blocked

    # 2. Validation
    problem = validate(tool, args)
    if problem:
        AUDIT_LOG.append({"blocked": tool, "why": f"validation: {problem}"})
        return {"error": f"BLOCKED: {problem}"}

    # 3. Run limits
    if tool == "issue_refund":
        if run_state["refunds"] >= POLICY["max_refunds_per_run"]:
            AUDIT_LOG.append({"blocked": tool, "why": "refund count limit"})
            return {"error": "BLOCKED: refund limit for this run reached."}
        if run_state["refunded_usd"] + args["amount_usd"] > POLICY["max_total_refund_usd"]:
            AUDIT_LOG.append({"blocked": tool, "why": "refund total limit"})
            return {"error": f"BLOCKED: would exceed the per-run refund cap of "
                             f"USD {POLICY['max_total_refund_usd']}."}

    # 4. Human-in-the-loop for consequential actions
    if is_high_stakes(tool, args):
        approved, reason = request_approval(tool, args)
        AUDIT_LOG.append({"approval": tool, "approved": approved, "reason": reason})
        if not approved:
            # The reason goes back to the agent as an observation.
            return {"error": f"CANCELLED by human reviewer: {reason}"}

    # 5. Execute and log
    result = TOOL_FUNCTIONS[tool](**args)
    if tool == "issue_refund" and "refunded" in result:
        run_state["refunds"] += 1
        run_state["refunded_usd"] += args["amount_usd"]
    AUDIT_LOG.append({"executed": tool, "result": result})
    return result


# ---------------------------------------------------------------------------
# TOOL SPECS AND LOOP
# ---------------------------------------------------------------------------

TOOL_SPECS = [
    {
        "name": "get_order",
        "description": "Read one order's customer, total and status by id. Use "
                       "this before any refund decision.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
    },
    {
        "name": "get_charge_history",
        "description": "List every charge recorded against an order. Use this to "
                       "confirm a duplicate or overcharge before refunding. Never "
                       "refund without checking this first.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
    },
    {
        "name": "issue_refund",
        "description": "Refund money to a customer. This moves real money and "
                       "cannot be undone. Only call it after confirming the "
                       "charge history justifies it. Refunds of USD 500 or more "
                       "require human approval and may be rejected.",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "amount_usd": {"type": "integer", "description": "Whole US dollars."},
                "reason": {"type": "string", "description": "Why this refund is owed."},
            },
            "required": ["order_id", "amount_usd", "reason"],
        },
    },
]


def run_agent(request: str) -> str:
    messages = [{"role": "user", "content": request}]
    run_state = {"refunds": 0, "refunded_usd": 0}

    for step in range(1, POLICY["max_steps"] + 1):
        response = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            output_config={"effort": "low"},
            system=("You handle customer refund requests. Always verify the charge "
                    "history before refunding. Refund only what was actually "
                    "overcharged. If an action is blocked or cancelled, explain "
                    "the situation to the user rather than retrying blindly."),
            tools=TOOL_SPECS,
            messages=messages,
        )

        for block in response.content:
            if block.type == "text" and block.text.strip():
                print(f"\n[{step}] {block.text.strip()}")

        if response.stop_reason != "tool_use":
            return "".join(b.text for b in response.content if b.type == "text").strip()

        messages.append({"role": "assistant", "content": response.content})

        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            print(f"  proposed: {block.name}({json.dumps(block.input)})")
            output = guarded_call(block.name, block.input, run_state)
            print(f"  outcome:  {json.dumps(output)}")
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(output),
                "is_error": "error" in output,
            })
        messages.append({"role": "user", "content": results})

    return "Stopped: step limit reached."


if __name__ == "__main__":
    final = run_agent(
        "Customer Northwind Ltd says they were charged twice for order 4471. "
        "Please investigate and make it right."
    )
    print(f"\n{'=' * 72}\nFINAL REPLY\n{'=' * 72}\n{final}")
    print(f"\nRefunds issued: {json.dumps(REFUNDS_ISSUED, indent=2)}")
    print(f"\nAUDIT LOG ({len(AUDIT_LOG)} entries):")
    for entry in AUDIT_LOG:
        print(f"  {json.dumps(entry)}")
