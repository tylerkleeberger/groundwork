# Groundwork

A grounded question-answering system over a document corpus: hybrid retrieval,
cited answers, an honest not-found gate, durable multi-step research runs, and
a broker that stands between a language model and any system of record.

It is built to be *measured*. Every phase shipped its measuring instrument
before the thing being measured, and the numbers below come from an evaluation
suite you can run yourself.

> **This repository is a clean-room copy, and its commit history is authored.**
> The system was built against a private knowledge base over five phases and
> roughly 120 commits. That trail stays private, because the corpus is
> personal. What ships here is the code, the decision record, and a demo
> corpus of FastAPI documentation pinned to one commit — so the published
> numbers are reproducible by a stranger rather than merely claimed. The
> commits you see are phase-shaped and written for a reader; `PROVENANCE.json`
> names the exact source commit every file came from.

## The demo numbers

Measured on the demo profile (FastAPI docs at a pinned commit), locked over
three runs:

| | |
|---|---|
| Exam | 15 cases — 11 answerable, 4 guards |
| Pass band | **13/15 — 13/15 — 13/15** |
| Context precision / recall | 0.4545 / 0.9091 |
| Judged faithfulness / relevancy | 0.8587 / 0.9457 |
| Guards declined through the gate | **4/4**, zero generation tokens |

The two standing failures are named, not hidden: one case fails on retrieval
(the required document is never retrieved for that phrasing) and one fails on
chunk selection (the right document is cited, but the retrieved chunk is the
introduction rather than the relevant section). Neither was fixed by weakening
the case. A number tuned against its own test is the failure this project
exists to avoid.

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
verdict. Public CI runs it as `--structural-only`, which is a caller
deliberately asking for the reduced check; every line of that output says the
verdict covers shapes and not content. A clean structural scan here is not a
statement that no personal string exists — it is a statement that nothing
*shaped like* a UUID, a machine path or a database hostname does.

The full-seed scan, and the one-time pre-publish sweep over this repository's
entire constructed history, ran locally before publication, where the seeds
live.

## Reproduce the numbers

```bash
python scripts/export_demo_corpus.py     # FastAPI docs at the pinned commit
docker compose up -d                     # Postgres + pgvector
scripts/gateway.sh &                     # model gateway
python ingest.py                         # embed + store (demo profile)
scripts/app.sh &                         # the API
pytest evals/                            # the exam
```

`config/corpus.json` selects the profile. It ships set to `demo`, which is the
only profile whose corpus is in this repository.

## Layout

| | |
|---|---|
| `app/` | API, retrieval, grounding, research runs, the action broker |
| `evals/` | the exam, the scorers, the judge and its rubrics |
| `corpus_demo/` | FastAPI documentation at a pinned commit (MIT — see its `ATTRIBUTION.md`) |
| `docs/DIRECTION.md` | the decision record: every rule here, and why |
| `specs/` | the six phase specifications, as written before each phase |
| `scripts/leak_scan.py` | the check described above |

`docs/DIRECTION.md` is the honest centre of this repository. It is the record
of what was decided, what was tried, and what turned out to be wrong.
