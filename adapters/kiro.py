from .static import StaticAdapter


class KiroAdapter(StaticAdapter):
    def __init__(self) -> None:
        super().__init__(
            agent_id="kiro",
            default_bin="kiro-cli",
            default_args=["acp", "-a"],
            default_mode_id="kiro_default",
            default_teardown_cli_command=["kiro-cli", "chat", "-d", "{session_id}"],
            aliases=["kiro-cli"],
            env_var_prefix="KIRO",
        )
