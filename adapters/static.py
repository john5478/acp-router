import os
from typing import Any, AsyncIterator, Dict, List, Optional

from litellm.types.utils import GenericStreamingChunk

from schemas import AgentSpec
from stream_types import StreamRequest
from utils import coerce_list
from .base import Adapter


class StaticAdapter(Adapter):
    def __init__(
        self,
        agent_id: str,
        default_bin: str,
        default_args: List[str],
        default_mode_id: Optional[str] = "code",
        default_bootstrap_commands: Optional[List[str]] = None,
        default_teardown_cli_command: Optional[List[str]] = None,
        aliases: Optional[List[str]] = None,
        env_var_prefix: Optional[str] = None,
    ) -> None:
        self.agent_id = agent_id.strip().lower()
        self.default_bin = default_bin
        self.default_args = list(default_args)
        self.default_mode_id = default_mode_id
        self.default_bootstrap_commands = list(default_bootstrap_commands or [])
        self.default_teardown_cli_command = list(default_teardown_cli_command or [])
        self.aliases = [a.strip().lower() for a in (aliases or [])]
        self.env_var_prefix = (env_var_prefix or self.agent_id).upper().replace("-", "_")

    def build_spec(self, model: str, optional_params: Dict[str, Any]) -> AgentSpec:
        bin_value = (
            optional_params.get(f"{self.agent_id}_bin")
            or optional_params.get("agent_bin")
            or os.getenv(f"{self.env_var_prefix}_BIN")
            or self.default_bin
        )

        args_value = (
            optional_params.get(f"{self.agent_id}_args")
            or optional_params.get("agent_args")
            or os.getenv(f"{self.env_var_prefix}_ARGS")
        )
        args = coerce_list(args_value) if args_value else list(self.default_args)

        mode_id = (
            optional_params.get(f"{self.agent_id}_mode_id")
            or optional_params.get("agent_mode_id")
            or os.getenv(f"{self.env_var_prefix}_MODE_ID")
            or self.default_mode_id
        )

        session_model_id = (
            optional_params.get(f"{self.agent_id}_model_id")
            or optional_params.get("agent_model_id")
        )

        if not session_model_id:
            session_model_id = model.strip()

        bootstrap_value = (
            optional_params.get(f"{self.agent_id}_bootstrap_commands")
            or optional_params.get("bootstrap_commands")
        )
        bootstrap_commands = (
            coerce_list(bootstrap_value)
            if bootstrap_value is not None
            else list(self.default_bootstrap_commands)
        )

        teardown_cli_value = (
            optional_params.get(f"{self.agent_id}_teardown_cli_command")
            or optional_params.get("teardown_cli_command")
        )
        teardown_cli_command = (
            coerce_list(teardown_cli_value)
            if teardown_cli_value is not None
            else list(self.default_teardown_cli_command)
        )

        session_model_cli_value = (
            optional_params.get(f"{self.agent_id}_session_model_cli_command")
            or optional_params.get("session_model_cli_command")
        )
        session_model_cli_command = (
            coerce_list(session_model_cli_value)
            if session_model_cli_value is not None
            else None
        )

        return AgentSpec(
            agent_id=self.agent_id,
            bin=str(bin_value),
            args=[str(x) for x in args],
            mode_id=str(mode_id) if mode_id else None,
            session_model_id=str(session_model_id) if session_model_id else None,
            bootstrap_commands=[str(x) for x in bootstrap_commands],
            teardown_cli_command=[str(x) for x in teardown_cli_command] if teardown_cli_command else None,
            session_model_cli_command=[str(x) for x in session_model_cli_command] if session_model_cli_command else None,
        )

    async def stream(
        self,
        runtime: Any,
        spec: AgentSpec,
        request: StreamRequest,
    ) -> AsyncIterator[GenericStreamingChunk]:
        import asyncio
        from acp import spawn_agent_process, text_block
        from client import AgentClient
        from utils import make_text_chunk, make_final_chunk

        optional_params = request.kwargs.get("optional_params", {}) or {}
        protocol_version = int(optional_params.get("protocol_version", 1))
        cwd = runtime.resolve_cwd(request.kwargs, request.messages)
        mcp_servers = optional_params.get("mcp_servers") or []
        permission_mode = str(optional_params.get("permission_mode", "auto_allow"))
        session_id: Optional[str] = None

        client = AgentClient(permission_mode=permission_mode)

        # 1. Model CLI Init
        await runtime.execute_model_cli_command(spec)

        prompt_task: Optional[asyncio.Task] = None
        try:
            # 2. Process Spawning
            async with spawn_agent_process(client, spec.bin, *spec.args) as (conn, _proc):
                # 3. Session Init
                await conn.initialize(protocol_version=protocol_version)
                session = await conn.new_session(
                    cwd=str(cwd),
                    mcp_servers=mcp_servers,
                )
                session_id = session.session_id

                if spec.session_model_id:
                    try:
                        set_model_func = getattr(conn, "set_session_model", getattr(conn, "set_model", None))
                        if callable(set_model_func):
                            await set_model_func(session_id=session_id, model_id=spec.session_model_id)
                    except Exception:
                        pass

                if spec.mode_id:
                    try:
                        set_mode_func = getattr(conn, "set_session_mode", getattr(conn, "set_mode", None))
                        if callable(set_mode_func):
                            await set_mode_func(session_id=session_id, mode_id=spec.mode_id)
                    except Exception:
                        pass

                # 4. Bootstrap
                await runtime.bootstrap_agent_session(
                    conn=conn,
                    session_id=session_id,
                    client=client,
                    spec=spec,
                )

                # 5. Prompt (concurrently)
                prompt_task = asyncio.create_task(
                    conn.prompt(
                        session_id=session_id,
                        prompt=[text_block(request.prompt_text)],
                    )
                )

                # 6. Event Loop
                while True:
                    if prompt_task.done() and client.queue.empty():
                        break

                    try:
                        event = await asyncio.wait_for(client.queue.get(), timeout=0.1)
                    except asyncio.TimeoutError:
                        continue

                    text = event.get("text") or ""
                    if text:
                        yield make_text_chunk(text)

                await prompt_task

        finally:
            # 7. Teardown
            if prompt_task and not prompt_task.done():
                prompt_task.cancel()
            
            # Drain queue if needed (AgentClient is per-request here)
            
            await runtime.execute_teardown(spec, session_id, cwd)

        yield make_final_chunk()
