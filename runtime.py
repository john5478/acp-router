import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from acp import spawn_agent_process, text_block
from litellm.types.utils import GenericStreamingChunk

from client import AgentClient
from errors import raise_provider_error, raise_stream_interrupted, ProviderErrorInfo
from schemas import AgentSpec
from stream_types import StreamRequest
from utils import (
    common_existing_parent,
    content_blocks_to_text,
    extract_existing_paths_from_text,
)

logger = logging.getLogger(__name__)


class Runtime:
    def resolve_cwd(
        self,
        kwargs: Dict[str, Any],
        messages: List[Dict[str, Any]],
    ) -> str:
        """Match reference handler: explicit cwd metadata first, then infer from paths in messages."""
        optional_params = kwargs.get("optional_params", {}) or {}
        metadata = kwargs.get("metadata") or optional_params.get("metadata") or {}

        for source in (optional_params, metadata):
            if not isinstance(source, dict):
                continue
            for key in ("cwd", "workspace_path", "project_root", "root_dir", "path"):
                value = source.get(key)
                if isinstance(value, str) and value.strip():
                    p = Path(value).expanduser()
                    if p.exists():
                        return str(p.resolve())

        text_blobs: List[str] = []
        for msg in messages or []:
            content = content_blocks_to_text(msg.get("content", ""))
            if content:
                text_blobs.append(content)

        found_paths: List[Path] = []
        for blob in text_blobs:
            found_paths.extend(extract_existing_paths_from_text(blob))

        inferred = common_existing_parent(found_paths)
        if inferred is not None:
            return str(inferred)

        return os.getcwd()

    async def bootstrap_agent_session(
        self,
        conn: Any,
        session_id: str,
        client: AgentClient,
        spec: AgentSpec,
    ) -> None:
        if not spec.bootstrap_commands:
            return

        client.suppress_stream = True
        try:
            for cmd in spec.bootstrap_commands:
                cmd = str(cmd).strip()
                if not cmd:
                    continue
                await conn.prompt(session_id=session_id, prompt=[text_block(cmd)])
        finally:
            client.suppress_stream = False

    async def run_acp_stream(
        self,
        *,
        spec: AgentSpec,
        request: StreamRequest,
    ) -> AsyncIterator[GenericStreamingChunk]:
        optional_params = request.kwargs.get("optional_params", {}) or {}
        protocol_version = int(optional_params.get("protocol_version", 1))
        cwd = self.resolve_cwd(request.kwargs, request.messages)
        mcp_servers = optional_params.get("mcp_servers") or []
        permission_mode = str(optional_params.get("permission_mode", "auto_allow"))
        session_id: Optional[str] = None

        client = AgentClient(permission_mode=permission_mode)

        model_set_by_cli = False
        if spec.session_model_cli_command:
            try:
                cmd_args = [
                    arg.replace("{model_id}", spec.session_model_id or "")
                    for arg in spec.session_model_cli_command
                ]
                proc = await asyncio.create_subprocess_exec(
                    *cmd_args,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                    model_set_by_cli = True
                except asyncio.TimeoutError:
                    if proc.returncode is None:
                        try:
                            proc.kill()
                        except Exception:
                            pass
            except Exception:
                pass

        async with spawn_agent_process(client, spec.bin, *spec.args) as (conn, _proc):
            await conn.initialize(protocol_version=protocol_version)
            session = await conn.new_session(
                cwd=str(cwd),
                mcp_servers=mcp_servers,
            )
            session_id = session.session_id

            if spec.session_model_id and not model_set_by_cli:
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

            await self.bootstrap_agent_session(
                conn=conn,
                session_id=session_id,
                client=client,
                spec=spec,
            )

            prompt_task = asyncio.create_task(
                conn.prompt(
                    session_id=session.session_id,
                    prompt=[text_block(request.prompt_text)],
                )
            )

            try:
                while True:
                    if prompt_task.done() and client.queue.empty():
                        break

                    try:
                        event = await asyncio.wait_for(client.queue.get(), timeout=0.1)
                    except asyncio.TimeoutError:
                        continue

                    text = event.get("text") or ""
                    if not text:
                        continue

                    yield {
                        "finish_reason": None,
                        "index": 0,
                        "is_finished": False,
                        "text": text,
                        "tool_use": None,
                        "usage": None,
                    }

                await prompt_task

            finally:
                if not prompt_task.done():
                    prompt_task.cancel()

        # Execute teardown CLI command if specified
        if spec.teardown_cli_command and session_id:
            try:
                teardown_args = [
                    arg.format(session_id=session_id)
                    for arg in spec.teardown_cli_command
                ]
                teardown_proc = await asyncio.create_subprocess_exec(
                    *teardown_args,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                # Wait briefly for it to complete, but don't block forever
                try:
                    await asyncio.wait_for(teardown_proc.wait(), timeout=30.0)
                except asyncio.TimeoutError:
                    if teardown_proc.returncode is None:
                        try:
                            teardown_proc.kill()
                        except Exception:
                            pass
                    logger.warning("Teardown command timed out")
            except Exception:
                logger.warning(f"Teardown failed: {e}")

        yield {
            "finish_reason": "stop",
            "index": 0,
            "is_finished": True,
            "text": "",
            "tool_use": None,
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        }

    async def run_cli_stream(
        self,
        *,
        spec: AgentSpec,
        request: StreamRequest,
        adapter: Any,
    ) -> AsyncIterator[GenericStreamingChunk]:
        """Execute a pure CLI tool and stream JSON output."""
        optional_params = request.kwargs.get("optional_params", {}) or {}
        cwd = self.resolve_cwd(request.kwargs, request.messages)
        session_id: Optional[str] = None
        has_emitted_text = False

        # Build template context
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

        # Format args with template context
        try:
            formatted_args = [arg.format_map(context) for arg in spec.args]
        except KeyError as e:
            raise_provider_error(
                ProviderErrorInfo(
                    message=f"Template variable not found: {e}",
                    status_code=400,
                    code="template_error",
                ),
                model=request.model,
            )

        # Spawn subprocess
        proc = await asyncio.create_subprocess_exec(
            spec.bin,
            *formatted_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            cwd=cwd,
        )

        try:
            # Read stdout line by line
            # assert proc.stdout is not None
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                print(f"line: {line}")

                line_str = line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue

                # Try to parse JSON
                try:
                    data = json.loads(line_str)
                    print(f"jsondata: {data}")
                except json.JSONDecodeError:
                    print(f"Failed to parse JSON: {line_str}")
                    logger.debug(f"Failed to parse JSON: {line_str}")
                    continue

                # Ensure data is dict
                if not isinstance(data, dict):
                    logger.debug(f"Event is not a dict: {type(data)}")
                    continue

                # Parse event with adapter
                result = adapter.parse_event(data)

                # Update session_id if provided
                if result.session_id:
                    session_id = result.session_id

                # Yield text if present
                if result.kind == "text" and result.text:
                    has_emitted_text = True
                    yield {
                        "finish_reason": None,
                        "index": 0,
                        "is_finished": False,
                        "text": result.text,
                        "tool_use": None,
                        "usage": None,
                    }

            # Wait for process to complete
            exit_code = await proc.wait()

        finally:
            # Execute teardown if applicable
            if spec.teardown_cli_command and session_id:
                try:
                    teardown_args = [
                        arg.format(session_id=session_id)
                        for arg in spec.teardown_cli_command
                    ]
                    teardown_proc = await asyncio.create_subprocess_exec(
                        *teardown_args,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    try:
                        await asyncio.wait_for(teardown_proc.wait(), timeout=30.0)
                    except asyncio.TimeoutError:
                        if teardown_proc.returncode is None:
                            try:
                                teardown_proc.kill()
                            except Exception:
                                pass
                        logger.warning("Teardown command timed out")
                except Exception as e:
                    logger.warning(f"Teardown failed: {e}")

        # Handle exit code
        if exit_code == 0:
            yield {
                "finish_reason": "stop",
                "index": 0,
                "is_finished": True,
                "text": "",
                "tool_use": None,
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
            }
        elif not has_emitted_text:
            # Pre-stream failure
            raise_provider_error(
                ProviderErrorInfo(
                    message=f"CLI exited with code {exit_code}",
                    status_code=500,
                    code="cli_error",
                ),
                model=request.model,
            )
        else:
            # Mid-stream failure
            raise_provider_error(
                ProviderErrorInfo(
                    message=f"CLI exited with code {exit_code} after emitting text",
                    status_code=500,
                    code="cli_error",
                ),
                model=request.model,
            )
