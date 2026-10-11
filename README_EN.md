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
- **Optional auto-decompression**: `.sc`, `.csv` and `.toml`, supporting Zstd, LZHAM, LZMA, SC v5 and legacy SC formats
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

## Troubleshooting

**`ModuleNotFoundError: No module named 'zstandard'` (or `PyQt5` / `qdarkstyle`)**  
The dependencies are not installed for the interpreter you are running. Install them with **the same**  
Python that runs `main.py`:

```
"<full path to your python.exe>" -m pip install -r requirements.txt
```

A common trap: packages installed for Python 3.13 but the script launched with 3.14, or IDLE / your IDE  
defaulting to a different interpreter than your terminal. The app now checks its dependencies at startup  
and prints that exact command (plus a dialog) instead of a raw traceback.

**`ValueError: check_hostname requires server_hostname` while installing dependencies**  
This is an old pip bug that only shows up when pip goes through a **proxy** (the urllib3 vendored into  
older pip versions breaks on `https://` proxy URLs). It has nothing to do with this project — look for  
`_connect_tls_proxy` / `_ssl_wrap_socket_impl` frames in the traceback.

Pick whichever fix fits:

```powershell
# 1. Easiest: drop the proxy and use a mirror instead
Remove-Item Env:HTTP_PROXY, Env:HTTPS_PROXY, Env:ALL_PROXY -ErrorAction SilentlyContinue
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 2. If you need the proxy: change its scheme from https:// to http://
$env:HTTPS_PROXY = "http://127.0.0.1:7890"   # use your real host and port

# 3. Upgrade pip - the bug is fixed in current releases
python -m pip install --upgrade pip
```

To see where the proxy is configured:

```powershell
Get-ChildItem env: | Where-Object Name -match 'proxy'
python -m pip config list
Get-Content "$env:APPDATA\pip\pip.ini" -ErrorAction SilentlyContinue
```

**`Could not connect to xxx:9339`**  
The host is unreachable or the port is blocked. Check proxy/firewall settings and whether the server is  
reachable from your network.

**`Server requires a different version`**  
The Brawl Stars backend expects a newer client version; adjust `major` / `build` / `minor` in `config.json`.

**The progress bar stops below 100%**  
Some files failed — the status bar shows `N failed` and the console prints `[x] Failed to download ...`.  
Only HTTP 5xx responses are retried (3 attempts); click Start Download again to fetch the missing files.

**Assets are still compressed**  
First make sure "Decompress compressed assets" is checked. If they still aren't decompressed,  
decompression failed (the console prints `[x] Failed to decompress file ...`) and the raw compressed data  
is saved as-is instead of a corrupt file. The most common cause is an LZHAM payload with no LZHAM  
decoder available on the machine - see "Supported compression formats and LZHAM support" above.

**"This patch was already downloaded"**  
The target directory already exists. Choose Yes to overwrite everything, or No to only fill in missing files.

**Can I continue after pressing Stop?**  
Yes. Stop only ends the current run and everything already downloaded is kept; clicking Start Download  
again resumes from the gaps.

## Known limitations

- Clash Royale's **Latest Patch is unavailable** (frozen handshake); use Masterhash or Fingerprint file.


- The built-in client-version bruteforcer is unreachable from the current UI and has no effect;  
  `major` / `build` / `minor` in `config.json` do not influence the current download flow.
- Decompression is **off by default** and must be enabled manually.
- There is no true pause/resume: **Stop** aborts the current run, and resuming relies on skipping files  
  that already exist.
- Failed files are not retried automatically (except HTTP 5xx) and there is no failure report file —  
  check the console output.

## Dependencies

| Package        | Purpose                                                            | Required      |
| -------------- | ------------------------------------------------------------------ | ------------- |
| PyQt5          | GUI                                                                | Yes           |
| qdarkstyle     | Dark theme                                                         | Yes           |
| zstandard      | Zstd decompression                                                 | Yes           |
| pylzham        | Native LZHAM decoder                                               | No, see above |
| sc-compression | provides `lzham.exe`, used when `pylzham` is not installed (GPLv3) | No, see above |

> Decompression is implemented in `lib/compression.py`, so `sc-compression` is **no longer needed**.  
> It survives only as an optional LZHAM fallback. Note that it is **GPLv3** (copyleft), so making it a  
> hard dependency would pull the whole project into a copyleft licence - one more reason it is not in  
> `requirements.txt`. If you do install it, pin it to `==0.6.1`: 0.6.6 fails to `import` on Windows.  
> See the comments in `requirements.txt`.

## License

[MIT](LICENSE) © 2026 Darknighture

---

This content is not affiliated with, endorsed, sponsored, or specifically approved by Supercell.  
Clash Royale, Brawl Stars and their trademarks and assets are the property of Supercell Oy.  
See the [Supercell Fan Content Policy](https://supercell.com/en/fan-content-policy/).
