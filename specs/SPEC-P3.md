# SPEC-P3 — Research: orchestrator-worker done honestly  **[RATIFIED]**

**Status: RATIFIED — director review round complete (2026-07-16), all
four rulings granted: (1) substrate — hand-rolled asyncio + Postgres
checkpoints, DIRECTION §3 amended accordingly, §A's revisit conditions
carried as written; (2) research set — 5–8 owner-certified cases via the
fenced method, adjudication split mechanical-verification-executor /
director-ratifies / owner-one-word; (3) planner = `frontier` with
strict-JSON; (4) task modes as specced. The design track ran parallel to
the portfolio track and the N=50 usage window (director sequencing
amendment: early P3 work has no usage-data dependency). STILL NOT
EXECUTABLE: implementation gates on the P2 phase-gate close.**

**Theme:** a research question becomes a multi-source, per-claim-cited
brief — the orchestrator-worker tier (BLUEPRINT P3) built to the same
standard as Ask: eval-first, checkpointed, measured, honest about the
~15× cost.

**Mode legend:** as SPEC-P1 (`[interactive]` / `[headless]` / `[human]`).

**Cross-doc flag (D11) — RESOLVED at the 2026-07-16 review round:**
DIRECTION.md §3 named "LangGraph checkpointer for P3"; the director
ratified §A's hand-rolled substrate and ordered the DIRECTION §3
amendment (carried in this same PR), with §A's revisit conditions
carried as written. The conflict died at the review gate, not in an
executor's silent pick — as designed.

---

## §A · Architecture

```
POST /research {question}
      │
      ▼
  PLANNER  — one gateway call (`frontier`), emits strict-JSON plan:
      │      {sub_questions: [{id, question, rationale}]}, count capped
      │      in config. Parse strictness per the T6 judge.py precedent;
      │      a plan that fails to parse fails the run loudly (no repair
      │      heuristics in v1).
      ▼
  WORKERS — asyncio fan-out, one per sub-question, each a fresh context
      │      (isolation per DIRECTION §3). Each worker runs the EXISTING
      │      ask pipeline — hybrid retrieve → rerank → T8 not-found gate
      │      → routing v1 → grounded generation — over its sub-question.
      │      NO second retrieval stack, no new prompt, no MCP hop.
      │      A gated decline is a first-class worker outcome: the brief
      │      reports the gap honestly (the not-found discipline lifted
      │      to brief level), it is never papered over.
      ▼
  SYNTHESIZER — one gateway call (`frontier`). Input: the original
      │      question + each worker's {sub_question, answer, citations}
      │      wrapped as DATA blocks (D12 — worker output is retrieved
      │      content once removed). Contract: preserve [source_id]
      │      brackets verbatim on every claim carried into the brief;
      │      introduce no id not present in worker output.
      ▼
  CRITIC — deterministic, $0, in code: (1) per-claim citation filter —
             extract_citations() with allowed = the UNION of all workers'
             retrieved ids for this run (the existing structural
             confabulation defense, one parameter wider); (2) coverage
             check — every planned sub-question is either addressed in
             the brief or listed in a declared-gaps section. An LLM
             critic pass is NOT in v1: the blueprint's "critic verifies
             citations" is exactly what the proven filter does for free;
             an LLM critic is earned only when evals demonstrate a
             failure class the deterministic layer misses (D8 pattern).
```

**Seam reuse (the director's constraint, made concrete):** the body of
`app.main.ask()` (retrieve → gate → route → generate → cite-filter) is
extracted into a callable `run_ask(question) -> AskResult` used by BOTH
`POST /ask` and each research worker — same code object, in-process, no
HTTP self-call. This is a small additive refactor of the T9
`run_export()`/`run_ingest()` class and will be HEADLINED in the
implementing PR. `/ask` behavior is unchanged; the exam proves it
(pre/post extraction eval runs must be byte-identical on retrieval and
within known flap on generation).

**Scope boundaries:** corpus-only research in P3 — "multi-source" means
multiple documents within the corpus. Web retrieval is out of scope
(new network surface → dangerous-actions approval, and no eval can
ground it yet). MCP-wrapped corpus search is P4's broker story
(BLUEPRINT P3 mentions MCP tooling for workers; the director ruling to
reuse the seam supersedes it for P3 — flagged here per D11 rather than
silently dropped).

**Substrate decision (RATIFIED 2026-07-16): hand-rolled asyncio +
Postgres checkpoints. The D1 argument, both sides stated:**

*The research consensus (for LangGraph):* DIRECTION §3 and the
underlying field report name orchestrator-worker as the reference shape
and "LangGraph checkpointer for P3 (resume, not restart)" as the
durable-lite consensus; BLUEPRINT §P3 offers "LangGraph with a Postgres
checkpointer — or Temporal for the heavier credential." The framework
buys a graph API, a maintained checkpointer abstraction, streaming,
retry policies, and human-in-the-loop interrupts. On the portfolio
axis, "LangGraph" is a recognizable credential token.

*The framework skepticism (against):* the actual P3 graph is a linear
fan-out/fan-in DAG — plan → N parallel workers → synthesize → critic —
with no cycles, no conditional edges, no mid-run human gates, no
streaming requirement. Every LangGraph feature listed above is
machinery this graph does not exercise; what it WOULD add is a
langchain-core dependency surface, a second state idiom alongside our
psycopg/pydantic house style, framework indirection in every stack
trace, and version churn — costs of the exact class D13 documented when
LiteLLM's dev-mode conveniences hijacked the environment. House rules
already decide this: D1 (complexity only when measured evidence
demands), CLAUDE.md conventions (small pure functions over frameworks),
and the D8 pattern (the fancier tool is FORBIDDEN until the eval set
demonstrates the failure it solves). The hand-rolled substrate is
`asyncio.gather` plus two tables — small enough that its planning and
merge logic are pure functions on the D16 offline floor. The portfolio
counter-argument also cuts the other way: a hand-rolled
orchestrator-worker with honest checkpoint semantics demonstrates
understanding; a framework demo demonstrates installation.

*Named revisit conditions (evidence that re-opens the decision):*
(1) control flow grows cycles — e.g. an eval-earned critic→replan loop;
(2) mid-run human approval gates enter the research path (P4 may do
this to Act, not Research); (3) checkpoint needs exceed step-boundary
resume (partial-generation resume, cross-process handoff). Any of the
three puts LangGraph back on the table with the evidence in hand.

*Temporal-class machinery:* rejected at this scale, per the director's
prior. Temporal earns its keep on multi-process workers, timers
measured in days, queue backpressure, and exactly-once side effects.
A P3 research run is minutes long, single-process, and side-effect-free
(reads + model calls only); the cost of re-running a dead step is
≤ $0.015 (§D), which is neither money nor trust (DIRECTION §3's own
durability bar). P4's approval-survives-restart requirement is a
database row, not a workflow engine; if P5 deployment ever demands
more, that phase argues it.

## §B · Durability — the smallest durable thing

**What persists (app Postgres on 8302, beside `chunks` — it is sitting
right there):** two tables, created by the T3 idempotent-DDL pattern.

```
research_runs   id uuid PK · question text · plan jsonb (null until
                planned) · status text (planning|running|synthesizing|
                done|failed) · brief text (null until synthesized) ·
                declared_gaps jsonb · trace_id text · cost_usd numeric ·
                created_at · updated_at
research_steps  run_id fk · step_no int · sub_question text ·
                status text (pending|done|failed) · result jsonb
                ({answer, citations, retrieved, gate_score, routed_to,
                route_reason, declined}) · error text · completed_at
                · PK (run_id, step_no)
```

**Checkpoint writes (each transactional, at natural call boundaries):**
(1) after plan parse — `plan` lands, step rows created `pending`, status
`running`; (2) after EACH worker completes — its step row flips `done`
with the full result (the unit of resume = one model call, the natural
retry unit); (3) after synthesis — `brief` lands, status `done`. Nothing
finer: mid-generation checkpointing buys nothing when re-running the
step costs half a cent.

**Resume semantics — what step 4 of 6 dying looks like:** the process
dies; rows for steps 1–3 are `done`, 4–6 `pending`/`failed`, the run
sits at `running`. `POST /research/{run_id}/resume` (and a CLI verb on
the T1-style entry point) loads the run: plan present → planning
skipped; every non-`done` step re-executes; all steps `done` → synthesis
runs if `brief` is null. Idempotency is by construction, not machinery:
workers only read the corpus and call the gateway, and a re-run
overwrites its own step row keyed (run_id, step_no) — at-least-once is
safe because there are no external side effects to duplicate. Concurrent
resume of the same run is refused via `pg_advisory_xact_lock(run_id)` —
one line, not a lease protocol.

**Deliberately NOT built (each a Temporal-class fragment this scale
can't justify):** no job queue, no scheduler, no worker processes, no
heartbeats or leases, no auto-resume on app start (surprise re-spend
violates budget discipline — resume is explicit; a `GET /research?status=running`
listing makes interrupted runs visible instead).

**Gate evidence (BLUEPRINT §P3 acceptance, runtime not artifact):**
`kill -9` the app mid-run with ≥2 workers done → restart → resume →
the brief completes; the Langfuse trace and step rows show steps 1–3
executed once and only 4–6 re-ran. Demonstrated live at the phase gate,
demo-script step 4.

## §C · Eval design FIRST (the house rule, applied before a single brief exists)

**Ordering enforced by the task list:** T1 (harness + case schema) and
T2 (owner-certified research set) land and are certified BEFORE T4
(the pipeline) produces its first brief — the same discipline P1
practiced (golden set before improvement, D2). The first research brief
ever generated is scored by machinery that predates it.

**The research golden set (proposal: 5–8 owner-certified cases,
`evals/research_set.jsonl`, same do-not-touch standing as
golden_set.jsonl):** case shape —

```
{ id: rs-001, question,
  must_cover: [themes the brief must address],
  must_cite_sources: [...], may_cite_any: [...],   # union-level, R1/T4 semantics carried
  answer_must_contain: [...], answer_must_not_contain: [...],  # case-insensitive (R1)
  expected_gaps: [aspects the corpus genuinely lacks — the brief must
                  DECLARE these, not improvise them],
  notes }
```

Composition requirements: ≥1 case whose honest outcome is mostly
"the corpus doesn't cover this" (the guard class, lifted to briefs);
≥1 case genuinely spanning ≥3 sources (if no case NEEDS multi-source
synthesis, research adds nothing over ask — this case anchors the §D
single-vs-multi comparison); the rest daily-real research questions
from the owner's actual work.

**Drafted the fenced way (T4 precedent, non-delegable core):** the owner
drafts cases; an ISOLATED verifier session — fenced to corpus/ + the
draft, no app/journal/Langfuse/git-history reads — verifies every
must_contain string and source attribution against the documents; the
owner certifies. Audit trail lands as `evals/research_set.review.md`
(the golden_set.review.md pattern).

**Layer 1 — deterministic checks (pure functions, D16 offline floor):**
- *Per-claim citation check:* the existing filter generalizes — allowed
  ids = union of all workers' retrieved sets; any bracket id in the
  brief outside that union is a confabulation defect. PRESERVED
  PROPERTY: only retrieval-provided ids pass, exactly as in Ask.
- *Claim citedness:* every claim-bearing paragraph carries ≥1 bracket
  (parser is a pure function; "claim-bearing" defined structurally —
  prose paragraphs outside the declared-gaps section).
- *Coverage:* every plan sub-question addressed in the brief or listed
  in declared gaps.
- *must_contain / must_not_contain / must_cite* per case, R1 semantics.

**Layer 2 — judges (T6 machinery reused, not rebuilt):** the
faithfulness judge runs as-is with answer = brief and chunks = the
union of worker chunks (the rubric already scores support-against-
shown-chunks; if the larger context degrades judge agreement, the
rubric iterates against labels exactly as T6/T8 did). One NEW rubric —
*synthesis quality*: coverage of must_cover, conflict handling
(sources that disagree are surfaced as disagreement, never silently
averaged), and gap honesty (expected_gaps declared, not filled).
Calibration per the frozen-anchor protocol (T7 lesson): a director-
labeled, owner-ratified anchor set of real briefs + constructed
negatives (an uncited-synthesis negative and a papered-over-gap
negative at minimum), FROZEN so agreement measures judge drift alone.

**Trajectory-level evals (DIRECTION §3: output-only scoring passes
20–40% more than step inspection reveals):** scored per run from the
step rows + trace, not just the brief — plan quality (sub-questions
decompose the question, count within cap, no duplicates), per-worker
outcomes (retrieval recall against per-sub-question expectations where
the owner specified them; gate honesty — declines consistent with the
corpus), and synthesis input fidelity (each brief claim traceable to a
specific worker's answer, checkable deterministically via the citation
sets). **The seeded-failure case (BLUEPRINT acceptance):** a fixture
run with one worker's answer replaced by plausible-but-uncited text
must be CAUGHT by trajectory checks while final-brief-only scoring
misses it — built as an offline test (D16 unmarked) so CI holds the
property forever.

**Results plumbing:** per-case rows + trajectory columns + per-stage
cost columns into `evals/results/` exactly as today; margin-discipline
reporting carries over.

## §D · Cost model — the ~15× named and bounded

**Measured inputs (P2-T3, locked 2026-07-15):** cheap generation
$0.005/answer · frontier generation $0.0144/answer · decline $0 ·
embed local $0 · blended ask ≈ $0.006/answer.

**Route choices (D3 ladder; assignments CONFIRMED by eval pass rates in
T4/T5, these are the openings, not conclusions):**
- **Planner → `frontier`.** Decomposition quality gates every dollar
  downstream — a bad plan wastes the whole worker fan-out; spending
  ~$0.01 to protect ~$0.05 is the correct direction of asymmetry.
  Demotion to `cheap` is permitted the moment plan-quality trajectory
  evals say cheap plans pass at the same rate (D3: pass rates, not
  vibes).
- **Workers → routing v1 unchanged.** Workers inherit the product
  ladder: `cheap` default, the [-1.67, 1.5) marginal band escalates,
  gate declines cost $0. No research-specific routing config exists.
- **Synthesizer → `frontier`.** D3 and the gateway config both name
  research synthesis as frontier's job; it also carries the largest
  context in the system (N worker briefs).
- **Critic → $0** (deterministic code). Eval-time judges stay on
  `cheap` (T6 unchanged).

**Projection per research question (k = 5 workers; planner/synth token
counts are ESTIMATES to be measured in T4 — bounds, not claims):**

| Stage | Route | Typical | Bounded worst |
|---|---|---|---|
| Planner | frontier | ~$0.010 | ~$0.015 |
| Workers ×5 | cheap default | 5 × $0.005 = $0.025 | all escalate: 5 × $0.0144 = $0.072 |
| Synthesizer | frontier (~2–3× ask input) | ~$0.030–0.050 | ~$0.060 |
| Critic | code | $0 | $0 |
| **Run total** | | **≈ $0.065–0.085** | **≈ $0.15** |

Against blended ask at ~$0.006: **~11–14× typical, ~25× bounded** — the
field's ~15× multi-agent multiplier (D1's own rationale) lands where
predicted. It is named here so nobody is surprised, and bounded by hard
limits, not intentions: `max_sub_questions` cap in `config/research.json`
(knobs in config, T7 precedent), per-stage `max_tokens`, and the
standing gateway `max_budget` $10/30d hard cap as the runaway backstop.
Per-run cost is recorded on one Langfuse trace per run (stages as child
spans — the T3 per-route discipline carries over) and printed in every
results file.

**The honest-comparison deliverable (BLUEPRINT bullet):** the same
research cases run single-agent (one frontier ask over the full
question) vs the orchestrated pipeline; quality delta (Layer 1 + judges)
against token multiple, INCLUDING any case single-agent wins. That
number is the portfolio point; flattering it is a defect.

## §E · D10 stated honestly

Two different "parallel"s, kept distinct: **runtime worker fan-out**
(asyncio inside the product) is not dispatch and needs no graduation —
D10 governs BUILD-time headless workers only.

- **No P3 task REQUIRES parallel dispatch.** The architectural tasks
  (T1, T3, T4, T6) are `[interactive]` by D10's own rule and run under
  the standing executor.
- **Headless-eligible (solo):** T5's seeded-failure fixtures and offline
  trajectory tests — well-specified, verifiable, low blast radius. Even
  these run SOLO: the standing graduation criterion (first zero-salvage
  post-flight pass, T9 ruling) is still unmet, and eligibility ≠
  graduation.
- **If** D10 graduates during the P2 usage window, T5-class tasks are
  the parallel candidates — a velocity gain, never a dependency. P3's
  critical path does not touch dispatch at all.

---

## Tasks

### P3-T1 `[interactive]` Research eval harness — BEFORE the pipeline
Case schema (§C) + Layer 1 deterministic checks as pure functions +
trajectory scoring over step rows + synthesis-quality rubric drafted +
results plumbing. The seeded-failure fixture test lands here, offline.
Done: harness scores a hand-constructed fixture run end-to-end offline;
rubric + anchor-set plan ready for owner labeling.

### P3-T2 `[human + fenced verifier]` Research golden set
Owner drafts 5–8 cases per §C composition; fenced verifier session
checks strings/sources against corpus; owner certifies; review sheet
committed. Non-delegable core, T4 protocol. Adjudication split per the
2026-07-16 ruling: mechanical verification is the executor's (fenced),
the director ratifies, the owner's sign-off is one word.
Done: `evals/research_set.jsonl` certified + review sheet.

### P3-T3 `[interactive]` Durable run state
Two tables (§B, idempotent DDL), checkpoint writes, resume verb,
advisory-lock guard, `run_ask()` extraction with byte-identical /ask
exam evidence.
Done: fake-stage kill/resume test green offline; /ask exam unchanged.

### P3-T4 `[interactive]` Planner → workers → synthesizer
The pipeline per §A over the T3 substrate; config knobs
(`config/research.json`); one trace per run; per-stage cost recorded.
Done: research set runs end-to-end; kill-mid-run → resume demonstrated
live; per-case + cost results committed.

### P3-T5 `[headless-eligible, solo]` Trajectory evals in anger + comparison data
Trajectory scoring against real runs; seeded worker failure demonstrated
caught (the BLUEPRINT acceptance); single-vs-multi comparison runs
executed and tabulated.
Done: trajectory catch demonstrated; comparison table with per-case
quality + cost.

### P3-T6 `[interactive + human]` The honest write-up
Single-vs-multi numbers into README measured-results (the §D
deliverable), losses included; PROGRESS/journal; portfolio-layer
LEARNING/DEFENSE updates.
Done: every published number reproducible from `evals/results/`.

---

**Phase gate (BLUEPRINT §P3, restated as evidence):** kill mid-run →
resume from checkpoint, live; trajectory evals catch the seeded worker
failure that final-output scoring misses; the single-vs-multi
cost/quality comparison is written up with losses included; research
set green (or deltas explained); every number reproducible.

**Dispatch note:** D10 ungraduated; §E governs. No P3 task waits on
graduation.
