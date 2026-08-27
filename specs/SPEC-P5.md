# SPEC-P5 — The public flip  **[RATIFIED]**

**Status: RATIFIED — review round complete (2026-08-03), all sections
ruled: clean-room public repo RATIFIED (constructed-safe over
hoped-recovered); §F scanner ratified with the seed set and CI rules
below; demo corpus, profile switch, enforced protection, demo script and
README ratified as specced; authored-history mitigation ADDED (public
README states the curation plainly; HIGHLIGHTS.md carries the private
trail's summary statistics — dates, PR/incident counts, no content);
engineering-knowledge-lab ruled COEXIST-THEN-SUPERSEDE (deferred
closeout item, no action in any task). Task order per spec, eval-first:
THE LEAK SCANNER EXISTS AND IS RED-GREEN TESTED BEFORE ANY PUBLIC
ARTIFACT IS CONSTRUCTED.**

**Theme:** the private system becomes the public portfolio piece —
without leaking one byte of the owner's personal KB.

**Mode legend:** as SPEC-P1.

**Both pre-round flags RESOLVED (2026-08-03):**
1. The truncated gate clause was completed by §F's scanner and RATIFIED
   with an explicit seed set (below) — nothing was assumed silently.
2. P4 closure verified: PR 34 merged at `07efd71`, `p4-gate` cut and
   pushed at that commit. P5 execution is unblocked.

---

## §A · Sanitization audit — the load-bearing task (spec'd first)

### The inventory (measured, not estimated — 2026-08-02, tracked files)

| Class | Where | Volume | What leaks |
|---|---|---|---|
| **Verbatim source quotes** | `evals/golden_set.review.md`, `evals/research_set.review.md` | 287 + 227 lines | Sentences copied verbatim out of the owner's KB documents, with source ids and hit counts — the audit trails' whole purpose |
| **Full answers + retrieved chunks** | `evals/judges/calibration_sheet.md`, `calibration.json` | 675 + 419 lines | Complete generated answers over personal documents AND the chunk payloads that grounded them — the densest leak in the repo |
| **Exam questions** | `evals/golden_set.jsonl` (31), `evals/research_set.jsonl` (6) | 37 cases | The questions themselves describe the owner's private study material; `answer_must_contain` strings are verbatim source fragments |
| **Committed results files** | `evals/results/research-*.json` (5 committed) | — | Briefs, worker answers, chunk texts, source ids |
| **Journal forensics** | `BUILD_JOURNAL.md` | 1,985 lines | Document titles, content summaries, corpus statistics, EM table names, personal project names (3 refs) |
| **Source ids** | 12+ tracked files | — | UUIDs that are meaningless publicly but are stable join keys into a private KB |

**Measured negatives (checked, not assumed):** zero `/Users/…` machine
paths and zero Neon hostnames in tracked docs — the incident forensics
were written carefully. That is the one class that does NOT need work.

### Disposition per class

- **Scrub-in-place is impossible for the review sheets and calibration
  payloads.** Their content IS the leak; a scrubbed `calibration_sheet.md`
  is an empty file. Disposition: **stay private**, replaced in public by
  a *description* of the artifact (what it is, what it proves, how it
  was produced) plus a synthetic example built on the demo corpus.
- **Exam sets: regenerate, don't scrub.** The public repo carries a
  DEMO golden set over FastAPI docs (§B) — same schema, same harness,
  publicly verifiable numbers. The personal sets stay private.
- **Journal: curate, don't sanitize line-by-line.** 1,985 lines of
  incident forensics is exactly the Track-B evidence worth publishing,
  and also exactly where titles and summaries hide. Disposition:
  **`HIGHLIGHTS.md`** — an authored selection of the ~25 incidents that
  carry the lessons, rewritten to reference the demo corpus or no corpus
  at all. The full journal stays private.
- **LEARNING.md / DEFENSE.md / README results: reuse as-is** (per the
  outline's item 6) after one leak scan — they were written
  evidence-sourced and corpus-agnostic, and re-auditing them is cheaper
  than rewriting.

### The history question — argued both ways, one recommendation

*The case for flipping this repo (scrub + rewrite history):* one repo,
one URL, the full 110-commit build narrative visible, and the
commit-by-commit story IS part of the demonstration.

*The case against, decisive:* **git history carries everything ever
committed.** The leaking files were committed across the whole build
(golden_set.review.md at T4, calibration payloads at T6, research
sheets at P3-T2), so a public flip of this repo requires rewriting
history across 110 commits — a `filter-repo` pass whose success
condition is "no personal string survives in any blob of any commit,"
verified how? Any miss is permanent and public. Worse, history rewriting
is on the dangerous-actions list, and a botched rewrite of the ONLY
copy of the build record is an unrecoverable loss of the portfolio's
own evidence.

**RATIFIED (2026-08-03): a clean-room public repo (`groundwork-public`)
with curated history.** The director's ruling, recorded in the ratifying
words: **constructed-safe over hoped-recovered.** The private repo stays the source of truth and the
evidence trail. The public repo is built by copying the ratified public
surface into a fresh repository with an authored commit sequence
(phase-shaped: P0 foundations → P1 ask → … → P4 act), each commit
message written for a reader. This makes "zero personal strings" a
property that is *constructed* rather than *recovered*, and it keeps
the private evidence intact.

Cost, stated honestly: the public repo loses genuine commit-by-commit
history (it will look authored, because it is), and two repos must be
kept in sync as the system evolves. Mitigations: HIGHLIGHTS.md carries
the real chronology with dates and PR numbers, and the sync burden is
bounded by making the public repo a *release target*, not a
double-maintained fork.

## §B · Demo corpus (D7, ratified long ago)

- **Source: FastAPI documentation** (public, MIT-licensed, technically
  substantial, and the framework this system is built on — a reviewer
  can check the answers).
- **Export pipeline:** `scripts/export_demo_corpus.py` — clone/fetch the
  docs at a PINNED commit (a moving corpus makes published numbers
  irreproducible), convert to the same front-matter shape
  (`source_id`/`title`/`source_table`) the existing pipeline expects, so
  ingestion, retrieval, and evals are untouched.
- **Profile switching, one line (`config/corpus.json`):**
  `{"profile": "personal" | "demo"}` selecting corpus dir + DB schema +
  eval set. The seam already exists (D7's promise); P5 cashes it.
- **Demo golden set: 12–15 cases** over FastAPI docs, same schema,
  ≥3 guards. Authored by the executor and director-ratified — this set
  is NOT owner ground truth about private material, so the T4 fenced
  protocol does not apply (stated for ratification). Owner-optional per
  the outline.
- **Acceptance:** the published README numbers are reproducible by a
  stranger running `pytest evals/` against the demo profile.

## §C · Public repo shape

**Ships:** all product code (`app/`, `scripts/`, `ingest.py`, `tests/`,
`config/`), `specs/SPEC-P0…P5`, `docs/DIRECTION.md` (decision record —
the D1–D17 rationale is the portfolio's spine), `docs/BLUEPRINT.md`,
`LEARNING.md`, `DEFENSE.md`, `HIGHLIGHTS.md`, the demo corpus exporter +
demo eval set, README (rewritten, §D), CI workflow, `hooks/`.

**Stays private:** `corpus/`, all review sheets, calibration payloads,
personal golden/research sets, committed personal results files, the
full BUILD_JOURNAL, `ops/em_writer_setup.md` (EM schema details),
`.env*`, the action log's contents.

**Branch protection ENFORCED (D14's clause finally cashing):** the
private repo is on a free plan where protection on a private repo is
limited; a PUBLIC repo gets full branch protection free. P5 turns the
owner-gate from convention into enforcement: protected `main`, required
CI status check, no direct pushes, PR-only. The rule that has governed
this build by discipline becomes a server-side fact.

## §D · Demo script + README

**The 10-minute walkthrough** (recorded once, linked from README):
1. **Ask** an in-corpus question → cited answer; click a citation. (~1 min)
2. **Decline** — an out-of-corpus question → honest not-found, zero
   generation tokens; show the gate score and the margin. (~1 min)
3. **Flag** a bad answer from the CLI → the candidate file it produces →
   the adjudication chain that turns it into an exam case. (~1 min)
4. **Research brief** — commission one, show the parallel workers in the
   trace tree, kill the process mid-run, resume: it continues, it does
   not restart. (~3 min)
5. **Gated write** — request `em_draft_kb`, show the approval payload
   (including the D12-quoted provenance), approve, show the row landing
   and the action log entry. Then the red-team fixture: the injection
   is refused and logged, the queue stays empty. (~3 min)
6. **The eval story** — change a prompt, run the exam, show the per-case
   delta, revert. Close on the cost dashboard. (~1 min)

**README rewrite** for a public audience: what it is in three sentences
→ the measured results table (reuse, per item 6) → architecture diagram
→ "reproduce these numbers in 10 minutes" quickstart on the demo profile
→ the honest-limitations section (gs-024, the synthesizer discipline
residual, single-user scale) → links to LEARNING/DEFENSE/HIGHLIGHTS.

## §E · Relationship to `engineering-knowledge-lab` — RULED: COEXIST-THEN-SUPERSEDE

**Owner ruling (2026-08-03):** the lab **stays untouched** as a public
artifact for now; retirement happens **only after** the new public repo
is live and strictly better. Recorded as a **deferred P5-closeout
item** — NO ACTION in any P5 task until that condition is met and the
owner rules again. (Options considered and set aside: immediate
supersede, permanent coexistence, lab-feeds-flagship cross-linking.)

## §F · Phase-gate criteria (including the truncated clause, completed
for ratification)

1. **Zero personal-KB strings in the public artifact — verified by
   `scripts/leak_scan.py`. RATIFIED seed set and rules (2026-08-03):**
   seeds = **all distinct ≥8-word corpus strings** + **EM document
   titles** + **calibration payloads**; plus the structural classes
   (`source_id` UUIDs, `/Users/…` paths, Neon hostnames, personal
   project names). **Public CI goes RED on any hit** — a leak
   introduced later is the same leak. **Plus a one-time pre-publish
   sweep over the CONSTRUCTED history** (every commit of the new repo
   before it goes public). The private corpus never enters the public
   repo: seeds are generated locally and the scan runs against the
   public artifact.
2. Demo numbers reproducible by a stranger (`pytest evals/` on the demo
   profile matches the published README table).
3. Branch protection active and proven (a direct push to public `main`
   is rejected).
4. The demo walkthrough recorded and linked.
5. The private repo remains intact and authoritative; nothing in it is
   deleted for the flip.

---

## Tasks

### P5-T1 `[interactive]` Sanitization audit + leak scanner
The §A inventory re-run mechanically, `scripts/leak_scan.py` built and
pinned offline, disposition table ratified.
Done: scanner catches a planted canary in both tree and history; the
disposition table has a ruling per class.

### P5-T2 `[interactive]` Demo corpus + profile switch
Exporter at a pinned commit, `config/corpus.json` profile, ingestion
proven identical on the demo profile.
Done: demo corpus ingests; `/ask` answers a FastAPI question with a
citation.

### P5-T3 `[interactive + human]` Demo golden set
12–15 cases, ≥3 guards, executor-authored + director-ratified; baseline
locked on the demo profile.
Done: demo exam runs green-or-explained; numbers recorded.

### P5-T4 `[interactive + human]` The clean-room public repo
Fresh repo, curated phase-shaped commits, public surface only, leak scan
green in CI, branch protection enforced (owner creates the repo — repo
creation is owner-only per the dangerous-actions list).
Done: public repo exists, CI green, protection proven, scan clean.

### P5-T5 `[interactive]` README + HIGHLIGHTS + demo script
Public README, HIGHLIGHTS.md curated from the journal, the walkthrough
script written (recording is the owner's).
Done: a stranger can follow the quickstart; HIGHLIGHTS carries the
chronology without personal content.

### P5-T6 `[human + interactive]` Flip + phase gate
Visibility flip per the P0 standing condition, gate criteria verified,
`p5-gate` tag, the self-audit (BLUEPRINT P5's review-agent deliverable)
scheduled or deferred with a ruling.

---

**Review round: COMPLETE (2026-08-03).** All six requests ruled —
clean-room ratified, disposition table ratified, demo-set split and size
confirmed, §E ruled coexist-then-supersede (deferred), scanner ratified
with the ≥8-word seed rule, task modes confirmed. Execution proceeds in
task order with the scanner first (eval-first).
