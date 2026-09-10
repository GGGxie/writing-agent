from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from writing_agent.config import get_settings
from writing_agent.models import SignalRecord


def _key(signal: SignalRecord) -> str:
    return hashlib.sha256(f"{signal.source_type}\0{signal.source_id}".encode()).hexdigest()


def _slug(value: str) -> str:
    result = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", value).strip("-").lower()
    return result[:48] or "signal"


def _render(signal: SignalRecord) -> str:
    tags = json.dumps(signal.tags, ensure_ascii=False)
    lines = [
        "---",
        'status: "idea"',
        f"discovered_at: {json.dumps(signal.discovered_at.isoformat())}",
    ]
    if signal.published_at:
        lines.append(f"published_at: {json.dumps(signal.published_at.isoformat())}")
    lines.extend(
        [
            f"source_url: {json.dumps(signal.url, ensure_ascii=False)}",
            f"source_type: {json.dumps(signal.source_type)}",
            f"source_id: {json.dumps(signal.source_id)}",
            f"source_name: {json.dumps(signal.source_name, ensure_ascii=False)}",
            f"source_author: {json.dumps(signal.author or '', ensure_ascii=False)}",
            f"source_tier: {json.dumps(signal.source_tier.value)}",
            f"tags: {tags}",
            'collector: "writing-agent"',
            "---",
            "",
            f"# {signal.title.replace(chr(10), ' ').strip()}",
            "",
            "## 原始说法",
            "",
            signal.content[:20_000].strip() or "（没有提取到正文，请打开来源链接核对。）",
            "",
            "## 为什么可能值得关注",
            "",
            "待人工判断。采集结果只是线索，不代表内容已经核实。",
            "",
            "## 待确认",
            "",
            "- [ ] 是否有官方公告、源码、论文或其他原始材料",
            "- [ ] 时间、版本、价格和适用范围",
            "- [ ] 是否只是旧信息再次传播",
            "- [ ] 是否有相互独立的补充来源",
            "",
        ]
    )
    return "\n".join(lines)


class CollectorStore:
    def __init__(self, database_path: Path | None = None, max_seen_items: int = 50_000):
        settings = get_settings()
        self.database_path = database_path or settings.collector_database_path
        self.signal_dir = settings.workspace_dir / "signals"
        self.max_seen_items = max_seen_items
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.signal_dir.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS signals (
                signal_key TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                discovered_at TEXT NOT NULL,
                markdown_path TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_signals_discovered
                ON signals(discovered_at DESC);
            CREATE TABLE IF NOT EXISTS feed_cursors (
                feed_id TEXT PRIMARY KEY,
                etag TEXT,
                last_modified TEXT,
                last_checked_at TEXT
            );
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def save_signal(self, signal: SignalRecord) -> bool:
        signal_key = _key(signal)
        if self.connection.execute(
            "SELECT 1 FROM signals WHERE signal_key = ?", (signal_key,)
        ).fetchone():
            return False
        timestamp = (signal.published_at or signal.discovered_at).astimezone(timezone.utc)
        filename = f"{timestamp:%Y%m%dT%H%M%SZ}-{_slug(signal.source_name)}-{signal_key[:10]}.md"
        path = self.signal_dir / filename
        temporary = path.with_suffix(f".md.{os.getpid()}.tmp")
        temporary.write_text(_render(signal), encoding="utf-8")
        temporary.replace(path)
        payload = json.dumps(signal.model_dump(), ensure_ascii=False, default=str)
        with self.connection:
            self.connection.execute(
                "INSERT INTO signals VALUES (?, ?, ?, ?, ?, ?)",
                (
                    signal_key,
                    signal.source_type,
                    signal.source_id,
                    payload,
                    signal.discovered_at.isoformat(),
                    str(path),
                ),
            )
            excess = self.connection.execute(
                "SELECT COUNT(*) - ? FROM signals", (self.max_seen_items,)
            ).fetchone()[0]
            if excess > 0:
                self.connection.execute(
                    "DELETE FROM signals WHERE signal_key IN "
                    "(SELECT signal_key FROM signals ORDER BY discovered_at ASC LIMIT ?)",
                    (excess,),
                )
        return True

    def list_signals(self, limit: int = 50) -> list[SignalRecord]:
        rows = self.connection.execute(
            "SELECT payload_json FROM signals ORDER BY discovered_at DESC LIMIT ?",
            (max(1, min(limit, 500)),),
        ).fetchall()
        return [SignalRecord(**json.loads(row["payload_json"])) for row in rows]

    def get_feed_cursor(self, feed_id: str) -> dict[str, str]:
        row = self.connection.execute(
            "SELECT etag, last_modified, last_checked_at FROM feed_cursors WHERE feed_id = ?",
            (feed_id,),
        ).fetchone()
        return dict(row) if row else {}

    def set_feed_cursor(
        self,
        feed_id: str,
        *,
        etag: str | None,
        last_modified: str | None,
    ) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO feed_cursors(feed_id, etag, last_modified, last_checked_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(feed_id) DO UPDATE SET
                    etag=excluded.etag,
                    last_modified=excluded.last_modified,
                    last_checked_at=excluded.last_checked_at
                """,
                (
                    feed_id,
                    etag,
                    last_modified,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
