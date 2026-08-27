"""Groundwork eval harness — Layer 1 (deterministic), wired to the live pipeline.

P1-T5: ask() now performs a real POST to the /ask endpoint; each case is scored
for context_precision / context_recall over the RETRIEVED chunk set and the run
is written to evals/results/<timestamp>.json so deltas are diffable across runs
(the file the PR description references from P1-T5 on — CI note in ci.yml).

Layer 2 (LLM-as-judge via the `cheap` alias) is P1-T6 and lands beside this.

Marked `@pytest.mark.live`: it needs the gateway + app + Ollama + Postgres up
and spends tokens, so the offline CI floor (`pytest -m "not live"`) skips it.
Run it locally with services up:
    set -a; source .env; set +a
    scripts/gateway.sh &                       # LiteLLM :4000
    .venv/bin/uvicorn app.main:app --port 8310 &
    pytest evals/                              # or: ASK_URL=... pytest evals/
When the endpoint is unreachable every live case skips (never red) with a
message pointing at the launch path.

Env: ASK_URL (default http://localhost:8310/ask), GATEWAY, LANGFUSE_*.
"""
import json
import pathlib
import subprocess
import urllib.error
import urllib.request
from datetime import datetime

import pytest

from app.profile import load_profile  # repo root on sys.path (pytest.ini)
from app.retrieval import load_retrieval_config
from judge import calibration_agreement, judge_case, load_anchors  # noqa: F401
from scoring import (  # evals/ is on sys.path (pytest prepend import mode)
    context_precision,
    context_recall,
    is_answerable,
    layer1_failures,
    relevant_ids,
)

# P5-T2: the exam set comes from the ACTIVE PROFILE, not a hardcoded path.
# The three settings a profile carries move together by design — a demo run
# scored against personal ground truth is the failure this seam exists to
# prevent. Under `personal` this resolves to evals/golden_set.jsonl, exactly
# the path that was hardcoded here before.
GOLDEN = load_profile().eval_set
RESULTS_DIR = pathlib.Path(__file__).parent / "results"  # gitignored
ASK_URL = __import__("os").environ.get("ASK_URL", "http://localhost:8310/ask")


def load_cases():
    """Cases for the active profile. A MISSING set yields zero cases rather
    than an import-time crash: collection must survive a profile whose exam
    has not been authored yet (the demo set lands in P5-T3). Zero cases can
    never masquerade as a pass — test_harness_alive below says so out loud."""
    if not GOLDEN.exists():
        return []
    return [json.loads(l) for l in GOLDEN.read_text().splitlines() if l.strip()]


def ask(question: str, timeout: float = 90.0) -> dict:
    """Real call to POST /ask. Returns the parsed
    {answer, citations[], confidence, retrieved[]} body."""
    body = json.dumps({"question": question}).encode()
    req = urllib.request.Request(
        ASK_URL, data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=pathlib.Path(__file__).parent, text=True,
        ).strip()
    except Exception:
        return None


def _mean(xs):
    return round(sum(xs) / len(xs), 4) if xs else None


@pytest.fixture(scope="session")
def live_ask():
    """Confirm the pipeline is up once (cheap GET /openapi.json — no tokens),
    then hand back the ask() caller. Skips the whole live layer if it's down."""
    base = ASK_URL.rsplit("/", 1)[0]
    try:
        urllib.request.urlopen(base + "/openapi.json", timeout=5)
    except (urllib.error.URLError, OSError) as e:
        pytest.skip(
            f"{ASK_URL} unreachable ({e}); bring up the pipeline "
            "(scripts/gateway.sh + uvicorn app.main:app --port 8310) then re-run"
        )
    return ask


@pytest.fixture(scope="session")
def answer_cache():
    """One /ask round-trip per case per run: test_layer1 fills it, the judge
    layer reuses it (re-asking would judge a DIFFERENT answer)."""
    return {}


@pytest.fixture(scope="session")
def judge_client():
    import os

    from openai import OpenAI
    return OpenAI(base_url=os.environ.get("GATEWAY", "http://localhost:4000"),
                  api_key="anything")


@pytest.fixture(scope="session")
def results_sink():
    """Collect per-case records; on teardown emit one diffable results file.
    Skipped/empty runs write nothing — no misleading zero-case artifacts."""
    records: list[dict] = []
    yield records
    if not records:
        return
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    golden = [r for r in records if r.get("type") != "calibration_constructed"]
    answerable = [r for r in golden if r["context_precision"] is not None]
    passed = [r for r in golden if r["passed"]]
    summary = {
        "timestamp": now.isoformat(timespec="seconds"),
        "git_commit": _git_commit(),
        "ask_url": ASK_URL,
        "cases_total": len(golden),
        "cases_passed": len(passed),
        "pass_rate": round(len(passed) / len(golden), 4) if golden else None,
        "answerable_evaluated": len(answerable),
        "notfound_cases": len(golden) - len(answerable),
        "mean_context_precision": _mean([r["context_precision"] for r in answerable]),
        "mean_context_recall": _mean([r["context_recall"] for r in answerable]),
    }
    # T8: the gate margin, printed every run so threshold decay is visible
    # BEFORE it fails (worst answerable vs best guard, on the gate signal)
    gated = [r for r in golden if r.get("gate_score") is not None]
    ans_g = [r["gate_score"] for r in gated if r.get("expected_behavior") != "not_found"]
    grd_g = [r["gate_score"] for r in gated if r.get("expected_behavior") == "not_found"]
    if ans_g and grd_g:
        summary["gate_margin"] = {
            "worst_answerable": min(ans_g), "best_guard": max(grd_g),
            "margin": round(min(ans_g) - max(grd_g), 4),
            # P5-T3: the ACTIVE PROFILE's threshold. This read used to be
            # hardcoded to config/retrieval.json, so a demo run printed the
            # personal corpus's -1.67 beside demo-derived scores — a margin
            # instrument reporting a number from a different distribution is
            # worse than no instrument.
            "threshold": load_retrieval_config()["not_found"]["min_rerank_score"],
            "profile": load_profile().name,
        }
    # P2-T3 routing visibility: per-route counts + band margin discipline
    # (T8 style — decay announces itself in every results file)
    routes = {}
    for r in golden:
        rt = r.get("routed_to")
        if rt:
            routes[rt] = routes.get(rt, 0) + 1
    if routes:
        summary["routes"] = routes
        rcfg = load_retrieval_config().get("routing", {})
        band = rcfg.get("escalate_band")
        # Report the band only when routing is actually ON: printing edges for
        # a disabled router describes a decision nothing made (the demo
        # profile has no failure cluster to calibrate a band against yet).
        if band and rcfg.get("enabled"):
            in_band = [r["gate_score"] for r in golden
                       if r.get("gate_score") is not None
                       and band[0] <= r["gate_score"] < band[1]]
            summary["routing_band"] = {
                "edges": band,
                "cases_in_band": len(in_band),
                # full disclosure: every in-band score, sorted — the
                # gate reads specific cases' headroom from here (the code
                # cannot know WHICH case is the captured failure).
                # drift_out_headroom = highest score's distance to the
                # upper edge: a routed case about to leave the band (a
                # cost change signal, and for a captured failure like
                # gs-024 a correctness-decay signal).
                "in_band_scores": sorted(round(g, 4) for g in in_band),
                "drift_out_headroom": round(band[1] - max(in_band), 4) if in_band else None,
            }
    judged = [r for r in records if r.get("faithfulness") is not None]
    if judged:
        summary["judged_cases"] = len(judged)
        summary["mean_faithfulness"] = _mean([r["faithfulness"] for r in judged])
        summary["mean_relevancy"] = _mean([r["relevancy"] for r in judged])
        summary["calibration_agreement"] = calibration_agreement(records)
    path = RESULTS_DIR / f"{now.strftime('%Y%m%dT%H%M%S')}.json"
    path.write_text(json.dumps({"summary": summary, "cases": records}, indent=2))
    print(
        f"\n[evals] wrote {path.relative_to(pathlib.Path(__file__).parent.parent)} "
        f"— {summary['cases_passed']}/{summary['cases_total']} passed, "
        f"mean precision {summary['mean_context_precision']}, "
        f"mean recall {summary['mean_context_recall']}"
    )


@pytest.mark.live
@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c["id"])
def test_layer1(case, live_ask, results_sink, answer_cache):
    if str(case.get("question", "")).startswith("TODO"):
        pytest.skip("placeholder case — replace during P1")

    resp = live_ask(case["question"])
    answer_cache[case["id"]] = resp
    answer = resp.get("answer", "")
    citations = resp.get("citations", [])
    retrieved = resp.get("retrieved", [])
    confidence = float(resp.get("confidence", 0.0))

    rel = relevant_ids(case)
    answerable = is_answerable(case)
    fails = layer1_failures(case, answer, citations, confidence)

    results_sink.append({
        "id": case["id"],
        "type": case.get("type"),
        "question": case["question"],
        "expected_behavior": case.get("expected_behavior"),
        "answer": answer,
        "citations": citations,
        "retrieved": retrieved,
        "confidence": confidence,
        "gate_score": resp.get("gate_score"),
        "routed_to": resp.get("routed_to"),
        "route_reason": resp.get("route_reason"),
        "relevant_ids": sorted(rel) if answerable else [],
        "context_precision": context_precision(retrieved, rel) if answerable else None,
        "context_recall": context_recall(retrieved, case) if answerable else None,
        "passed": not fails,
        "failures": fails,
    })

    assert not fails, "; ".join(fails)


@pytest.mark.live
@pytest.mark.judge
@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c["id"])
def test_judge(case, live_ask, results_sink, answer_cache, judge_client):
    """P1-T6 Layer 2: faithfulness + relevancy via alias `cheap` (skippable:
    -m "not judge"). Scores attach to this run's Layer-1 record so the
    results file gains the columns; aggregates + calibration agreement land
    in the summary."""
    resp = answer_cache.get(case["id"]) or live_ask(case["question"])
    scores = judge_case(
        judge_client,
        question=case["question"],
        answer=resp.get("answer", ""),
        chunks=resp.get("chunks", []),
    )
    record = next((r for r in results_sink if r["id"] == case["id"]), None)
    if record is None:  # judge-only run (-m judge): minimal record
        record = {"id": case["id"], "type": case.get("type"),
                  "question": case["question"], "answer": resp.get("answer", ""),
                  "context_precision": None, "context_recall": None,
                  "passed": None, "failures": []}
        results_sink.append(record)
    record.update(scores)
    assert 0.0 <= scores["faithfulness"] <= 1.0
    assert 0.0 <= scores["relevancy"] <= 1.0


@pytest.mark.live
@pytest.mark.judge
@pytest.mark.parametrize("anchor", load_anchors(), ids=lambda a: a["id"])
def test_judge_anchor(anchor, results_sink, judge_client):
    """Calibration anchors: FROZEN payloads judged every run. No /ask call —
    the payload IS the fixture, so agreement measures judge movement alone
    (pipeline changes cannot contaminate it; T7 drift finding)."""
    scores = judge_case(judge_client, question=anchor["question"],
                        answer=anchor["answer"], chunks=anchor["chunks"])
    results_sink.append({
        "id": anchor["id"], "type": "calibration_constructed",
        "question": anchor["question"], "answer": anchor["answer"][:200],
        "context_precision": None, "context_recall": None,
        "passed": None, "failures": [], **scores,
    })
    assert 0.0 <= scores["faithfulness"] <= 1.0
    assert 0.0 <= scores["relevancy"] <= 1.0


def test_harness_alive():
    """Offline sanity (unmarked): the ACTIVE PROFILE's exam set loads and is
    non-trivial. If the profile's set has not been authored yet, say which
    profile and which path out loud — an absent exam must never read as a
    quiet pass (P5-T1's shape: a gate never reports a verdict it did not
    earn)."""
    if not GOLDEN.exists():
        pytest.skip(f"profile {load_profile().name!r} has no exam set at "
                    f"{GOLDEN} yet — the demo set is P5-T3")
    assert len(load_cases()) >= 3


@pytest.mark.live
def test_related_live(live_ask):
    """P2-T1 smoke: /related answers the KB-review question without a
    generation call — covered territory scores in the covered band.

    P5-T3: the probe topic and the `related_bands` thresholds it asserts
    against were both calibrated on the PERSONAL corpus. Running it under
    another profile asserts a personal-corpus fact about a corpus that never
    contained it — a red test that means nothing. /related has no demo
    calibration (it is not part of the demo exam); giving it one is its own
    task."""
    profile = load_profile()
    if profile.name != "personal":
        pytest.skip(
            f"/related bands are calibrated on the personal corpus; profile is "
            f"{profile.name!r}. A demo /related calibration is a separate task.")
    body = json.dumps({"topic": "JavaScript closures"}).encode()
    req = urllib.request.Request(ASK_URL.rsplit("/", 1)[0] + "/related",
                                 data=body,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        resp = json.loads(r.read().decode())
    assert resp["verdict"] == "likely covered"
    assert resp["sources"] and resp["sources"][0]["best_rerank_score"] > 0


def test_exam_set_comes_from_the_active_profile():
    """P5-T2, offline (unmarked): the third leg of the profile switch. A demo
    run scored against personal ground truth is the failure the profile exists
    to prevent — so the exam set is SELECTED, not hardcoded. Under `personal`
    it must resolve to exactly the path that was hardcoded here before."""
    active = load_profile()
    assert GOLDEN == active.eval_set
    assert load_profile("personal").eval_set.name == "golden_set.jsonl"
    assert load_profile("demo").eval_set != load_profile("personal").eval_set
