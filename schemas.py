from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AgentSpec:
    agent_id: str
    bin: str
    args: List[str]
    mode_id: Optional[str] = "code"
    session_model_id: Optional[str] = None
    bootstrap_commands: List[str] = field(default_factory=list)
    teardown_cli_command: Optional[List[str]] = None
    session_model_cli_command: Optional[List[str]] = None
