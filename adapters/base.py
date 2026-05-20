from typing import Any, AsyncIterator, Dict, List

from litellm.types.utils import GenericStreamingChunk

from schemas import AgentSpec
from stream_types import StreamRequest


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

    async def stream(
        self,
        runtime: Any,
        spec: AgentSpec,
        request: StreamRequest,
    ) -> AsyncIterator[GenericStreamingChunk]:
        raise NotImplementedError
