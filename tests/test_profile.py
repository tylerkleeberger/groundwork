"""P5-T2: the corpus profile switch (D7 cashed).

The refusals matter more than the happy path. A profile that silently falls
back, or that takes some settings from one corpus and some from another, is
the failure this phase exists to prevent: a run that believes it is the demo
while reading the owner's documents.
"""

import json
import pathlib
import subprocess

import pytest

from app.profile import load_profile


def write_config(tmp_path, payload) -> object:
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps(payload))
    return path


def test_active_profile_is_declared_and_its_corpus_is_present_or_ignored():
    """The active profile must be declared, complete, and point at a corpus
    that is either PRESENT or DELIBERATELY GITIGNORED.

    Not "the default is personal": that is a private-repo convention, and this
    file ships to a public repo whose only corpus is the demo one.

    Not "the corpus directory exists" either — that was this test's first form
    and it went red in CI, because the personal corpus is gitignored ON
    PURPOSE and therefore absent from every checkout. Red for a reason no
    reader could act on is exactly the fault the previous version had, in the
    other direction.

    The invariant that is actually true in both repos and in CI: a profile
    points at a corpus that is here, or at one that is intentionally kept out
    of version control. A path that is neither is a typo."""
    active = load_profile()
    cfg = json.loads(pathlib.Path(load_profile.__globals__["CONFIG_PATH"]).read_text())
    assert active.name in cfg["profiles"]

    for name in cfg["profiles"]:
        p = load_profile(name)
        assert p.corpus_dir and p.db_schema and p.eval_set
        if p.corpus_dir.is_dir():
            continue
        # Trailing slash matters: `.gitignore` says `corpus/`, a
        # DIRECTORY-only pattern, and when the directory is absent git cannot
        # tell the bare path is one. Measured: `check-ignore corpus` -> rc 1,
        # `check-ignore corpus/` -> rc 0. The absent case is the only case
        # this branch runs in, so the slash is not optional.
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", f"{p.corpus_dir.name}/"],
            cwd=str(p.corpus_dir.parent), capture_output=True).returncode == 0
        assert ignored, (
            f"profile {name!r} points at {p.corpus_dir}, which is neither "
            "present nor gitignored — a path that is neither is a typo")


def test_personal_adds_no_connect_arguments_at_all():
    """PARITY BY CONSTRUCTION: the personal profile must connect exactly as it
    did before this seam existed. An empty kwargs dict is the property; an
    `options` string that merely *means* the same thing is not."""
    assert load_profile("personal").connect_kwargs() == {}


def test_demo_puts_its_own_schema_first_and_keeps_public_reachable():
    kwargs = load_profile("demo").connect_kwargs()
    assert kwargs == {"options": "-c search_path=demo,public"}


def test_demo_and_personal_share_no_setting():
    """The two profiles must not overlap on any of the three: an overlap is a
    path by which demo output lands in personal storage."""
    personal, demo = load_profile("personal"), load_profile("demo")
    assert personal.corpus_dir != demo.corpus_dir
    assert personal.db_schema != demo.db_schema
    assert personal.eval_set != demo.eval_set


def test_unknown_profile_refuses_rather_than_defaulting(tmp_path):
    cfg = write_config(tmp_path, {
        "profile": "typo",
        "profiles": {"personal": {"corpus_dir": "corpus", "db_schema": "public",
                                  "eval_set": "evals/golden_set.jsonl"}},
    })
    with pytest.raises(SystemExit, match="unknown corpus profile"):
        load_profile(path=cfg)


def test_partial_profile_refuses(tmp_path):
    cfg = write_config(tmp_path, {
        "profile": "half", "profiles": {"half": {"corpus_dir": "corpus_demo"}},
    })
    with pytest.raises(SystemExit, match="missing"):
        load_profile(path=cfg)


@pytest.mark.parametrize("schema", ["", "public; DROP TABLE chunks", "Demo-1", "デモ"])
def test_unusable_schema_refuses(tmp_path, schema):
    """The schema reaches SQL by interpolation (identifiers cannot be bound),
    so anything outside a conservative identifier is refused at load."""
    cfg = write_config(tmp_path, {
        "profile": "x",
        "profiles": {"x": {"corpus_dir": "c", "db_schema": schema, "eval_set": "e"}},
    })
    with pytest.raises(SystemExit, match="unusable db_schema"):
        load_profile(path=cfg)


# ---------- P5-T2 review pass: the wiring, not just the config ----------

def test_one_definition_of_the_schema_rule(tmp_path):
    """The connect rule has ONE definition (`schema_connect_kwargs`), used by
    both Profile.connect_kwargs and ingest.run_ingest. A second copy could
    drift, and the drift is silent: a caller on the wrong schema reads an
    empty corpus, which looks like a retrieval bug rather than a config one."""
    from app.profile import schema_connect_kwargs

    assert schema_connect_kwargs("public") == {}
    assert schema_connect_kwargs("demo") == {
        "options": "-c search_path=demo,public"}

    import inspect

    import ingest
    assert "schema_connect_kwargs" in inspect.getsource(ingest.run_ingest), (
        "run_ingest must use the shared rule, not restate it")
    for prof in ("personal", "demo"):
        p = load_profile(prof)
        assert p.connect_kwargs() == schema_connect_kwargs(p.db_schema)


def test_sync_refuses_under_a_non_personal_profile():
    """sync pulls the owner's PERSONAL corpus from Neon. Running it while the
    demo profile is active is the 'believes it is running the demo' failure —
    refuse rather than surprise."""
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent
                           / "scripts"))
    from sync import profile_refusal

    assert profile_refusal("personal") is None
    msg = profile_refusal("demo")
    assert msg and "REFUSING TO SYNC" in msg
    assert "export_demo_corpus.py" in msg, "name the right tool for the job"
