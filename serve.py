"""
Start the LiteLLM proxy with this project's config by default.

Equivalent to `litellm --config litellm_config.yaml`, but resolves the config path
next to this file so you can run from any working directory.

Usage:
  acp-router
  acp-router --port 8080
  python serve.py --host 127.0.0.1

Environment:
  LITELLM_CONFIG  Override default config path when --config is not passed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _has_config_in_argv(argv: list[str]) -> bool:
    for a in argv:
        if a in ("--config", "-c") or a.startswith("--config="):
            return True
    return False


def main() -> None:
    argv = list(sys.argv[1:])
    if not _has_config_in_argv(argv):
        env_path = os.environ.get("LITELLM_CONFIG")
        if env_path:
            cfg = Path(env_path).expanduser().resolve()
        else:
            cfg = Path(__file__).resolve().parent / "litellm_config.yaml"
        if not cfg.is_file():
            raise FileNotFoundError(
                f"LiteLLM config not found: {cfg}. "
                "Pass --config /path/to/litellm_config.yaml or set LITELLM_CONFIG."
            )
        argv = ["--config", str(cfg)] + argv

    from litellm import run_server

    run_server.main(argv, standalone_mode=True)


if __name__ == "__main__":
    main()
