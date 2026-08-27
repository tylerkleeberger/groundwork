# Groundwork

A grounded question-answering system over a document corpus: hybrid retrieval,
cited answers, an honest not-found gate, durable multi-step research runs, and
a broker that stands between a language model and any system of record.

It is built to be *measured*. Every phase shipped its measuring instrument
before the thing being measured, and every number below was produced by an
evaluation suite — one of which you can run yourself in ten minutes.

> **This repository is a clean-room copy, and its commit history is authored.**
> The system was built over five phases and roughly 120 commits against a
> private knowledge base. That trail stays private, because the corpus is
> personal. What ships here is the code, the decision record, and a demo
> corpus of FastAPI documentation pinned to one commit — so the published
> numbers are reproducible by a stranger rather than merely claimed. The
> commits you see are phase-shaped and written for a reader;
> `PROVENANCE.json` names the exact source commit every file came from.

---

## The result worth leading with

**A narrow-domain corpus makes an honest "I don't know" *harder*, not easier.**

The not-found gate declines to answer when the best re-ranked chunk scores
below a threshold. That threshold is derived from each corpus's own score
distribution, and the *margin* — the gap between the worst question the system
should answer and the best question it should refuse — is what makes the gate
robust or fragile.

| Corpus | Worst answerable | Best guard | **Margin** |
|---|---|---|---|
| Personal KB (606 documents, many domains) | -1.27 | -2.07 | **0.8008** |
| FastAPI docs (155 documents, one project) | -0.2844 | -0.3858 | **0.1014** |

**The same pipeline has an eight-times narrower safety margin on the tidier
corpus.** The intuition says a small, clean, single-topic corpus is the easy
case. The measurement says the opposite, and the reason is visible once stated:
a single-project documentation set is *topically homogeneous*, so a question
about gRPC or Terraform — genuinely uncovered — still retrieves chunks about
serving and deploying software. The re-ranker's scores compress, and the
distance between "answerable" and "unanswerable" shrinks with them.

This is why thresholds in this system are never copied between corpora, and
why every evaluation run prints its margin: threshold decay announces itself
before it fails rather than after.

---

## Results

Two tables, because they are two different claims.

### Demo profile — reproducible by you

FastAPI documentation pinned at `95f8322`, 155 documents. Locked over three
runs; the band is the honest report, not the best run.

| | |
|---|---|
| Exam | 15 cases — 11 answerable, 4 guards |
| **Pass band** | **13/15 — 13/15 — 13/15** |
| Context precision / recall | 0.4545 / 0.9091 |
| Judged faithfulness / relevancy | 0.8587 / 0.9457 |
| Guards declined through the gate | **4/4**, zero generation tokens |
| Not-found threshold | **-0.3351**, derived on this corpus |
| **Measured cost** | **$0.0287 for the 15-case exam — $0.00191/question all-in**, $0.00261 per *answered* question |
| Judge calibration | mean abs. difference 0.0938, within-tolerance 93.75% against 8 frozen anchors |

### Personal profile — measured, corpus private, **not reproducible by you**

The system's real workload: 606 documents from the author's own knowledge base.
These numbers are stated for honesty about what the system does in daily use.
**You cannot verify them, and you should weigh them accordingly.**

| | |
|---|---|
| Exam | 31 cases — 26 answerable, 5 guards |
| Pass band | 29–30 / 31 across four locked runs |
| Context precision / recall | 0.6077 / 1.00 |
| Judged faithfulness / relevancy | 0.9408 / 0.9263 |
| Not-found threshold | -1.67, derived on this corpus |
| Cost | ~$0.006 per answer blended (cheap $0.005 / frontier $0.0144 / decline $0) |
| Research briefs | ~$0.095 per question (multi-step, 11–14× a single ask) |
| Whole project through the P2 gate | $6.99 across 2,293 traces |

The two exams are different sizes over different material and are **not
comparable to each other**. Neither is a benchmark score; both are regression
instruments.

---

## Honest limitations

Named, because a results table without them is marketing.

- **dg-002 (demo, failing).** A retrieval miss: the document that answers
  "which path operation wins when two could match" is never retrieved for that
  phrasing — `context_precision` 0.0. The system declines honestly rather than
  guessing, which is the correct behaviour on bad input, but the retrieval is
  what failed.
- **dg-010 (demo, failing).** A chunk-selection miss: the right document *is*
  cited, but the retrieved chunk is the page introduction rather than the
  relevant section, so the generator refuses to assert what it was not given.
- **Neither was fixed by weakening the case.** A number tuned against its own
  15-case test would be worth less than an honest 13/15.
- **gs-024 (personal, known limitation).** Answer *altitude* — the system
  answers a question about a methodology at the wrong level of abstraction.
  Routing to the frontier model fixed the citation half; the phrasing half is
  open and documented as a known limitation rather than quietly dropped.
- **Synthesizer citation discipline (research tier).** Multi-step briefs still
  occasionally assert a claim whose citation traces to a retrieved chunk that
  does not support it. Hardening reduced the rate substantially (quantified
  29 → 17 instances); it is **not zero**, and the trajectory evals catch it
  rather than the product preventing it.
- **The demo margin is 0.1014.** See the headline above. It is a real
  fragility on this corpus, not a rounding detail.
- **Single-user scale.** One corpus, one machine, one person. Nothing here has
  been load-tested, and the concurrency story is "there isn't one".

---

## The leak scanner ships without its seeds

`scripts/leak_scan.py` is the check that kept the private corpus out of this
repository. It ships here, and it is deliberately **less capable in public than
it is in private** — for a reason worth stating plainly:

* **Structural classes ship.** UUID, machine-path and hostname *shapes* are
  patterns. Reading them tells you nothing about what they match.
* **Content seeds do not ship.** Corpus strings, document titles, calibration
  payloads and personal project names are supplied at runtime from an
  untracked local file (`--seeds`, or `$GROUNDWORK_LEAK_SEEDS`). A detector
  that hardcodes the private strings it looks for would *publish those very
  strings to everyone who reads it* — the check would become the leak.

Because of that split, the scanner refuses to claim more than it checked. With
no content seeds it exits **2 — CANNOT VERIFY** rather than printing a clean
verdict. CI here runs it as `--structural-only`, which is a caller deliberately
asking for the reduced check; every line of that output says the verdict covers
shapes and not content. A clean structural scan is **not** a statement that no
personal string exists — it is a statement that nothing *shaped like* a UUID, a
machine path or a database hostname does.

The full-seed scan, and a one-time sweep over this repository's entire
constructed history, ran locally before publication, where the seeds live.

---

## Reproduce the demo numbers

```bash
python scripts/export_demo_corpus.py     # FastAPI docs at the pinned commit
docker compose up -d                     # Postgres + pgvector
scripts/gateway.sh &                     # model gateway (frontier/cheap/local/embed)
python ingest.py                         # embed + store (demo profile)
scripts/app.sh &                         # the API on :8310
pytest evals/                            # the exam
```

`config/corpus.json` selects the profile. It ships set to `demo`, the only
corpus in this repository. A profile selects corpus directory, database schema,
evaluation set **and** retrieval thresholds together — because a demo run
scored against personal ground truth is exactly the mistake worth engineering
against.

---

## Layout

| | |
|---|---|
| `app/` | API, retrieval, grounding, research runs, the action broker |
| `evals/` | the exam, the scorers, the judge and its rubrics |
| `corpus_demo/` | FastAPI documentation at a pinned commit (MIT — see its `ATTRIBUTION.md`) |
| `docs/DIRECTION.md` | the decision record: every rule here, and why |
| `docs/LEARNING.md`, `docs/DEFENSE.md` | what the build taught, and the security posture |
| `HIGHLIGHTS.md` | the incident chronology — what broke, and what each break established |
| `specs/` | the six phase specifications, as written *before* each phase |
| `scripts/leak_scan.py` | the check described above |

`docs/DIRECTION.md` is the honest centre of this repository: the record of what
was decided, what was tried, and what turned out to be wrong.
`HIGHLIGHTS.md` is the one to read if you only read one.
