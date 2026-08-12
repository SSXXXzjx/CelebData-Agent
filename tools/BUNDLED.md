# 内置 tui-banner（Bundled）

本目录内置 [coolbeevip/tui-banner](https://github.com/coolbeevip/tui-banner) v0.2.2 的多平台预编译二进制，开箱即用、无需联网下载：

| 平台 | 路径 |
|------|------|
| Windows x86_64 | tools/win-x86_64/tui-banner.exe |
| Linux x86_64 | tools/linux-x86_64/tui-banner |
| Linux aarch64 | tools/linux-aarch64/tui-banner |
| macOS arm64 | tools/darwin-aarch64/tui-banner |

banner.py 会按当前平台自动选择对应二进制；若缺失（如 macOS x86_64 无官方发布包）则回退到内置 ASCII 横幅。