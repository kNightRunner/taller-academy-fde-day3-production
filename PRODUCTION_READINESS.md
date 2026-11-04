# Lab 3.5 — Production readiness review

**Agent under review:** an **internal, read-only contract and spend research assistant** that retrieves approved documents, compares supplier exposure, and drafts recommendations with source citations. This is a course design using fictional records, not a description of an employer's system.

## 1. Cost shape

**Reference run:** retrieval/search → summarize evidence → identify deadline → answer with citations. I would expect **3–5 model calls** for a typical complex question and cap execution at 8 turns. The last call sees the most history because it includes all previous tool outputs. The cost of repeatedly sending the growing history matters more than the cost of a single short final response.

Three measures, with deliberate quality checks:

| Change | Reduction | What could worsen | Detect it by |
|---|---|---|---|
| Stop when the necessary contract, notice, and spend sources have been retrieved; avoid duplicate searches | Fewer model calls | Premature stopping, especially missing `doc-06` | Retrieval coverage and absent-evidence accuracy on the repeated evaluation set |
| Retain the original question and all cited evidence IDs; summarize verbose historical tool output | Smaller context | A crucial notice period or exclusion could be dropped | Compare source facts before/after compaction and run contradiction tests |
| Route only unambiguous query rewriting to a smaller model, while preserving the more capable model for final synthesis | Lower model cost for some decisions | Worse query formulation and missed niche documents | Strict-success, clean-process, and sources-retrieved metrics by routed model |

**Operational ceiling:** eight model turns, at most four searches by default for an ordinary question; report `Incomplete` if resources run out. Timeouts and token limits are checked by the program rather than by instructions alone. The final answer must distinguish facts, calculations, and inferences.

## 2. Evaluation plan

These are **test cases, not live operational results**. Repeat each **three times** to expose nondeterminism; run the suite for every relevant prompt/tool/schema change and nightly against a pinned corpus snapshot.

| Test | Measurable success criterion |
|---|---|
| Vendor renegotiation priority | Identify Northwind, cite `doc-01` and `doc-02`, distinguish renewal term from latest internal notice date, mention the 90-day external and 30-day internal lead times |
| Support-inclusive cost | Cite `doc-03` and `doc-07`; compute USD 288,500 + 12 × USD 2,000 = **USD 312,500** without swapping labels |
| Absent termination penalty | State explicitly that the penalty is **not in the corpus**, and do not invent one |
| Informal vocabulary | Reformulate informal “bill too high” into a search that retrieves `doc-04` and identifies egress/growth as evidence |
| Early tool failure | Handle empty search or malformed `top_k` as an error, requery validly or stop with `Incomplete`; never claim success without evidence |

**Precommitted release bar:** **≥90% strict task success and ≥95% clean-process rate** across repeated runs, **0 invented early-termination penalties**, and **0 unapproved writes**. The bar is set before the experiments and should not be lowered after seeing a result. With a small suite, this threshold cannot prove production reliability: supplement with larger examples, hard-negative cases, and human review before a live rollout.

## 3. Tool inventory and least privilege

| Tool | Read/write | Impact / reversibility | Decision |
|---|---|---|---|
| `search_documents(query, top_k)` | Read | Low impact, reversible | Allow on an access-scoped, logged corpus |
| `get_document(doc_id)` | Read | Low/medium impact depending on sensitivity; reversible | Allow only for permitted documents |
| `summarize_evidence(doc_ids)` | Read/computation | Low/medium impact; reversible | Internal computation; not an external write |
| `create_contract_change_request(...)` | Write | High impact, reversible only with approval process | **Remove from autonomous agent**; a human handles changes |
| `send_supplier_notice(...)` | Write | High impact, potentially irreversible | **Never expose to this agent** |

**Explicit removal:** the write tool `create_contract_change_request` is not necessary to deliver most of the research value. The model can produce a cited draft that an authorized person reviews and acts upon. This eliminates the main externally visible risk without sacrificing analytical help.

## 4. Guardrails and human checkpoints

This selected agent is **read-only**; there are no permitted write tools. The separate Lab 3.3 refund example demonstrates a bounded write action with an independent validation and approval gate, but that synthetic refund tool does **not** exist in this research assistant.

If a later version introduced `create_contract_change_request`, it would require a validated supplier ID from the approved directory, a contract ID from retrieval, a documented rationale and evidence list, duplicate-request suppression, a scope limited to draft creation, and explicit approval by a designated procurement owner. The `send_supplier_notice` action would remain absent entirely. A proposed approval volume above **20 per day** would signal poor triage; instead of increasing a reviewer’s workload, we would restrict approvals to genuinely consequential drafts and keep routine analysis read-only.

The gate must check least privilege, argument validity, scope and quotas, approval, **then** execution and audit. A reviewer must see the supplier, contract, requested action, evidence links and impact, not just a yes/no prompt. Missing, ambiguous or expired approval **denies** execution.

## 5. Monitoring dashboard

| Metric | Investigate when | Why |
|---|---|---|
| Strict success rate (rolling golden set) | Drops below **90%** | Outcome regressions |
| Clean-process rate | Drops below **95%** | Reckless paths can produce right answers by chance |
| Citation coverage and retrieval provenance | **Decreases** or unsupported claims appear | Missing evidence is an early-warning sign |
| Absent-information fabrication rate | **Any** invented penalty or unavailable contract term | High-consequence hallucination |
| p95 end-to-end latency | Exceeds **25 seconds** or grows >30% week over week | Tool or model saturation |
| Mean input/output tokens and per-task cost | Rises >25% without quality gain, **or falls suddenly alongside lower retrieval coverage** | A lower cost may reflect premature termination, not efficiency |

Also review tool-error rate, step-cap hit rate, approval denial outcomes, and changes in the source corpus version. Log a correlation ID for each synthetic run in the course; in a real system, avoid putting document content or identifiers in public logs.

**Likely production failure:** an answer sounds coherent but overlooks the procurement policy because the search missed a document with different vocabulary. That can shift a deadline materially while leaving the prose polished. The combination of document-coverage checks, a source-grounded evaluation set, and reviewer verification of actual notice dates would catch it. Because the sample term dates are historical as of November 2026, **all examples are illustrative and must not be treated as actionable current deadlines.**