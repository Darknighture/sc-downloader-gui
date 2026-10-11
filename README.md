# SC Downloader GUI

一个用于下载 Supercell 游戏资源的 GUI 工具，直接连接游戏服务器获取最新资源并下载、解压。

## 支持的游戏

| 游戏 | 服务器 |
|------|--------|
| Brawl Stars（国际服） | game.brawlstarsgame.com |
| Brawl Stars CN（荒野乱斗国服） | game.brawlstars.cn |
| Clash Royale（皇室战争） | game.clashroyaleapp.com |
| Clash Royale CN（皇室战争国服） | game.production.clashroyale.cn |

## 功能

- 三种下载方式：最新版本 / 指定版本哈希 / 本地 fingerprint 文件
- 自动解压 `.sc`、`.csv`、`.toml` 压缩资源（支持 Zstd、LZHAM、LZMA、SC v5 格式）
- 多线程下载，线程数可调
- 按文件类型筛选下载

## 使用

1. 安装依赖：

   ```
   pip install -r requirements.txt
   ```

2. 运行：

   ```
   python main.py
   ```

3. 在界面选择游戏服务器和下载方式，点击 Start Download。

## 配置

`config.json`：

- `servers` — 游戏服务器地址映射，可自行增删
- `workers_count` — 下载线程数（1-10）
- `output_path` — 输出目录
- `major` / `build` / `minor` — Clash Royale 客户端版本号（Brawl Stars 系列无需配置）

## 免责声明

本内容与 Supercell 无关，未经 Supercell 认可、赞助或特别批准。详见 Supercell Fan Content Policy。
