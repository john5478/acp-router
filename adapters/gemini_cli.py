from .cli import CliAdapter


class GeminiCliAdapter(CliAdapter):
    def __init__(self) -> None:
        super().__init__(
            agent_id="gemini_cli",
            default_bin="gemini",
            default_args=[
                "-y", "-m", "{session_model_id}",
                "-o", "stream-json", "-p", "{prompt_text}"
            ],
            default_mode_id="yolo",
            default_teardown_cli_command=[
                "gemini", "--delete-session", "{session_id}"
            ],
            aliases=["gemini-cli"],
            env_var_prefix="GEMINI_CLI",
        )
