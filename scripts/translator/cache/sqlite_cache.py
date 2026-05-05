"""
SQLite-backed translation cache.

Cache key: SHA-256(site_id:src_lang:tgt_lang:normalized_text)
Stores translations persistently to avoid redundant LLM calls.
Repeat runs with the same content produce identical output (idempotent).

Usage:
  cache = TranslationCache("cache/translation_cache.db")
  if (hit := cache.lookup("docs", "en", "fr", "Hello world")) is not None:
      return hit
  translation = backend.translate(...)
  cache.store("docs", "en", "fr", "Hello world", translation, "professionalize_llm")
"""
from __future__ import annotations
import hashlib
import logging
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS translations (
    key          TEXT PRIMARY KEY,
    site_id      TEXT NOT NULL,
    src_lang     TEXT NOT NULL,
    tgt_lang     TEXT NOT NULL,
    src_text     TEXT NOT NULL,
    translation  TEXT NOT NULL,
    model_id     TEXT,
    created_at   TEXT NOT NULL,
    hit_count    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tgt_lang ON translations(tgt_lang);
"""

_WHITESPACE_RE = re.compile(r"\s+")


class TranslationCache:
    """
    Persistent SQLite cache for translation segments.
    Thread-safe via WAL journal mode and per-operation connection lifecycle.

    For :memory: databases (used in tests) a single persistent connection is
    kept alive for the lifetime of the instance, because SQLite in-memory
    databases are destroyed as soon as their last connection closes.
    """

    def __init__(self, db_path: str | Path = "cache/translation_cache.db"):
        self._in_memory = str(db_path) == ":memory:"
        self.db_path = Path(db_path)
        if not self._in_memory:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # Persistent connection only for in-memory mode
        self._mem_conn: Optional[sqlite3.Connection] = None
        if self._in_memory:
            self._mem_conn = sqlite3.connect(":memory:", timeout=10, check_same_thread=False)
            self._mem_conn.row_factory = sqlite3.Row
            self._mem_conn.executescript(_CREATE_TABLE_SQL)
            self._mem_conn.commit()
        else:
            self._init_db()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(_CREATE_TABLE_SQL)

    @contextmanager
    def _conn(self):
        if self._in_memory:
            # Yield the persistent in-memory connection without closing it
            conn = self._mem_conn
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        else:
            conn = sqlite3.connect(str(self.db_path), timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def close(self) -> None:
        """Explicitly close the in-memory connection (no-op for file-based DBs)."""
        if self._mem_conn is not None:
            self._mem_conn.close()
            self._mem_conn = None

    @staticmethod
    def _make_key(site_id: str, src_lang: str, tgt_lang: str, text: str) -> str:
        """Return SHA-256 hex digest of the normalized cache input."""
        normalized = _WHITESPACE_RE.sub(" ", text).strip()
        raw = f"{site_id}:{src_lang}:{tgt_lang}:{normalized}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize(text: str) -> str:
        """Collapse internal whitespace for consistent storage."""
        return _WHITESPACE_RE.sub(" ", text).strip()

    def lookup(
        self,
        site_id: str,
        src_lang: str,
        tgt_lang: str,
        text: str,
    ) -> Optional[str]:
        """
        Look up a cached translation.
        Returns the cached translation string, or None if not found.
        Increments hit_count on each successful lookup.
        """
        key = self._make_key(site_id, src_lang, tgt_lang, text)
        with self._conn() as conn:
            row = conn.execute(
                "SELECT translation FROM translations WHERE key = ?", (key,)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE translations SET hit_count = hit_count + 1 WHERE key = ?",
                    (key,),
                )
                return row["translation"]
        return None

    def store(
        self,
        site_id: str,
        src_lang: str,
        tgt_lang: str,
        text: str,
        translation: str,
        model_id: Optional[str] = None,
    ) -> None:
        """
        Store a translation in the cache.
        Uses INSERT OR REPLACE so re-translating a segment updates the row.
        """
        key = self._make_key(site_id, src_lang, tgt_lang, text)
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO translations
                   (key, site_id, src_lang, tgt_lang, src_text, translation, model_id, created_at, hit_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                (
                    key,
                    site_id,
                    src_lang,
                    tgt_lang,
                    self._normalize(text),
                    translation,
                    model_id,
                    now,
                ),
            )

    def flush(self, tgt_lang: Optional[str] = None) -> int:
        """
        Remove cached translations.
        If tgt_lang is specified, only flush entries for that language.
        Returns the number of rows deleted.
        """
        with self._conn() as conn:
            if tgt_lang:
                cursor = conn.execute(
                    "DELETE FROM translations WHERE tgt_lang = ?", (tgt_lang,)
                )
            else:
                cursor = conn.execute("DELETE FROM translations")
            return cursor.rowcount

    def flush_for_source(self, site_id: str, tgt_lang: str, src_text: str) -> int:
        """Flush a specific cached translation by source text and target language."""
        key = self._make_key(site_id, "en", tgt_lang, src_text)
        with self._conn() as conn:
            cursor = conn.execute("DELETE FROM translations WHERE key = ?", (key,))
            return cursor.rowcount

    def stats(self) -> dict:
        """Return a dictionary of cache statistics."""
        with self._conn() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM translations"
            ).fetchone()[0]
            hits = conn.execute(
                "SELECT SUM(hit_count) FROM translations"
            ).fetchone()[0] or 0
            by_lang = conn.execute(
                "SELECT tgt_lang, COUNT(*) as cnt "
                "FROM translations GROUP BY tgt_lang ORDER BY cnt DESC"
            ).fetchall()
            return {
                "total_entries": total,
                "total_hits": hits,
                "by_language": {row["tgt_lang"]: row["cnt"] for row in by_lang},
            }
