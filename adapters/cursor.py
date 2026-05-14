from .static import StaticAdapter


class CursorAdapter(StaticAdapter):
    def __init__(self) -> None:
        super().__init__(
            agent_id="cursor",
            default_bin="agent",
            default_args=["acp"],
            default_mode_id="agent",
            default_teardown_cli_command=["rm", '-rf', '/Users/john/.cursor/acp-sessions/{session_id}'],
            env_var_prefix="CURSOR"
        )
