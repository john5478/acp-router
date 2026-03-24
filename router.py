import os

from adapters import KimiAdapter
from registry import Registry
from router_handler import RouterHandler


registry = Registry(default_agent=os.getenv("ROUTER_DEFAULT_AGENT", "kimi"))

registry.register(KimiAdapter())

router_handler = RouterHandler(registry)
