# SPEC-P6 — The Engineering Map lane [DRAFT for ratification]

Theme: groundwork stops being a system Tyler built and becomes the system Tyler
uses. It binds to command-center-os (CC-OS) as the Engineering Map (EM) space's
engine, reachable from phone, Slack, Cowork/Code sessions, and the operator
surface, at any time of day.

## Decisions (ratified in the founding round, recorded as D18-D22)

- D18 DURABLE REQUESTS. An invocation is a row on the CC-OS Message bus, not
  only a live HTTP call. Answers return to the asking surface
  retry-until-delivered (CheckIn machinery). The pattern that survived kill -9,
  a billing outage, and dormancy, applied to requests.
- D19 REACHABILITY OVER RELOCATION. The serving tier stays local (embeddings,
  vectors, thresholds, exam evidence all untouched); a tunnel (Cloudflare
  Tunnel or Tailscale) makes it reachable so phone-time answers arrive in
  seconds. The durable queue is the FALLBACK when the laptop is unreachable —
  no request is ever lost. Relocation (hosted embeddings/vectors) is a P7
  candidate whose trigger is LEDGER EVIDENCE: queued requests the owner was
  actively waiting on — AND/OR sustained local-stack burden on the owner's
  machine (two incidents already on record).
- D20 SYNC SPLIT BY DIRECTION. Inbound (EM -> corpus) pre-authorized on a
  schedule, one audit row per run; blast radius is groundwork's own rebuildable
  store. Outbound (em_draft_kb -> EM inbox) stays gated per act. Revisit:
  inbound returns to gated if it gains any delete path beyond the existing
  prune or writes outside groundwork. Rationale: an approval firing hourly for
  a benign act trains the approver to stop reading — cries-wolf applied to the
  gate itself.
- D21 MULTI-CORPUS SERVING (other CC-OS spaces via D7 profiles) is P7.
- D22 EXPOSURE REQUIRES AUTH. The API has been localhost-only by design; the
  tunnel never terminates at an open port. Cloudflare Access or shared-secret
  header, decided at T3 with evidence.

## Architecture

- Repos stay separate (P5 ruling). CC-OS binds groundwork as the EM space's
  engine — CC-OS "integration" type, thin router over an external engine.
  Transport: groundwork's existing MCP servers via dispatch(), so gating stays
  uniform.
- Gate authority: groundwork's approval-row remains authoritative;
  #cc-checkins is the DELIVERY SURFACE for approvals, never a second gate. Two
  gates on one write is a race.
- State/answering split: EM state (sync status, ledger summary, inbox) lives in
  Neon, always-on for the operator surface; answering is local and queues
  visibly when unreachable.

## Tasks (eval-first order)

T1 [DONE pending merge] Usage ledger — floors defined, thresholds deliberately
unset, pinned by test.

T2 [interactive] Ledger persistence + wiring: every ask/related/research
invocation writes a row; summarize() published to a local endpoint. Done: real
invocations produce rows; leak scan clean.

T3 [interactive + human] Reachability: tunnel + auth (D22). Owner holds the
tunnel account. Done: an authenticated request from outside the LAN answers; an
unauthenticated one is refused and logged; both transcripts captured.

T4 [interactive] Durable requests: bus request/response rows, a local drain
loop, answers delivered retry-until-delivered. PRECONDITION: verify the CC-OS
Railway orchestrator is live; if dormant, standing it up is T4a (CC-OS-side,
owner-assisted). Done: a request posted while groundwork is DOWN is answered
after it comes up, with queue_wait_ms in the ledger row.

T5 [interactive + human] Slack + session surfaces: operate(engineering-map)
verbs routed to ask/related/research; a phone-originated Slack ask answered live
via T3. Research briefs land in groundwork_inbox as today; approval delivery
via #cc-checkins.

T6 [interactive] Scheduled inbound sync (D20): launchd StartInterval, hourly
while awake; every run posts an audit row to the bus and updates EM STATE (last
sync, files, chunks, clean/failed). Staleness becomes a surfaced fact — CC-OS's
"gone dark" flagship fed by a real signal. A run that cannot reach the bus logs
CANNOT DELIVER loudly, never silently skips.

T7 [human + interactive] Usage window + gate. Two weeks of real use. Thresholds
DERIVED from the window's distribution, then floors locked. Gate: floors
reported (served_without_queue_rate, p95, abandonment), D19's bet scored against
evidence, p6-gate tag, DIRECTOR_HISTORY entry.

## Gate criteria

1. A question asked from the phone, answered in seconds, ledger row present —
   demonstrated live.
2. A request made while the laptop was closed, answered on wake, delivered to
   the asking surface — demonstrated live.
3. Inbound sync running scheduled with audit rows; outbound writes still gated
   (a probe proves the gate).
4. Ledger floors reported over a real window with derived thresholds; no number
   authored by hand.
5. Ask exam re-lock in band (29-30/31) — the daily-use lane must not have moved
   the product's floor.

## Deferred with rulings

P7 candidates: relocation (D19 trigger), multi-corpus (D21), operator-surface
EM page build (CC-OS work; P6 ships the data contract only). Carried: gs-009
adjudication, margin watch (trigger 0.5), synthesizer residual, walkthrough
recording + portfolio paste (P5 post-gate).
