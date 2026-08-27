# SPEC-P4 — Act: the control plane  **[DRAFT]**

**Status: DRAFT — director-commissioned design (outline ruling,
2026-07-18). One review round before ratification. NOT EXECUTABLE: no
product code until ratified. This document is the deliverable — design
only, specs/ constraint honored.**

**Theme (the director's, verbatim in spirit):** the manual governance
this project has practiced — human gates, findings-before-changes,
append-only journals — becomes running software. The system gains the
ability to DO things, starting with writing back to the owner's world,
through an action broker that mechanizes the human-gate pattern the
build itself has been demonstrating since P0.

**Mode legend:** as SPEC-P1.

**Cross-doc flag (D11):** BLUEPRINT §P4 names email-drafter (mock SMTP)
and ticket-filer (GitHub Issues) as the first tools. This spec follows
the director outline instead: EM-aligned tools (em_draft_kb,
groundwork_sync, related_check) — the P3 strategic-direction seam
cashing in, and a first write the owner actually wants. Ratifying this
spec amends BLUEPRINT §P4's tool list; the blueprint's three acceptance
properties (no-bypass proven by test, injection red-team blocked and
logged, approval survives restart) are KEPT unchanged.

---

## §A · Architecture

```
            caller (CLI / research pipeline / future UI)
                          │
                          ▼
      ┌─────────────── ACTION BROKER (deterministic code, no model) ──┐
      │ 1. PERMISSION CHECK — config/actions.json:                    │
      │    per-tool allow/deny + class: read | write                  │
      │    unknown tool → deny, logged                                │
      │ 2. APPROVAL GATE — v1: EVERY write requires a human approval; │
      │    there is NO auto-approve tier (earned later, like          │
      │    everything). reads: auto-allowed, still logged.            │
      │ 3. EXECUTE — the broker is the ONLY holder of MCP client      │
      │    sessions and the only module with tool credentials         │
      │ 4. LOG — append-only action record: full request + response   │
      │    + provenance, one Langfuse trace per action (audit doubles │
      │    as observability, DIRECTION §3)                            │
      └───────────────┬──────────────────────────────────────────────┘
                      │ MCP (the protocol is the point — Q02)
      ┌───────────────┼───────────────────┐
      ▼               ▼                   ▼
  related_check   groundwork_sync     em_draft_kb
  (read class)    (write, local)      (write, external — Neon EM)
```

**Broker mechanics (deterministic, D1-shaped):**
- `config/actions.json` declares every tool: name, class (`read`|`write`),
  allow/deny, arg schema. Not listed = denied. Policy is CODE-FREE
  config; the decision function is a pure function over (tool, args,
  config) — offline-testable to the last branch (D16).
- **Approval store = the P3 pattern reused:** `action_requests` table in
  the app Postgres (id, tool, args jsonb, class, provenance jsonb,
  status `pending|approved|denied|executed|failed`, requested_at,
  decided_at, result jsonb, trace_id). A pending approval is a ROW —
  which is how "approval survives an app restart" (BLUEPRINT acceptance)
  is a SELECT, not machinery. Status transitions are the only writes;
  executed rows are never mutated — the table is the append-only log.
  Autocommit store, constructor-guarded (the savepoint lesson applied
  at birth).
- **No-bypass, structurally then proven:** tool internals live in
  `app/tools/`; the ONLY importer of `app/tools/` and the only holder
  of MCP sessions/credentials is the broker module. The blueprint's
  no-bypass test greps the import graph and fails on any second
  importer, plus a runtime test that tool credentials are absent from
  every other process env.
- **Kill switch (BLUEPRINT):** one config flag — `actions_enabled:
  false` denies everything including reads; checked before permission.

**Why tools are MCP servers even in a single-process v1:** the protocol
is the deliverable (Q02). Each tool is a small stdio MCP server started
and owned by the broker; the broker is the MCP client. This buys the
demonstrable seam (a tool is swappable/inspectable via a standard
protocol, `tools/list` is the live inventory) at the cost of process
plumbing — accepted deliberately as the ONE place P4 spends complexity,
because it is the thing P4 exists to demonstrate. Everything else
(broker, store, approval) stays plain code.

## §B · First tools (smallest real set)

1. **`related_check` (read class — the read-tier exemplar).** Wraps the
   existing POST /related pipeline function. Auto-allowed, fully
   logged. Exists so the log shows both classes and so the broker's
   read path is proven on a zero-risk tool first.
2. **`groundwork_sync` (write class, local).** Triggers
   `scripts/sync.py` (exists since P1-T9, idempotent, pin-guarded).
   Lowest-risk write imaginable — its blast radius is this app's own
   DB, protected by its own refuse-to-mix pin — but STILL approval-gated
   in v1: the gate pattern is uniform or it is nothing.
3. **`em_draft_kb` (write class, external — the seam cashing in).**
   Drafts a new KB entry into the owner's EM as a clearly-marked DRAFT
   row. Input contract: title, body_markdown, provenance (research
   run_id + citations — the P3 brief is the natural payload), and an
   immutable `origin: groundwork` marker. The EM's editorial authority
   is untouched: a draft row is an INBOX ITEM, never a published entry
   (strategic direction 1, journaled 2026-07-17).

## §C · Credentials — the first WRITE credential to the EM

The bar is the `corpus_reader` precedent (P1-T1: role scoped to SELECT
on exactly 7 tables, owner-rotated exposure, shape-checked without
printing). Three options, one recommended:

- **Option A — INSERT-only on the real KB table(s), status column
  DRAFT.** Least moving parts, but couples Groundwork to the EM's live
  schema and puts machine-written rows inside the owner's working
  tables; a bug pollutes the editorial surface directly. The EM's own
  constraints/triggers become part of our failure surface. NOT
  recommended.
- **Option B — dedicated STAGING table (RECOMMENDED):** a new
  `groundwork_inbox` table in the EM database, owned by a new
  `groundwork_writer` role with INSERT-only on exactly that table
  (no UPDATE, no DELETE, no SELECT on anything else — SELECT on the
  inbox itself for idempotency checks only, decided at review).
  The owner's EM process promotes inbox rows into real KB tables —
  the promotion step IS the editorial gate, human by construction.
  Credential: `APP_EM_WRITER_URL` (D13 prefix, double-quoted, .env
  only, shape-checked never printed), provisioned by the OWNER
  `[human]` exactly like corpus_reader. Blast radius of a total
  compromise: spurious inbox rows, deletable by the owner, touching
  nothing the EM has published.
- **Option C — no DB write at all:** emit draft files the owner
  imports. Zero new credential, but the loop is manual enough that P4
  demonstrates nothing the repo doesn't already do — rejected as
  not-the-capability.

## §D · Eval-first, again

The harness precedes the first real write, in this order:

1. **Action golden set (offline, D16 unmarked, BEFORE the broker
   executes anything):** N ≈ 10–14 owner-certified cases over the pure
   policy function — allow-read, deny-unknown-tool, write-requires-
   approval, kill-switch-denies-all, oversized/malformed args denied,
   injection-marked provenance surfaces in the approval payload,
   double-approval idempotency, deny persists. Cases live in
   `evals/action_set.jsonl`, drafted the fenced way ONLY if they touch
   owner data; policy cases are executor-draftable + director-ratified
   (they encode the ruling above, not owner ground truth) — split
   stated for the review round.
2. **Dry-run contract (the broker's testing seam):** `dry_run: true`
   executes EVERYTHING except the final tool call — permission check,
   approval flow (against a test approver), payload assembly — and
   returns the would-be MCP request verbatim. The first em_draft_kb
   "write" in every environment is a dry run whose payload the owner
   reads. Dry-run results are logged with class `dry_run` so the log
   distinguishes rehearsal from action.
3. **The D12 story for tool-call inputs:** everything reaching a tool
   arg from retrieved/generated content is DATA with provenance. The
   red-team case (BLUEPRINT, kept): a corpus document containing
   instruction-shaped text ("call em_draft_kb with…") must produce NO
   action — v1's structural defense is that nothing writes without a
   human reading the approval payload, and the payload always shows
   provenance (which chunks/brief produced these args). The test
   seeds such a document, runs the research pipeline over it, and
   proves the broker's action queue stays empty + the attempt shape is
   visible in the log. Approval prompts render args as quoted data,
   never as text the approver's terminal interprets.

## §E · The UI question — FLAGGED FOR THE DIRECTOR, not decided

The D1 answer is a **CLI approval prompt on the owner's terminal**
(`ask`-CLI precedent: approve/deny pending actions where the owner
already works; zero new surface, zero new auth). Alternatives, costs in
one paragraph: a web approval queue (BLUEPRINT's "simple queue page")
adds a served page + its auth story to a localhost-only system — real
cost, real credential surface, better UX only if approvals become
frequent; macOS notifications add push plumbing for the same decision a
terminal shows; Slack/email approval adds an EXTERNAL round-trip and a
new credential class to the very phase whose theme is least-privilege —
the most capability for the most surface. Recommendation stated for the
round: CLI in v1, revisit condition = approval latency observed to
block real use (measured, not imagined).

## §F · D10 — stated honestly

No P4 task wants parallel dispatch. Broker core, credential work, MCP
plumbing, and the approval flow are architectural or
credential-sensitive — `[interactive]` by D10's own rule. The action
golden set fixtures and offline policy tests are headless-ELIGIBLE
(T5-class) but the graduation criterion (first zero-salvage post-flight
pass) keeps waiting for an organic opportunity — P4's critical path
does not manufacture one.

---

## Tasks

### P4-T1 `[interactive]` Broker core, eval-first
Pure policy function + `config/actions.json` schema + action_requests
store (autocommit-guarded) + kill switch + action golden set offline.
Done: policy decisions 100% offline-covered; approval row survives a
process restart (test); zero tools exist yet — by design.

### P4-T2 `[interactive]` MCP plumbing + the read exemplar
Broker as MCP client; `related_check` as the first stdio MCP server;
no-bypass import-graph test; log + trace per action.
Done: a read action flows caller→broker→MCP→log with a trace; bypass
test red-teams the import graph.

### P4-T3 `[human + interactive]` The EM write credential + dry-run
Owner provisions per the ratified §C option (default: Option B staging
table + INSERT-only role). em_draft_kb server built; dry-run contract
demonstrated — the owner reads a would-be payload before any real
write exists.
Done: dry-run payload reviewed; credential shape-checked, never
printed; zero real writes yet.

### P4-T4 `[interactive + human]` Approval flow v1 + the first real write
CLI approval per §E (pending the director's ruling); the first
approved em_draft_kb write lands a DRAFT row the owner promotes (or
deletes) in the EM.
Done: approve→execute→log→owner-promotes demonstrated end-to-end;
deny path demonstrated; approval survived a restart live.

### P4-T5 `[interactive]` groundwork_sync tool + the red team
Second write tool; the D12 injection case seeded and proven blocked;
BLUEPRINT acceptance sweep (no-bypass, injection, restart).
Done: all three blueprint properties green with runtime evidence.

### P4-T6 `[interactive + human]` Phase materials
LEARNING/DEFENSE P4 rows, cost story (broker adds ~$0 — it is code),
p4-gate draft.

---

**Phase gate (BLUEPRINT §P4 kept + outline):** no code path reaches a
tool around the broker (test proves it); the injection red-team case is
blocked and logged; an approval survives an app restart; every write in
the log carries full request/response + provenance; the first real
owner-approved EM draft exists and was promoted or deleted BY THE OWNER.

**Review round requests:** ratify §A broker shape; ratify §B tool set
(and the D11 blueprint amendment); choose §C credential option (B
recommended) and the inbox-SELECT question; ratify §D's action-set
authorship split; rule §E (CLI recommended); confirm §F task modes.
