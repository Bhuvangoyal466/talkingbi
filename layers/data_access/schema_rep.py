import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from typing import Optional, Any
import pandas as pd


try:
    import duckdb
    _DUCKDB_AVAILABLE = True
except ImportError:
    _DUCKDB_AVAILABLE = False


@dataclass
class Field:
    name: str
    dtype: str
    description: str = ""
    sample_data: list = field(default_factory=list)


@dataclass
class SharedFieldGroup:
    group_id: str
    fields: list
    tables: list
    field_hash: str


@dataclass
class Table:
    name: str
    schema: str
    fields: list
    shared_group: Optional[Any] = None
    description: str = ""
    row_count: int = 0


@dataclass
class DatabaseSchema:
    db_name: str
    tables: dict
    shared_groups: dict


class SchemaRepresentation:
    """
    Transforms relational database schema into traversable tree structure.
    Implements Shared Field Group abstraction to reduce redundancy from
    O(N×M) to O(N+M) complexity as described in SQLAgent paper.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = self._connect(db_path)

    def _connect(self, db_path: str):
        if db_path.endswith(".duckdb") and _DUCKDB_AVAILABLE:
            return duckdb.connect(db_path)
        return sqlite3.connect(db_path)

    def _field_hash(self, fields: list) -> str:
        """Generate unique 128-bit MD5 hash for a set of fields."""
        sorted_fields = sorted(f"{f.name}:{f.dtype}" for f in fields)
        canonical = "|".join(sorted_fields)
        return hashlib.md5(canonical.encode()).hexdigest()

    def extract_schema(self) -> DatabaseSchema:
        """Extract full database schema with Shared Field Group abstraction."""
        tables = {}
        signature_map: dict = {}

        if isinstance(self.conn, sqlite3.Connection):
            cursor = self.conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            table_names = [row[0] for row in cursor.fetchall()]
        else:
            table_names = [
                r[0]
                for r in self.conn.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='main'"
                ).fetchall()
            ]

        for tname in table_names:
            fields = self._extract_fields(tname)
            fhash = self._field_hash(fields)
            signature_map.setdefault(fhash, []).append(tname)
            tables[tname] = Table(
                name=tname,
                schema="main",
                fields=fields,
                row_count=self._get_row_count(tname),
            )

        shared_groups = self._build_shared_groups(signature_map, tables)

        for group in shared_groups.values():
            for tname in group.tables:
                if tname in tables:
                    tables[tname].shared_group = group

        db_name = self.db_path.replace("\\", "/").split("/")[-1].replace(".db", "").replace(".duckdb", "")
        return DatabaseSchema(db_name=db_name, tables=tables, shared_groups=shared_groups)

    def _extract_fields(self, table_name: str) -> list:
        fields = []
        if isinstance(self.conn, sqlite3.Connection):
            cursor = self.conn.cursor()
            cursor.execute(f"PRAGMA table_info({table_name})")
            rows = cursor.fetchall()
            for row in rows:
                sample = self._get_sample(table_name, row[1])
                fields.append(Field(name=row[1], dtype=row[2], sample_data=sample))
        else:
            # DuckDB
            result = self.conn.execute(
                f"SELECT column_name, data_type FROM information_schema.columns "
                f"WHERE table_name='{table_name}'"
            ).fetchall()
            for row in result:
                sample = self._get_sample(table_name, row[0])
                fields.append(Field(name=row[0], dtype=row[1], sample_data=sample))
        return fields

    def _get_sample(self, table: str, col: str, n: int = 3) -> list:
        try:
            if isinstance(self.conn, sqlite3.Connection):
                cursor = self.conn.cursor()
                cursor.execute(
                    f"SELECT DISTINCT {col} FROM {table} WHERE {col} IS NOT NULL LIMIT {n}"
                )
                return [r[0] for r in cursor.fetchall()]
            else:
                return [
                    r[0]
                    for r in self.conn.execute(
                        f"SELECT DISTINCT {col} FROM {table} WHERE {col} IS NOT NULL LIMIT {n}"
                    ).fetchall()
                ]
        except Exception:
            return []

    def _get_row_count(self, table: str) -> int:
        try:
            if isinstance(self.conn, sqlite3.Connection):
                cursor = self.conn.cursor()
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                return cursor.fetchone()[0]
            else:
                return self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except Exception:
            return 0

    def _build_shared_groups(
        self, sig_map: dict, tables: dict
    ) -> dict:
        """Greedy selection of non-overlapping Shared Field Groups."""
        candidates = [
            (fhash, tnames)
            for fhash, tnames in sig_map.items()
            if len(tnames) >= 2
        ]
        candidates.sort(
            key=lambda x: (len(x[1]), len(tables[x[1][0]].fields)), reverse=True
        )

        groups = {}
        assigned = set()

        for fhash, tnames in candidates:
            unassigned = [t for t in tnames if t not in assigned]
            if len(unassigned) < 2:
                continue
            rep_table = tables[tnames[0]]
            group = SharedFieldGroup(
                group_id=f"FieldGroup_{fhash[:8]}",
                fields=rep_table.fields,
                tables=unassigned,
                field_hash=fhash,
            )
            groups[fhash] = group
            assigned.update(unassigned)

        return groups

    def to_json(self, schema: DatabaseSchema) -> str:
        """Serialize schema to JSON for LLM consumption."""
        out = {"db": schema.db_name, "tables": {}}
        for tname, table in schema.tables.items():
            out["tables"][tname] = {
                "fields": [
                    {"name": f.name, "type": f.dtype, "sample": f.sample_data[:3]}
                    for f in table.fields
                ],
                "rows": table.row_count,
                "group": table.shared_group.group_id if table.shared_group else None,
            }
        return json.dumps(out, indent=2)
