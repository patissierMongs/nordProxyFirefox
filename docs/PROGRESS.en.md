# Progress record

**English** | [한국어](PROGRESS.md)

## Final goal

Route only one Firefox instance through a NordVPN SOCKS5 (Socket Secure version 5) server without turning on a system-wide VPN (Virtual Private Network). Firefox cannot do SOCKS5 username/password authentication by itself, so a local HTTP (HyperText Transfer Protocol) proxy handles it. The project stays a single script that uses only the Python standard library.

## Current implementation status

All code lives in `main.py`. Status was verified by reading the code and by running it against a test SOCKS5 server and a local web server.

| Feature | Status | Code location | How verified |
|---|---|---|---|
| SOCKS5 client (username/password auth, no-auth) | Implemented | `socks5_open_tunnel()` | Correct credentials succeed; wrong password gives `socks5 auth failed` |
| Host names passed to the SOCKS5 server for remote resolution (ATYP(Address Type) 0x03) | Implemented | `socks5_open_tunnel()` | Code review |
| IPv4/IPv6 (Internet Protocol version 4/6) destinations | Implemented | `socks5_open_tunnel()` | IPv4 run; IPv6 code review |
| HTTP `CONNECT` tunnel | Implemented | `handle_client()`, `_parse_connect_target()` | Run with `curl -p` |
| Absolute-form URL (Uniform Resource Locator) HTTP forwarding | Partial | `handle_client()`, `_extract_host_port_from_absolute_url()` | First request forwarded correctly. Further requests on a kept-alive connection are piped as-is to the same upstream without rewriting the request line |
| `502 Bad Gateway` on upstream errors | Implemented | `handle_client()` | Request to a closed port |
| `--socks` URL / `host:port` shorthand | Implemented | `_apply_socks_url_overrides()` | Run with `--socks socks5://127.0.0.1:1080` |
| Credential env vars (`NORD_SOCKS_USER`, `NORD_SOCKS_PASS`) | Implemented | `main()` | Run |
| `--check-upstream` connectivity check | Implemented | `main()` | Success and failure both run |
| `--proxy-only`, `--verbose` | Implemented | `main()`, `handle_client()` | Run |
| Firefox executable auto-detection (Windows/macOS/Linux) | Implemented | `find_firefox_exe()` | Code review (no Firefox in this environment) |
| Proxy-pinned `user.js` (HTTP/3 off, WebRTC (Web Real-Time Communication) proxy-only) | Implemented | `write_profile_prefs()` | Generated file inspected |
| Launch Firefox with `-no-remote -profile ... -private-window` | Implemented | `launch_firefox()` | Command checked with `--firefox-path /bin/echo` |
| Temporary profile deletion, Firefox terminated on exit | Implemented | `finally` block in `main()` | Code review |
| Stop the proxy when the Firefox window closes | Not started | - | Proxy keeps running until `Ctrl+C` |
| NordVPN server list lookup / auto-selection | Not started | - | User supplies the host |
| Automated tests | Not started | - | No test files |

## Work history

From `git log`. Commit times are already stored with a +0900 offset, so they are KST (Korea Standard Time) as-is.

| Date (KST) | Commit | Change |
|---|---|---|
| 2025-12-12 23:22 | `6a7360c` | Repository created with a title-only `README.md` |
| 2025-12-12 23:23 | `18da6ff` | Added `main.py`: SOCKS5 client, local HTTP proxy, Firefox profile writing and launch |
| 2025-12-14 01:27 | `06ec317` | ver 0.1: added `--socks` URL, `--check-upstream`, `--proxy-only`, `--verbose`, `--socks-timeout`; improved auth negotiation and error messages; added 502 response; wrote README |
| 2026-09-27 | - | Untracked `__pycache__` and added `.gitignore`; Korean/English README with screenshots; progress record |
