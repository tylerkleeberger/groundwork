# DIRECTION.md — Director's Brief & Decision Record

**Audience:** any executor session (Claude Code, interactive or headless) and any
future director session. This file carries the *why* behind the build. CLAUDE.md
carries the *rules*; specs carry the *tasks*; PROGRESS.md carries the *state*.
Read this once per phase, or whenever a decision here seems to conflict with a task.

**Provenance:** distilled from a mid-2026 field research report and a director
engagement covering AI engineering, orchestration, and FDE practice. Where a
number appears, treat it as directional field consensus, not gospel.

---

## 1 · Project thesis

Groundwork is a grounded knowledge-and-action desk AND a portfolio object for a
forward-deployed-engineer profile. Every architectural choice serves both: it must
be genuinely useful daily (corpus = owner's own research/notes) and it must
demonstrate a field-consensus practice with **reproducible numbers**. A feature
that works but can't be measured is incomplete. A claim in the README that can't
be reproduced by running the eval suite is a defect.

Three capabilities, each chosen to force one architecture tier:
- **Ask** → full RAG lifecycle (hybrid retrieval, rerank, citations, honest not-found)
- **Research** → orchestrator-worker multi-agent, checkpointed/durable
- **Act** → control plane (action broker, approval gates, audit log)

The build itself is the fourth demonstration: director (chat) → executor
(Claude Code) → human approval gates, logged in BUILD_JOURNAL.md. The system
contains agents AND is built by agents; both are documented deliberately.

## 2 · Standing decisions (with rationale)

**D1 — Simplest-thing rule, enforced by phase gates.** Complexity is added only
when measured evidence demands it. Phases complete only when their acceptance
criteria pass; no starting P(n+1) before P(n)'s gate. Field basis: the single
strongest consensus across frontier labs — start with a tooled single model call;
multi-agent only for genuinely parallel or context-exceeding work (it costs ~15×
tokens vs. a single chat).

**D2 — Evals gate everything.** Golden set before improvements; every
prompt/retrieval/model change runs `pytest evals/` and reports per-case deltas;
red does not merge. The golden set is HUMAN-AUTHORED (task P1-T4 is non-delegable):
it is proprietary ground truth and the credibility of every published number.
Layer 1 deterministic checks on everything; Layer 2 LLM-as-judge (calibrated
against hand labels); Layer 3 periodic human review feeding new cases.

**D3 — The gateway is the seam.** All product model calls go through LiteLLM
(:4000) using aliases `frontier` / `cheap` / `local` — never a provider SDK
directly from feature code. Rationale: swappable providers (including the local
Ollama model as a routing target), one place for spend caps, uniform Langfuse
tracing. Routing is per-TASK, not per-turn (mid-conversation model switches
forfeit cached prefixes). Assignments live in config and are decided by eval
pass rates, not vibes or public benchmarks.

**D4 — Subscription/API split.** All build work (interactive Claude Code,
headless dispatch) runs on the owner's subscription. The metered API key exists
ONLY for the product's runtime and evals, is project-scoped, and is capped twice:
provider-side hard limit + gateway `max_budget`. Two keys, two fences —
per-project identity practiced from day one.

**D5 — Port convention.** This machine has heavy port contention. Groundwork
claims **8300–8399**: Langfuse web = 8300, app Postgres (pgvector) = 8302,
future FastAPI app = 8310 (reserve), gateway on 4000. The Langfuse v3 stack
(official upstream compose, isolated in `ops/langfuse/`) exposes NO other host
ports — its internal Postgres/ClickHouse/Redis/MinIO talk over Docker's network
only. Never assume 3000-range or 5432 defaults anywhere.

**D6 — Python 3.13, pinned.** 3.14 broke Rust-based wheels (orjson/PyO3 ceiling).
`.python-version` pins 3.13; do not "fix" build failures with ABI-compat
environment flags — downgrade the interpreter, not the guardrails.

**D7 — Corpus is pluggable; personal vs demo configs.** The daily instance
points at the owner's own documents (`corpus/`, gitignored, never committed);
a demo config points at a public OSS-docs corpus so the portfolio never exposes
personal material. Ingestion must handle sync honestly: re-index changed files
only, delete removed ones, pin the embedding model version. A silently stale
index is the most common production RAG failure.

**D8 — Retrieval is the bottleneck; fix it before generation.** Naive pipelines
fail retrieval on ~40% of queries. The mandated sequence: naive end-to-end →
golden set → hybrid (vector + BM25, RRF merge) → wide retrieve (top-50) →
cross-encoder rerank (top-5). Agentic RAG / GraphRAG are FORBIDDEN until the
golden set demonstrates the specific failure they solve. Out-of-corpus questions
must produce an honest "not found," never a confabulated citation.

**D9 — Oversight is checkpoint-based, by design.** Automation converts human
oversight from inline (watching every hop) to checkpoints: review the diff AND
the runtime evidence (e.g., `docker compose ps`, eval output) — never the
artifact alone. Claude Code permission modes + the dangerous-actions list in
CLAUDE.md are the dev-time control plane. Long-horizon work leaves artifacts
(PROGRESS.md, journal, git history) so any session can resume cold.

**D10 — Dispatch graduation rule.** Headless workers (scripts/dispatch.sh) get
only tasks marked [headless] in a spec — well-specified, verifiable, low blast
radius. First dispatch runs SOLO; parallel dispatch is earned by one clean solo
review cycle. Ambiguous or architectural work stays interactive. Trust is
granted per-task-type, never globally.

**D11 — Documentation is layered, not duplicated.** One source of truth per
concern: CLAUDE.md (rules, auto-loaded) → DIRECTION.md (decisions/why) →
docs/BLUEPRINT.md (product/PRD/roadmap) → specs/SPEC-Pn.md (current tasks) →
PROGRESS.md (live state) → BUILD_JOURNAL.md (history/evidence). If two docs
disagree, flag it — do not silently pick one. Amend the blueprint rather than
forking a new PRD.

**D12 — Injection defense from P1 onward.** Retrieved chunks, tool results, and
any external content entering model context are DATA, not instructions — wrap
and treat accordingly. P4 includes a red-team case (malicious corpus document
attempting to trigger an action) that the broker must block. Third-party MCP
servers: provenance-checked, minimally credentialed.

**D13 — App-owned environment variables carry the APP_ prefix.** Conventional
names (DATABASE_URL, REDIS_URL, PORT, etc.) are shared namespace that
third-party tools may read as their own configuration — LiteLLM's dev-mode
load_dotenv() walking up from its install path proved the class. Never rely on
shell-level unsetting to resolve such collisions; rename to the app-scoped
name. Gateway runs LITELLM_MODE=PRODUCTION always.

**D14 — Git is executor-operated; merges require recorded authority.** The
executor branches, commits, and opens PRs. A private-repo PR may be self-merged
only with an explicit director PASS and green CI, followed by mechanical
verification of `state`, `mergedAt`, and `baseRefName`. Public-repo PRs remain
owner-merged without exception; phase-gate tags and ratification merges also
require the owner's word. From P1 on, PR review replaces working-tree review as
the D9 checkpoint (diff + runtime evidence live in the PR description), and
BUILD_JOURNAL entries reference PR numbers. Branch naming:
`<phase-task>-<slug>`. The P0 bootstrap commit directly on main — made on
Director instruction, before the remote existed — is the sole exception;
branch protection on main converts the owner-gate from promise to enforcement.

**D15 — Trunk-based development, ratified.** main is always releasable truth;
one short-lived branch per spec task (`<phase-task>-<slug>`); no
develop/release/environment branches; phase gates are annotated tags;
branches deleted after merge. Named and ratified so no future session
"improves" it toward GitFlow — that machinery exists to coordinate many
humans shipping to many environments, which this repo is not. (Owner ruling:
`p0-gate` predates this rule and stays a lightweight tag; annotated applies
from `p1-gate` forward.)

**D16 — CI enforces the offline floor; live evals stay local.** (1) pytest
markers split the suite: `@pytest.mark.live` for anything needing services
(gateway/Langfuse/Postgres/Ollama) or spending tokens; everything unmarked
must run offline anywhere — pure functions (chunking, parsing, RRF math,
config validation) are the unmarked batch, starting with P1-T2. (2) A
minimal GitHub Actions workflow runs `pytest -m "not live"` (Python 3.13,
requirements.txt, no secrets, no services) on every PR, enforced via
required status checks in branch protection. (3) Full evals run locally
before any PR opens; from P1-T5 the results file
(`evals/results/<timestamp>.json`) is referenced in the PR description —
the owner gate reviews eval evidence, CI enforces the deterministic floor.
CD does not exist until P5 has a deployment target. Self-hosted live-eval
runner: revisit at P3, not before — earned complexity.

**D17 — Embeddings ride the gateway seam; personal-corpus embeddings stay
local by default.** The `embed` alias routes through LiteLLM like every
other model call (traced, swappable, one config line). The owner's personal
corpus is embedded locally (nomic-embed-text, 768d, task prefixes
`search_document:` / `search_query:` from the start — retrofitting prefixes
forces a full re-embed). Upgrading to an API embedding model is permitted
only on golden-set evidence of embedding-quality recall failures, and costs
exactly one alias change plus a full re-embed. Model identity + dimensions
are pinned in three places: gateway config, the DB's ingest_meta row
(ingest refuses to mix models), and the Ollama model tag.

**D18 — Durable requests.** An invocation is a row on the CC-OS Message bus,
not only a live HTTP call. Answers return to the asking surface
retry-until-delivered through the CheckIn machinery. This applies the pattern
that survived kill -9, a billing outage, and dormancy to requests themselves.

**D19 — Reachability over relocation.** The serving tier stays local, leaving
embeddings, vectors, thresholds, and exam evidence untouched. A tunnel
(Cloudflare Tunnel or Tailscale) makes it reachable so phone-time answers
arrive in seconds; the durable queue is the fallback when the laptop is
unreachable, so no request is lost. Relocating embeddings/vectors to a hosted
tier is a P7 candidate triggered by ledger evidence of queued requests the
owner was actively waiting on and/or sustained local-stack burden on the
owner's machine (two incidents are already on record).

**D20 — Sync is split by direction.** Inbound EM-to-corpus sync is
pre-authorized on a schedule with one audit row per run; its blast radius is
groundwork's own rebuildable store. Outbound `em_draft_kb`-to-EM-inbox writes
remain gated per act. Inbound returns to gated if it gains any delete path
beyond the existing prune or writes outside groundwork. An approval firing
hourly for a benign act trains the approver to stop reading — the cries-wolf
rule applies to the gate itself.

**D21 — Multi-corpus serving is P7.** Serving other CC-OS spaces through D7
profiles is explicitly deferred beyond the Engineering Map lane.

**D22 — Exposure requires authentication.** The API has been localhost-only by
design, and a tunnel must never terminate at an open port. T3 chooses between
Cloudflare Access and a shared-secret header using evidence, then proves an
authenticated external request succeeds and an unauthenticated one is refused
and logged.

## 3 · Field principles the build encodes (the research, distilled)

- **Context engineering over prompt accumulation:** curate what enters context;
  isolate concerns (fresh contexts for workers); leave durable artifacts instead
  of relying on conversation memory.
- **Orchestrator-worker is the reference multi-agent shape:** plan (JSON) →
  parallel workers with isolated contexts and scoped tools → synthesize → critic
  pass. Its value is context isolation as much as parallelism; its cost is real.
- **Trajectory-level evals for agents:** final-output-only evaluation passes
  20–40% more cases than step-level inspection reveals. P3 scores tool arguments
  and intermediate steps, not just briefs.
- **Observability doubles as audit:** every model call traced (inputs, outputs,
  tokens, cost, tool calls); traces retained as the action record for governance.
- **Cost levers in order of leverage:** task-based model routing (the ~100× price
  spread) → prompt caching (static prefixes first; watch hit rate) → escalation
  cascades (cheap → check → frontier retry) → batch for non-latency work.
- **Local models are the floor, not the ceiling:** the local alias owns tasks it
  has PASSED evals for (classification, extraction, embeddings-adjacent, bulk
  summarization); frontier owns synthesis, hard reasoning, agent loops. Re-run
  the golden set against new open-weight releases — the local-owned set grows.
- **Durability where failure costs money or trust:** resume, not restart. P3
  runs on hand-rolled asyncio + Postgres step-boundary checkpoints (SPEC-P3 §A,
  director-ratified 2026-07-16, superseding the LangGraph field default for
  this build; the spec carries named revisit conditions that put LangGraph
  back on the table on evidence); full durable execution (Temporal-class)
  only if side effects demand it. Idempotency for anything that touches
  the world.
- **Benchmarks are directional; internal evals decide.** Public leaderboards are
  gameable and harness-sensitive; no model/tool selection cites them alone.

## 4 · Roles and the working loop

- **Director** (chat session with repo visibility): writes phase specs with
  tasks pre-classified [interactive]/[headless]/[human], reviews at gates,
  resolves conflicts between docs, produces SPEC-P(n+1) when a gate passes.
- **Executor** (Claude Code): orients via CLAUDE.md → PROGRESS.md → current
  spec (and this file at phase start), executes tasks per their definition of
  done, verifies rather than assumes, reports findings-before-changes when
  reality contradicts instructions, updates PROGRESS.md and BUILD_JOURNAL.md.
- **Owner** (human): approves diffs + runtime evidence at every checkpoint,
  authors the golden set, holds all credentials, makes corpus and deployment
  decisions, and is the only party who can expand the dangerous-actions list.

Executor behavior standard (set by the P0 Langfuse session, hold to it):
verify claims with commands (`git check-ignore`, in-container checks) rather
than assuming; investigate-and-note rather than silently work around;
surface contradictions before acting on them.

## 5 · Known open items (do not lose these)

- `ops/langfuse/.env` retains upstream CHANGEME default secrets — acceptable
  localhost-only; MUST change before any non-local deployment.
- MinIO media-upload endpoint references an unmapped host port — affects only
  unused media-upload features; revisit if media features are ever wanted.
- Review-agent audit of Groundwork itself is scheduled for P5 (self-audit is
  a deliverable, not an afterthought).
