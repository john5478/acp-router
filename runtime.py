import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from acp import text_block

from client import AgentClient
from schemas import AgentSpec
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

        print(f"kwargs: {kwargs}")
        print(f"messages: {messages}")
        for source in (optional_params, metadata):
            if not isinstance(source, dict):
                continue
            for key in ("cwd", "workspace_path", "project_root", "root_dir", "path"):
                print(f"source: {source}")
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

        print(f"found_paths: {found_paths}")
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

    async def execute_model_cli_command(self, spec: AgentSpec) -> None:
        """Run the optional session model CLI command."""
        if not spec.session_model_cli_command:
            return
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
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except Exception:
            pass

    async def execute_teardown(
        self, spec: AgentSpec, session_id: Optional[str], cwd: str
    ) -> None:
        """Generic teardown executor used by all adapters."""
        if not spec.teardown_cli_command or not session_id:
            return
        try:
            teardown_args = [
                arg.format(session_id=session_id) for arg in spec.teardown_cli_command
            ]
            proc = await asyncio.create_subprocess_exec(
                *teardown_args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                cwd=cwd,
            )
            try:
                await asyncio.wait_for(proc.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                if proc.returncode is None:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                logger.warning("Teardown command timed out")
        except Exception as e:
            logger.warning(f"Teardown failed: {e}")
