"""
An evaluation harness for the retrieval agent.

Measures BOTH outcome (did the answer meet the criteria) and process (did the
agent behave sanely getting there), repeats every case to expose
non-determinism, and reports failures individually rather than only an average.

Run:  python eval_harness.py
"""

import statistics
from collections import Counter

from retrieval_agent import run_retrieval_agent

RUNS_PER_CASE = 3

# ---------------------------------------------------------------------------
# THE EVALUATION SET.
# Criteria are CHECKABLE strings, not vibes. Each `must_contain` entry is a
# list of acceptable alternatives — any one of them counts as satisfying it.
# ---------------------------------------------------------------------------

EVAL_SET = [
    {
        "id": "renegotiate-priority",
        "task": ("Which vendor contract should we renegotiate first, and by what "
                 "date do we need to act? Explain the reasoning."),
        "must_contain": [
            ["northwind"],                       # names the right vendor
            ["2026-09-30", "september"],         # the term end date
            # Note the phrasing: a bare "90" would also match "2026-09-30" and
            # "360,000". A criterion that passes by accident is worse than none.
            ["90 days", "90-day", "ninety days"],   # the notice period
            ["30 days", "30-day", "thirty days"],   # procurement's lead time
            ["overage", "412,000", "412000", "commitment"],   # the cost driver
        ],
        "must_cite_docs": ["doc-01", "doc-02"],
        "min_searches": 2,
    },
    {
        "id": "cheapest-vendor-total",
        "task": ("What is our total annual cost for Acme Compute including "
                 "support? Show the components."),
        "must_contain": [
            ["288,500", "288500"],               # consumption
            ["2,000", "2000", "24,000", "24000"],  # support, monthly or annual
            ["312,500", "312500"],               # the correct total
        ],
        "must_cite_docs": ["doc-03", "doc-07"],
        "min_searches": 2,
    },
    {
        "id": "absent-information",
        "task": ("What is our contractual penalty for terminating the Northwind "
                 "contract early?"),
        # This information is NOT in the corpus. The correct behaviour is to
        # say so. We check for an admission, not for an answer.
        "must_contain": [
            ["not find", "no information", "does not", "not specify", "unable",
             "no document", "not available", "cannot find", "nothing"],
        ],
        "must_cite_docs": [],
        "min_searches": 1,
        "must_not_contain": ["penalty is", "the penalty of"],  # no invention
    },
]


# ---------------------------------------------------------------------------
# OUTCOME EVALUATION — per criterion, so you get partial credit and know
# WHICH criterion failed.
# ---------------------------------------------------------------------------

def check_outcome(case, trace):
    answer = (trace["answer"] or "").lower()
    results = {}

    for group in case["must_contain"]:
        label = group[0]
        results[f"contains:{label}"] = any(alt.lower() in answer for alt in group)

    for doc in case.get("must_cite_docs", []):
        results[f"cites:{doc}"] = doc in answer

    for phrase in case.get("must_not_contain", []):
        results[f"avoids:{phrase}"] = phrase.lower() not in answer

    # Reject a known false positive: the right numerals attached to wrong concepts.
    if case.get("id") == "cheapest-vendor-total":
        import re
        bad_consumption = re.search(r"(?:consumption|spend)\\s*(?:is|was|:|=)\\s*(?:usd\\s*)?312,?500", answer)
        bad_total = re.search(r"(?:annual\\s+total|total\\s+annual\\s+cost|total\\s+cost)\\s*(?:is|was|:|=)\\s*(?:usd\\s*)?288,?500", answer)
        results["amounts_correctly_assigned"] = not (bad_consumption or bad_total)

    passed = sum(results.values())
    return {
        "criteria": results,
        "score": passed / len(results) if results else 1.0,
        "passed_all": passed == len(results),
    }


# ---------------------------------------------------------------------------
# PROCESS EVALUATION — over the trace. Catches what outcome checks cannot:
# right answers reached by reckless means.
# ---------------------------------------------------------------------------

def check_process(case, trace):
    queries = trace["queries"]
    checks = {
        "searched_enough": len(queries) >= case["min_searches"],
        "no_duplicate_query": len(queries) == len(set(q.lower().strip() for q in queries)),
        "no_tool_errors": not any(s["is_error"] for s in trace["steps"]),
        "within_step_limit": not trace["hit_step_limit"],
        "produced_an_answer": bool(trace["answer"]),
    }
    return {
        "checks": checks,
        "clean": all(checks.values()),
    }


# ---------------------------------------------------------------------------
# THE HARNESS
# ---------------------------------------------------------------------------

def evaluate():
    rows, failures = [], []

    for case in EVAL_SET:
        print(f"\n### {case['id']}  ({RUNS_PER_CASE} runs)")
        for run in range(1, RUNS_PER_CASE + 1):
            trace = run_retrieval_agent(case["task"], verbose=False)
            outcome = check_outcome(case, trace)
            process = check_process(case, trace)

            rows.append({
                "case": case["id"], "run": run,
                "score": outcome["score"],
                "passed_all": outcome["passed_all"],
                "clean": process["clean"],
                "searches": len(trace["queries"]),
                "steps": trace["step_count"],
                "tokens": trace["input_tokens"] + trace["output_tokens"],
            })

            flag = "PASS" if outcome["passed_all"] else "FAIL"
            clean = "clean" if process["clean"] else "DIRTY"
            print(f"  run {run}: {flag}  score {outcome['score']:.2f}  "
                  f"process {clean}  searches {len(trace['queries'])}  "
                  f"tokens {rows[-1]['tokens']:,}")

            if not (outcome["passed_all"] and process["clean"]):
                failures.append({
                    "case": case["id"], "run": run,
                    "failed_criteria": [k for k, v in outcome["criteria"].items() if not v],
                    "failed_process": [k for k, v in process["checks"].items() if not v],
                    "queries": trace["queries"],
                    "answer": (trace["answer"] or "")[:400],
                })

    # --- aggregate ---------------------------------------------------------
    print(f"\n{'=' * 72}\nSUMMARY over {len(rows)} runs\n{'=' * 72}")
    print(f"Strict success rate (all criteria met): "
          f"{statistics.mean(r['passed_all'] for r in rows):.0%}")
    print(f"Mean partial score:                     "
          f"{statistics.mean(r['score'] for r in rows):.2f}")
    print(f"Clean-process rate:                     "
          f"{statistics.mean(r['clean'] for r in rows):.0%}")
    print(f"Mean tokens per run:                    "
          f"{statistics.mean(r['tokens'] for r in rows):,.0f}")
    print(f"Total tokens spent evaluating:          "
          f"{sum(r['tokens'] for r in rows):,}")

    print(f"\nPer-case strict success:")
    for case in EVAL_SET:
        case_rows = [r for r in rows if r["case"] == case["id"]]
        rate = statistics.mean(r["passed_all"] for r in case_rows)
        searches = [r["searches"] for r in case_rows]
        print(f"  {case['id']:<28} {rate:>4.0%}   searches per run: {searches}")

    # --- variance: the same case behaving differently across runs ----------
    print(f"\nVariance check (a case that sometimes passes is a reliability "
          f"problem, not a capability gap):")
    for case in EVAL_SET:
        outcomes = [r["passed_all"] for r in rows if r["case"] == case["id"]]
        if len(set(outcomes)) > 1:
            print(f"  {case['id']}: INCONSISTENT — {outcomes}")
        else:
            print(f"  {case['id']}: consistent ({'pass' if outcomes[0] else 'fail'})")

    # --- read the failures, do not just average them ----------------------
    if failures:
        print(f"\n{'=' * 72}\nFAILURES ({len(failures)}) — group these by cause\n{'=' * 72}")
        for f in failures:
            print(f"\n[{f['case']} run {f['run']}]")
            if f["failed_criteria"]:
                print(f"  missed criteria: {f['failed_criteria']}")
            if f["failed_process"]:
                print(f"  process issues:  {f['failed_process']}")
            print(f"  queries: {f['queries']}")
            print(f"  answer:  {f['answer'][:200]}...")

        causes = Counter(c for f in failures for c in f["failed_criteria"])
        print(f"\nMost frequent missed criteria: {causes.most_common(5)}")
    else:
        print("\nNo failures. Your evaluation set is probably too easy — "
              "add a harder case.")


if __name__ == "__main__":
    evaluate()
