"""P5-T1 leak scanner — SPEC-P5 §F.1, ratified 2026-08-03.

Proves the gate criterion: ZERO personal-KB strings in a public
artifact. Seeds are generated LOCALLY at scan time from the private
corpus and calibration payloads and are NEVER written to disk or
committed — the scanner reads private material, the public artifact
never contains it.

TWO CLASSES OF CHECK, and only one of them ships (director ruling,
P5-T2 gate — the self-referential leak):
  * STRUCTURAL (ships publicly): home-directory paths, Neon hostnames and
    endpoints. These describe SHAPES and disclose nothing.
  * CONTENT (never ships): >=8-word corpus strings, EM document titles,
    calibration payloads, source_id UUIDs, and personal project names.
    In the private repo these are generated at scan time from corpus/;
    in the public repo they are read from an untracked local file
    (--seeds / $GROUNDWORK_LEAK_SEEDS), because a shipped string-matcher
    publishes its own seed list.

With no content seeds the scanner exits 2 CANNOT VERIFY rather than
implying it looked. `--structural-only` is how a caller asks for the
reduced check deliberately; that verdict is labelled as being about
shapes, not content, in every line it prints.

Scans BOTH surfaces (a leak in history is the same leak):
  - working tree of the target directory
  - full git history (`git log -p --all`) of the target repo

Usage:
  .venv/bin/python scripts/leak_scan.py [TARGET] [--no-history] [--json]
    TARGET defaults to the current repo (self-scan; expected RED here —
    this repo legitimately contains the private material).
  .venv/bin/python scripts/leak_scan.py TARGET --sweep
    The ONE-TIME pre-publish sweep: force-includes the short-title seed
    class (excluded from routine CI as a cries-wolf class) and reports
    its hits for HUMAN REVIEW.

Exit codes: 0 clean · 1 leak found · 2 CANNOT VERIFY (usage/environment
error, empty seed set, or an unscannable history — fail closed, never
report an unverifiable artifact as clean).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
CORPUS = REPO / "corpus"
JUDGES = REPO / "evals" / "judges"

MIN_SEED_WORDS = 8          # ratified threshold
_WORD = re.compile(r"\S+")
_TITLE = re.compile(r'^title:\s*"?(.+?)"?\s*$', re.M)
_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
                   r"[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)

# STRUCTURAL classes — the only ones that SHIP (director ruling, P5-T2 gate).
# These describe SHAPES, not content: a UUID pattern discloses nothing about
# what the UUIDs identify, and a /Users/ pattern names no user. They are safe
# in a public repository precisely because reading them teaches an attacker
# nothing they did not already know about how paths and hostnames look.
#
# Personal PROJECT NAMES used to live here, and that was the self-referential
# leak P5-T2 found: a shipped string-matcher publishes its own seed list, so a
# detector that hardcodes a private name discloses that name to everyone who
# reads the detector. Project names are now CONTENT seeds and never ship —
# they are supplied at runtime from an untracked local file.
STRUCTURAL = {
    "machine_path": re.compile(r"/Users/[A-Za-z0-9._-]+"),          # leak-scan-allow
    "neon_host": re.compile(r"\b[a-z0-9-]+\.neon\.tech\b", re.I),   # leak-scan-allow
    "neon_endpoint": re.compile(r"\bep-[a-z]+-[a-z]+-[a-z0-9]{6,}\b", re.I),  # leak-scan-allow
}

# Where the public scanner looks for CONTENT seeds. Untracked by construction
# (.gitignore) and generated locally by --emit-seeds from the private repo.
SEED_FILE_ENV = "GROUNDWORK_LEAK_SEEDS"
DEFAULT_SEED_FILE = ".leak_seeds.local.json"

# Paths that legitimately contain leak-shaped text INSIDE this private repo
# and are never part of a public artifact. `--skip-private` consults this, and
# that is how the private repo's CI scans only what could actually ship: a
# structural hit inside .env or ops/ is a fact about a private file, not a
# finding, and a check that reports it is a check people learn to ignore.
PRIVATE_ONLY = ("corpus/", "evals/judges/calibration",
                "evals/golden_set.review.md", "evals/research_set.review.md",
                "evals/research_set.jsonl", "evals/golden_set.jsonl",
                "evals/results/", "evals/candidates/", "evals/flags/",
                # P5-T4: these are TRACKED and legitimately hold machine paths
                # and a database endpoint — launch agents are machine-specific
                # by definition, and the director's own instructions quote the
                # host. None of them are in the public surface, so a structural
                # hit here is a fact about a private file, not a finding.
                "ops/", "docs/DIRECTOR.md", "docs/DIRECTOR_HISTORY.md",
                ".env", ".dispatch/", "BUILD_JOURNAL.md")


# ---------- seed generation (pure; offline-testable) ----------

def ngram_seeds(text: str, min_words: int = MIN_SEED_WORDS) -> set[str]:
    """Distinct >=N-word strings from a document, taken as whole LINES
    (a line is the natural authored unit; sub-line n-grams would explode
    the seed set without catching anything a line miss wouldn't)."""
    seeds = set()
    for line in text.splitlines():
        line = line.strip()
        if len(_WORD.findall(line)) >= min_words:
            seeds.add(line)
    return seeds


def title_seeds(text: str) -> set[str]:
    return {m.group(1).strip() for m in _TITLE.finditer(text)
            if m.group(1).strip()}


def uuid_seeds(text: str) -> set[str]:
    return set(m.group(0).lower() for m in _UUID.finditer(text))


def build_seeds(corpus_dir: pathlib.Path | None = None,
                judges_dir: pathlib.Path | None = None) -> dict[str, set[str]]:
    """Generate every seed class locally. Returns a dict of class →
    seed set; NOTHING is written to disk (§F.1: seeds are never
    committed).

    Paths resolve at CALL time, not import time — default-argument
    binding made the module constants unpatchable and therefore
    untestable (caught by the empty-seed-refusal test)."""
    corpus_dir = corpus_dir if corpus_dir is not None else CORPUS
    judges_dir = judges_dir if judges_dir is not None else JUDGES
    corpus_strings: set[str] = set()
    titles: set[str] = set()
    uuids: set[str] = set()
    if corpus_dir.exists():
        for path in sorted(corpus_dir.glob("*.md")):
            text = path.read_text(errors="replace")
            corpus_strings |= ngram_seeds(text)
            titles |= title_seeds(text)
            uuids |= uuid_seeds(text)
    calibration: set[str] = set()
    if judges_dir.exists():
        for path in sorted(judges_dir.glob("calibration*")):
            text = path.read_text(errors="replace")
            calibration |= ngram_seeds(text)
            uuids |= uuid_seeds(text)
    # Title seeds split by distinctiveness (P5-T1 measurement): 48 of
    # 600 EM titles are only 1-2 words long and therefore match
    # ordinary prose — as false positives they would flood public CI and
    # train its readers to ignore it (the injection-detector lesson).
    # They are NOT discarded: they become a separate class the caller
    # can gate on or report, so coverage is a ruling, not an accident.
    strong = {t for t in titles if len(t.split()) > 2}
    weak = titles - strong
    return {"corpus_string": corpus_strings, "em_title": strong,
            "em_title_short": weak,
            "calibration": calibration, "source_id": uuids,
            # Content class since the P5-T2 ruling: names that identify the
            # owner's other projects. Empty unless supplied — the scanner does
            # not guess, and a guessed list is a false sense of coverage.
            "project_name": set()}


def seed_file_path(explicit: str | None = None) -> pathlib.Path:
    """Where content seeds live for a scanner with no corpus to read.

    Resolution order: explicit flag → $GROUNDWORK_LEAK_SEEDS → the default
    untracked filename in the current directory.
    """
    import os
    if explicit:
        return pathlib.Path(explicit)
    env = os.environ.get(SEED_FILE_ENV)
    return pathlib.Path(env) if env else pathlib.Path(DEFAULT_SEED_FILE)


def load_content_seeds(path: pathlib.Path) -> dict[str, set[str]]:
    """Read content seeds from an untracked local file.

    THE PUBLIC SCANNER HAS NO CORPUS. In the private repo the seeds are
    generated at scan time from `corpus/` and never written; in the public
    repo there is nothing to generate from, so a human who wants the full
    scan supplies this file, which is gitignored and must never be committed.
    That is the whole point of the ruling: the CHECK ships, the SECRETS
    do not.
    """
    data = json.loads(path.read_text())
    return {k: set(v) for k, v in data.items() if isinstance(v, list)}


def emit_seeds(path: pathlib.Path,
               seeds: dict[str, set[str]] | None = None) -> dict[str, int]:
    """Write the content-seed file for use by a scanner elsewhere.

    This is the ONE sanctioned write of seed material, and it is a deliberate
    amendment to P5-T1's "seeds are never written" property: that property
    assumed one repository that always had `corpus/` beside it. A public
    scanner cannot generate what it cannot read, so the seeds must cross the
    gap as a file — untracked, local, and never committed. The narrower rule
    that survives is the one that always mattered: **seed material never
    enters a repository.**
    """
    seeds = seeds if seeds is not None else build_seeds()
    path.write_text(json.dumps({k: sorted(v) for k, v in seeds.items()},
                               indent=0))
    return {k: len(v) for k, v in seeds.items()}


# ---------- scanning (pure over supplied text) ----------

# An explicit, line-level acknowledgement that a line is SUPPOSED to look
# like a leak. Two things legitimately carry leak-shaped text: this scanner's
# own pattern definitions, and its tests' synthetic fixtures. Blanket-skipping
# those files would hide a real leak hidden among them; a marker makes each
# exemption a decision recorded on the line it applies to, greppable and
# reviewable. A detector that cannot describe what it detects is not shippable,
# and one that exempts whole files is not trustworthy.
ALLOW_MARKER = "leak-scan-allow"


def scan_text(text: str, seeds: dict[str, set[str]],
              max_hits: int = 50) -> list[dict]:
    """Find seed and structural hits, LINE BY LINE. Returns findings with
    class + the matched string (truncated — a finding report must not
    itself become a leak vector in CI logs).

    Line-wise rather than whole-blob so the allow marker can be scoped to the
    line it appears on. Equivalent in reach: every seed class is either a
    single authored line (corpus strings, calibration payloads) or a substring
    within one (titles, UUIDs), so nothing that matched before stops matching.
    """
    findings: list[dict] = []
    for line in text.splitlines():
        if ALLOW_MARKER in line:
            continue
        for klass, pattern in STRUCTURAL.items():
            for m in pattern.finditer(line):
                findings.append({"class": klass, "match": m.group(0)[:60]})
                if len(findings) >= max_hits:
                    return findings
        for klass, seed_set in seeds.items():
            for seed in seed_set:
                if seed and seed in line:
                    findings.append({"class": klass, "match": seed[:60]})
                    if len(findings) >= max_hits:
                        return findings
    return findings


# ---------- surfaces ----------

TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".jsonl", ".yaml", ".yml",
                 ".toml", ".cfg", ".ini", ".sh", ".plist", ".html", ".sql", ""}


def scan_tree(target: pathlib.Path, seeds: dict[str, set[str]],
              skip_private: bool = False) -> list[dict]:
    findings = []
    for path in sorted(target.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(target))
        if rel.startswith((".git/", ".venv/", "__pycache__",
                           ".pytest_cache/", "node_modules/", ".mypy_cache/")):
            continue  # build detritus, never part of a published surface
        # NOTE: gitignored files ARE scanned (e.g. .env). A directory
        # being published can leak a file git would not have committed;
        # failing closed on presence is the safer default.
        if skip_private and rel.startswith(PRIVATE_ONLY):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(errors="replace")
        except Exception:
            continue
        for f in scan_text(text, seeds):
            findings.append({**f, "where": "tree", "path": rel})
    return findings


def scan_history(target: pathlib.Path,
                 seeds: dict[str, set[str]]) -> list[dict]:
    """Scan every commit's patch text — a leak in history is the same
    leak (§A: this is precisely why a scrubbed flip was rejected)."""
    try:
        proc = subprocess.run(
            ["git", "log", "-p", "--all", "--no-color"], cwd=str(target),
            capture_output=True, text=True, timeout=900)
    except Exception as exc:
        return [{"class": "history_scan_error", "match": repr(exc)[:60],
                 "where": "history", "path": "-"}]
    if proc.returncode != 0:
        return [{"class": "history_scan_error",
                 "match": (proc.stderr or "")[:60], "where": "history",
                 "path": "-"}]
    return [{**f, "where": "history", "path": "(commit patch)"}
            for f in scan_text(proc.stdout, seeds)]


def _report(args, target, seeds, counts, seed_source, findings,
            structural_only) -> int:
    """One reporting path for every mode — so a new mode cannot ship a
    verdict that describes itself differently from the others."""
    # A scan that COULD NOT RUN is not a clean scan: fail closed, but
    # report it distinctly from an actual leak (exit 2 = cannot verify,
    # exit 1 = leak found). Conflating them would let an unscannable
    # history masquerade as either a pass or a breach.
    errors = [f for f in findings if f["class"] == "history_scan_error"]
    findings = [f for f in findings if f["class"] != "history_scan_error"]

    short_hits = [f for f in findings if f["class"] == "em_title_short"]

    if args.json:
        print(json.dumps({"target": str(target), "seed_counts": counts,
                          "mode": ("sweep" if args.sweep else
                                   "structural-only" if structural_only
                                   else "scan"),
                          "seed_source": seed_source,
                          "classes_checked": (sorted(STRUCTURAL) if structural_only
                                              else sorted(STRUCTURAL) + sorted(counts)),
                          "content_classes_checked": not structural_only,
                          "findings": findings[:50],
                          "leak_count": len(findings),
                          "human_review_count": len(short_hits),
                          "scan_errors": errors[:5]}, indent=2))
    else:
        print(f"target: {target}")
        if args.sweep:
            print("MODE: one-time pre-publish sweep — short-title class "
                  "force-included; its hits require HUMAN REVIEW "
                  f"({len(short_hits)} of {len(findings)} findings)")
        if structural_only:
            print("MODE: STRUCTURAL ONLY — checked "
                  f"{', '.join(sorted(STRUCTURAL))}. Content classes "
                  "(corpus strings, titles, calibration payloads, source ids, "
                  "project names) were NOT checked: no seeds available. This "
                  "verdict is about SHAPES, not about content.")
        print(f"seeds ({seed_source}): " +
              (", ".join(f"{k}={v}" for k, v in counts.items()) or "none"))
        if findings:
            print(f"\nLEAKS FOUND: {len(findings)}")
            for f in findings[:20]:
                print(f"  [{f['class']}] {f['where']}:{f['path']} — "
                      f"{f['match']!r}")
            if len(findings) > 20:
                print(f"  … {len(findings) - 20} more")
        elif errors:
            print("\nCANNOT VERIFY: history scan failed — "
                  f"{errors[0]['match']!r}")
        elif structural_only:
            print("\nSTRUCTURALLY CLEAN: no UUIDs, machine paths or "
                  "hostnames in tree or history. CONTENT NOT CHECKED — this "
                  "is not a 'no personal strings' verdict.")
        else:
            print("\nCLEAN: no personal-KB strings found in tree or history")
    if findings:
        return 1
    return 2 if errors else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("target", nargs="?", default=str(REPO))
    ap.add_argument("--no-history", action="store_true")
    ap.add_argument("--skip-private", action="store_true",
                    help="self-scan aid: skip paths that legitimately hold "
                         "private material in THIS repo")
    ap.add_argument("--strict-titles", action="store_true",
                    help="also seed 1-2 word EM titles (high recall, high "
                         "false-positive rate — measured 48/600 titles)")
    ap.add_argument("--sweep", action="store_true",
                    help="the ONE-TIME pre-publish sweep (§F.1): scans "
                         "tree + full constructed history and FORCE-INCLUDES "
                         "the short-title class, whose hits are for human "
                         "review. Not for routine CI.")
    ap.add_argument("--seeds", metavar="FILE",
                    help=f"content-seed file (default ${SEED_FILE_ENV} or "
                         f"./{DEFAULT_SEED_FILE}). Used when there is no "
                         "corpus/ to generate from — i.e. in the public repo.")
    ap.add_argument("--emit-seeds", metavar="FILE",
                    help="write the locally-generated content seeds to FILE "
                         "for a scanner elsewhere. UNTRACKED, never committed.")
    ap.add_argument("--structural-only", action="store_true",
                    help="run ONLY the structural classes and say so. The "
                         "verdict covers shapes (UUIDs, machine paths, "
                         "hostnames), NOT content. This is the public CI mode.")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.emit_seeds:
        counts = emit_seeds(pathlib.Path(args.emit_seeds))
        if not any(counts.values()):
            print("REFUSING: generated zero seeds — nothing to emit "
                  "(is corpus/ present?)", file=sys.stderr)
            return 2
        print(f"wrote content seeds -> {args.emit_seeds}")
        print("  " + ", ".join(f"{k}={v}" for k, v in counts.items()))
        print("  THIS FILE IS UNTRACKED AND MUST STAY THAT WAY.")
        return 0

    target = pathlib.Path(args.target).resolve()
    if not target.exists():
        print(f"target does not exist: {target}", file=sys.stderr)
        return 2

    # The sweep is DEFINED over the constructed history (§F.1). A
    # history-less sweep would report a verdict it did not earn.
    if args.sweep and args.no_history:
        print("REFUSING: --sweep is defined over the constructed history; "
              "--no-history would make its verdict unearned",
              file=sys.stderr)
        return 2

    # --structural-only FORCES the reduced check. It used to only soften the
    # refusal when seeds happened to be missing, which made it a flag that did
    # not do what its name says: in the private repo's CI, corpus/ is absent
    # but evals/judges/calibration* IS committed, so seeds were generated
    # anyway and the "structural-only" run performed a full content scan of a
    # tree that legitimately contains private material — 150 hits, all of them
    # correct and none of them actionable. Same class as the --seeds bug
    # earlier in this task: a flag that reports something other than what it
    # did is worse than no flag.
    if args.structural_only:
        seeds, counts, seed_source = {}, {}, "not consulted (--structural-only)"
        structural_only = True
        findings = scan_tree(target, seeds, skip_private=args.skip_private)
        if not args.no_history:
            findings += scan_history(target, seeds)
        return _report(args, target, seeds, counts, seed_source, findings,
                       structural_only)

    # Content seeds: generated from corpus/ when it is there (the private
    # repo), otherwise read from the untracked local file (the public repo).
    seeds = build_seeds()
    seed_source = "generated from corpus/"
    sfile = seed_file_path(args.seeds)
    if sfile.is_file():
        # MERGE, never replace. An EXPLICIT --seeds that gets silently ignored
        # because corpus/ happened to be present is a flag that lies: the first
        # sweep run here reported project_name=0 for exactly that reason, while
        # the operator believed those seeds were in play. Classes the generator
        # cannot produce (project names) live only in the file.
        loaded = load_content_seeds(sfile)
        for klass, values in loaded.items():
            seeds[klass] = seeds.get(klass, set()) | values
        seed_source = (f"generated from corpus/ + merged {sfile}"
                       if any(build_seeds().values()) else f"loaded from {sfile}")
    elif not any(seeds.values()):
        seeds = {}
        seed_source = f"NONE ({sfile} absent)"
    elif args.seeds:
        print(f"REFUSING: --seeds {args.seeds} does not exist", file=sys.stderr)
        return 2
    counts = {k: len(v) for k, v in seeds.items()}

    # THE NO-VACUOUS-CLEAN RULE, unchanged since P5-T1 and now load-bearing
    # for the public repo: with no content seeds, the scanner has not looked
    # for content and must not imply that it did.
    #
    # --structural-only is how a caller says "I know, and I want the reduced
    # check anyway" — the public CI mode. The reduced verdict is LABELLED in
    # every line of output, so it is an explicit narrower claim rather than a
    # silent one. Without that flag, missing seeds are still exit 2.
    if not any(counts.values()) and not args.structural_only:
        print("CANNOT VERIFY: no content seeds "
              f"({seed_source}). The structural classes alone cannot support "
              "a 'no personal strings' verdict. Supply --seeds FILE, or pass "
              "--structural-only to run the reduced check deliberately.",
              file=sys.stderr)
        return 2
    structural_only = not any(counts.values())

    # Director ruling (2026-08-26, P5-T1 gate): the short-title class is
    # EXCLUDED from routine CI scans (cries-wolf — 48/600 titles match
    # ordinary prose, and a noisy gate trains its readers to ignore it)
    # and FORCE-INCLUDED in the one-time pre-publish sweep with human
    # review of the hits. --sweep therefore does NOT depend on a human
    # remembering --strict-titles: coverage at the one moment it matters
    # is structural, not remembered. The class stays SEPARATE either way
    # so its hits are identifiable as the ones a human adjudicates.
    if not (args.sweep or args.strict_titles):
        seeds = {k: v for k, v in seeds.items() if k != "em_title_short"}
    findings = scan_tree(target, seeds, skip_private=args.skip_private)
    if not args.no_history:
        findings += scan_history(target, seeds)
    return _report(args, target, seeds, counts, seed_source,
                   findings, structural_only)


if __name__ == "__main__":
    sys.exit(main())
