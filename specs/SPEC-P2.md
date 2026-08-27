# SPEC-P2 — Ask becomes a daily tool  **[DRAFT]**

**Status: DRAFT — director-authored outline (P1 gate, 2026-07-13);
executor-drafted task detail below awaits director/owner review at the
P2 kickoff gate. Do not execute against this spec until ratified.**

**Theme:** the system earns real usage and learns from it.

**Mode legend:** as SPEC-P1 (`[interactive]` / `[headless]` / `[human]`).

---

### P2-T1 `[interactive]` Persistence + daily-use onboarding
Whatever the owner needs to make asking frictionless — CLI alias or minimal
UI, smallest thing (D1). Executor draft detail: launch agents from
`ops/launchd/` installed and verified surviving a reboot; an `ask` entry
point (shell function or tiny CLI wrapping POST /ask) that prints the
answer, citations, and gate verdict; onboarding = the owner asks real
questions in real work without touching a terminal tab ritual.
Done: owner reports asking from daily flow with zero setup steps.

### P2-T2 `[interactive]` The feedback loop
A one-keystroke way to flag a bad answer in real use; flagged failures
become golden-set candidates with OWNER adjudication as the human anchor
(the T4/T6 standing rule cashing in). Executor draft detail: /ask response
gains a flag affordance (CLI: `ask --flag-last "reason"`); flags persist
(app DB table) with question/answer/retrieved/gate_score snapshot; a
review command lists unadjudicated flags; adjudicated flags emit
clearly-marked golden-set candidate JSON (never self-added — owner
ratifies per the do-not-touch rule). Traps accrue here per the standing
first-three-observed-failures rule.
Done: flag → snapshot → adjudication → candidate flows end-to-end.

### P2-T3 `[interactive]` Routing v1 — D3's ladder in product
Escalate to `frontier` on gate-marginal or owner-flagged cases, starting
from the banked gs-024 evidence (frontier fixes the source-directed
citation half). Executor draft detail: escalation triggers in config
(gate_score band; flagged-question list); per-route cost visible in
Langfuse (route recorded on the trace); the exam runs against the routed
product; gs-024's disposition re-measured under routing and formally
recorded.
Done: routing live behind config; cost-per-route visible; gs-024
re-dispositioned with evidence.

### P2-T4 `[headless-eligible]` Exam growth from usage
Traps from observed failures (the standing rule), guard refresh per
re-lock (the T8 guard-decay insight as routine). Executor draft detail:
a re-lock playbook run (guards validity-checked against the grown corpus,
margin trend recorded); flagged-and-adjudicated failures converted to
cases/traps as proposals; exam size and composition documented per run.
Done: exam reflects real usage; guard floor ≥5 valid; margin trend
plotted across re-locks.

---

**Phase gate:** N real questions asked with feedback captured (owner sets
N at kickoff); gs-024 resolved via routing or formally re-dispositioned;
cost-per-answer curve documented (Langfuse data, per-route).

**Dispatch note:** D10 remains ungraduated — the standing criterion (first
zero-salvage post-flight pass) applies to any P2 headless dispatch; P3
parallel dispatch waits on it.
