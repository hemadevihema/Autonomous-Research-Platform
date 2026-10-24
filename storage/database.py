"""
Persistent Relational Storage Engine (SQLite)
==============================================
Provides structured, ACID-compliant local database storage for projects,
sources, extracted evidence, verbatim quotes, QC logs, and audit trails.
"""
import sqlite3
import json
from contextlib import contextmanager
from datetime import datetime
from typing import List, Dict, Any, Optional
from config.settings import DATABASE_PATH


class ResearchDatabase:
    """Relational vault for research automation persistence and audit trails."""

    def __init__(self, db_path=DATABASE_PATH):
        self.db_path = str(db_path)
        self.init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self):
        """Create tables if they do not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Projects Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                topic TEXT,
                disease TEXT,
                countries TEXT,
                sections TEXT,
                min_publication_year INTEGER,
                status TEXT,
                created_at TEXT
            )
            """)

            # Sources Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS sources (
                source_id TEXT PRIMARY KEY,
                project_id TEXT,
                title TEXT,
                publisher TEXT,
                source_type TEXT,
                publication_year INTEGER,
                data_period TEXT,
                source_url TEXT,
                validation_status TEXT,
                sections_covered TEXT,
                rejection_reasons TEXT,
                data_json TEXT,
                created_at TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(project_id)
            )
            """)

            # Insights Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS insights (
                insight_id TEXT PRIMARY KEY,
                project_id TEXT,
                source_id TEXT,
                country TEXT,
                section TEXT,
                insight_text TEXT,
                evidence_passage TEXT,
                is_verified INTEGER,
                created_at TEXT,
                data_json TEXT
            )
            """)

            # Verbatim Quotations Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS verbatims (
                verbatim_id TEXT PRIMARY KEY,
                project_id TEXT,
                source_id TEXT,
                country TEXT,
                section TEXT,
                exact_quote TEXT,
                match_verified INTEGER,
                created_at TEXT,
                data_json TEXT
            )
            """)

            # Audit Trail Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT,
                stage TEXT,
                message TEXT,
                timestamp TEXT
            )
            """)
            # Upgrade databases created before structured evidence payloads were persisted.
            for table in ("insights", "verbatims"):
                columns = {row[1] for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()}
                if "data_json" not in columns:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN data_json TEXT")
            conn.commit()

    def save_project(self, project_id: str, topic: str, disease: str, countries: List[str], sections: List[str], min_year: int, status: str = "INITIALIZED"):
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO projects (project_id, topic, disease, countries, sections, min_publication_year, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (project_id, topic, disease, json.dumps(countries), json.dumps(sections), min_year, status, now))
            conn.commit()

    def update_project_status(self, project_id: str, status: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE projects SET status = ? WHERE project_id = ?", (status, project_id))
            conn.commit()

    def save_source(self, project_id: str, source_dict: Dict[str, Any]):
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            prior_row = cursor.execute(
                "SELECT data_json FROM sources WHERE source_id = ? AND project_id = ?",
                (source_dict["id"], project_id),
            ).fetchone()
            source_dict = dict(source_dict)
            prior = json.loads(prior_row["data_json"]) if prior_row and prior_row["data_json"] else None
            history = list(source_dict.get("validation_history") or (prior or {}).get("validation_history", []))
            snapshot_fields = (
                "validation_status", "validation_reasons", "validation_checks",
                "validation_check_outcomes", "sections_covered",
            )
            if prior and any(prior.get(field) != source_dict.get(field) for field in snapshot_fields):
                previous_snapshot = {field: prior.get(field) for field in snapshot_fields}
                if not history or history[-1].get("previous_state") != previous_snapshot:
                    history.append({"recorded_at": now, "previous_state": previous_snapshot})
            if history:
                source_dict["validation_history"] = history
            cursor.execute("""
            INSERT OR REPLACE INTO sources (
                source_id, project_id, title, publisher, source_type, publication_year,
                data_period, source_url, validation_status, sections_covered, rejection_reasons,
                data_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                source_dict["id"],
                project_id,
                source_dict.get("source_title", ""),
                source_dict.get("name_of_source", ""),
                source_dict.get("source_type", ""),
                source_dict.get("publication_year"),
                source_dict.get("data_period", ""),
                source_dict.get("source_link", ""),
                source_dict.get("validation_status", ""),
                json.dumps(source_dict.get("sections_covered", [])),
                json.dumps(source_dict.get("validation_reasons", [])),
                json.dumps(source_dict),
                now
            ))
            conn.commit()

    def save_insight(self, project_id: str, insight: Dict[str, Any]):
        """Persist an insight as an independent, idempotently keyed record."""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO insights (
                    insight_id, project_id, source_id, country, section,
                    insight_text, evidence_passage, is_verified, created_at, data_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    insight.get("id", ""), project_id, insight.get("source_id", ""),
                    insight.get("country", ""), insight.get("section", ""),
                    insight.get("insight_text", ""), insight.get("evidence_passage", ""),
                    int(bool(insight.get("is_verified"))), now,
                    json.dumps(insight, ensure_ascii=False),
                ),
            )

    def save_verbatim(self, project_id: str, verbatim: Dict[str, Any]):
        """Persist an exact quote and its verification/location metadata independently."""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO verbatims (
                    verbatim_id, project_id, source_id, country, section,
                    exact_quote, match_verified, created_at, data_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    verbatim.get("id", ""), project_id, verbatim.get("source_id", ""),
                    verbatim.get("country", ""), verbatim.get("section", ""),
                    verbatim.get("exact_quote", ""),
                    int(bool(verbatim.get("match_verified"))), now,
                    json.dumps(verbatim, ensure_ascii=False),
                ),
            )

    def get_insights_for_project(self, project_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT data_json FROM insights WHERE project_id = ? ORDER BY created_at, insight_id",
                (project_id,),
            ).fetchall()
            return [json.loads(row["data_json"]) for row in rows if row["data_json"]]

    def get_verbatims_for_project(self, project_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT data_json FROM verbatims WHERE project_id = ? ORDER BY created_at, verbatim_id",
                (project_id,),
            ).fetchall()
            return [json.loads(row["data_json"]) for row in rows if row["data_json"]]

    def log_audit_event(self, project_id: str, stage: str, message: str):
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO audit_events (project_id, stage, message, timestamp)
            VALUES (?, ?, ?, ?)
            """, (project_id, stage, message, now))
            conn.commit()

    def get_sources_for_project(self, project_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data_json FROM sources WHERE project_id = ?", (project_id,))
            rows = cursor.fetchall()
            return [json.loads(row["data_json"]) for row in rows]
