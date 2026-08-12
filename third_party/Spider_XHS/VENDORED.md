# 内置 Spider_XHS（Vendored）

本目录是 [cv-cat/Spider_XHS](https://github.com/cv-cat/Spider_XHS) 的源码副本，随 Celebrity 一起分发，保证离线可用、开箱即跑。

- 来源仓库：https://github.com/cv-cat/Spider_XHS
- 拷贝日期：2026-08-08（本地副本）
- 包含：`apis/`、`spider/`、`xhs_utils/`、`requirements.txt`、`package*.json`、`.env.example`、`Dockerfile`、`README.md`
- 未包含（首次运行时自动安装/生成）：
  - `datas/`、`models/`、`node_modules/`、`.npm-cache/`、`__pycache__/`
  - 运行日志、自定义爬虫脚本、`.env`（含用户 Cookie，禁止分发）

部署时若 `config.json` 的 `spider_xhs.dir` 未设置或不存在，Celebrity 会自动使用本内置目录；需要升级时删除本目录并改配置为仓库地址即可重新拉取。