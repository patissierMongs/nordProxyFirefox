# 진행 기록

[English](PROGRESS.en.md) | **한국어**

## 최종 목표

시스템 전체에 VPN(Virtual Private Network)을 켜지 않고, Firefox 한 개만 NordVPN SOCKS5(Socket Secure version 5) 서버를 거쳐 접속하도록 만드는 것입니다. Firefox가 SOCKS5 사용자 인증을 직접 지원하지 않는 문제를 로컬 HTTP(HyperText Transfer Protocol) 프록시로 해결하고, Python 표준 라이브러리만으로 동작하는 단일 스크립트를 유지합니다.

## 현재 구현 상태

모든 코드는 `main.py` 한 파일에 있습니다. 상태는 코드를 직접 읽고, 테스트용 SOCKS5 서버와 로컬 웹 서버를 띄워 실행한 결과로 확인했습니다.

| 기능 | 상태 | 코드 위치 | 확인 방법 |
|---|---|---|---|
| SOCKS5 클라이언트 (사용자 이름/비밀번호 인증, 인증 없음) | 구현됨 | `socks5_open_tunnel()` | 올바른 자격 증명은 성공, 잘못된 비밀번호는 `socks5 auth failed` 확인 |
| 도메인 이름을 SOCKS5 서버로 넘겨 원격에서 해석 (ATYP(Address Type) 0x03) | 구현됨 | `socks5_open_tunnel()` | 코드 확인 |
| IPv4/IPv6(Internet Protocol version 4/6) 대상 주소 | 구현됨 | `socks5_open_tunnel()` | IPv4 실행 확인, IPv6는 코드 확인 |
| HTTP `CONNECT` 터널 | 구현됨 | `handle_client()`, `_parse_connect_target()` | `curl -p`로 실행 확인 |
| 절대 URL(Uniform Resource Locator) 형식 HTTP 요청 전달 | 부분 구현 | `handle_client()`, `_extract_host_port_from_absolute_url()` | 첫 요청은 정상 전달 확인. 연결을 유지한 채 이어지는 요청은 요청 줄을 다시 쓰지 않고 같은 업스트림으로 그대로 흘려보냄 |
| 업스트림 오류 시 `502 Bad Gateway` 응답 | 구현됨 | `handle_client()` | 닫힌 포트로 요청해 확인 |
| `--socks` URL/`host:port` 한 번에 지정 | 구현됨 | `_apply_socks_url_overrides()` | `--socks socks5://127.0.0.1:1080`로 실행 확인 |
| 자격 증명 환경 변수 (`NORD_SOCKS_USER`, `NORD_SOCKS_PASS`) | 구현됨 | `main()` | 실행 확인 |
| `--check-upstream` 연결 점검 | 구현됨 | `main()` | 성공/실패 모두 실행 확인 |
| `--proxy-only`, `--verbose` | 구현됨 | `main()`, `handle_client()` | 실행 확인 |
| Firefox 실행 파일 자동 탐색 (Windows/macOS/Linux) | 구현됨 | `find_firefox_exe()` | 코드 확인 (이 환경에 Firefox 없음) |
| 프록시 고정 `user.js` 작성 (HTTP/3 끄기, WebRTC(Web Real-Time Communication) 프록시 전용) | 구현됨 | `write_profile_prefs()` | 생성된 파일 확인 |
| `-no-remote -profile ... -private-window` 로 Firefox 실행 | 구현됨 | `launch_firefox()` | `--firefox-path /bin/echo`로 명령 확인 |
| 임시 프로필 삭제, 종료 시 Firefox 종료 | 구현됨 | `main()`의 `finally` | 코드 확인 |
| Firefox 창을 닫으면 프록시도 종료 | 미구현 | - | 프록시는 `Ctrl+C`까지 계속 동작 |
| NordVPN 서버 목록 조회·자동 선택 | 미구현 | - | 호스트는 사용자가 직접 지정 |
| 자동화 테스트 | 미구현 | - | 테스트 파일 없음 |

## 작업 이력

`git log` 기록입니다. 커밋 시각은 이미 +0900으로 저장되어 있어 그대로 KST(Korea Standard Time, 한국 표준시)입니다.

| 날짜 (KST) | 커밋 | 내용 |
|---|---|---|
| 2025-12-12 23:22 | `6a7360c` | 저장소 생성, 제목만 있는 `README.md` 추가 |
| 2025-12-12 23:23 | `18da6ff` | `main.py` 추가: SOCKS5 클라이언트, 로컬 HTTP 프록시, Firefox 프로필 작성과 실행 |
| 2025-12-14 01:27 | `06ec317` | ver 0.1: `--socks` URL 지정, `--check-upstream`, `--proxy-only`, `--verbose`, `--socks-timeout` 추가, 인증 방식 협상과 오류 메시지 개선, 502 응답 추가, README 작성 |
| 2026-09-27 | - | `__pycache__` 추적 해제와 `.gitignore` 추가, 한국어/영어 README와 스크린샷, 진행 기록 추가 |
