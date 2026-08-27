"""P2-T2 batch adjudication: the standing human-anchor rule cashing in.

Run at re-locks (not per-flag): lists unadjudicated flags from evals/flags/
(gitignored, raw), renders each, records the OWNER's verdict:

  g  golden-candidate → emits a clearly-marked candidate JSON into
     evals/candidates/ (TRACKED — curated evidence joins the evidence
     chain per the T2 gate amendment). NEVER self-added to the golden set;
     candidates await spec-gate ratification.
  t  trap-candidate   → same, shaped for answer_must_not_contain (the
     first-three-observed-failures standing rule).
  n  not-a-failure    → dismissed; reason kept in the flag file.

The verdict is appended INTO the flag file — the audit trail is the file.
Pure logic (candidate assembly, verdict application) offline-tested in
tests/test_flags.py.
"""

import datetime
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FLAGS_DIR = REPO / "evals" / "flags"
CANDIDATES_DIR = REPO / "evals" / "candidates"


# ---------- pure logic (offline-tested) ----------

def is_adjudicated(flag: dict) -> bool:
    return "verdict" in flag


def render_flag(flag: dict) -> str:
    chunks = flag.get("chunks") or []
    lines = [
        f"question:  {flag.get('question')}",
        f"flagged:   {flag.get('flagged_at')}  reason: {flag.get('reason') or '(none)'}",
        f"gate {flag.get('gate_score')} · confidence {flag.get('confidence')}",
        f"answer: {(flag.get('answer') or '')[:400]}",
        "retrieved: " + ", ".join(
            f"[{c.get('source_id', '?')[:8]}] {(c.get('title') or '?')[:40]}"
            for c in chunks),
    ]
    return "\n".join(lines)


def make_candidate(flag: dict, kind: str, note: str | None) -> dict:
    """Candidate JSON, clearly marked: evidence for a future exam change,
    never a self-added case."""
    assert kind in ("golden", "trap")
    base = {
        "_status": ("CANDIDATE — owner-adjudicated from a real-use flag; "
                    "NOT in the golden set until ratified at a spec gate"),
        "_kind": kind,
        "_adjudicated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "_adjudication_note": note,
        "_flag": {k: flag.get(k) for k in
                  ("flagged_at", "reason", "question", "answer",
                   "citations", "retrieved", "gate_score", "confidence")},
        "question": flag.get("question"),
    }
    if kind == "trap":
        base["answer_must_not_contain_SUGGESTION"] = (
            "<owner fills: the observed-wrong phrase from the flagged answer>")
    else:
        base["must_cite_sources_SUGGESTION"] = (
            "<owner fills: verified source id(s)>")
        base["answer_must_contain_SUGGESTION"] = (
            "<owner fills: verbatim strings from the source doc(s)>")
    return base


def apply_verdict(flag: dict, verdict: str, note: str | None) -> dict:
    flag = dict(flag)
    flag["verdict"] = {"kind": verdict, "note": note,
                       "at": datetime.datetime.now().isoformat(timespec="seconds")}
    return flag


# ---------- interactive batch (owner-run) ----------

def main() -> int:
    flags = sorted(FLAGS_DIR.glob("*.json")) if FLAGS_DIR.exists() else []
    pending = [(f, json.loads(f.read_text())) for f in flags]
    pending = [(f, d) for f, d in pending if not is_adjudicated(d)]
    if not pending:
        print("no unadjudicated flags — nothing to do")
        return 0
    print(f"{len(pending)} flag(s) to adjudicate\n")
    CANDIDATES_DIR.mkdir(exist_ok=True)
    for path, flag in pending:
        print("=" * 70)
        print(render_flag(flag))
        choice = input("\n[g]olden-candidate / [t]rap-candidate / "
                       "[n]ot-a-failure / [s]kip ? ").strip().lower()
        if choice == "s" or choice not in ("g", "t", "n"):
            print("skipped\n")
            continue
        note = input("note (optional): ").strip() or None
        kind = {"g": "golden", "t": "trap", "n": "dismissed"}[choice]
        if choice in ("g", "t"):
            out = CANDIDATES_DIR / f"{path.stem}-{kind}-candidate.json"
            out.write_text(json.dumps(make_candidate(flag, kind, note), indent=2))
            print(f"candidate → {out.relative_to(REPO)}")
        path.write_text(json.dumps(apply_verdict(flag, kind, note), indent=2))
        print("verdict recorded\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
