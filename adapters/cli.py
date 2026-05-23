import asyncio
import json
import os
from typing import Any, AsyncIterator, Dict, List, Optional

from litellm.types.utils import GenericStreamingChunk

from errors import ProviderErrorInfo, raise_provider_error, raise_stream_interrupted
from schemas import AgentSpec
from stream_types import StreamRequest, StreamParseResult
from utils import coerce_list, make_text_chunk, make_final_chunk
from .base import Adapter


class CliAdapter(Adapter):
    """Adapter for wrapping pure CLI tools that output JSON streaming."""

    def __init__(
        self,
        agent_id: str,
        default_bin: str,
        default_args: List[str],
        default_mode_id: Optional[str] = None,
        default_teardown_cli_command: Optional[List[str]] = None,
        aliases: Optional[List[str]] = None,
        env_var_prefix: Optional[str] = None,
    ) -> None:
        self.agent_id = agent_id.strip().lower()
        self.default_bin = default_bin
        self.default_args = list(default_args)
        self.default_mode_id = default_mode_id
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

        teardown_cli_value = (
            optional_params.get(f"{self.agent_id}_teardown_cli_command")
            or optional_params.get("teardown_cli_command")
        )
        teardown_cli_command = (
            coerce_list(teardown_cli_value)
            if teardown_cli_value is not None
            else list(self.default_teardown_cli_command)
        )

        return AgentSpec(
            agent_id=self.agent_id,
            bin=str(bin_value),
            args=[str(x) for x in args],
            mode_id=str(mode_id) if mode_id else None,
            session_model_id=str(session_model_id) if session_model_id else None,
            teardown_cli_command=[str(x) for x in teardown_cli_command] if teardown_cli_command else None
        )

    def parse_event(self, data: Dict[str, Any]) -> StreamParseResult:
        """Parse a single JSON event from CLI output.

        Default behavior:
        - Extract session_id from data["session_id"] if present
        - Return text if type=="message" and role=="assistant"
        """
        session_id = data.get("session_id")

        if data.get("type") == "message" and data.get("role") == "assistant":
            text = data.get("content", "")
            return StreamParseResult(kind="text", text=str(text), session_id=session_id)

        return StreamParseResult(kind="noop", text="", session_id=session_id)

    async def stream(
        self,
        runtime: Any,
        spec: AgentSpec,
        request: StreamRequest,
    ) -> AsyncIterator[GenericStreamingChunk]:
        optional_params = request.kwargs.get("optional_params", {}) or {}
        cwd = runtime.resolve_cwd(request.kwargs, request.messages)

        context = {
            "agent_id": spec.agent_id,
            "mode_id": spec.mode_id or "",
            "session_model_id": spec.session_model_id or "",
            "model": request.model,
            "cwd": cwd,
            "prompt_text": request.prompt_text,
            "messages_json": json.dumps(request.messages, ensure_ascii=False),
        }
        context.update(optional_params)

        try:
            formatted_args = [arg.format_map(context) for arg in spec.args]
        except KeyError as e:
            raise_provider_error(
                ProviderErrorInfo(
                    message=f"Missing required parameter for CLI arguments: {e}",
                    status_code=400,
                ),
                model=request.model,
            )
        except Exception as e:
            raise_provider_error(
                ProviderErrorInfo(
                    message=f"Error formatting CLI arguments: {e}",
                    status_code=400,
                ),
                model=request.model,
            )

        proc = await asyncio.create_subprocess_exec(
            spec.bin,
            *formatted_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )

        session_id: Optional[str] = None
        has_yielded = False

        try:
            async for line in proc.stdout:
                line_str = line.decode().strip()
                if not line_str:
                    continue

                try:
                    data = json.loads(line_str)
                    result = self.parse_event(data)

                    if result.session_id:
                        session_id = result.session_id

                    if result.kind == "text" and result.text:
                        has_yielded = True
                        yield GenericStreamingChunk(**make_text_chunk(result.text))
                except json.JSONDecodeError:
                    continue

            exit_code = await proc.wait()
            if exit_code != 0:
                stderr_data = await proc.stderr.read()
                stderr_text = stderr_data.decode().strip()
                error_msg = f"CLI {spec.bin} failed with exit code {exit_code}"
                if stderr_text:
                    error_msg += f": {stderr_text}"

                if has_yielded:
                    raise_stream_interrupted(error_msg, model=request.model)
                else:
                    raise_provider_error(
                        ProviderErrorInfo(message=error_msg, status_code=500),
                        model=request.model,
                    )

            yield GenericStreamingChunk(**make_final_chunk())

        finally:
            if proc.returncode is None:
                try:
                    proc.kill()
                    await proc.wait()
                except ProcessLookupError:
                    pass
                except Exception:
                    pass

            await runtime.execute_teardown(spec, session_id, cwd)
