from .static import StaticAdapter


class GeminiAdapter(StaticAdapter):
    def __init__(self) -> None:
        super().__init__(
            agent_id="gemini",
            default_bin="gemini",
            default_args=["--acp"],
            default_mode_id="default",
            default_bootstrap_commands=["/yolo"],
            aliases=["gemini-cli"],
            env_var_prefix="GEMINI",
        )
