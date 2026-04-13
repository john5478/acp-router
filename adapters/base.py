from typing import Any, Dict, List

from schemas import AgentSpec


class Adapter:
    agent_id: str = ""
    aliases: List[str] = []

    def matches(self, value: str) -> bool:
        normalized = value.strip().lower()
        if not normalized:
            return False
        return normalized == self.agent_id or normalized in self.aliases

    def build_spec(self, model: str, optional_params: Dict[str, Any]) -> AgentSpec:
        raise NotImplementedError
