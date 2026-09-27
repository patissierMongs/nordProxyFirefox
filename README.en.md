# nordProxyFirefox

A Python script that starts a local HTTP (HyperText Transfer Protocol) proxy which tunnels through a NordVPN SOCKS5 (Socket Secure version 5) server, then launches Firefox with a dedicated profile pinned to that proxy, so only that one browser goes through NordVPN.

**English** | [한국어](README.md)

![Proxy demo](docs/images/proxy-demo.gif)

> All screens are real terminal output from running this repository's `main.py`. Instead of a NordVPN account, a test SOCKS5 server on `127.0.0.1:1080` (user `demo-user`) and a local web server on `127.0.0.1:8000` were used.

## Features

- **Local HTTP proxy**: accepts HTTP `CONNECT` requests and absolute-form URL (Uniform Resource Locator) HTTP requests on `127.0.0.1:18080` by default.
- **SOCKS5 tunneling**: forwards each request to a SOCKS5 server with username/password authentication. Host names are passed to the SOCKS5 server unresolved, so no local DNS (Domain Name System) lookup happens.
- **Proxy-pinned Firefox**: writes `user.js` into a dedicated profile that pins the HTTP/HTTPS (HTTP Secure) proxy to the local proxy, adds settings that reduce HTTP/3 and WebRTC (Web Real-Time Communication) bypasses, and starts Firefox with `-private-window`.
- **Temporary profile cleanup**: without `--profile-dir`, a temporary profile is created and deleted on exit.
- **Upstream check**: `--check-upstream` only tests the SOCKS5 connection and authentication, then exits.
- **Proxy-only mode**: `--proxy-only` runs the proxy without Firefox for use by other programs. Upstream failures are returned as `502 Bad Gateway` with the reason.
- **Standard library only**: no extra packages to install.

## Usage

### 1. Requirements

- Python 3.10 or later
- Firefox (Windows, macOS, Linux). If it is not found in the default install location or on `PATH`, pass the executable with `--firefox-path`.
- NordVPN SOCKS5 details: server host, port (default 1080), username, password

```bash
git clone https://github.com/patissierMongs/nordProxyFirefox.git
cd nordProxyFirefox
```

### 2. Credentials

Passing the password as a command-line argument can expose it in the process list, so environment variables are recommended.

```bash
export NORD_SOCKS_USER="<username>"
export NORD_SOCKS_PASS="<password>"
```

In PowerShell:

```powershell
$env:NORD_SOCKS_USER = "<username>"
$env:NORD_SOCKS_PASS = "<password>"
```

Provide both username and password, or neither. If only one is set, the script exits.

### 3. Check the upstream

```bash
python main.py --check-upstream --socks-host <SOCKS5 host> --socks-port 1080
```

By default it connects to `example.com:443` through the SOCKS5 server. Change the target with `--check-host` and `--check-port`.

![Upstream check result](docs/images/check-upstream.png)

### 4. Launch Firefox

```bash
python main.py --socks-host <SOCKS5 host> --socks-port 1080 --url https://example.com
```

You can also give the endpoint in one option: `--socks socks5://<user>:<password>@<host>:1080` or `--socks <host>:1080`. The proxy keeps running after the Firefox window is closed; stop it with `Ctrl+C`. On exit it terminates Firefox if still running and deletes the temporary profile.

The screen below uses `/bin/echo` in place of Firefox to show the launch command and the generated `user.js` (Firefox is not installed in this environment).

![Firefox launch command and user.js](docs/images/firefox-profile.png)

### 5. Proxy only

```bash
python main.py --proxy-only --verbose --socks-host <SOCKS5 host>
```

Point another program's HTTP proxy at `127.0.0.1:18080`.

![Proxy-only mode with curl requests](docs/images/proxy-only.png)

### Options

| Option | Default | Description |
|---|---|---|
| `--socks` | none | `socks5://user:pass@host:port` or `host:port` |
| `--socks-host` / `--socks-port` | none / `1080` | SOCKS5 server address |
| `--socks-user` / `--socks-pass` | env `NORD_SOCKS_USER` / `NORD_SOCKS_PASS` | SOCKS5 credentials |
| `--listen-host` / `--listen-port` | `127.0.0.1` / `18080` | Local proxy address |
| `--socks-timeout` | `15` | SOCKS5 connect/handshake timeout (seconds) |
| `--proxy-only` | off | Run the proxy without Firefox |
| `--check-upstream` | off | Check the upstream and exit |
| `--check-host` / `--check-port` | `example.com` / `443` | Target for the upstream check |
| `--verbose` | off | Log requests and errors |
| `--firefox-path` | auto-detect | Firefox executable path |
| `--profile-dir` | temporary directory | Firefox profile path |
| `--url` | none | URL to open on start |
| `--ff-arg` | none | Extra Firefox argument (repeatable) |

### Troubleshooting

- If the browser shows `502 Bad Gateway`, run `--check-upstream` to verify the SOCKS5 connection and credentials first.
- Run with `--proxy-only --verbose` to see incoming requests and upstream errors in the terminal.
- To wait less when the upstream does not answer, set e.g. `--socks-timeout 5`.
- Logs contain only hosts and ports; credentials are never logged.

## Tech stack

| Area | Details |
|---|---|
| Language | Python 3.10 or later (uses `str \| None` type syntax) |
| Libraries | Standard library only: `asyncio`, `argparse`, `socket`, `struct`, `subprocess`, `tempfile`, `urllib.parse` |
| Protocols | SOCKS5 (RFC (Request for Comments) 1928), username/password auth (RFC 1929), HTTP `CONNECT` proxy |
| External programs | Firefox, NordVPN SOCKS5 server |

There is no dependency file with pinned versions.

## Docs

- [Progress record](docs/PROGRESS.en.md)
