"""RECLAIM Edge Gateway — durable store-and-forward buffer (SQLite).

Every received frame is persisted here BEFORE any publish attempt. The publisher
drains batches and acks only on confirmed cloud delivery, so a link drop or a reboot
never loses an in-flight frame. Drop-oldest when capped (stale telemetry has least
value); the drop count is exposed as a health metric.

v1.1 additions (2026-08 review fixes):
  * dead_letter(): frames the cloud rejected as FINAL (stale, contract violation)
    are moved out of the queue into a bounded `dl` table with their reason —
    they stop blocking delivery (fix C1/H3) but remain inspectable, so nothing
    is silently discarded.
  * meta get/set: small key-value store used to persist the framer's sequence
    high-water mark per run_id, so a gateway restart resuming a fixed run_id
    cannot reuse sequence numbers (fix M7).

Author: LJW.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import List, Optional, Tuple

_DL_MAX_ROWS = 2000   # bounded dead-letter retention (newest kept)


class Buffer:
    def __init__(self, path: str, max_frames: int):
        self.max_frames = max_frames
        self._lock = threading.Lock()
        self._drops = 0
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS q ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL)"
        )
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS dl ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL, "
            "reason TEXT NOT NULL, ts REAL NOT NULL)"
        )
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL)"
        )
        self._db.commit()

    def enqueue(self, payload: str, meta_key: Optional[str] = None,
                meta_value: Optional[str] = None) -> None:
        """Persist one frame; optionally update a meta key in the SAME
        transaction (used for the seq high-water mark, so frame and marker can
        never disagree after a crash)."""
        with self._lock:
            self._db.execute("INSERT INTO q(payload) VALUES(?)", (payload,))
            if meta_key is not None:
                self._db.execute(
                    "INSERT INTO meta(k, v) VALUES(?, ?) "
                    "ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                    (meta_key, str(meta_value)),
                )
            self._db.commit()
            self._trim()

    def _trim(self) -> None:
        count = self._db.execute("SELECT COUNT(*) FROM q").fetchone()[0]
        if count > self.max_frames:
            over = count - self.max_frames
            self._db.execute(
                "DELETE FROM q WHERE id IN (SELECT id FROM q ORDER BY id ASC LIMIT ?)",
                (over,),
            )
            self._db.commit()
            self._drops += over

    def dequeue_batch(self, n: int) -> List[Tuple[int, str]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, payload FROM q ORDER BY id ASC LIMIT ?", (n,)
            ).fetchall()
            return list(rows)

    def ack(self, ids: List[int]) -> None:
        if not ids:
            return
        with self._lock:
            self._db.executemany("DELETE FROM q WHERE id=?", [(i,) for i in ids])
            self._db.commit()

    def dead_letter(self, items: List[Tuple[int, str, str]]) -> None:
        """Move finally-rejected frames out of the queue: [(id, payload, reason)].
        They no longer block delivery but stay auditable in the dl table."""
        if not items:
            return
        import time
        now = time.time()
        with self._lock:
            self._db.executemany(
                "INSERT INTO dl(payload, reason, ts) VALUES(?, ?, ?)",
                [(p, r, now) for _, p, r in items],
            )
            self._db.executemany("DELETE FROM q WHERE id=?", [(i,) for i, _, _ in items])
            # bound the dead-letter table (keep newest)
            self._db.execute(
                "DELETE FROM dl WHERE id IN (SELECT id FROM dl ORDER BY id DESC "
                "LIMIT -1 OFFSET ?)", (_DL_MAX_ROWS,),
            )
            self._db.commit()

    def dead_letter_count(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM dl").fetchone()[0]

    def get_meta(self, key: str) -> Optional[str]:
        with self._lock:
            row = self._db.execute("SELECT v FROM meta WHERE k=?", (key,)).fetchone()
            return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO meta(k, v) VALUES(?, ?) "
                "ON CONFLICT(k) DO UPDATE SET v=excluded.v", (key, str(value)))
            self._db.commit()

    def depth(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM q").fetchone()[0]

    @property
    def drops(self) -> int:
        return self._drops

    def close(self) -> None:
        with self._lock:
            self._db.close()
