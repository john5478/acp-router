# ACP Router for LiteLLM

ACP Router lets OpenAI-compatible clients talk to ACP-based CLI agents through LiteLLM.

The project is currently **Kimi-first**. Internally, the router is adapter-based, so support for additional agents can be added later without changing the overall structure.

## What it does

- accepts OpenAI-style requests through LiteLLM
- routes them to an ACP-compatible CLI agent
- keeps local setup simple
- ships with a bundled LiteLLM config and launcher

## Current scope

Right now, the main supported path is:

- **Kimi via ACP**

The architecture is intentionally generic, but the initial release is focused on getting one path working well before expanding further.

## Installation

### Install this project

This installs the project and its dependencies, including LiteLLM and the Agent Client Protocol SDK.

```bash
pip install -e .
```

### Install LiteLLM manually

If you want LiteLLM separately, make sure to install the proxy extras:

```bash
pip install "litellm[proxy]"
```

## Running the proxy

After installing with `pip install -e .`, use the bundled launcher:

```bash
acp-router
```

The launcher always points to this repository’s `litellm_config.yaml` using an absolute path, so it can be started from any directory.

### Optional overrides

You can still override the port, config path, or pass normal LiteLLM flags:

```bash
PORT=8080 acp-router
LITELLM_CONFIG=/path/to/other.yaml acp-router
acp-router --port 8080 --host 127.0.0.1
```

### Without the script entry point

You can also run the bundled launcher directly:

```bash
python serve.py
```

## Running LiteLLM manually

If you prefer to launch LiteLLM yourself:

```bash
litellm --config /full/path/to/acp_router/litellm_config.yaml
```

Use an **absolute** config path if your shell is not inside the project directory. This avoids module resolution issues and ensures LiteLLM can find the router module correctly.

## Example request

```bash
curl -X POST http://127.0.0.1:4000/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "acp-kimi",
    "messages": [
      {
        "role": "user",
        "content": "Create a simple index.ts file"
      }
    ]
  }'
```

## Project structure

```text
.
├── adapters/
├── client.py
├── registry.py
├── router.py
├── router_handler.py
├── runtime.py
├── schemas.py
├── serve.py
├── utils.py
├── litellm_config.yaml
└── pyproject.toml
```

## Notes

- the project is currently focused on **Kimi via ACP**
- the router architecture is generic even though the first supported backend is Kimi
- additional adapters can be added later without changing the external LiteLLM entrypoint

## License

MIT