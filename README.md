# Celebrity

轻量、可扩展的 **Agent**，用于构建明星图片数据集：模型 API 默认接入 **DeepSeek（deepseek-v4-flash）**（OpenAI 兼容协议），把「爬取 → 清洗 → 模型判断 → 打标签 → 打包」沉淀为一组可被 Agent 调用的工具，同时保留确定性流水线模式。

## 设计原则

- **窄腰核心**：`celebrity/core/agent.py` 是唯一的对话/工具循环；CLI 只是入口适配层，不重复实现第二套引擎。
- **注册表扩展**：模型 Provider、视觉模型、工具全部走注册表；新增 OpenAI 兼容厂商只需在 `config.yaml` 加一段配置，无需改代码。
- **轻便**：默认安装不含 torch/transformers（视觉大模型为可选 extra），核心依赖仅 httpx/PyYAML/rich 等。
- **安全**：密钥只进 `.env`；工具按 `read / write / destructive` 风险分级；破坏性操作需人工确认；路径强制限制在工作目录内；所有输出做密钥脱敏；重试有界。
- **自由化**：任意 OpenAI 兼容 API 可作模型 Provider（默认 DeepSeek）；视觉模型可选 YuNet / OpenAI 兼容视觉 / 本地 Qwen3-VL；Agent 可自由编排工具或走确定性 `pipeline` 命令。

## 快速开始

```bash
pip install -r requirements.txt     # 或 pip install -e .
cp .env.example .env      # 填写 DEEPSEEK_API_KEY（默认模型 API）
python -m celebrity doctor   # 环境自检
python main.py                 # 主页面：横幅 + 功能介绍 + 菜单（↑/↓ 选择，ESC/Ctrl+C 返回上一级）
```

主页面选「进入对话」后直接输入任务即可；输入 `/` 开头可设置运行时配置。进度步骤显示在输入框上方，模型 / Token / 耗时显示在输入框下方：

**直接粘贴密钥**：在对话里粘贴 `DEEPSEEK_API_KEY=sk-xxx`、`XHS_COOKIE=...` 或裸的 `sk-xxx` / Cookie 文本，程序会本地识别并写入 `.env`（只显示脱敏提示，**不会发送给模型**）。

```
/model    切换模型厂商（deepseek / openai / 自定义）、设置 API Key
/apikey   为当前厂商设置 API Key（写入 .env）
/cookie   设置小红书 Cookie（写入 .env）
/vision   切换视觉模型（无 / YuNet / OpenAI 兼容视觉 / 本地 Qwen3-VL）
/status   查看当前配置（密钥脱敏）
/tools    查看可用工具
/reset    开启新会话
/exit     返回主页面
```

按 ESC 或 Ctrl+C 可逐级返回（对话 → 主页面），在主页面再按一次 Ctrl+C 是退出前确认。

一次性任务：

```bash
python -m celebrity agent "构建 宋雨琦 的数据集，500 张" --allow-write
```

确定性流水线（对已有 `raw/` 的任务目录执行步骤 5-8）：

```bash
python -m celebrity pipeline --work datasets/宋雨琦_20260812_000000 --skip-vision
```

## 配置与密钥

- 行为配置：`config.yaml`（模型 Provider、视觉模型、爬取关键词、质量阈值等）。
- 密钥：`.env`（`DEEPSEEK_API_KEY`、`XHS_COOKIE`、`DASHSCOPE_API_KEY` 等），绝不写入 YAML 或日志。
- 换模型：`provider.default` 改成任意已配置的 OpenAI 兼容 Profile；新增厂商只需在 `provider` 下加 `base_url / model / api_key_env`。

## 架构

```
celebrity/
├── cli.py                  # CLI 入口：agent / chat / pipeline / deploy / doctor / banner
├── core/                   # agent 循环、消息角色语法
├── providers/              # 模型 Provider 抽象 + OpenAI 兼容实现（DeepSeek 默认）
├── tools/                  # 工具契约、注册表、内置工具（crawl / pipeline / filesystem）
├── vision/                 # 视觉 Provider：YuNet / OpenAI 兼容视觉 / 本地 Qwen3-VL（可选）
├── pipeline/               # 确定性步骤 5-8：检查/去重/判断/相似去重/建集/打包
├── crawler.py              # Spider_XHS 爬虫集成（懒加载）
├── deploy.py               # 爬虫部署与依赖检查
├── security.py             # 脱敏、路径围栏、风险分级
├── config.py               # YAML + .env 配置加载
└── sessions.py             # 任务持久化与恢复
```

### 扩展一个工具

在 `celebrity/tools/builtin/` 注册一个 `ToolSpec(name, description, parameters, handler, risk, check_fn)`，自动出现在 Agent 的工具 Schema 中；权限在 `dispatch` 阶段强制执行，不依赖 Schema 隐藏。

### 扩展一个模型厂商

在 `config.yaml` 添加：

```yaml
provider:
  myvendor:
    base_url: "https://api.example.com/v1"
    model: "example-chat"
    api_key_env: "MYVENDOR_API_KEY"
```

然后 `provider.default: myvendor` 即可，无需代码。

## 测试

```bash
python -m pytest tests -q
```

测试全部走公共接口（agent loop、工具注册表、Provider 解析、流水线步骤），不触碰真实密钥与用户数据。

> 仅供学习与技术交流，请遵守平台条款，勿商用。
