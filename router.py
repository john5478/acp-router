import os

# from adapters import KimiAdapter
from adapters import GeminiAdapter, OpenCodeAdapter
from registry import Registry
from router_handler import RouterHandler


registry = Registry(default_agent=os.getenv("ROUTER_DEFAULT_AGENT", "gemini"))

# registry.register(KimiAdapter())
registry.register(GeminiAdapter())
registry.register(OpenCodeAdapter())

router_handler = RouterHandler(registry)
