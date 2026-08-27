"""T1-export: read-only export of the owner's KB into corpus/*.md.

Source: APP_CORPUS_SOURCE_URL (SELECT-only corpus_reader role; seven granted
tables). One markdown file per row, YAML frontmatter + body. Deterministic
filenames from source_id so re-export overwrites in place — ingest.py's hash
check (P1-T2) owns change detection from there.

Mapping (owner-approved 2026-07-06): EmKb (status != STUB — D8's honest
not-found applied at ingestion time), EmSession, KbUnit. EmDomain/EmLayer
serve as join-based frontmatter enrichment, not documents. EmConcept and
EmResource carry no prose and are not exported.

Run: set -a; source .env; set +a; python scripts/export_corpus.py
"""

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

CORPUS_DIR = Path(__file__).resolve().parent.parent / "corpus"


# ---------- pure logic (offline-tested in tests/test_export_corpus.py) ----------

def filename_for(source_table: str, source_id: str) -> str:
    """Deterministic filename from the stable row identifier.

    No title slugs: a renamed title must not orphan its file. The id is
    sanitized so a hostile/odd id cannot escape corpus/.
    """
    safe_id = "".join(c if c.isalnum() or c in "-_" else "-" for c in source_id)
    return f"{source_table.lower()}-{safe_id}.md"


def yaml_scalar(value: Any) -> str:
    """Render a frontmatter value safely. JSON string encoding is valid YAML,
    which sidesteps colons/quotes in titles without a YAML dependency."""
    if value is None:
        return '""'
    if isinstance(value, datetime):
        return value.isoformat()
    return json.dumps(str(value), ensure_ascii=False)


def frontmatter(fields: dict[str, Any]) -> str:
    lines = ["---"]
    lines += [f"{key}: {yaml_scalar(value)}" for key, value in fields.items()]
    lines.append("---")
    return "\n".join(lines) + "\n"


def assemble_sections(sections: list[tuple[str, str | None]]) -> str:
    """Join (heading, text) pairs, skipping empty texts. Single section →
    no heading (the frontmatter already carries the title)."""
    present = [(h, t.strip()) for h, t in sections if t and t.strip()]
    if not present:
        return ""
    if len(present) == 1:
        return present[0][1] + "\n"
    return "\n\n".join(f"## {h}\n\n{t}" for h, t in present) + "\n"


def document(fields: dict[str, Any], body: str) -> str:
    return frontmatter(fields) + "\n" + body


# ---------- table specs ----------

@dataclass(frozen=True)
class TableSpec:
    name: str
    sql: str

    def to_file(self, row: dict[str, Any]) -> tuple[str, str] | None:
        """(filename, content) for a row, or None to skip (empty body)."""
        raise NotImplementedError


EMKB_SQL = '''
SELECT k.id, k.concept, k."kbType", k.status::text AS status, k.body,
       k."updatedAt", d.name AS domain, l.name AS layer
FROM "EmKb" k
LEFT JOIN "EmDomain" d ON d.id = k."domainId"
LEFT JOIN "EmLayer"  l ON l.id = d."layerId"
WHERE k.status::text <> 'STUB'
ORDER BY k.id
'''

EMSESSION_SQL = '''
SELECT s.id, s.topic, s.date, s."createdAt", s.decisions, s.notes,
       d.name AS domain
FROM "EmSession" s
LEFT JOIN "EmDomain" d ON d.id = s."domainId"
ORDER BY s.id
'''

KBUNIT_SQL = '''
SELECT id, unit, "unitType", tier, domain, content, "createdAt"
FROM "KbUnit"
ORDER BY id
'''


def emkb_to_file(row: dict[str, Any]) -> tuple[str, str] | None:
    body = assemble_sections([("Body", row["body"])])
    if not body:
        return None
    fields = {
        "source_id": row["id"],
        "title": row["concept"],
        "updated_at": row["updatedAt"],
        "source_table": "EmKb",
        "kb_type": row["kbType"],
        "status": row["status"],
        "domain": row["domain"],
        "layer": row["layer"],
    }
    return filename_for("EmKb", row["id"]), document(fields, body)


def emsession_to_file(row: dict[str, Any]) -> tuple[str, str] | None:
    body = assemble_sections([("Decisions", row["decisions"]), ("Notes", row["notes"])])
    if not body:
        return None
    fields = {
        "source_id": row["id"],
        "title": row["topic"],
        # no updatedAt column exists; createdAt accepted (T2 hash check
        # owns change detection — owner/Director ruling 2026-07-06)
        "updated_at": row["createdAt"],
        "source_table": "EmSession",
        "session_date": row["date"],
        "domain": row["domain"],
    }
    return filename_for("EmSession", row["id"]), document(fields, body)


def kbunit_to_file(row: dict[str, Any]) -> tuple[str, str] | None:
    body = assemble_sections([("Content", row["content"])])
    if not body:
        return None
    fields = {
        "source_id": row["id"],
        "title": row["unit"],
        "updated_at": row["createdAt"],  # same ruling as EmSession
        "source_table": "KbUnit",
        "unit_type": row["unitType"],
        "tier": row["tier"],
        "domain": row["domain"],
    }
    return filename_for("KbUnit", row["id"]), document(fields, body)


TABLES = [
    ("EmKb", EMKB_SQL, emkb_to_file),
    ("EmSession", EMSESSION_SQL, emsession_to_file),
    ("KbUnit", KBUNIT_SQL, kbunit_to_file),
]


# ---------- export ----------

@dataclass
class ExportResult:
    """Counts plus the exact filename set written — the prune stage of
    scripts/sync.py (P1-T9) diffs corpus/ against `filenames` to remove
    files whose rows no longer exist (export overwrites, never deletes)."""
    exported: dict[str, int]
    skipped: dict[str, int]
    filenames: set[str]
    samples: list[str]

    @property
    def total(self) -> int:
        return sum(self.exported.values())


def run_export(url: str, corpus_dir: Path = CORPUS_DIR) -> ExportResult:
    import psycopg
    from psycopg.rows import dict_row

    corpus_dir.mkdir(exist_ok=True)
    result = ExportResult(exported={}, skipped={}, filenames=set(), samples=[])

    with psycopg.connect(url, row_factory=dict_row) as conn:
        # read-only in code as well as in the role's grants; must be set
        # before the first statement (it can't change mid-transaction)
        conn.read_only = True
        for name, sql, to_file in TABLES:
            result.exported[name] = result.skipped[name] = 0
            for row in conn.execute(sql):
                converted = to_file(row)
                if converted is None:
                    result.skipped[name] += 1
                    continue
                fname, content = converted
                (corpus_dir / fname).write_text(content, encoding="utf-8")
                result.filenames.add(fname)
                result.exported[name] += 1
                if len(result.samples) < 3 and result.exported[name] == 1:
                    result.samples.append(fname)
    return result


def main() -> int:
    url = os.environ.get("APP_CORPUS_SOURCE_URL")
    if not url:
        print("ERROR: APP_CORPUS_SOURCE_URL not set. Load .env first:", file=sys.stderr)
        print("       set -a; source .env; set +a", file=sys.stderr)
        return 1

    result = run_export(url)
    print(f"exported: {result.total} files -> {CORPUS_DIR}/")
    for name in result.exported:
        print(f"  {name}: {result.exported[name]} exported, "
              f"{result.skipped[name]} skipped (empty body)")
    print("samples:", ", ".join(result.samples))
    return 0


if __name__ == "__main__":
    sys.exit(main())
