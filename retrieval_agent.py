"""
An agentic retrieval loop over a small in-memory corpus.

The corpus is deliberately awkward: the answers to the test questions are
spread across several documents, and the documents use different vocabulary
than a user would. A single fixed search cannot answer them.

Exports run_retrieval_agent(question) -> trace dict, so eval_harness.py can
import it.

Run directly:  python retrieval_agent.py
"""

import json
import re

from runtime import make_client

client = make_client()

MODEL = "claude-opus-5"
MAX_STEPS = 8


# ---------------------------------------------------------------------------
# THE CORPUS. Note the vocabulary mismatch: nothing here says "bill is too
# high" or "cancel", which is how a user would ask.
# ---------------------------------------------------------------------------

CORPUS = {
    "doc-01": {
        "title": "Vendor contracts summary FY26",
        "text": "Northwind Cloud: term ends 2026-09-30, auto-renews unless notice "
                "is given 90 days prior. Acme Compute: term ends 2027-02-28, no "
                "auto-renewal, 30 days notice. Zephyr Hosting: term ends "
                "2026-05-15, auto-renews, 60 days notice.",
    },
    "doc-02": {
        "title": "Committed-use agreements",
        "text": "Northwind Cloud carries a committed-use discount of 15% against "
                "an annual commitment of USD 360,000. Consumption above the "
                "commitment is billed at undiscounted list price. Acme Compute "
                "has no commitment and no discount. Zephyr Hosting is on startup "
                "credit which expires with the term.",
    },
    "doc-03": {
        "title": "Actual spend FY26",
        "text": "Full-year spend: Northwind Cloud USD 412,000. Acme Compute USD "
                "288,500. Zephyr Hosting USD 96,200. Figures exclude support "
                "contracts, which are billed separately.",
    },
    "doc-04": {
        "title": "Egress and storage growth analysis",
        "text": "Northwind Cloud monthly spend rose 34.6% across FY26, from USD "
                "31,200 to USD 42,000. The dominant driver is object storage "
                "egress, which tripled following the analytics migration in Q2.",
    },
    "doc-05": {
        "title": "Acme Compute utilisation trend",
        "text": "Acme Compute monthly spend fell 7.6% across FY26 as workloads "
                "migrated off virtual machines. Remaining usage is concentrated "
                "in two legacy batch pipelines.",
    },
    "doc-06": {
        "title": "Notice period policy",
        "text": "Procurement requires that any intent to renegotiate or terminate "
                "be filed internally 30 days before the contractual notice "
                "deadline, to allow legal review.",
    },
    "doc-07": {
        "title": "Support contract terms",
        "text": "Support is billed at 8% of consumption for Northwind Cloud and a "
                "flat USD 2,000 per month for Acme Compute. Zephyr Hosting "
                "includes support in its base rate.",
    },
    "doc-08": {
        "title": "Planned migrations FY27",
        "text": "The data-platform team plans to move two pipelines from Acme "
                "Compute to Northwind Cloud starting 2026-06-01, adding an "
                "estimated USD 8,400 per month to Northwind consumption.",
    },
}

STOPWORDS = {"the", "a", "an", "of", "for", "and", "or", "to", "in", "on", "is",
             "are", "what", "which", "how", "our", "we", "does", "do", "with"}


def search_documents(query: str, top_k: int = 3) -> dict:
    """Keyword-overlap search. Crude on purpose — real indexes are better, but
    the failure mode you should notice here (vocabulary mismatch) is real in
    every retrieval system."""
    if not query or not query.strip():
        return {"error": "query must be a non-empty string."}
    if not isinstance(top_k, int) or not 1 <= top_k <= 5:
        return {"error": f"top_k must be an integer from 1 to 5, got {top_k}."}

    terms = {t for t in re.findall(r"[a-z0-9]+", query.lower()) if t not in STOPWORDS}
    if not terms:
        return {"error": f"Query '{query}' contained only stopwords. Use specific terms."}

    scored = []
    for doc_id, doc in CORPUS.items():
        haystack = (doc["title"] + " " + doc["text"]).lower()
        hits = sum(1 for t in terms if t in haystack)
        if hits:
            scored.append((hits, doc_id, doc))

    scored.sort(key=lambda row: -row[0])
    if not scored:
        return {
            "query": query,
            "results": [],
            "hint": "No document matched. Try different vocabulary — the corpus "
                    "uses formal contract and finance terms.",
        }

    return {
        "query": query,
        "results": [
            {"doc_id": doc_id, "title": doc["title"], "text": doc["text"],
             "match_score": hits}
            for hits, doc_id, doc in scored[:top_k]
        ],
    }


TOOL_FUNCTIONS = {"search_documents": search_documents}

TOOL_SPECS = [{
    "name": "search_documents",
    "description": (
        "Search the internal document corpus and return matching documents in "
        "full. Call this whenever the answer depends on internal records — "
        "contracts, spend, policies — rather than general knowledge. Matching is "
        "keyword-based, so choose the specific terms a formal document would "
        "use rather than the words in the user's question. Call it repeatedly "
        "with different queries to gather everything a multi-part question needs. "
        "It does not compare or summarise; you must do that yourself."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Specific search terms, e.g. 'committed-use discount "
                               "commitment overage'.",
            },
            "top_k": {
                "type": "integer",
                "description": "How many documents to return, 1 to 5. Default 3.",
            },
        },
        "required": ["query"],
    },
}]

SYSTEM = (
    "You answer questions from an internal document corpus.\n\n"
    "Rules you must follow:\n"
    "1. Ground every factual claim in a document you actually retrieved, and "
    "cite it by doc_id.\n"
    "2. Separate what you found from what you inferred. Label inferences.\n"
    "3. If you cannot find evidence for part of the question, say so explicitly "
    "rather than filling the gap. An admitted gap is a correct answer; an "
    "invented figure is not.\n"
    "4. Search more than once when a question has several parts. Rephrase your "
    "query if a search returns nothing useful."
)


def run_retrieval_agent(question: str, verbose: bool = True) -> dict:
    """Run the agent and return a trace. The trace is what Lab 3.2 evaluates."""
    messages = [{"role": "user", "content": question}]
    trace = {
        "question": question,
        "steps": [],          # one entry per tool call
        "queries": [],        # every query string issued
        "docs_seen": [],      # every doc_id returned
        "answer": None,
        "step_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "hit_step_limit": False,
    }

    for step in range(1, MAX_STEPS + 1):
        response = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            output_config={"effort": "low"},
            system=SYSTEM,
            tools=TOOL_SPECS,
            messages=messages,
        )
        trace["step_count"] = step
        trace["input_tokens"] += response.usage.input_tokens
        trace["output_tokens"] += response.usage.output_tokens

        if response.stop_reason != "tool_use":
            trace["answer"] = "".join(
                b.text for b in response.content if b.type == "text"
            ).strip()
            if verbose:
                print(f"\n{'=' * 72}\nANSWER (after {step} steps, "
                      f"{len(trace['queries'])} searches)\n{'=' * 72}")
                print(trace["answer"])
            return trace

        messages.append({"role": "assistant", "content": response.content})

        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            function = TOOL_FUNCTIONS.get(block.name)
            if function is None:
                output = {"error": f"Unknown tool {block.name}"}
            else:
                try:
                    output = function(**block.input)
                except Exception as exc:  # noqa: BLE001
                    output = {"error": f"{type(exc).__name__}: {exc}"}

            query = block.input.get("query", "")
            found = [r["doc_id"] for r in output.get("results", [])]
            trace["queries"].append(query)
            trace["docs_seen"].extend(found)
            trace["steps"].append({
                "step": step, "tool": block.name, "args": block.input,
                "docs_returned": found, "is_error": "error" in output,
            })
            if verbose:
                print(f"[{step}] search: {query!r} -> {found or 'nothing'}")

            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(output),
                "is_error": "error" in output,
            })

        messages.append({"role": "user", "content": results})

    trace["hit_step_limit"] = True
    trace["answer"] = "Incomplete: step limit reached before an answer."
    if verbose:
        print("\nHit the step limit without answering.")
    return trace


if __name__ == "__main__":
    QUESTION = (
        "Which vendor contract should we renegotiate first, and by what date do "
        "we need to act? Explain the reasoning."
    )
    result = run_retrieval_agent(QUESTION)
    print(f"\nQueries issued: {result['queries']}")
    print(f"Documents seen: {sorted(set(result['docs_seen']))}")
    print(f"Tokens — in: {result['input_tokens']:,}  out: {result['output_tokens']:,}")
