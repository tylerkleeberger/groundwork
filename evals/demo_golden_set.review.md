# Demo golden set verification review — P5-T3

**Set:** `evals/demo_golden_set.jsonl` — **15 cases = 11 answerable + 4 guards**.
**Corpus:** `corpus_demo/`, FastAPI docs pinned at
`95f8322ee1dcda7ceace7b1c4f6c9915b36d748f` (release `0.141.1`, 155 documents).
**Authorship:** executor-authored and director-ratified. The T4 fenced protocol
does **not** apply — this set is not owner ground truth about private material,
it is a public exam over public documents. **That is exactly why this sheet
matters: a stranger can check every claim in it.**

**Method (same rigor as the personal set):** every `answer_must_contain` string
was grep-verified **case-sensitively verbatim** in its cited source document,
and counted corpus-wide for distinctiveness (file-hit counts below; 1 = the
source document alone). Guards were verified absent by direct term search **and
by an adjacency sweep of synonyms**, because a guard the corpus quietly covers
is not a guard.

## A property of this corpus that shaped the set

FastAPI's documentation embeds its code samples as mkdocs-macro references
(`{* … *}`) pointing at example files. The exporter strips them, so **the
ingested documents carry prose only, no code**. One drafted string
(`status_code`, dg-006) failed verification for exactly this reason — it lives
only inside code samples — and was replaced with a prose string. Any future
case over this corpus must choose strings from prose.

## Changes from the draft (attention here first)

| Case | Change | Why |
|---|---|---|
| dg-006 | `status_code` → `raise` | **Not verbatim in the source.** `status_code` appears only in the stripped code samples; `raise` is prose ("you don't `return` it, you `raise` it") and is what a correct answer says. |
| dg-011 | `pydantic-settings` → `environment variables` (kept `BaseSettings`) | **Live-probe evidence, the gs-001 precedent:** a correct, correctly-cited answer failed the drafted string. The run cited `advanced/settings.md` and explained `BaseSettings` properly, but never named the *package* — that name lives in an install section the retriever did not surface. Amending a string that a right answer cannot satisfy is the ratified move; the replacement is verbatim in the source and present in the observed answer. |

## Guards — verified unanswerable, and re-swept

The decay lesson applies even to a pinned corpus: a guard is only a guard if
the corpus does not quietly cover it by another name. Every guard was swept for
synonyms and adjacent phrasings, all negative.

| Case | Topic | Direct hits | Adjacency sweep (all zero unless noted) |
|---|---|---|---|
| dg-012 | gRPC | **0 files** | `protobuf` 0 · `protocol buffer` 0 · `service mesh` 0 |
| dg-013 | Terraform | **0 files** | `infrastructure as code` 0 · `provisioning` 0 · `Pulumi` 0 · `cloud formation` 0 |
| dg-014 | Elasticsearch | **0 files** | `full-text` 0 · `full text search` 0 · `search engine` 1 (release notes only) |
| dg-015 | circuit breaker | **0 files** | adjacent to `deployment/concepts.md`, which covers restarts and replication but names no resilience pattern |

Each guard is deliberately **adjacent** to territory the corpus does cover
(API serving, deployment, SQL databases, operational concerns) rather than
absurdly off-topic — a guard that is trivially far away tests nothing.

## Per-case audit trail

Format: verdict; the cited source; each shipped string with corpus-wide file
hits and the verbatim source line it traces to.

### dg-001 — YES
**Q:** How do I let a browser frontend running on a different origin call my FastAPI backend?
**must_cite_sources:** `1f84166e…` → `tutorial/cors.md`
- `CORSMiddleware` — verbatim ✓ · corpus file hits **3**
  > ## Use `CORSMiddleware` { #use-corsmiddleware }
- `allowed origins` — verbatim ✓ · corpus file hits **1**
  > To achieve this, the `:80`-backend must have a list of "allowed origins".

### dg-002 — YES
**Q:** If two path operations could match the same URL, which one does FastAPI use?
**must_cite_sources:** `ed4c003a…` → `tutorial/path-params.md`
- `the path matches first` — verbatim ✓ · corpus file hits **1**
  > The first one will always be used since the path matches first.

### dg-003 — YES
**Q:** How do I schedule work to run after the response has been sent?
**may_cite_any:** `19156c06…` → `tutorial/background-tasks.md`, `6045b4e1…` → `reference/background.md`
- `BackgroundTasks` — verbatim ✓ · corpus file hits **3**
  > ## Using `BackgroundTasks` { #using-backgroundtasks }

### dg-004 — YES
**Q:** How do I run cleanup steps after a dependency has finished being used?
**must_cite_sources:** `d1e84524…` → `tutorial/dependencies/dependencies-with-yield.md`
- `yield` — verbatim ✓ · corpus file hits **11**
  > title: "Dependencies with yield"
- `extra steps` — verbatim ✓ · corpus file hits **1**
  > FastAPI supports dependencies that do some <dfn title='sometimes also called "exit code", "cleanup code", "teardown code", "closing code", "context manager exit code", etc.'>extra steps afte

### dg-005 — YES
**Q:** How do I make a response omit fields that were never explicitly set?
**must_cite_sources:** `c226c5ab…` → `tutorial/response-model.md`
- `response_model_exclude_unset` — verbatim ✓ · corpus file hits **2**
  > ### Use the `response_model_exclude_unset` parameter { #use-the-response-model-exclude-unset-parameter }

### dg-006 — YES
**Q:** How do I return an HTTP error such as 404 to the client from a path operation?
**must_cite_sources:** `c99d90e0…` → `tutorial/handling-errors.md`
- `HTTPException` — verbatim ✓ · corpus file hits **9**
  > ## Use `HTTPException` { #use-httpexception }
- `raise` — verbatim ✓ · corpus file hits **13**
  > ### Raise an `HTTPException` in your code { #raise-an-httpexception-in-your-code }

### dg-007 — YES
**Q:** What does FastAPI provide for writing tests against my endpoints?
**must_cite_sources:** `a7a9ab45…` → `tutorial/testing.md`
- `TestClient` — verbatim ✓ · corpus file hits **7**
  > ## Using `TestClient` { #using-testclient }
- `pytest` — verbatim ✓ · corpus file hits **5**
  > With it, you can use [pytest](https://docs.pytest.org/) directly with **FastAPI**.

### dg-008 — YES
**Q:** How do I serve static files from a directory in a FastAPI application?
**must_cite_sources:** `9893a11f…` → `tutorial/static-files.md`
- `StaticFiles` — verbatim ✓ · corpus file hits **4**
  > You can serve static files automatically from a directory using `StaticFiles`.
- `Mount` — verbatim ✓ · corpus file hits **7**
  > * "Mount" a `StaticFiles()` instance in a specific path.

### dg-009 — YES
**Q:** What happens when a path operation function is declared with normal def instead of async def?
**must_cite_sources:** `ce5af47a…` → `async.md`
- `external threadpool` — verbatim ✓ · corpus file hits **1**
  > When you declare a *path operation function* with normal `def` instead of `async def`, it is run in an external threadpool that is then awaited, instead of being called directly (as it would
- `async def` — verbatim ✓ · corpus file hits **13**
  > Details about the `async def` syntax for *path operation functions* and some background about asynchronous code, concurrency, and parallelism.

### dg-010 — YES
**Q:** How do I split a large FastAPI application across multiple files?
**must_cite_sources:** `36bf3c4c…` → `tutorial/bigger-applications.md`
- `APIRouter` — verbatim ✓ · corpus file hits **11**
  > ## `APIRouter` { #apirouter }
- `include_router` — verbatim ✓ · corpus file hits **6**
  > With `app.include_router()` we can add each `APIRouter` to the main `FastAPI` application.

### dg-011 — YES
**Q:** How do I read application configuration from environment variables using Pydantic?
**must_cite_sources:** `558324ba…` → `advanced/settings.md`
- `BaseSettings` — verbatim ✓ · corpus file hits **2**
  > Import `BaseSettings` from Pydantic and create a sub-class, very much like with a Pydantic model.
- `environment variables` — verbatim ✓ · corpus file hits **4**
  > For this reason it's common to provide them in environment variables that are read by the application.

---

## Baseline lock — 3 runs on the demo profile

Every run identical to four decimal places; retrieval is byte-identical across
runs, and the generator is pinned at temperature 0 (product behavior since
P1-T6's gate).

| Run | Pass | context P | context R | Faithfulness | Relevancy | Judged cases |
|---|---|---|---|---|---|---|
| `20260826T145511` | **13/15** | 0.4545 | 0.9091 | 0.8587 | 0.9457 | 23 |
| `20260826T145904` | **13/15** | 0.4545 | 0.9091 | 0.8587 | 0.9457 | 23 |
| `20260826T150504` | **13/15** | 0.4545 | 0.9091 | 0.8587 | 0.9457 | 23 |

**Band: 13/15 — 13/15 — 13/15.** Reported as a band, not a number, per standing
practice; this one happens to have zero width.

**Guards: 4/4 declined through the gate**, routed `none` — zero generation
tokens spent on any of them.

Judge calibration (the 8 frozen anchors, re-judged every run): mean absolute
difference **0.0938**, within-tolerance rate **93.75%** — consistent with the
personal profile's calibration, so the judge is measuring the demo answers with
the same instrument it measures the personal ones.

### The two standing failures — both real, neither an exam defect

| Case | What happened | Verdict |
|---|---|---|
| **dg-002** | Honest decline. `context_precision` **0.0** — the required document was never retrieved. The question ("which path operation wins when two could match") is answered in the corpus by a sentence the retriever did not surface for this phrasing. | **Retrieval miss.** Kept as a failing case: it is the baseline's job to carry real defects, not to be clean. |
| **dg-010** | Honest decline *while citing the right document*. The retrieved chunk from `tutorial/bigger-applications.md` was the introduction rather than the `APIRouter` section, so the generator correctly refused to assert what it had not been given. | **Chunk-selection miss.** The refusal is the pipeline behaving well on bad input; the retrieval is what failed. |

Neither was "fixed" by weakening the case. Both name a specific, reproducible
retrieval weakness on this corpus, which is what a locked baseline is for.

## The derived not-found threshold

**THRESHOLDS DO NOT TRANSFER.** The personal corpus's `-1.67` was derived
against its own rerank-score distribution and is meaningless here. The demo
gate was derived from a **calibration run with the gate disabled**, scoring all
15 cases:

| | Score | Case |
|---|---|---|
| Worst answerable | **-0.2844** | dg-005 |
| Best guard | **-0.3858** | dg-012 |
| **Margin** | **0.1014** | |
| **Derived threshold** | **-0.3351** | midpoint — the same derivation rule that produced `-1.67` from (-1.27 / -2.07) |

Full guard distribution: `-0.3858`, `-0.6317`, `-1.5051`, `-1.5277`.
Answerable distribution: `-0.2844`, `2.2748`, `2.7895`, `3.7397`, `5.1650`,
`6.3244`, `6.6609`, `6.8377`, `6.8823`, `7.5477`, `8.9305`.

### ⚠ WATCH: this margin is 0.1014 against the personal corpus's 0.8008

Stated plainly because it is the most interesting number in this task. A
**single-project documentation corpus is topically homogeneous**: an
out-of-corpus question about gRPC or Terraform still retrieves chunks about
serving and deploying software, so the reranker's scores compress and the
answerable/guard separation narrows. **A narrow-domain corpus makes the
not-found gate harder, not easier** — the opposite of the intuition that a
small tidy corpus is an easier problem.

Re-derivation trigger recorded in `config/retrieval.demo.json`: any reranker
change, any corpus-pin change, or a measured margin below **0.05**.

### Routing is OFF on the demo profile, deliberately

The personal escalate band `[-1.67, 1.5]` was derived from eight runs of
failure clustering on the personal corpus. There is no demo failure cluster to
calibrate against — two failures, both retrieval-side, neither fixable by
escalating the generator — so importing the band would be exactly the
threshold transfer this ruling forbids. Recorded as a decision, not an
oversight; the demo runs report `routes: {cheap: 11, none: 4}`.
