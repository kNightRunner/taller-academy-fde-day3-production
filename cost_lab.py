"""
Measures the effect of prompt caching, then breaks it on purpose.

Every number here comes from response.usage, so nothing is estimated.

Run:  python cost_lab.py
"""

import datetime

import anthropic

client = anthropic.Anthropic()
MODEL = "claude-opus-5"

# A long, stable system prompt — the kind an agent carries on every turn.
# Caching needs a prefix of at least a few hundred tokens to engage, so this
# is padded to a realistic size.
POLICY_SECTIONS = [
    f"Section {i}. Vendor engagement rule {i}: all procurement decisions "
    f"involving annual spend above USD {i * 10_000} must be documented with a "
    f"written justification, reviewed by the finance partner assigned to the "
    f"relevant cost centre, and filed no later than fifteen business days after "
    f"the decision is taken. Exceptions require written approval from the head "
    f"of procurement and must reference the specific clause being waived."
    for i in range(1, 26)
]
STABLE_SYSTEM = (
    "You are an assistant answering questions about internal procurement "
    "policy. Answer only from the policy text below.\n\n" + "\n".join(POLICY_SECTIONS)
)

QUESTIONS = [
    "In one sentence: who reviews a high-spend decision?",
    "In one sentence: what is the filing deadline?",
    "In one sentence: who can grant an exception?",
]


def ask(system, question, use_cache: bool):
    kwargs = {
        "model": MODEL,
        "max_tokens": 16000,
        "output_config": {"effort": "low"},
        "system": system,
        "messages": [{"role": "user", "content": question}],
    }
    if use_cache:
        # Top-level automatic caching: caches the last cacheable block, which
        # here is the long system prompt.
        kwargs["cache_control"] = {"type": "ephemeral"}
    return client.messages.create(**kwargs)


def report(label, responses):
    created = sum(r.usage.cache_creation_input_tokens or 0 for r in responses)
    read = sum(r.usage.cache_read_input_tokens or 0 for r in responses)
    fresh = sum(r.usage.input_tokens for r in responses)
    out = sum(r.usage.output_tokens for r in responses)

    print(f"\n{label}")
    print("-" * 72)
    print(f"  cache WRITE tokens (billed ~1.25x): {created:>8,}")
    print(f"  cache READ  tokens (billed ~0.1x):  {read:>8,}")
    print(f"  fresh input tokens (billed 1x):     {fresh:>8,}")
    print(f"  output tokens:                      {out:>8,}")

    # Rough effective input cost in "full-price token equivalents".
    equivalent = fresh + created * 1.25 + read * 0.1
    print(f"  effective input cost: {equivalent:,.0f} full-price-token equivalents")
    return equivalent


print("=" * 72)
print("EXPERIMENT 1 — stable prefix, caching ON")
print("=" * 72)
print("The same long system prompt on all three calls. The first call writes")
print("the cache; the next two should read it.\n")

cached = []
for i, q in enumerate(QUESTIONS, 1):
    r = ask(STABLE_SYSTEM, q, use_cache=True)
    cached.append(r)
    print(f"  call {i}: write={r.usage.cache_creation_input_tokens or 0:>6,}  "
          f"read={r.usage.cache_read_input_tokens or 0:>6,}  "
          f"fresh={r.usage.input_tokens:>5,}")
cost_cached = report("WITH CACHING", cached)


print("\n" + "=" * 72)
print("EXPERIMENT 2 — no caching at all")
print("=" * 72)
print("Identical calls with cache_control omitted. Every token is processed")
print("fresh, every time.\n")

uncached = []
for i, q in enumerate(QUESTIONS, 1):
    r = ask(STABLE_SYSTEM, q, use_cache=False)
    uncached.append(r)
    print(f"  call {i}: fresh={r.usage.input_tokens:>5,}")
cost_uncached = report("WITHOUT CACHING", uncached)


print("\n" + "=" * 72)
print("EXPERIMENT 3 — caching requested, but silently defeated")
print("=" * 72)
print("cache_control is set, but a timestamp is interpolated into the TOP of")
print("the system prompt. Caching is a PREFIX match, so a prefix that differs")
print("on every call can never hit. Note that there is no error.\n")

broken = []
for i, q in enumerate(QUESTIONS, 1):
    poisoned = f"Current time: {datetime.datetime.now().isoformat()}\n\n" + STABLE_SYSTEM
    r = ask(poisoned, q, use_cache=True)
    broken.append(r)
    print(f"  call {i}: write={r.usage.cache_creation_input_tokens or 0:>6,}  "
          f"read={r.usage.cache_read_input_tokens or 0:>6,}  "
          f"fresh={r.usage.input_tokens:>5,}")
cost_broken = report("CACHING REQUESTED BUT BROKEN", broken)


print("\n" + "=" * 72)
print("VERDICT")
print("=" * 72)
print(f"  caching on, prefix stable:  {cost_cached:>10,.0f}")
print(f"  no caching:                 {cost_uncached:>10,.0f}")
print(f"  caching on, prefix broken:  {cost_broken:>10,.0f}")
if cost_uncached:
    print(f"\n  Caching saved {(1 - cost_cached / cost_uncached) * 100:.0f}% of "
          f"effective input cost.")
    print(f"  The broken version cost {(cost_broken / cost_cached - 1) * 100:.0f}% "
          f"more than the working one — with no error to tell you.")
print("\n  Three calls is a small sample. An agent making twelve calls per task,")
print("  thousands of times a day, turns this ratio into a budget line.")
