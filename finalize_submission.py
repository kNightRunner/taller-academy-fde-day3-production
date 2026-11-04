"""Insert measured experiments into the written Day 3 submission, without inventing evidence."""
from __future__ import annotations
import json
from pathlib import Path

source=Path("results/experiments.json")
if not source.exists():
    raise SystemExit("No measured experiments file: run run_experiments.py first.")
data=json.loads(source.read_text(encoding="utf-8"))
out=["# Measured Day 3 execution evidence","",
     f"- Runtime: **{data['provider']}** / **{data['model']}**",
     f"- Recorded UTC: {data['created_utc']}",
     "- All numerical usage metrics below come from observed provider responses, not estimates.",""]

for key,title in [
    ("retrieval_original","3.1 — Iterative retrieval"),
    ("vocabulary_gap","3.1(a) — Vocabulary mismatch"),
    ("absent_information","3.1(b) — Absent information"),
    ("starved_search","3.1(d) — Two-step ceiling")
]:
    t=data[key]
    out += [f"## {title}","",
        f"- Search count: **{len(t['queries'])}**; model turns: **{t['step_count']}**",
        f"- Queries in observed order: `{json.dumps(t['queries'],ensure_ascii=False)}`",
        f"- Document IDs: `{json.dumps(sorted(set(t['docs_seen'])))}`",
        f"- Input / output tokens: **{t['input_tokens']} / {t['output_tokens']}**",
        f"- Hit limit: **{t['hit_step_limit']}**","",
        "**Verbatim answer:**","","> "+(t["answer"] or "(none)").replace("\n","\n> "),""]

out += ["## 3.1(c) — Grounding rules removed",""]
for name,trace in data["grounding_rules_removed"].items():
    out += [f"### {name}","",
      f"Queries: `{json.dumps(trace['queries'],ensure_ascii=False)}`",
      f"Answer: {trace['answer']}",""]

for key,title in [
    ("baseline_evaluation","3.2 — Baseline (three cases)"),
    ("four_case_evaluation","3.2(a) — Added fourth case"),
    ("five_step_process_limit","3.2(b) — Five-step process threshold"),
    ("vague_description_regression","3.2(c) — Weakened search tool description"),
    ("release_evaluation","3.2(d) — Final release evaluation")
]:
    ev=data[key]
    out += [f"## {title}","",
       f"- Runs: {len(ev['runs'])}",
       f"- Strict success rate: **{ev['strict_success']:.1%}**",
       f"- Mean partial score: **{ev['mean_partial']:.3f}**",
       f"- Clean-process rate: **{ev['clean_process']:.1%}**",
       f"- Total input tokens: **{ev['input_tokens']:,}**",
       f"- Total output tokens: **{ev['output_tokens']:,}**",
       f"- Total tokens: **{ev['total_tokens']:,}**","",
       "| Case | Run | Strict | Partial | Process clean | Searches | Steps |",
       "|---|---:|---|---:|---|---:|---:|"]
    for row in ev["runs"]:
        tr=row["trace"]
        out.append(f"| {row['case']} | {row['run']} | {row['outcome']['passed_all']} | {row['outcome']['score']:.2f} | {row['process']['clean']} | {len(tr['queries'])} | {tr['step_count']} |")
    failed=[row for row in ev["runs"] if not(row["outcome"]["passed_all"] and row["process"]["clean"])]
    out += ["",f"Failures observed: **{len(failed)}**. These failures remain visible instead of being hidden by the mean.",""]
    for row in failed:
        c=[k for k,v in row["outcome"]["criteria"].items() if not v]
        p=[k for k,v in row["process"]["checks"].items() if not v]
        out += [f"- {row['case']} run {row['run']}: failed criteria {c}, process violations {p}; queries `{json.dumps(row['trace']['queries'])}`"]
    out.append("")

out += ["## Release decision","",f"Precommitted thresholds: {data['release_bar_precommitted']}.",
        f"Observed decision: **{data['release_verdict']}**.","",
        "## 3.3 — Simulated refund approval, rejection, and adversarial requests","",
        "All recorded refunds are Python in-memory writes only. No payment provider is connected.",""]
for name,record in data["guardrails"].items():
    out += [f"### {name}","",
     f"Final reply: {record.get('answer',record.get('exception','(direct gate test)'))}",
     f"Simulated refund ledger: `{json.dumps(record.get('refunds',record.get('unsafe_simulated_refunds',[])),ensure_ascii=False)}`",
     f"Audit entries: {len(record.get('audit',[]))}",""]
    for item in record.get("audit",[]):
        out.append(f"- `{json.dumps(item,ensure_ascii=False)}`")
    out.append("")

out += ["## 3.4 — Prompt caching limitation","",
   data["cache_measurement"],
   "See `COST_WORKSHEET.md` for explicitly theoretical arithmetic and `cost_lab.py` for hosted-only real measurements.","",
   "## Reproduction","",
   "Raw traces with exact queries, tool results, answer text and token usage are preserved in `results/experiments.json`.",""]

report="\n".join(out)+"\n"
target=Path("results/EVIDENCE.md")
target.parent.mkdir(exist_ok=True)
target.write_text(report,encoding="utf-8")
submission=Path("SUBMISSION.md")
text=submission.read_text(encoding="utf-8")
start="<!-- BEGIN MEASURED -->"
end="<!-- END MEASURED -->"
assert start in text and end in text
before, rest=text.split(start,1)
_,after=rest.split(end,1)
submission.write_text(before+start+"\n"+report+"\n"+end+after,encoding="utf-8")
print(f"Updated {target} and {submission} with measured data.")
