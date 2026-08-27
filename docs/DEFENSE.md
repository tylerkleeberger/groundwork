# DEFENSE.md — the hard-questions brief

Every claim in this file traces to a journal entry, a results file, or a
PR. If it couldn't, it isn't here. Companion evidence index:
docs/LEARNING.md.

---

## The 90-second system summary

*(Director edits expected at gate — this is the executor's draft.)*

Groundwork is a grounded knowledge-and-action desk over my own knowledge
base: 567 documents synced one-command from the live source of truth,
3,773 chunks, hybrid retrieval (dense + BM25 + reciprocal rank fusion +
a local cross-encoder rerank), grounded generation with structural
citation enforcement, a calibrated not-found gate so its silence is as
trustworthy as its answers, an LLM-judge layer whose drift is anchored to
frozen human-labeled payloads, and cost-based routing that escalates
marginal cases to a frontier model. Every model call crosses one gateway
seam and lands in Langfuse with a cost figure. It was built
measurement-first: a human-authored golden set gates every merge, every
improvement has a locked before/after, and the two floors that matter —
retrieval recall 1.00 and zero confabulated citations — have never broken
in a locked run. It was also built *by* the pattern it demonstrates: a
director/executor/owner loop with human gates, whose own failures
(a leaked credential, a false worker report, a breached branch rule) are
journaled and fenced rather than smoothed.

*Usage claim, stated precisely: built and instrumented for daily use;
the usage window was shortened by owner priority call (P2 gate,
2026-07-16 — evidence-based closure, not criteria-met).*

## The metrics table (per-claim provenance)

| Claim | Number | Evidence |
|---|---|---|
| Faithfulness (LLM-judge, calibrated) | **0.9408** (target >0.9) | `evals/results/` run 2026-07-15T23:44 · PR 20 |
| Relevancy | **0.9263** (target >0.85) | same run · PR 20 |
| Exam pass rate | **30/31**, single characterized failure | same run; gs-024 dispositioned at the P2 gate: citation half RESOLVED via routing, phrase half KNOWN-LIMITATION (journal, 2026-07-16) |
| Retrieval precision, before→after | **0.55 → 0.6077** (caveat: exam/corpus revised mid-series — see LEARNING.md) | baseline: PR 9 (run 20260708T092139); current: PR 20 runs |
| Retrieval recall | **1.00 — a floor, never broken in a locked run** | every locked run since PR 9; the one break (0.958, pure-CE rerank) failed the task and never merged — PR 11 |
| Honest abstention | **5/5 guards declined by the gate; zero confabulated citations across every locked run** | PR 13 (gate), PR 20 (routed re-validation) |
| Judge–human agreement | mad **0.094**, 93.75% within 0.25, on 8 frozen anchors | PR 13; anchors design PR 11 |
| Cost per answer | cheap **$0.0050** · frontier **$0.0144** · declines **$0** → **~$0.006 blended** | Langfuse trace data, PR 20 |
| Corpus sync | 567 files / 3,773 chunks, one command, idempotent (proven no-op ×2), pin-guarded | PR 15 live demonstrations |
| Total project cost, P0 → P2 gate | **$6.99 / 2,293 traces** (every model call, build + evals + product; frontier share $0.40) | Langfuse daily-metrics API, aggregated at the gate — journal 2026-07-16, tag p2-gate |

## The five hard questions

**1. "Why no framework — no LangChain, no LlamaIndex?"**
Decision D1 (simplest-thing, enforced by phase gates) and D3 (the gateway
is the seam). The pipeline is small pure functions over one HTTP seam;
every layer that matters — chunking, RRF, gate, judge scoring — is
offline-unit-tested precisely *because* it isn't buried in a framework.
When torch's CPU path bus-faulted in Apple's BLAS (journal, 2026-07-09),
the fix was swapping one module for onnxruntime — a framework would have
made that surgery weeks. The evidence the discipline works: every config
change in T7 was measured against the full suite before shipping (PR 11's
four-variant table).

**2. "What broke?" (the honest inventory, each with its fence)**
Five that matter, all journaled the day they happened:
(1) *Unpinned SDK drift silently killed observability* (P0) → the pin
file, and "a repo with no dependency pin file was the class error."
(2) *The reranker broke the recall floor while improving precision* (T7)
→ blend mode + "floors, not averages" as named principle.
(3) *A dispatch worker ran on a leaked API key and died on the spend cap;
a later worker's report attested commits that didn't exist* (T5, T9) →
key-stripping, then mechanical post-flight verification; D10 graduation
is still withheld — trust is earned by a zero-salvage pass, not granted.
(4) *The executor itself pushed to main* (P2) → self-report + a versioned
pre-push hook, tested by blocking its own author.
(5) *A third-party agent session trifurcated the repo via a severed
rename-redirect* → repo-level operations are dangerous-actions; deletion
is permanently human-only.
The pattern across all five: the fix is never "be more careful" — it's a
mechanical check that makes the mistake structurally hard.

**3. "Why RAG instead of fine-tuning?"**
The corpus is alive: it grew **+42 documents in five days** mid-build
(journal, 2026-07-12) and the system absorbed that in one 24-second sync
with zero re-training. Two exam guards became *wrong* in that window
because the knowledge grew into them — a fine-tune would have baked the
old world in. Fine-tuning teaches form, not facts (that claim is itself
in the corpus and survived an adversarial probe — T4's t2). RAG keeps
facts in a database where updating them is an UPDATE, provenance is a
citation, and staleness is a hash mismatch.

**4. "This is one user and 567 documents — does any of it survive scale?"**
The *numbers* wouldn't; the *disciplines* are scale-invariant, and they're
the deliverable: baselines locked before changes; floors that fail tasks;
thresholds calibrated per input distribution (proven twice: ask-gate vs
topic-bands); judge drift anchored to frozen payloads; exams that decay
and get renewed; cost visible per route. Scale swaps components — pgvector
for a dedicated store, one gateway for a fleet — but the seams where those
swaps happen are exactly the ones this build kept clean (D3, D17: any of
them is one config line plus a re-embed).

**5. "What would you do differently?"**
Three things the journal already convicted: **pin generation temperature
from day one** — the unpinned baseline flapped ±3 and cost a re-lock
(T6 gate); **verify worker reports mechanically from the first dispatch**
— trust-the-report cost two salvages before post-flight verification
existed (T9); **treat guard validity as perishable from the start** — the
corpus outgrew two guards before re-locks checked for it (T8). All three
are now standing machinery, which is the honest version of "lessons
learned": a lesson isn't learned until a check enforces it.

## P3 addendum (Research tier — the gate evidence)

| Claim | Number | Evidence |
|---|---|---|
| Research baseline, eval-first | **0/6** first-run, every failure a named defect class; best runs **1/6**; residual uncited blocks 29→17 across run pairs | `evals/results/research-*.json` (committed) · PRs 27-28+ |
| Kill/resume, proven | step's pre-kill checkpoint survived `kill -9` + two resumes; a REAL billing outage recovered with zero re-bought work | journal 2026-07-17 · PR 27 |
| The savepoint bug | checkpoints were silently savepoints — falsified ONLY by killing a real process; store now refuses non-autocommit connections | journal 2026-07-17 (headline finding) |
| $0 critic production record | one-hex-char citation mutations caught ×2; zero-citation workers caught by trajectory checks; zero tokens spent on any catch | run records + results files |
| Cost per research question | **$0.083–0.101 settled** (plan+synth ~$0.043 + workers); §D projection corrected-by-measurement (worker frontier share the driver) | Langfuse trace-joined, PR 28+ |
| Budget fence, fired | build stopped at $9.89/$10.00; in-memory-counter loophole DECLINED on the record; raised 10→20 by director ruling only | journal 2026-07-17 |

## P4 addendum (Act tier — the control plane)

| Claim | Number / fact | Evidence |
|---|---|---|
| First real gated external write | research brief → CLI approval → INSERT-only role → inbox row `c06eadc2` (DRAFT, origin=groundwork), read back verified | journal 2026-08-02 · PR 33 |
| No code path reaches a tool around the broker | AST import-graph test; a second importer of tools/MCP-client **fails CI** | `tests/test_mcp.py` · PR 32 |
| Injection blocked and logged | injection reached a live generator (gate 9.34) and was refused; action queue unchanged; 4 attempts logged as denied rows; research path same | `scripts/redteam_case.py` live run, 2026-08-02 |
| Approval survives restart | pending row survived a kill, a real billing outage, and a 2-week dormancy | journals 2026-07-17 / 07-20 / 08-02 |
| Honest failure in the log | a gated sync executed with `clean:false` + failure banner verbatim (model store wiped by an ollama update) | action log, 2026-08-02 |
| The four persistence surfaces | launchd (processes) · Docker (containers) · Postgres (state) · **model store (pinned models — found unowned)** | journal 2026-08-02 |
| Broker cost | **$0** — deterministic code, no model in the loop | `app/broker.py` |

---

*Sources: BUILD_JOURNAL.md (31 entries), evals/results/ (34 locked runs),
PRs 1–20, docs/DIRECTION.md (D1–D17).*
