from .static import StaticAdapter


class OpenCodeAdapter(StaticAdapter):
    def __init__(self) -> None:
        super().__init__(
            agent_id="opencode",
            default_bin="opencode",
            default_args=["acp"],
            default_mode_id="default",
            env_var_prefix="OPENCODE"
        )
