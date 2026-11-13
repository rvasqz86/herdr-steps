"""Plain data types shared by readers, pins, and the UIs."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Turn:
    """One piece of a conversation.

    role is "user" (a prompt the person typed), "agent" (visible agent text),
    "tool" (a one-line summary of a tool call), or "line" (a raw scrollback
    line when no structured history is available).
    """

    role: str
    text: str
    timestamp: str | None = None


@dataclass
class PinLine:
    """One rendered line of a pin: "user", "text", "tool", "step" or "blank"."""

    kind: str
    text: str
    step_id: int | None = None


@dataclass
class Pin:
    id: str
    name: str
    folder: str
    source: str
    agent: str | None
    session_id: str | None
    created_at: str
    lines: list[PinLine]
    checked: set[int] = field(default_factory=set)

    @property
    def progress(self) -> tuple[int, int]:
        step_ids = {l.step_id for l in self.lines if l.kind == "step"}
        return (len(self.checked & step_ids), len(step_ids))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "folder": self.folder,
            "source": self.source,
            "agent": self.agent,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "lines": [
                {"kind": l.kind, "text": l.text, "step_id": l.step_id}
                for l in self.lines
            ],
            "checked": sorted(self.checked),
        }

    @classmethod
    def from_dict(cls, d: dict) -> Pin:
        return cls(
            id=d["id"],
            name=d["name"],
            folder=d["folder"],
            source=d["source"],
            agent=d.get("agent"),
            session_id=d.get("session_id"),
            created_at=d["created_at"],
            lines=[
                PinLine(l["kind"], l["text"], l.get("step_id"))
                for l in d.get("lines", [])
            ],
            checked=set(d.get("checked", [])),
        )
