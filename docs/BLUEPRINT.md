# Groundwork — An FDE Portfolio System Blueprint

**What this is:** a build specification for one flagship, solo-buildable production system that embodies every concept from the field report and deep-dive doc — and is deliberately structured to produce FDE-resume evidence: deployed system, measured outcomes, both angles demonstrated (AI *in* the product, AI *building* the product).

**Why one system, not several:** a portfolio of small demos reads as tutorials completed. One system where RAG, orchestration, evals, routing, governance, and durability all interlock — with numbers — reads as deployment ability. Optional satellite artifacts spin off from it (listed at the end).

---

## 1 · The system

**Groundwork: a grounded knowledge-and-action desk.** Point it at a document corpus (an OSS project's docs, a synthetic company wiki, or a real client's knowledge base). Users ask questions and get cited answers; can commission deep research briefs; and can trigger real-world actions (draft an email, file a ticket) — which never fire without approval.

Three user-facing capabilities, each existing to force one architecture tier:

| Capability | What the user gets | Architecture it forces |
|---|---|---|
| **Ask** | Cited answer or honest "not found," in seconds | Full RAG pipeline + guardrails (Track A core) |
| **Research** | Multi-source brief, minutes, async | Orchestrator-worker multi-agent + durable execution |
| **Act** | Drafted email / filed ticket, gated | Action broker, approval gates, audit log (control plane) |

The corpus choice matters for the resume: pick something with a real audience (e.g., a popular OSS project's docs + issues) so "62% of questions answered with citations, judged faithful" is a claim about real questions.

## 2 · Architecture (target state)

```
                        ┌────────────────────────────────────────┐
  Web UI / API  ──────► │  App layer (FastAPI)                   │
  POST /ask  /research  │  auth · request classify · route       │
  /act  /approve        └───────┬───────────────┬────────────────┘
                                │               │
                     ┌──────────▼───┐   ┌───────▼───────────────┐
                     │ ASK pipeline │   │ RESEARCH workflow      │
                     │ hybrid       │   │ LangGraph or Temporal: │
                     │ retrieve →   │   │ plan → parallel        │
                     │ rerank →     │   │ workers (fresh ctx) →  │
                     │ generate+cite│   │ synthesize → critic    │
                     └──────┬───────┘   └───────┬───────────────┘
                            │                   │
                 ┌──────────▼───────────────────▼──────────┐
                 │ GATEWAY (LiteLLM)                        │
                 │ task→model routing · caching · spend caps│
                 │ targets: frontier API · cheap API ·      │
                 │          LOCAL model (Ollama endpoint)   │
                 └──────────┬───────────────────────────────┘
                            │
   ┌────────────────────────▼───────────────────────────────┐
   │ ACTION BROKER (control plane)                          │
   │ every tool call: identity → policy → allow/queue/deny  │
   │ approval queue · kill switch · immutable audit log     │
   └───────────┬────────────────────────────────────────────┘
               │ MCP
   ┌───────────▼───────────┐     ┌───────────────────────────┐
   │ Tools as MCP servers  │     │ CROSS-CUTTING              │
   │ corpus search · email │     │ Langfuse traces (all calls)│
   │ (mock→real) · tickets │     │ golden sets + eval suite   │
   └───────────────────────┘     │ ingestion sync worker      │
                                 └───────────────────────────┘
```

Every box maps to a deep-dive section: RAG (Q07), orchestrator-worker (Q01), gateway/routing (Q08, Q10), local model (Q11/Q14), broker (Q09), durability (Q06), MCP (Q02), evals/traces (Q03).

## 3 · Build phases

Each phase ends with acceptance criteria and the resume bullet it earns. Do not start a phase until the prior one's criteria pass — this discipline is itself the methodology being demonstrated.

### P0 — Foundations before features (≈ week 1)
Repo, FastAPI skeleton, Langfuse wired so every model call traces from the first day, LiteLLM gateway with two targets (one frontier, one cheap model) and a hard spend cap, `AGENTS.md`/`CLAUDE.md` written by hand.
- **Accept:** a hello-world model call appears in Langfuse with cost; gateway config swaps models with zero code change.
- **Track B requirement (applies to all phases):** build with Claude Code; agent-produced changes land as reviewed PRs; keep a `BUILD_JOURNAL.md` logging what agents did vs. what you did. This is your "AI-assisted building" evidence.

### P1 — Ask, naive → measured → good (≈ weeks 1–3). *The RAG practice you asked for.*
1. Naive end-to-end: parse corpus, chunk 400–800 tokens on structural boundaries, embed into **pgvector** (Postgres — you'll want it anyway), top-5 cosine, generate. Ship to yourself; it will be mediocre.
2. **Golden set before improvement:** 30+ real questions; per question, record which chunks should surface and what a good answer contains. Wire RAGAS (or hand-rolled checks) into pytest; every change reports retrieval + answer scores.
3. Fix retrieval: add BM25 via Postgres full-text search, merge with RRF, widen to top-50, rerank to 5 (Cohere/Voyage API, or a local cross-encoder). Add citation rendering and a confidence threshold that routes to "not found."
4. Ingestion sync worker: re-index on change, delete on removal, embedding model version pinned.
- **Accept:** faithfulness >0.9 and answer relevancy >0.85 on the golden set; a documented before/after retrieval-quality delta from step 3; "not found" fires on out-of-corpus questions.
- **Resume bullet earned:** *"Built a hybrid-retrieval RAG service (pgvector + BM25 + reranking) over N documents; improved context precision X→Y via measured retrieval fixes; faithfulness 0.9+ on a 30-case golden set."*

### P2 — Routing, caching, and the local floor (≈ week 4)
Static task→model routing in gateway config: classification/extraction → cheap; Ask generation → mid; Research synthesis → frontier. Order prompts for cache hits; instrument cache-hit rate. Add the **local target**: Ollama serving a Qwen-class model, registered in LiteLLM as just another provider; route embeddings-adjacent and classification tasks to it; run the golden set against it to decide what it's allowed to own.
- **Old MacBook setup — Apple Silicon (M1+, 16GB+):** install Ollama → `ollama pull qwen2.5:14b-instruct-q4` (or 7B on 16GB) → `OLLAMA_HOST=0.0.0.0 ollama serve` → add its OpenAI-compatible endpoint to LiteLLM. It's now your zero-marginal-cost floor.
- **Old MacBook — Intel:** skip inference; make it the always-on **control node**: runs the gateway, MCP servers, self-hosted Langfuse (Docker), the ingestion sync worker, and cron-dispatched jobs.
- **Accept:** cost-per-answer dashboard shows the routed mix; cache-hit >50% on stable prefixes; an eval-backed list of tasks the local model owns.
- **Bullet:** *"Cut cost/request X% via task-based model routing and prompt caching across frontier, cheap, and locally hosted open-weight models behind one gateway — assignments decided by eval pass rates, not benchmarks."*

### P3 — Research: orchestrator-worker done honestly (≈ weeks 5–6)
An orchestrator call emits a JSON plan of subtasks; dispatch code runs workers concurrently, each with a fresh context and scoped tools (corpus search via MCP, optionally web); synthesis call merges; a critic pass verifies citations before delivery. Run it inside **LangGraph with a Postgres checkpointer** (durable-lite) — or Temporal if you want the heavier credential — so a crash mid-run resumes, not restarts. Add **trajectory-level evals**: score tool arguments and step outputs on 5–10 scripted research tasks, not just final briefs. Publish your measured single-agent vs multi-agent comparison (quality delta vs token multiple) — including, if honest, the cases where single-agent won.
- **Accept:** kill the process mid-run → resumes from checkpoint; trajectory evals catch a seeded worker failure that final-output evals miss; the cost/quality comparison is written up.
- **Bullet:** *"Designed a checkpointed orchestrator-worker research system; documented a measured quality/cost tradeoff vs single-agent (~Nx tokens for +M% eval score) and step-level evaluation catching failures invisible to output-only scoring."*

### P4 — Act: the control plane (≈ weeks 7–8)
Two action tools as MCP servers — email drafter (mock SMTP first) and ticket filer (real: GitHub Issues) — reachable **only** through the action broker: per-agent scoped identity, policy rules (allow/deny, per-agent daily budget), a "consequential actions" list that always queues for approval, an approval UI (a simple queue page counts), kill switch, and the Langfuse trace stream doubling as the immutable audit log. Add injection defense: retrieved chunks and MCP results are wrapped/escaped as data; write a red-team test where a corpus document contains an injection attempt and prove the broker blocks the resulting action.
- **Accept:** no code path reaches a tool around the broker (test proves it); the injection red-team case is blocked and logged; an approval survives an app restart.
- **Bullet:** *"Implemented an agent control plane (action broker with per-agent identity, policy-before-dispatch, durable approval gates, audit logging); demonstrated prompt-injection containment via red-team tests."*

### P5 — Ship + the meta-artifact (≈ week 9)
Deploy (small VPS or Fly/Railway; the Intel MacBook can host the non-inference services), write the README as a case study with the numbers, record a 5-minute demo. Then run the **AI Systems Review Agent** (companion doc) against Groundwork itself and publish the report, findings and all. Auditing your own system with your own agent-facing checklist is the single most FDE-shaped artifact in the portfolio.

## 4 · The demo script (interview-ready, ~7 minutes)

1. Ask an in-corpus question → cited answer; click a citation. Ask an out-of-corpus question → honest "not found." *(reliability)*
2. Open Langfuse: the trace tree for that answer — retrieval, rerank, generation, cost. *(observability)*
3. Change a prompt live → run evals → show the per-case score delta → revert. *(evaluation-driven development)*
4. Commission a research brief; show workers running in parallel; kill the process; resume. *(orchestration + durability)*
5. Ask it to file a ticket → approval queue → approve → audit log entry. Then trigger the injection test doc → blocked. *(governance)*
6. Show the cost dashboard: which model handled what, including the MacBook. *(economics)*
7. Close with `BUILD_JOURNAL.md`: which parts agents built, how you reviewed them. *(Track B — you don't just ship agents, you work with them)*

## 5 · Satellite artifacts (each spins off nearly free)

- The **review-agent checklist** run against 1–2 public OSS AI projects → published audit posts.
- Your **MCP servers** (corpus search, broker-gated actions) as standalone repos.
- A short write-up: *"Single vs multi-agent: what 15× tokens actually bought me"* — honest numbers are rare and memorable.
- The golden-set + pytest eval harness as a template repo.

## 6 · Guardrails for the build itself

- **Don't skip phase gates.** The discipline is the demonstration; an FDE who builds P3 before P1's evals pass is exhibiting the anti-pattern the whole field warns about.
- **Keep mock/real boundaries explicit** (mock SMTP, real GitHub Issues) — knowing where to keep training wheels is judgment worth showing.
- **Every number in the README must be reproducible** by running the eval suite in the repo. That single property separates this from every tutorial project a reviewer has seen.
