<div align="center">

# CelebData Agent
**轻量、可扩展的明星图片数据集构建 Agent，默认接入 DeepSeek。**

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

输入一句任务，Agent 自动完成「爬取 → 去重 → 模型判断 → 打标签 → 打包」全流程，产出可直接用于训练的图片数据集。

- **Agent 自由编排**：爬取、判断、补爬、打标签由模型按需调度，数量不足自动补充。
- **模型即插即用**：默认 DeepSeek，任意 OpenAI 兼容 API 改配置即可切换；逐图判断默认 Qwen3-VL，轻量 YuNet 兜底。
- **全程可见**：流式输出、实时进度条与耗时统计，不像是黑盒。
- **密钥安全**：API Key / Cookie 只进 `.env`，粘贴即自动填充，绝不发送给模型或进入仓库。

## Get Started

```bash
pip install -r requirements.txt
python main.py
```

首次使用：

1. 在对话里粘贴 `DEEPSEEK_API_KEY=sk-...`（或输入 `/model`），自动写入 `.env`；
2. 粘贴小红书 Cookie（`XHS_COOKIE`），爬虫即可使用；
3. 输入任务，例如：`帮我爬取宋雨琦的图片，50 张`。

## 功能要点

- 8 步流水线：部署 → 爬取 → 检查/去重 → 模型判断 → 相似去重 → 打标签 → 打包 → 通知。
- 断点续跑：任务进度落盘（manifest / judgment / reports），中断后继续不重复爬取。
- 逐图判断：默认 Qwen3-VL（可下载或指定本地路径），支持 flash-attention 加速与批量打标签。
- 数量校验：进入打标签前检查是否达到目标，不足自动返回补爬。
- Claude Code 风格终端：流式输出、动画状态行、进度条、快捷命令补全。
- 注册表式扩展：新增工具、OpenAI 兼容厂商、视觉模型均为配置级扩展，无需改核心。

## 常用命令

| 命令 | 说明 |
|------|------|
| `/model` | 切换模型厂商 / 设置 API Key |
| `/vision` | 选择视觉模型（下载 Qwen-VL / 本地路径 / YuNet） |
| `/cookie` | 设置小红书 Cookie |
| `/status` | 查看当前配置（密钥脱敏） |
| `/tools` | 查看可用工具 |
| `/reset` | 开启新会话 |
| `/exit` | 返回主页面 |

对话内可直接粘贴密钥自动填充；`Esc` / `Ctrl+C` 返回上一级，主页面再次按下为退出确认。

## 配置与密钥

- 行为配置：`config.yaml`（模型厂商、视觉模型、爬取关键词、质量阈值）。
- 密钥：`.env`（`DEEPSEEK_API_KEY`、`XHS_COOKIE` 等），支持 `CELEBRITY_ENV_FILE` 重定向。
- 核心模块：`celebrity/core`（Agent 循环）、`providers`（模型）、`tools`（工具）、`vision`（视觉）、`pipeline`（流水线）。

## 测试

```bash
python -m pytest tests -q
```

> 仅供学习与技术交流，请遵守平台条款，勿商用。
