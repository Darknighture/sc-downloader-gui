# SC Downloader GUI

[简体中文](README.md) | **English**

A desktop downloader that pulls Clash Royale and Brawl Stars game assets straight from Supercell's  
official servers: it retrieves the asset manifest (`fingerprint.json`) from the game login server or  
the CDN, downloads the files with a multi-threaded worker pool, and can optionally decompress  
compressed assets on the fly.

> This project is not affiliated with, endorsed, sponsored or specifically approved by Supercell.  
> See the Supercell Fan Content Policy.

---

## Features

- **Three ways to get assets**: Latest Patch (login-server handshake), a specific masterhash (direct CDN), or a local fingerprint file
- **Multi-threaded downloader**: 1–10 workers; automatic retry with exponential backoff on HTTP 502/503/504 (up to 3 attempts)
- **Interruptible and re-entrant**: Stop halts the current run immediately; starting again only fetches what is missing
- **Resume friendly**: existing files are skipped; if the target patch directory already exists you are asked whether to overwrite
- **Filter by file type**: pick only the extensions you need (`.csv`, `.sc`, `.png`, …) before downloading
- **Optional auto-decompression**: `.sc`, `.csv` and `.toml`, supporting Zstd, LZMA, SC v5 and legacy SC formats
- **Atomic writes**: files are written to `.part` and renamed on success, so an interrupted run never leaves half a file
- **Dark theme UI**: fixed-size QDarkStyle window

## Supported games and servers

| Game            | Login server (TCP 9339)          | Asset CDN                                |
| --------------- | -------------------------------- | ---------------------------------------- |
| Clash Royale    | `game.clashroyaleapp.com`        | `http://game-assets.clashroyaleapp.com`  |
| Clash Royale CN | `game.production.clashroyale.cn` | `https://cr-cdn.supercellgame.cn`        |
| Brawl Stars     | `game.brawlstarsgame.com`        | `https://game-assets.brawlstarsgame.com` |
| Brawl Stars CN  | `game.brawlstars.cn`             | `https://game-assets.tencent-cloud.com`  |

## Requirements

- Python 3.8 – 3.14
- Network access to the corresponding game servers and CDNs

## Installation

```bash
git clone https://github.com/Darknighture/sc-downloader-gui.git
cd sc-downloader-gui

python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS / Linux: source .venv/bin/activate

pip install -r requirements.txt
python main.py
```

## Quick start

1. Run `python main.py`
2. Pick a game server in the **Game** dropdown
3. Pick a method in **Download from** (see below)
4. Click **Start Download** and choose "Every files" or "Only specific files"
5. Progress is shown in the status bar; assets land in `output_path/<masterhash>/`
6. **Stop** interrupts a run at any time; clicking **Start Download** again skips what is already  
   there and only fills the gaps

## Download methods

| Method               | Description                                                                                              | Available for             |
| -------------------- | -------------------------------------------------------------------------------------------------------- | ------------------------- |
| **Latest Patch**     | Performs the login handshake and reads the CDN host + latest fingerprint out of the Loginfailed response | Brawl Stars (global / CN) |
| **Masterhash**       | Skips the handshake and fetches `fingerprint.json` for a 40-char hex masterhash directly from the CDN    | All servers               |
| **Fingerprint file** | Uses a local `fingerprint.json` and downloads assets under its `sha`                                     | All servers               |

> The Clash Royale handshake is currently frozen server-side (error code 16), so **Latest Patch is not  
> offered for Clash Royale**. Use Masterhash or Fingerprint file instead.

## UI overview

- **Download tab** – game/method selection; the masterhash field validates the format live  
  (40 lowercase hex chars); the "Decompress compressed assets" checkbox toggles `.sc` / `.csv` / `.toml`  
  decompression (**off by default**).
- **Settings tab** – output folder and worker count (1–10); click **Save settings** to write `config.json`.
- **Status bar** – current stage, live progress (including a failure count) and elapsed time.

## Acknowledgements

This project stands on two open-source projects:

- [**Galaxy1036/SC-Assets-Downloader-GUI**](https://github.com/Galaxy1036/SC-Assets-Downloader-GUI) — where this
  project started. The GUI, the download queue and worker-thread structure, and the foundation modules
  (`lib/reader.py`, `lib/writer.py`, `lib/utils.py`) all come from it.
- [**Shei-Bi/even-better-sc-downloader**](https://github.com/Shei-Bi/even-better-sc-downloader) — a reference for
  the login handshake and manifest retrieval: ClientHello message `10100`, the `major` / `build` / `minor` wire
  order, and how the Loginfailed response is parsed. Multi-server support was inspired by it as well.

## License

[GPLv3](LICENSE) © 2026 Darknighture

---

This content is not affiliated with, endorsed, sponsored, or specifically approved by Supercell.  
Clash Royale, Brawl Stars and their trademarks and assets are the property of Supercell Oy.  
See the [Supercell Fan Content Policy](https://supercell.com/en/fan-content-policy/).
