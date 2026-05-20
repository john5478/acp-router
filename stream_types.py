from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

ParseEventKind = Literal["noop", "text"]


@dataclass
class StreamRequest:
    """Request object passed to adapter.stream()."""
    model: str
    prompt_text: str
    kwargs: Dict[str, Any]
    messages: List[Dict[str, Any]]


@dataclass
class StreamParseResult:
    """Result from adapter.parse_event()."""
    kind: ParseEventKind
    text: str = ""
    session_id: Optional[str] = None
