# SC Downloader GUI

**简体中文** | [English](README_EN.md)

一个用于从 Supercell 官方服务器直接拉取《皇室战争》《荒野乱斗》等游戏资源的图形化下载器：
通过游戏登录服务器或 CDN 取到资源清单，再按需多线程下载，并可选地自动解压压缩资源。

> 本项目与 Supercell 无任何关联，未经 Supercell 认可、赞助或特别批准。详见 Supercell Fan Content Policy。

---

## 功能特性

- **三种资源获取方式**：最新补丁、指定 masterhash、本地 fingerprint 文件
- **多线程下载**：线程数 1–10 可调，服务端 502/503/504 自动重试（指数退避，最多 3 次）
- **可中断、可重入**：Stop 会立刻停住当前下载；再次 Start 只补下缺失文件
- **断点友好**：已存在的文件自动跳过；若目标补丁目录已存在会询问是否覆盖
- **按类型筛选**：下载前可勾选只下载 `.csv` / `.sc` / `.png` 等指定后缀
- **可选自动解压**：`.sc`、`.csv`、`.toml` 支持 Zstd、LZMA、SC v5 与旧版 SC 格式
- **原子写入**：文件先写 `.part` 再改名，中断不会留下半截文件
- **暗色主题**：基于 QDarkStyle 的固定尺寸窗口，界面简洁

## 支持的游戏与服务器

| 游戏 | 登录服务器（TCP 9339） | 资源 CDN |
| --- | --- | --- |
| Clash Royale（皇室战争国际服） | `game.clashroyaleapp.com` | `http://game-assets.clashroyaleapp.com` |
| Clash Royale CN（皇室战争国服） | `game.production.clashroyale.cn` | `https://cr-cdn.supercellgame.cn` |
| Brawl Stars（荒野乱斗国际服） | `game.brawlstarsgame.com` | `https://game-assets.brawlstarsgame.com` |
| Brawl Stars CN（荒野乱斗国服） | `game.brawlstars.cn` | `https://game-assets.tencent-cloud.com` |

## 环境要求

- Python 3.8 – 3.14
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

## 致谢

本项目站在两个开源项目的肩膀上：

- [**Galaxy1036/SC-Assets-Downloader-GUI**](https://github.com/Galaxy1036/SC-Assets-Downloader-GUI) —— 本项目的起点。
  图形界面、下载队列与多线程工作线程的结构，以及 `lib/reader.py`、`lib/writer.py`、`lib/utils.py`
  等基础模块都源自它。
- [**Shei-Bi/even-better-sc-downloader**](https://github.com/Shei-Bi/even-better-sc-downloader) ——
  登录握手与资源清单获取流程的参考实现，包括 ClientHello 消息 `10100`、`major` / `build` / `minor`
  的报文写入顺序，以及 Loginfailed 报文的解析方式；多游戏服务器支持也参考了它。

## 许可证

[GPLv3](LICENSE) © 2026 Darknighture

---

本内容与 Supercell 无关，未经 Supercell 认可、赞助或特别批准。Clash Royale、Brawl Stars 及相关商标、
素材均为 Supercell Oy 的财产。详见 [Supercell Fan Content Policy](https://supercell.com/en/fan-content-policy/)。
