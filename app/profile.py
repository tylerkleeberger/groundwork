"""D7's corpus profile, cashed (P5-T2).

D7 promised a pluggable corpus: the daily instance points at the owner's own
documents, a demo profile points at public OSS docs so the portfolio never
exposes personal material. The seam was the promise; this is the wiring.

ONE SWITCH, ONE SOURCE OF TRUTH. `config/corpus.json` carries `profile` and the
per-profile settings. There is deliberately NO environment override: a second
way to select the profile is a second thing to get wrong, and the failure mode
is the one this whole phase exists to prevent — the personal corpus reachable
from something that believes it is running the demo.

WHAT A PROFILE SELECTS: the corpus directory (what is ingested), the database
schema (where it lands, so the two corpora cannot mix in one table), and the
eval set (what "the numbers" are measured over). Those three move together;
selecting them separately is how a demo run scores personal ground truth.

Mirrors config/retrieval.json's loader shape (app/retrieval.py) rather than
inventing a config mechanism.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "corpus.json"

# A schema name reaches SQL by interpolation (identifiers cannot be bound as
# parameters), so it is constrained to a conservative identifier here and the
# set of legal profiles is closed by the config file itself.
_SCHEMA_OK = set("abcdefghijklmnopqrstuvwxyz0123456789_")


def schema_connect_kwargs(schema: str) -> dict[str, str]:
    """Extra psycopg.connect kwargs selecting `schema`.

    EMPTY for the default `public` schema — deliberately. The personal profile
    must connect EXACTLY as it did before this seam existed, so its parity is
    structural (no argument is added) rather than argued (an argument is added
    and claimed equivalent). Any other schema gets `options` with itself FIRST
    and `public` retained, so shared extensions stay reachable while
    unqualified DDL lands in the profile's schema.

    ONE definition, used by every connect site (Profile.connect_kwargs and
    ingest.run_ingest). A second copy of this rule is a second thing that can
    drift, and the drift would be silent: a caller pointed at the wrong schema
    reads an empty corpus, which looks like a retrieval bug, not a config one.
    """
    if schema == "public":
        return {}
    return {"options": f"-c search_path={schema},public"}


@dataclass(frozen=True)
class Profile:
    name: str
    corpus_dir: pathlib.Path
    db_schema: str
    eval_set: pathlib.Path
    # Optional 4th setting (P5-T3): retrieval knobs whose THRESHOLDS were
    # derived on this profile's own score distribution. None = the shipped
    # config/retrieval.json, so the personal profile reads exactly the file
    # it always read.
    retrieval_config: pathlib.Path | None = None

    def connect_kwargs(self) -> dict[str, str]:
        return schema_connect_kwargs(self.db_schema)


def load_config(path: pathlib.Path | None = None) -> dict:
    return json.loads((path or CONFIG_PATH).read_text())


def load_profile(name: str | None = None, path: pathlib.Path | None = None) -> Profile:
    """The active profile. `name` is for tests and explicit callers; the file's
    `profile` key is the switch everything else obeys."""
    cfg = load_config(path)
    selected = name or cfg.get("profile")
    profiles = cfg.get("profiles", {})
    if selected not in profiles:
        raise SystemExit(
            f"REFUSING: unknown corpus profile {selected!r}; "
            f"config declares {sorted(profiles)}. An unrecognised profile must "
            "not silently fall back to the personal corpus."
        )
    entry = profiles[selected]
    missing = {"corpus_dir", "db_schema", "eval_set"} - set(entry)
    if missing:
        raise SystemExit(
            f"REFUSING: profile {selected!r} is missing {sorted(missing)}. "
            "A partial profile would take some settings from one corpus and "
            "some from another."
        )
    schema = entry["db_schema"]
    if not schema or set(schema) - _SCHEMA_OK:
        raise SystemExit(
            f"REFUSING: profile {selected!r} has an unusable db_schema "
            f"{schema!r} (lowercase letters, digits and underscore only)."
        )
    rcfg = entry.get("retrieval_config")
    return Profile(
        name=selected,
        corpus_dir=REPO_ROOT / entry["corpus_dir"],
        db_schema=schema,
        eval_set=REPO_ROOT / entry["eval_set"],
        retrieval_config=(REPO_ROOT / rcfg) if rcfg else None,
    )
