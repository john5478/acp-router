import os

# from adapters import KimiAdapter
from adapters import *
from registry import Registry
from router_handler import RouterHandler


registry = Registry(default_agent=os.getenv("ROUTER_DEFAULT_AGENT", "gemini"))

# registry.register(KimiAdapter())
registry.register(KiroAdapter())
registry.register(GeminiAdapter())
registry.register(OpenCodeAdapter())
registry.register(CursorAdapter())
registry.register(GeminiCliAdapter())

router_handler = RouterHandler(registry)
