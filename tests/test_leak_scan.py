"""P5-T1 offline tests (D16 unmarked) — the leak scanner's red-green
property pinned in CI.

The canary discipline: a scanner that has never been PROVEN to catch a
plant is a scanner nobody should trust (the T4 lesson — a test the
defense never faced is not a passed test). These tests build a
throwaway git repo, plant a canary in tree and history, prove RED, then
prove GREEN once removed.
"""
import subprocess

import pytest

from scripts.leak_scan import (STRUCTURAL, build_seeds, ngram_seeds,
                               scan_history, scan_text, scan_tree,
                               title_seeds, uuid_seeds)

CANARY = ("The owner's private note about agent memory layers and how "
          "context is assembled across them")
SEEDS = {"corpus_string": {CANARY}, "em_title": set(),
         "calibration": set(), "source_id": set()}


# ---------- seed generation ----------

def test_ngram_seeds_respects_threshold():
    text = "short line here\nthis line has more than eight words in it truly\n"
    seeds = ngram_seeds(text)
    assert any("more than eight words" in s for s in seeds)
    assert not any(s == "short line here" for s in seeds)


def test_title_and_uuid_seeds():
    doc = ('---\ntitle: "Layered Cake Architecture for Widgets"\n'
           'source_id: "3f2a91c4-7d0e-4b8a-9c15-6e2d8fa07b31"\n---\n')
    assert title_seeds(doc) == {"Layered Cake Architecture for Widgets"}
    assert uuid_seeds(doc) == {"3f2a91c4-7d0e-4b8a-9c15-6e2d8fa07b31"}


def test_build_seeds_writes_nothing(tmp_path):
    """§F.1: seeds are generated locally and NEVER persisted."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.md").write_text(
        '---\ntitle: "A Doc"\nsource_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"\n'
        '---\nthis sentence is long enough to become a seed for scanning\n')
    before = set(p.name for p in tmp_path.rglob("*"))
    seeds = build_seeds(corpus_dir=corpus, judges_dir=tmp_path / "none")
    after = set(p.name for p in tmp_path.rglob("*"))
    assert before == after, "seed generation must not create files"
    # "A Doc" is 2 words → the em_title_short class (see the split test)
    assert seeds["em_title_short"] == {"A Doc"}
    assert seeds["source_id"] == {"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}


# ---------- structural classes ----------

@pytest.mark.parametrize("klass,sample", [
    ("machine_path", "/Users/someone/GitHub/x"),  # leak-scan-allow
    ("neon_host", "ep-quiet-mode-12345.us-east-2.aws.neon.tech"),  # leak-scan-allow
    ("neon_endpoint", "ep-quiet-mode-a1b2c3"),  # leak-scan-allow
])
def test_structural_classes_fire(klass, sample):
    assert STRUCTURAL[klass].search(sample), klass
    hits = scan_text(sample, {"corpus_string": set(), "em_title": set(),
                              "calibration": set(), "source_id": set()})
    assert any(h["class"] == klass for h in hits)


def test_clean_text_is_clean():
    assert scan_text("A perfectly ordinary sentence about FastAPI.",
                     SEEDS) == []


# ---------- THE RED-GREEN CANARY PROOF (tree + history) ----------

def _git(repo, *args):
    subprocess.run(["git", *args], cwd=str(repo), check=True,
                   capture_output=True, text=True)


@pytest.fixture
def canary_repo(tmp_path):
    repo = tmp_path / "artifact"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "T")
    (repo / "README.md").write_text("# Public artifact\n\nNothing private.\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "initial clean commit")
    return repo


def test_canary_red_in_tree(canary_repo):
    (canary_repo / "leak.md").write_text(f"Some prose.\n\n{CANARY}\n")
    findings = scan_tree(canary_repo, SEEDS)
    assert findings, "scanner MISSED a planted canary in the working tree"
    assert findings[0]["class"] == "corpus_string"
    assert findings[0]["where"] == "tree"


def test_canary_red_in_history_after_removal(canary_repo):
    """The decisive case (§A's whole argument): a canary committed and
    then DELETED is gone from the tree but still in history — the
    scanner must still go RED."""
    (canary_repo / "leak.md").write_text(f"{CANARY}\n")
    _git(canary_repo, "add", "-A")
    _git(canary_repo, "commit", "-qm", "oops")
    (canary_repo / "leak.md").unlink()
    _git(canary_repo, "add", "-A")
    _git(canary_repo, "commit", "-qm", "remove it")

    assert scan_tree(canary_repo, SEEDS) == [], "tree should look clean"
    hist = scan_history(canary_repo, SEEDS)
    assert hist, "scanner MISSED a canary that survives only in history"
    assert hist[0]["where"] == "history"


def test_canary_green_when_never_committed(canary_repo):
    """GREEN half: an artifact that never carried the canary scans
    clean in BOTH surfaces."""
    assert scan_tree(canary_repo, SEEDS) == []
    assert scan_history(canary_repo, SEEDS) == []


def test_scanner_refuses_empty_seed_set(tmp_path, monkeypatch):
    """An empty seed set would make ANY artifact look clean — the
    scanner must refuse rather than pass vacuously (exit 2)."""
    import scripts.leak_scan as ls
    monkeypatch.setattr(ls, "CORPUS", tmp_path / "missing")
    monkeypatch.setattr(ls, "JUDGES", tmp_path / "missing")
    monkeypatch.setattr("sys.argv", ["leak_scan.py", str(tmp_path)])
    assert ls.main() == 2


def test_cannot_verify_is_distinct_from_leak(tmp_path, monkeypatch):
    """A non-git target cannot have its history scanned. That is
    CANNOT-VERIFY (exit 2), not CLEAN and not a leak — an unscannable
    artifact must never be reported as clean."""
    import scripts.leak_scan as ls
    (tmp_path / "f.md").write_text("nothing private here at all\n")
    monkeypatch.setattr("sys.argv", ["leak_scan.py", str(tmp_path)])
    assert ls.main() == 2


def test_short_titles_are_a_separate_class(tmp_path):
    """P5-T1 measurement: 1-2 word EM titles match ordinary prose. They
    are split into `em_title_short` so gating them is a RULING, never an
    accident — and never silently discarded."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.md").write_text(
        '---\ntitle: "Widgets"\n---\nbody\n')
    (corpus / "b.md").write_text(
        '---\ntitle: "Layered Cake Architecture for Widgets"\n---\nbody\n')
    seeds = build_seeds(corpus_dir=corpus, judges_dir=tmp_path / "none")
    assert seeds["em_title"] == {"Layered Cake Architecture for Widgets"}
    assert seeds["em_title_short"] == {"Widgets"}


# ---------- the sweep path (director ruling, 2026-08-26 P5-T1 gate) ----------

def _seeded_corpus(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.md").write_text(
        '---\ntitle: "Widgets"\n---\n'
        'this sentence is long enough to become a corpus seed for scanning\n')
    return corpus


def test_sweep_force_includes_short_titles(canary_repo, tmp_path,
                                           monkeypatch, capsys):
    """RULING: the short-title class is EXCLUDED from routine CI scans
    (cries-wolf) and FORCE-INCLUDED in the one-time pre-publish sweep,
    whose hits get human review. The sweep must not depend on a human
    also remembering --strict-titles — coverage at the one moment it
    matters is structural, not remembered."""
    import scripts.leak_scan as ls
    monkeypatch.setattr(ls, "CORPUS", _seeded_corpus(tmp_path))
    monkeypatch.setattr(ls, "JUDGES", tmp_path / "none")
    (canary_repo / "doc.md").write_text("A page about Widgets in general.\n")

    monkeypatch.setattr("sys.argv", ["leak_scan.py", str(canary_repo)])
    assert ls.main() == 0, "routine scan must NOT fire on a short title"

    monkeypatch.setattr("sys.argv",
                        ["leak_scan.py", str(canary_repo), "--sweep"])
    assert ls.main() == 1, "sweep MUST fire on the short-title class"
    out = capsys.readouterr().out
    assert "em_title_short" in out
    assert "HUMAN REVIEW" in out


def test_sweep_refuses_without_history(canary_repo, tmp_path, monkeypatch):
    """The sweep is defined over the CONSTRUCTED history; a history-less
    sweep would report a verdict it did not earn (exit 2)."""
    import scripts.leak_scan as ls
    monkeypatch.setattr(ls, "CORPUS", _seeded_corpus(tmp_path))
    monkeypatch.setattr(ls, "JUDGES", tmp_path / "none")
    monkeypatch.setattr("sys.argv", ["leak_scan.py", str(canary_repo),
                                     "--sweep", "--no-history"])
    assert ls.main() == 2


# ---------- structural/content split (director ruling, P5-T2 gate) ----------

def test_no_project_names_are_hardcoded_in_the_shipped_scanner():
    """THE SELF-REFERENTIAL LEAK: a shipped string-matcher publishes its own
    seed list, so a detector that hardcodes a private name discloses that name
    to every reader. Structural classes describe SHAPES and are safe to ship;
    content — project names included — never does."""
    import pathlib

    import scripts.leak_scan as ls

    assert set(ls.STRUCTURAL) == {"machine_path", "neon_host", "neon_endpoint"}
    assert "project_name" not in ls.STRUCTURAL
    assert "project_name" in ls.build_seeds(
        corpus_dir=pathlib.Path("/nonexistent"),
        judges_dir=pathlib.Path("/nonexistent")), "it is a CONTENT class now"

    # NOTE: this test deliberately names no private project. Writing the
    # obvious assertion — "these names must not appear in the scanner
    # source" — would put those names in tests/, which ships too. The
    # check that actually catches a hardcoded name is the pre-publish
    # sweep, whose project_name seeds come from the untracked seed file.
    # A test cannot forbid a string by containing it.


def test_seed_roundtrip_through_an_untracked_file(tmp_path, monkeypatch):
    """The public scanner has no corpus to read, so content seeds cross the
    gap as an untracked file. This is a deliberate amendment to P5-T1's
    'seeds are never written': the rule that survives is the one that always
    mattered — seed material never enters a REPOSITORY."""
    import scripts.leak_scan as ls

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.md").write_text(
        '---\ntitle: "A Long Enough Title Here"\n---\n'
        'this sentence is long enough to become a corpus seed for scanning\n')
    seeds = ls.build_seeds(corpus_dir=corpus, judges_dir=tmp_path / "none")
    seedfile = tmp_path / ".leak_seeds.local.json"
    counts = ls.emit_seeds(seedfile, seeds)
    assert counts["corpus_string"] == 1

    loaded = ls.load_content_seeds(seedfile)
    assert loaded["corpus_string"] == seeds["corpus_string"]
    assert loaded["em_title"] == seeds["em_title"]


def test_seed_file_is_gitignored():
    """A seed file that can be committed is a seed file that will be."""
    import pathlib
    import subprocess

    root = pathlib.Path(__file__).resolve().parent.parent
    probe = root / "_probe.leak_seeds.local.json"
    rc = subprocess.run(["git", "check-ignore", "-q",
                         str(root / ".leak_seeds.local.json")],
                        cwd=str(root)).returncode
    assert rc == 0, ".leak_seeds.local.json must be gitignored"
    assert not probe.exists()


def test_missing_seeds_cannot_verify_but_structural_only_is_explicit(
        canary_repo, tmp_path, monkeypatch, capsys):
    """No content seeds => the scanner has not looked for content and must
    not imply that it did (exit 2). --structural-only is the caller saying
    'I know, run the reduced check anyway' — the public CI mode — and its
    verdict is LABELLED as being about shapes, not content."""
    import scripts.leak_scan as ls

    monkeypatch.setattr(ls, "CORPUS", tmp_path / "no-corpus")
    monkeypatch.setattr(ls, "JUDGES", tmp_path / "no-judges")
    monkeypatch.chdir(tmp_path)          # no .leak_seeds.local.json here

    monkeypatch.setattr("sys.argv", ["leak_scan.py", str(canary_repo)])
    assert ls.main() == 2, "missing seeds must never produce a clean verdict"
    assert "CANNOT VERIFY" in capsys.readouterr().err

    monkeypatch.setattr("sys.argv",
                        ["leak_scan.py", str(canary_repo), "--structural-only"])
    assert ls.main() == 0
    out = capsys.readouterr().out
    assert "STRUCTURAL ONLY" in out
    assert "not a 'no personal strings' verdict" in out


def test_structural_only_still_catches_structural_leaks(
        canary_repo, tmp_path, monkeypatch):
    """The reduced check is reduced, not decorative."""
    import scripts.leak_scan as ls

    monkeypatch.setattr(ls, "CORPUS", tmp_path / "no-corpus")
    monkeypatch.setattr(ls, "JUDGES", tmp_path / "no-judges")
    monkeypatch.chdir(tmp_path)
    (canary_repo / "notes.md").write_text("path: /Users/someone/GitHub/x\n")  # leak-scan-allow
    monkeypatch.setattr("sys.argv",
                        ["leak_scan.py", str(canary_repo), "--structural-only"])
    assert ls.main() == 1


def test_allow_marker_is_line_scoped_not_file_scoped(tmp_path):
    """The scanner's own patterns and its synthetic fixtures are SUPPOSED to
    look like leaks. Exempting whole files would hide a real leak sitting
    among them; the marker makes each exemption a decision recorded on the
    line it applies to — and the line BELOW an exempt line is still scanned."""
    import scripts.leak_scan as ls

    # Assembled from parts on purpose: a literal machine path written here
    # would trip the scan of THIS file (see the test below), and a test that
    # forces an exemption to prove a point is the tail wagging the dog.
    home = "/User" + "s"
    text = (f"a path {home}/alice/thing  " + ls.ALLOW_MARKER + "\n"
            f"another path {home}/bob/thing\n")
    hits = ls.scan_text(text, {})
    assert len(hits) == 1, "exactly one line was exempt"
    assert "bob" in hits[0]["match"]


def test_the_scanner_and_its_tests_survive_their_own_scan(tmp_path):
    """Public CI runs this scanner over a tree containing the scanner. If its
    own pattern definitions tripped it, the required status check would be
    permanently red and would teach everyone to ignore it."""
    import pathlib

    import scripts.leak_scan as ls

    for f in (pathlib.Path(ls.__file__), pathlib.Path(__file__)):
        hits = ls.scan_text(f.read_text(), {})
        assert hits == [], f"{f.name} trips the structural classes: {hits[:3]}"


def test_structural_only_actually_restricts_the_scan(tmp_path, monkeypatch, capsys):
    """A flag named 'only' must RESTRICT. This one used to merely soften the
    refusal when seeds happened to be absent, so in the private repo's CI —
    where corpus/ is gone but the calibration payloads are committed — seeds
    were generated anyway and the 'structural-only' run did a full content
    scan of a tree that legitimately holds private material. A flag that
    reports something other than what it did is worse than no flag."""
    import scripts.leak_scan as ls

    judges = tmp_path / "judges"
    judges.mkdir()
    (judges / "calibration.json").write_text(
        "a line long enough to become a calibration seed for this scan\n")
    monkeypatch.setattr(ls, "CORPUS", tmp_path / "no-corpus")
    monkeypatch.setattr(ls, "JUDGES", judges)
    assert any(ls.build_seeds().values()), "seeds ARE available here"

    target = tmp_path / "artifact"
    target.mkdir()
    (target / "f.md").write_text(
        "a line long enough to become a calibration seed for this scan\n")

    monkeypatch.setattr("sys.argv", ["leak_scan.py", str(target),
                                     "--structural-only", "--no-history"])
    assert ls.main() == 0, "content seeds must not be consulted"
    out = capsys.readouterr().out
    assert "not consulted (--structural-only)" in out


# ---------- allowlist vs denylist: the overlap that must not exist ----------

def test_public_surface_and_private_only_are_disjoint():
    """PRIVATE_ONLY is a DENYLIST standing next to the public allowlist, and
    its failure mode is silent in the worst direction: a path wrongly added to
    it stops being SCANNED while continuing to SHIP — the file would be in the
    public repo and exempt from the check meant to protect it.

    Nothing in the code prevents that overlap; the two lists merely happen not
    to intersect. This test is what makes the allowlist ruling hold, because
    an allowlist that fails closed only fails closed if nothing quietly
    re-opens it.

    NOTE ON THE SKIP: build_public_repo.py is private-repo tooling and is
    deliberately absent from the public repo, while this test file ships. The
    skip is therefore correct rather than convenient — in the public repo
    there is no allowlist to be disjoint FROM, because the whole tree is the
    public surface. It is stated out loud so nobody later reads a green run
    there as evidence this property was checked.
    """
    import pathlib
    import sys

    import pytest

    import scripts.leak_scan as ls

    root = pathlib.Path(ls.__file__).resolve().parent.parent
    builder = root / "scripts" / "build_public_repo.py"
    if not builder.is_file():
        pytest.skip("build_public_repo.py absent — this is the public repo, "
                    "where the whole tree IS the public surface and there is "
                    "no allowlist to be disjoint from")

    sys.path.insert(0, str(root / "scripts"))
    import build_public_repo as bpr

    def norm(p: str) -> str:
        return p.rstrip("/")

    shippable = {norm(p) for p in bpr.PUBLIC_PATHS} - {norm(p) for p in bpr.EXCLUDE_WITHIN}
    skipped = {norm(p) for p in ls.PRIVATE_ONLY}

    # Exact collisions.
    both = shippable & skipped
    assert not both, (
        f"paths are BOTH shipped and skip-scanned: {sorted(both)} — they would "
        "reach the public repo exempt from the scan that guards it")

    # Prefix collisions: PRIVATE_ONLY entries match by startswith, so a
    # denylist prefix that covers an allowlisted path is the same failure
    # wearing a different shape.
    for s in shippable:
        for k in skipped:
            assert not s.startswith(k + "/") and s != k, (
                f"shipped path {s!r} is covered by the skip-scan prefix {k!r}")
        # …and the reverse: an allowlisted DIRECTORY that contains a
        # skip-scanned path is fine only because EXCLUDE_WITHIN removes the
        # specific file; assert that is how it was handled, not by accident.
        for k in skipped:
            if k.startswith(s + "/"):
                assert any(norm(e).startswith(s + "/") for e in bpr.EXCLUDE_WITHIN) or \
                    not (root / k).exists(), (
                    f"skip-scanned {k!r} sits inside shipped directory {s!r} "
                    "with nothing removing it from the build")
