# Celebrity

A lightweight, extensible **agent** for building celebrity image datasets. The default model API is **DeepSeek (deepseek-v4-flash)** (OpenAI-compatible), and the crawl → clean → judge → caption → package workflow is exposed as agent tools while a deterministic `pipeline` mode is preserved.

## Design principles

- **Narrow waist**: `celebrity/core/agent.py` is the single conversation/tool loop; the CLI only adapts to it.
- **Registry-driven extensions**: model providers, vision providers, and tools are all registered. Adding an OpenAI-compatible vendor is pure configuration.
- **Lightweight**: no torch/transformers in the default install (local VLM is an optional extra).
- **Secure**: secrets live in `.env` only; tools are risk-graded (`read` / `write` / `destructive`); destructive actions require confirmation; file paths are confined to work directories; outputs are secret-redacted; retries are bounded.
- **Free**: any OpenAI-compatible API can be the model provider (DeepSeek by default); vision can be YuNet, an OpenAI-compatible vision endpoint, or a local Qwen3-VL.

## Quick start

```bash
pip install -r requirements.txt     # or pip install -e .
cp .env.example .env      # fill in DEEPSEEK_API_KEY (default model API)
python -m celebrity doctor   # environment self-check
python main.py                 # main page: banner + intro + menu (↑/↓ to select)
```

Choose "enter chat" from the main page, then just type tasks; `/` opens
slash-command autocomplete. Pipeline progress renders above the input box,
model / token / elapsed metrics below it:

**Paste-to-fill secrets**: paste `DEEPSEEK_API_KEY=sk-xxx`, `XHS_COOKIE=...`,
or a bare `sk-...` / cookie into the chat. It is recognized locally and
written to `.env` (masked confirmation only, never sent to the model).

```
/model    switch provider (deepseek / openai / custom) and set API key
/apikey   set API key for the current provider (writes .env)
/cookie   set the Xiaohongshu cookie (writes .env)
/vision   switch vision provider (none / YuNet / OpenAI-compatible / local Qwen3-VL)
/status   show current config (secrets masked)
/tools    list available tools
/reset    start a new session
/exit     back to main page
```

ESC / Ctrl+C pop one level (chat → main page); at the main page, Ctrl+C asks
for exit confirmation first.

One-shot task:

```bash
python -m celebrity agent "build a 500-image dataset for 宋雨琦" --allow-write
```

Deterministic pipeline over an existing task directory:

```bash
python -m celebrity pipeline --work datasets/some_task --skip-vision
```

## Configuration and secrets

- Behavior: `config.yaml` (providers, vision, crawl keywords, quality thresholds).
- Secrets: `.env` (`DEEPSEEK_API_KEY`, `XHS_COOKIE`, `DASHSCOPE_API_KEY`, ...). Never put secrets in YAML or logs.
- New vendor: add `base_url / model / api_key_env` under `provider.*` and switch `provider.default`.

## Layout

```
celebrity/
├── cli.py                  # agent / chat / pipeline / deploy / doctor / banner
├── core/                   # agent loop, message role grammar
├── providers/              # provider boundary + OpenAI-compatible (DeepSeek default)
├── tools/                  # tool contract, registry, built-ins
├── vision/                 # YuNet / OpenAI-compatible vision / local Qwen3-VL (optional)
├── pipeline/               # deterministic steps 5-8
├── crawler.py  deploy.py   # Spider_XHS integration
├── security.py             # redaction, path fence, risk gates
├── config.py  sessions.py  # config and task persistence
```

## Tests

```bash
python -m pytest tests -q
```

> For learning and technical exchange only. Please comply with platform terms; no commercial use.
