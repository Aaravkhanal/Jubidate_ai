from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import re
from threading import RLock


SECRET_PATTERNS = (
    re.compile(r"\b(sk-[A-Za-z0-9_-]{8,})\b"),
    re.compile(r"\b([A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,})\b"),
    re.compile(r"(?i)\b(api[_-]?key|token|secret)\s*[:=]\s*[^\s,;]+"),
)


@dataclass(frozen=True)
class RuntimeDiaryEntry:
    created_at: str
    source: str
    event: str
    detail: str
    session_id: str | None = None

    def public_dict(self) -> dict:
        return asdict(self)


class RuntimeDiary:
    def __init__(self, limit: int = 160) -> None:
        self._entries: deque[RuntimeDiaryEntry] = deque(maxlen=limit)
        self._lock = RLock()

    def record(
        self,
        source: str,
        event: str,
        detail: str = "",
        *,
        session_id: str | None = None,
    ) -> None:
        entry = RuntimeDiaryEntry(
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            source=self._clean(source, 40) or "system",
            event=self._clean(event, 80) or "event",
            detail=self._scrub(detail, 500),
            session_id=self._clean(session_id or "", 80) or None,
        )
        with self._lock:
            self._entries.append(entry)

    def recent(self, *, limit: int = 30, session_id: str | None = None) -> list[dict]:
        with self._lock:
            entries = list(self._entries)
        if session_id:
            entries = [entry for entry in entries if entry.session_id in {None, session_id}]
        return [entry.public_dict() for entry in entries[-limit:]]

    def format_for_prompt(self, *, limit: int = 24, session_id: str | None = None) -> str:
        entries = self.recent(limit=limit, session_id=session_id)
        if not entries:
            return "No runtime diary entries have been captured yet."
        return "\n".join(
            f"- {entry['created_at']} | {entry['source']} | {entry['event']}: {entry['detail'] or 'No detail.'}"
            for entry in entries
        )

    def _scrub(self, value: str, limit: int) -> str:
        text = self._clean(value, limit)
        for pattern in SECRET_PATTERNS:
            text = pattern.sub("[redacted]", text)
        return text

    def _clean(self, value: str, limit: int) -> str:
        text = " ".join(str(value or "").strip().split())
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + "..."


runtime_diary = RuntimeDiary()
