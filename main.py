#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
nord_firefox_proxy.py
- 로컬 HTTP CONNECT 프록시를 띄우고 (127.0.0.1:listen_port)
- 업스트림으로 NordVPN SOCKS5(유저/패스 포함)에 접속해 터널링
- Firefox를 "프록시 고정 프로필"로 실행

표준 라이브러리만 사용.
"""

import argparse
import asyncio
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


# -------------------------
# SOCKS5 client (RFC 1928/1929)
# -------------------------

class Socks5Error(RuntimeError):
    pass


def _fmt_exc(e: BaseException) -> str:
    s = str(e).strip()
    if s:
        return f"{type(e).__name__}: {s}"
    return type(e).__name__


def _socks5_rep_to_msg(rep: int) -> str:
    table = {
        0x01: "general SOCKS server failure",
        0x02: "connection not allowed by ruleset",
        0x03: "network unreachable",
        0x04: "host unreachable",
        0x05: "connection refused",
        0x06: "TTL expired",
        0x07: "command not supported",
        0x08: "address type not supported",
    }
    return table.get(rep, f"unknown error (0x{rep:02x})")


async def socks5_open_tunnel(
    dest_host: str,
    dest_port: int,
    socks_host: str,
    socks_port: int,
    username: str | None,
    password: str | None,
    timeout: float = 15.0,
):
    """업스트림 SOCKS5에 붙어 dest_host:dest_port 로 CONNECT 터널 생성."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(socks_host, socks_port),
            timeout=timeout,
        )
    except Exception as e:
        raise Socks5Error(f"upstream socks5 connect failed: {_fmt_exc(e)}") from e

    # greeting
    # If credentials are provided, offer both username/password and no-auth to
    # accommodate servers that ignore auth while still working.
    methods = [0x02, 0x00] if username is not None else [0x00]
    writer.write(bytes([0x05, len(methods), *methods]))
    await writer.drain()

    try:
        ver, method = (await asyncio.wait_for(reader.readexactly(2), timeout=timeout))
    except Exception as e:
        writer.close()
        raise Socks5Error(f"socks5 greeting read failed: {_fmt_exc(e)}") from e

    if ver != 0x05:
        writer.close()
        raise Socks5Error(f"invalid socks version: {ver}")

    # username/password auth
    if method == 0xFF:
        writer.close()
        raise Socks5Error("socks5: server rejected offered auth methods")

    if method == 0x02:
        if username is None or password is None:
            writer.close()
            raise Socks5Error("server requires username/password but none provided")

        u = username.encode("utf-8")
        p = password.encode("utf-8")
        if len(u) > 255 or len(p) > 255:
            writer.close()
            raise Socks5Error("username/password too long for SOCKS5")

        writer.write(bytes([0x01, len(u)]) + u + bytes([len(p)]) + p)
        await writer.drain()

        try:
            aver, status = await asyncio.wait_for(reader.readexactly(2), timeout=timeout)
        except Exception as e:
            writer.close()
            raise Socks5Error(f"socks5 auth read failed: {_fmt_exc(e)}") from e

        if aver != 0x01 or status != 0x00:
            writer.close()
            raise Socks5Error("socks5 auth failed (bad credentials?)")

    elif method == 0x00:
        pass
    else:
        writer.close()
        raise Socks5Error(f"socks5: unsupported auth method selected: 0x{method:02x}")

    # CONNECT request
    atyp = None
    addr = b""

    # If not literal IP, use domain name (prevents local DNS leak)
    is_ip = False
    for af, code in ((socket.AF_INET, 0x01), (socket.AF_INET6, 0x04)):
        try:
            packed = socket.inet_pton(af, dest_host)
            atyp = code
            addr = packed
            is_ip = True
            break
        except OSError:
            continue

    if not is_ip:
        host_idna = dest_host.encode("idna")
        if len(host_idna) > 255:
            writer.close()
            raise Socks5Error("destination hostname too long for SOCKS5")
        atyp = 0x03
        addr = bytes([len(host_idna)]) + host_idna

    port_bytes = struct.pack("!H", dest_port)
    writer.write(bytes([0x05, 0x01, 0x00, atyp]) + addr + port_bytes)
    await writer.drain()

    # reply
    try:
        hdr = await asyncio.wait_for(reader.readexactly(4), timeout=timeout)
    except Exception as e:
        writer.close()
        raise Socks5Error(f"socks5 reply read failed: {_fmt_exc(e)}") from e

    rver, rep, _rsv, ratyp = hdr
    if rver != 0x05:
        writer.close()
        raise Socks5Error(f"invalid socks reply version: {rver}")
    if rep != 0x00:
        writer.close()
        raise Socks5Error(f"socks5 CONNECT failed: {_socks5_rep_to_msg(rep)}")

    # consume BND.ADDR + BND.PORT
    try:
        if ratyp == 0x01:
            await reader.readexactly(4)
        elif ratyp == 0x04:
            await reader.readexactly(16)
        elif ratyp == 0x03:
            ln = (await reader.readexactly(1))[0]
            await reader.readexactly(ln)
        else:
            writer.close()
            raise Socks5Error(f"unknown ATYP in reply: 0x{ratyp:02x}")
        await reader.readexactly(2)
    except Exception as e:
        writer.close()
        raise Socks5Error(f"socks5 reply parse failed: {_fmt_exc(e)}") from e

    return reader, writer


# -------------------------
# Minimal HTTP proxy (CONNECT + absolute-form HTTP)
# -------------------------

async def _pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter):
    try:
        while True:
            data = await src.read(16384)
            if not data:
                break
            dst.write(data)
            await dst.drain()
    except Exception:
        pass


async def _bidir(a_r, a_w, b_r, b_w):
    t1 = asyncio.create_task(_pipe(a_r, b_w))
    t2 = asyncio.create_task(_pipe(b_r, a_w))
    _, pending = await asyncio.wait({t1, t2}, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
    try:
        a_w.close()
    except Exception:
        pass
    try:
        b_w.close()
    except Exception:
        pass


def _parse_connect_target(target: str):
    target = target.strip()

    # RFC 7231: authority-form for CONNECT. Commonly "host:port".
    # IPv6 literal may arrive as "[::1]:443".
    if target.startswith("["):
        end = target.find("]")
        if end == -1:
            raise ValueError("invalid CONNECT target (unterminated IPv6 literal)")
        host = target[1:end]
        rest = target[end + 1 :]
        if rest.startswith(":") and len(rest) > 1:
            return host, int(rest[1:])
        return host, 443

    if ":" not in target:
        return target, 443
    host, port_s = target.rsplit(":", 1)
    return host, int(port_s)


def _extract_host_port_from_absolute_url(url: str):
    u = urlsplit(url)
    host = u.hostname
    if host is None:
        raise ValueError("no hostname in url")
    port = u.port
    if port is None:
        port = 443 if u.scheme == "https" else 80
    path = (u.path or "/")
    if u.query:
        path += "?" + u.query
    return host, port, path


async def handle_client(
    client_r: asyncio.StreamReader,
    client_w: asyncio.StreamWriter,
    socks_host: str,
    socks_port: int,
    username: str | None,
    password: str | None,
    socks_timeout: float = 15.0,
    verbose: bool = False,
):
    try:
        raw = await client_r.readuntil(b"\r\n\r\n")
    except Exception:
        client_w.close()
        return

    dst_label = None
    try:
        head = raw.decode("iso-8859-1")
        lines = head.split("\r\n")
        method, target, version = lines[0].split(" ", 2)
        method_u = method.upper()
        if verbose:
            peer = client_w.get_extra_info("peername")
            print(f"[>] {peer} {method_u} {target} {version}")
    except Exception as e:
        if verbose:
            print(f"[!] Bad request line: {e!r}")
        client_w.close()
        return

    try:
        if method_u == "CONNECT":
            dst_host, dst_port = _parse_connect_target(target)
            dst_label = f"{dst_host}:{dst_port}"
            up_r, up_w = await socks5_open_tunnel(
                dst_host, dst_port, socks_host, socks_port, username, password, timeout=socks_timeout
            )
            client_w.write(b"HTTP/1.1 200 Connection Established\r\nProxy-Agent: nord-shim\r\n\r\n")
            await client_w.drain()
            await _bidir(client_r, client_w, up_r, up_w)
            return

        # HTTP proxy absolute-form
        dst_host, dst_port, path = _extract_host_port_from_absolute_url(target)
        dst_label = f"{dst_host}:{dst_port}"
        up_r, up_w = await socks5_open_tunnel(
            dst_host, dst_port, socks_host, socks_port, username, password, timeout=socks_timeout
        )

        new_lines = [f"{method} {path} {version}"]
        host_header_present = False
        for h in lines[1:]:
            if not h:
                continue
            k = h.split(":", 1)[0].strip().lower()
            if k == "proxy-connection":
                continue
            if k == "host":
                host_header_present = True
            new_lines.append(h)
        if not host_header_present:
            new_lines.append(f"Host: {dst_host}")

        up_w.write(("\r\n".join(new_lines) + "\r\n\r\n").encode("iso-8859-1"))
        await up_w.drain()
        await _bidir(client_r, client_w, up_r, up_w)

    except Socks5Error as e:
        if verbose:
            print(f"[!] Upstream SOCKS5 error for {dst_label or 'unknown target'}: {e}")
        try:
            msg = (
                "HTTP/1.1 502 Bad Gateway\r\n"
                "Content-Type: text/plain; charset=utf-8\r\n"
                "\r\n"
                f"Upstream SOCKS5 error for {dst_label or 'unknown target'}: {e}\n"
            )
            client_w.write(msg.encode("utf-8", "replace"))
            await client_w.drain()
        except Exception:
            pass
        client_w.close()
    except Exception:
        if verbose:
            import traceback

            print(f"[!] Unexpected proxy error for {dst_label or 'unknown target'}:")
            traceback.print_exc()
        try:
            client_w.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            await client_w.drain()
        except Exception:
            pass
        client_w.close()


async def run_proxy(listen_host: str, listen_port: int, socks_host: str, socks_port: int,
                    username: str | None, password: str | None, socks_timeout: float = 15.0, verbose: bool = False):
    server = await asyncio.start_server(
        lambda r, w: handle_client(
            r,
            w,
            socks_host,
            socks_port,
            username,
            password,
            socks_timeout=socks_timeout,
            verbose=verbose,
        ),
        host=listen_host,
        port=listen_port,
        limit=65536,
    )
    addrs = ", ".join(str(s.getsockname()) for s in server.sockets or [])
    print(f"[+] Local HTTP proxy listening on {addrs}")
    print(f"[+] Upstream SOCKS5: {socks_host}:{socks_port} (auth={'yes' if username else 'no'})")
    async with server:
        await server.serve_forever()


# -------------------------
# Firefox launcher (profile with forced proxy)
# -------------------------

def find_firefox_exe(explicit: str | None) -> str:
    if explicit:
        return explicit

    if sys.platform.startswith("win"):
        pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        pfx = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        candidates = [
            str(Path(pf) / "Mozilla Firefox/firefox.exe"),
            str(Path(pfx) / "Mozilla Firefox/firefox.exe"),
        ]
        for c in candidates:
            if Path(c).exists():
                return c

    if sys.platform == "darwin":
        c = "/Applications/Firefox.app/Contents/MacOS/firefox"
        if Path(c).exists():
            return c

    # linux / fallback
    p = shutil.which("firefox")
    if p:
        return p

    raise FileNotFoundError("Firefox executable not found. Provide --firefox-path.")


def write_profile_prefs(profile_dir: str, proxy_host: str, proxy_port: int):
    """
    user.js: 매 실행 시 prefs를 덮어쓰게 해서 '항상 프록시'가 되게 만듦.
    """
    ud = Path(profile_dir)
    ud.mkdir(parents=True, exist_ok=True)

    user_js = ud / "user.js"
    content = f'''// Auto-generated by nord_firefox_proxy.py
user_pref("network.proxy.type", 1);
user_pref("network.proxy.http", "{proxy_host}");
user_pref("network.proxy.http_port", {proxy_port});
user_pref("network.proxy.ssl", "{proxy_host}");
user_pref("network.proxy.ssl_port", {proxy_port});
user_pref("network.proxy.share_proxy_settings", true);
user_pref("network.proxy.no_proxies_on", "");

// UDP/HTTP3 쪽 우회 가능성 줄이기(완전 보장은 아님)
user_pref("network.http.http3.enabled", false);
user_pref("media.peerconnection.ice.proxy_only", true);
'''
    user_js.write_text(content, encoding="utf-8")


def launch_firefox(firefox_exe: str, profile_dir: str, start_url: str | None, extra_args: list[str]):
    cmd = [
        firefox_exe,
        "-no-remote",
        "-profile", profile_dir,
    ]

    # "무조건 프록시로 도는 파폭" 느낌을 위해 private window 기본
    if start_url:
        cmd += ["-private-window", start_url]
    else:
        cmd += ["-private-window"]

    cmd += extra_args

    print("[+] Launching Firefox:")
    print("    " + " ".join(cmd))
    return subprocess.Popen(cmd)


def _apply_socks_url_overrides(args: argparse.Namespace) -> None:
    """
    Allow passing SOCKS endpoint as a single URL or host:port for convenience.

    Examples:
      - socks5://user:pass@host:1080
      - host:1080
    """
    socks = getattr(args, "socks", None)
    if not socks:
        return

    s = str(socks).strip()
    if not s:
        return

    if "://" not in s:
        # host[:port]
        if s.count(":") == 1:
            host, port_s = s.rsplit(":", 1)
            args.socks_host = host
            args.socks_port = int(port_s)
        else:
            args.socks_host = s
        return

    u = urlsplit(s)
    if u.scheme and u.scheme.lower() not in ("socks5", "socks"):
        raise SystemExit(f"Unsupported SOCKS URL scheme: {u.scheme!r} (use socks5://...)")
    if not u.hostname:
        raise SystemExit("Invalid --socks URL (no hostname)")

    args.socks_host = u.hostname
    if u.port is not None:
        args.socks_port = u.port
    if u.username is not None or u.password is not None:
        args.socks_user = u.username
        args.socks_pass = u.password


def main():
    ap = argparse.ArgumentParser(description="Run Firefox through NordVPN SOCKS5 via local HTTP CONNECT shim proxy.")
    ap.add_argument("--socks", default=None, help="SOCKS endpoint as URL (e.g. socks5://user:pass@host:1080) or host:port")
    ap.add_argument("--socks-host", default=None, help="NordVPN SOCKS5 host")
    ap.add_argument("--socks-port", type=int, default=1080, help="NordVPN SOCKS5 port (default: 1080)")
    ap.add_argument("--socks-user", default=os.environ.get("NORD_SOCKS_USER"), help="SOCKS5 username (or env NORD_SOCKS_USER)")
    ap.add_argument("--socks-pass", default=os.environ.get("NORD_SOCKS_PASS"), help="SOCKS5 password (or env NORD_SOCKS_PASS)")

    ap.add_argument("--listen-host", default="127.0.0.1", help="Local proxy listen host (default: 127.0.0.1)")
    ap.add_argument("--listen-port", type=int, default=18080, help="Local proxy listen port (default: 18080)")

    ap.add_argument("--socks-timeout", type=float, default=15.0, help="SOCKS connect/handshake timeout seconds (default: 15)")
    ap.add_argument("--proxy-only", action="store_true", help="Run proxy only (do not launch Firefox / profile)")
    ap.add_argument("--check-upstream", action="store_true", help="Check SOCKS5 connectivity then exit")
    ap.add_argument("--check-host", default="example.com", help="Host for --check-upstream (default: example.com)")
    ap.add_argument("--check-port", type=int, default=443, help="Port for --check-upstream (default: 443)")
    ap.add_argument("--verbose", action="store_true", help="Verbose logging")

    ap.add_argument("--firefox-path", default=None, help="Path to firefox executable")
    ap.add_argument("--profile-dir", default=None, help="Firefox profile dir (default: temp dir)")
    ap.add_argument("--url", default=None, help="Open URL on start (optional)")
    ap.add_argument("--ff-arg", action="append", default=[], help="Extra Firefox args (repeatable)")

    args = ap.parse_args()

    _apply_socks_url_overrides(args)

    if not args.socks_host:
        print("[-] Provide --socks-host or --socks.")
        sys.exit(2)

    if (args.socks_user is None) != (args.socks_pass is None):
        print("[-] Provide both --socks-user and --socks-pass (or env vars), or neither.")
        sys.exit(2)

    if args.check_upstream:
        async def _check():
            r, w = await socks5_open_tunnel(
                args.check_host,
                args.check_port,
                args.socks_host,
                args.socks_port,
                args.socks_user,
                args.socks_pass,
                timeout=args.socks_timeout,
            )
            w.close()
            try:
                await w.wait_closed()
            except Exception:
                pass

        try:
            asyncio.run(_check())
            print(f"[+] Upstream SOCKS5 OK: {args.socks_host}:{args.socks_port} -> {args.check_host}:{args.check_port}")
            return
        except Socks5Error as e:
            print(f"[-] Upstream SOCKS5 FAILED: {e}")
            sys.exit(1)

    firefox_exe = None
    if not args.proxy_only:
        firefox_exe = find_firefox_exe(args.firefox_path)

    temp_profile = None
    profile_dir = None
    if not args.proxy_only:
        if args.profile_dir:
            profile_dir = args.profile_dir
            Path(profile_dir).mkdir(parents=True, exist_ok=True)
        else:
            temp_profile = tempfile.mkdtemp(prefix="firefox-nord-profile-")
            profile_dir = temp_profile

        # Firefox는 로컬 HTTP 프록시만 보게 고정
        write_profile_prefs(profile_dir, args.listen_host, args.listen_port)

    ff_proc = None
    if not args.proxy_only:
        ff_proc = launch_firefox(firefox_exe, profile_dir, args.url, args.ff_arg)

    try:
        asyncio.run(
            run_proxy(
                args.listen_host,
                args.listen_port,
                args.socks_host,
                args.socks_port,
                args.socks_user,
                args.socks_pass,
                socks_timeout=args.socks_timeout,
                verbose=args.verbose,
            )
        )
    except KeyboardInterrupt:
        print("\n[!] stopping...")
    finally:
        if ff_proc and ff_proc.poll() is None:
            try:
                ff_proc.terminate()
            except Exception:
                pass
        if temp_profile:
            shutil.rmtree(temp_profile, ignore_errors=True)


if __name__ == "__main__":
    main()
