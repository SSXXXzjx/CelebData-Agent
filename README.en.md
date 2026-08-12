<div align="center">

# CelebData Agent
**A lightweight, extensible agent for building celebrity image datasets, powered by DeepSeek by default.**

[![Python][python-shield]][python-url]
[![Platform][platform-shield]][platform-url]
[![License][license-shield]][license-url]
<br>
[![Release][release-shield]][release-url]
[![Downloads][downloads-shield]][downloads-url]

[python-shield]: https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white
[python-url]: https://www.python.org/
[platform-shield]: https://img.shields.io/badge/Win%20%7C%20Linux%20%7C%20macOS-lightgrey
[platform-url]: https://github.com/SSXXXzjx/CelebData-Agent
[license-shield]: https://img.shields.io/badge/License-MIT-orange
[license-url]: https://github.com/SSXXXzjx/CelebData-Agent/blob/main/LICENSE
[release-shield]: https://img.shields.io/github/v/release/SSXXXzjx/CelebData-Agent?style=flat
[release-url]: https://github.com/SSXXXzjx/CelebData-Agent/releases
[downloads-shield]: https://img.shields.io/github/downloads/SSXXXzjx/CelebData-Agent/total?style=flat
[downloads-url]: https://github.com/SSXXXzjx/CelebData-Agent/releases

</div>

Describe a task in one sentence and the agent runs the full pipeline — crawl, dedup, model judging, captioning, packaging — into a training-ready image dataset.

- **Agent-driven orchestration**: crawl, judge, backfill, and caption are scheduled by the model; missing counts are topped up automatically.
- **Plug-and-play models**: DeepSeek by default; any OpenAI-compatible API works via config. Image judging uses Qwen3-VL with a lightweight YuNet fallback.
- **Fully visible**: streaming output, live progress bars, and elapsed-time stats — never a black box.
- **Secret-safe**: API keys / cookies live only in `.env`, auto-filled on paste, never sent to the model or committed.

## Get Started

```bash
pip install -r requirements.txt
python main.py
```

First run:

1. Paste `DEEPSEEK_API_KEY=sk-...` in the chat (or type `/model`) to write `.env`.
2. Paste the Xiaohongshu cookie (`XHS_COOKIE`) to enable crawling.
3. Type a task, e.g. `build a 50-image dataset for 宋雨琦`.

## Features

- 8-step pipeline: deploy → crawl → check/dedup → model judging → similarity dedup → captioning → packaging → notify.
- Resumable: task state is persisted (manifest / judgment / reports); resumes never re-crawl.
- Image judging: Qwen3-VL by default (download or local path), flash-attention acceleration and batch captioning.
- Count validation: checks the target before captioning and auto-backfills by crawling more.
- Claude Code style terminal: streaming output, animated status, progress bars, slash-command completion.
- Registry-driven extensions: new tools, OpenAI-compatible vendors, and vision models are config-level.

## Commands

| Command | Description |
|---------|-------------|
| `/model` | Switch provider / set API key |
| `/vision` | Choose vision model (download Qwen-VL / local path / YuNet) |
| `/cookie` | Set the Xiaohongshu cookie |
| `/status` | Show current config (secrets masked) |
| `/tools` | List available tools |
| `/reset` | Start a new session |
| `/exit` | Back to main page |

Paste secrets directly in chat to auto-fill; `Esc` / `Ctrl+C` pops one level, and at the main page confirms exit.

## Configuration & Secrets

- Behavior: `config.yaml` (providers, vision, crawl keywords, quality thresholds).
- Secrets: `.env` (`DEEPSEEK_API_KEY`, `XHS_COOKIE`, ...); `CELEBRITY_ENV_FILE` redirects the env file.
- Core modules: `celebrity/core` (agent loop), `providers` (models), `tools`, `vision`, `pipeline`.

## Tests

```bash
python -m pytest tests -q
```

> For learning and technical exchange only. Please comply with platform terms; no commercial use.
