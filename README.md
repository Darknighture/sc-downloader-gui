# SC Downloader GUI

**简体中文** | [English](README_EN.md)

一个用于从 Supercell 官方服务器直接拉取《皇室战争》《荒野乱斗》游戏资源的图形化下载器：
通过游戏登录服务器（或 CDN）取到资源清单 `fingerprint.json`，再按需多线程下载，并可选地自动解压压缩资源。

> 本项目与 Supercell 无任何关联，未经 Supercell 认可、赞助或特别批准。详见 Supercell Fan Content Policy。

---

## 功能特性

- **三种资源获取方式**：最新补丁（走登录服务器握手）、指定 masterhash（直取 CDN）、本地 fingerprint 文件
- **多线程下载**：线程数 1–10 可调，服务端 502/503/504 自动重试（指数退避，最多 3 次）
- **可中断、可重入**：Stop 会立刻停住当前下载；再次 Start 只补下缺失文件
- **断点友好**：已存在的文件自动跳过；若目标补丁目录已存在会询问是否覆盖
- **按类型筛选**：下载前可勾选只下载 `.csv` / `.sc` / `.png` 等指定后缀
- **可选自动解压**：`.sc`、`.csv`、`.toml` 支持 Zstd、LZHAM、LZMA、SC v5 与旧版 SC 格式
- **原子写入**：文件先写 `.part` 再改名，中断不会留下半截文件
- **暗色主题**：基于 QDarkStyle 的固定尺寸窗口，界面简洁

## 支持的游戏与服务器

| 游戏 | 登录服务器（TCP 9339） | 资源 CDN |
| --- | --- | --- |
| Clash Royale（国际服） | `game.clashroyaleapp.com` | `http://game-assets.clashroyaleapp.com` |
| Clash Royale CN（皇室战争国服） | `game.production.clashroyale.cn` | `https://cr-cdn.supercellgame.cn` |
| Brawl Stars（荒野乱斗国际服） | `game.brawlstarsgame.com` | `https://game-assets.brawlstarsgame.com` |
| Brawl Stars CN（荒野乱斗国服） | `game.brawlstars.cn` | `https://game-assets.tencent-cloud.com` |

服务器列表来自 `config.json` 的 `servers` 字段，可自行增删。

## 环境要求

- Python 3.8 – 3.14（3.13 与 3.14 已实测）
- 可访问对应游戏服务器与 CDN 的网络环境

## 安装

```bash
git clone https://github.com/Darknighture/sc-downloader-gui.git
cd sc-downloader-gui

python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS / Linux: source .venv/bin/activate

pip install -r requirements.txt
python main.py
```

## 快速开始

1. 运行 `python main.py`
2. 在 **Game** 下拉框选择游戏服务器
3. 在 **Download from** 选择下载方式（见下节）
4. 点击 **Start Download**，在弹出的对话框中选择「全部文件」或「仅指定类型」
5. 下载进度显示在状态栏，完成后资源位于 `输出目录/<masterhash>/` 下
6. 中途可点 **Stop** 中断；再次点击 **Start Download** 会跳过已下载的文件，只补齐缺失部分

## 下载方式

| 方式 | 说明 | 适用 |
| --- | --- | --- |
| **Latest Patch** | 直接向游戏登录服务器发起握手，从 Loginfailed 报文里取出 CDN 地址与最新 fingerprint | Brawl Stars 国际服 / 国服 |
| **Masterhash** | 跳过握手，用你输入的 40 位十六进制 masterhash 直接从 CDN 取 `fingerprint.json` | 全部服务器 |
| **Fingerprint file** | 使用本地已有的 `fingerprint.json`，按其中的 `sha` 从 CDN 拉取资源 | 全部服务器 |

> 皇室战争（国际服与国服）的登录握手目前被服务端冻结（返回错误码 16），因此该游戏的
> **Latest Patch 选项不会显示**，请使用 Masterhash 或 Fingerprint file。

## 界面说明

- **Download 页**：选择游戏与下载方式；Masterhash 输入框会实时校验格式（40 位小写十六进制）；
  「Decompress compressed assets」复选框控制是否解压 `.sc` / `.csv` / `.toml`（**默认关闭**）。
- **Settings 页**：设置输出目录与下载线程数（1–10），点 **Save settings** 写回 `config.json`。
- **状态栏**：显示当前阶段、实时进度（含失败计数）与耗时。

## 配置文件

`config.json`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `workers_count` | int | 下载线程数，界面限制 1–10 |
| `output_path` | string | 输出根目录；相对路径相对**程序所在目录**解析（不是当前工作目录） |
| `major` / `build` / `minor` | int | 客户端版本号，用于皇室战争握手（见「已知限制」） |
| `servers` | object | `显示名 -> 登录服务器域名` 映射 |

## 输出结构

```
<output_path>/
└── <masterhash 或 fingerprint 的 sha>/
    ├── fingerprint.json
    └── ...（与 CDN 上一致的资源目录结构）
```

## 工作原理

1. 向 `<登录服务器>:9339` 发送 ClientHello（消息 ID `10100`），读取 Loginfailed 回复。
2. 根据错误码分支：`7` = 正常（含 CDN 地址与 fingerprint）、`8`/`16` = 客户端版本不符、`9` = 版本过高、`10` = 服务器维护。
3. 解析 fingerprint 中的文件列表，做扩展名过滤与已存在文件去重，投递到下载队列。
4. 多个 `DownloadWorker` 线程从队列取任务，先把内容写进 `<目标文件>.part`，成功后再改名为正式文件；
   若开启解压，`.sc` / `.csv` / `.toml` 会先经 `lib/compression.py` 解码
   （识别 SC v5 头部 + Zstd/LZHAM，其余交给 `sc_compression`）。

> 协议细节：皇室战争使用 VInt 编码，荒野乱斗使用 UInt32 编码，两者在解析 Loginfailed 时走不同分支。

## 常见问题

**Q：报 `Could not connect to xxx:9339`？**
网络不可达或端口被拦截。检查代理 / 防火墙，必要时确认该服务器是否可以从当前网络直连。

**Q：报 `Server requires a different version`？**
荒野乱斗服务端要求更高的客户端版本，需调整 `config.json` 中的 `major` / `build` / `minor`。

**Q：进度条停在 100% 以下就结束了？**
部分文件下载失败，状态栏会显示 `N failed`，控制台同时打印 `[x] Failed to download ...`。
除 5xx 会重试 3 次外，其余错误不重试，重新点击 Start Download 即可补下缺失文件。

**Q：解压后文件还是压缩态 / 没有解压？**
先确认勾选了「Decompress compressed assets」。若仍如此，说明解压失败（控制台会打印
`[x] Failed to decompress file ...`），此时程序会**原样保存下载的压缩数据**而不是写出坏文件。
LZHAM 资源在 Windows 上即使没装 `pylzham` 也能解压，详见上文「LZHAM 支持」。

**Q：提示 "This patch was already downloaded"？**
目标目录已存在，选择 Yes 覆盖全部文件，或选择 No 只补齐缺失文件。

**Q：Stop 之后还能继续吗？**
能。Stop 只终止本次运行，已下载的文件会保留；再点 Start Download 会从缺口继续。

## 已知限制

- 皇室战争的 **Latest Patch 已不可用**（服务端握手冻结），只能用 Masterhash / Fingerprint file。
- 「自动探测客户端版本（bruteforce）」在当前界面下走不到，实际不生效；`config.json` 中的
  `major` / `build` / `minor` 对现有下载流程没有影响。
- 解压默认**关闭**，需要在界面上手动勾选。
- 不支持真正意义上的暂停 / 续传：**Stop** 会终止当前任务，续传靠“重跑时跳过已存在文件”实现。
- 失败的文件不会自动重试（5xx 除外），也没有失败清单文件，需要看控制台输出。

## 依赖

| 包 | 用途 | 必需 |
| --- | --- | --- |
| PyQt5 | 图形界面 | 是 |
| qdarkstyle | 暗色主题 | 是 |
| sc-compression | Supercell 资源解压（旧版 SC / LZMA / LZHAM 回退） | 是 |
| zstandard | Zstd 解压（SC v5 主要载荷） | 是 |
| pylzham | LZHAM 原生解码器（更快） | 否 |

## 许可证

[MIT](LICENSE) © 2026 Darknighture

---

本内容与 Supercell 无关，未经 Supercell 认可、赞助或特别批准。Clash Royale、Brawl Stars 及相关商标、
素材均为 Supercell Oy 的财产。详见 [Supercell Fan Content Policy](https://supercell.com/en/fan-content-policy/)。
