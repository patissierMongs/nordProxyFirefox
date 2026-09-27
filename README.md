# nordProxyFirefox

Firefox 한 개만 NordVPN SOCKS5(Socket Secure version 5) 서버를 거쳐 인터넷에 접속하도록 로컬 HTTP(HyperText Transfer Protocol) 프록시를 띄우고, 프록시가 고정된 전용 프로필로 Firefox를 실행하는 Python 스크립트입니다.

[English](README.en.md) | **한국어**

![프록시 동작 데모](docs/images/proxy-demo.gif)

> 화면은 이 저장소의 `main.py`를 실제로 실행해 얻은 터미널 출력입니다. NordVPN 계정 대신 `127.0.0.1:1080`에 띄운 테스트용 SOCKS5 서버(사용자 `demo-user`)와 `127.0.0.1:8000`의 로컬 웹 서버를 사용했습니다.

## 주요 기능

- **로컬 HTTP 프록시**: `127.0.0.1:18080`(기본값)에서 HTTP `CONNECT` 요청과 절대 URL(Uniform Resource Locator) 형식의 일반 HTTP 요청을 받습니다.
- **SOCKS5 터널링**: 받은 요청을 사용자 이름/비밀번호 인증이 붙은 SOCKS5 서버로 넘깁니다. 도메인 이름은 SOCKS5 서버 쪽에서 해석하도록 그대로 전달하므로 로컬 DNS(Domain Name System) 조회가 일어나지 않습니다.
- **프록시 고정 Firefox 실행**: 전용 프로필에 `user.js`를 써서 HTTP/HTTPS(HTTP Secure) 프록시를 로컬 프록시로 고정하고, HTTP/3와 WebRTC(Web Real-Time Communication)의 프록시 우회를 줄이는 설정을 넣은 뒤 개인정보 보호 창(`-private-window`)으로 Firefox를 실행합니다.
- **임시 프로필 정리**: `--profile-dir`을 주지 않으면 임시 프로필을 만들고, 종료할 때 삭제합니다.
- **업스트림 점검**: `--check-upstream`으로 SOCKS5 서버 연결과 인증만 확인하고 끝낼 수 있습니다.
- **프록시 단독 실행**: `--proxy-only`로 Firefox 없이 프록시만 띄워 다른 프로그램에서 쓸 수 있습니다. 업스트림 오류는 `502 Bad Gateway`와 원인 메시지로 돌려줍니다.
- **표준 라이브러리만 사용**: 추가 패키지 설치가 필요 없습니다.

## 사용 방법

### 1. 준비

- Python 3.10 이상
- Firefox (Windows, macOS, Linux). 기본 설치 경로나 `PATH`에서 찾지 못하면 `--firefox-path`로 실행 파일을 지정합니다.
- NordVPN SOCKS5 접속 정보: 서버 호스트, 포트(기본 1080), 사용자 이름, 비밀번호

```bash
git clone https://github.com/patissierMongs/nordProxyFirefox.git
cd nordProxyFirefox
```

### 2. 자격 증명 설정

비밀번호를 명령행 인자로 넘기면 프로세스 목록에 노출될 수 있으므로 환경 변수를 권장합니다.

```bash
export NORD_SOCKS_USER="<사용자 이름>"
export NORD_SOCKS_PASS="<비밀번호>"
```

PowerShell에서는 다음과 같이 설정합니다.

```powershell
$env:NORD_SOCKS_USER = "<사용자 이름>"
$env:NORD_SOCKS_PASS = "<비밀번호>"
```

사용자 이름과 비밀번호는 둘 다 주거나 둘 다 생략해야 합니다. 하나만 있으면 스크립트가 종료됩니다.

### 3. 업스트림 연결 확인

```bash
python main.py --check-upstream --socks-host <SOCKS5 서버 호스트> --socks-port 1080
```

기본으로 SOCKS5 서버를 거쳐 `example.com:443`에 연결해 봅니다. `--check-host`, `--check-port`로 대상을 바꿀 수 있습니다.

![업스트림 점검 결과](docs/images/check-upstream.png)

### 4. Firefox 실행

```bash
python main.py --socks-host <SOCKS5 서버 호스트> --socks-port 1080 --url https://example.com
```

`--socks socks5://<사용자>:<비밀번호>@<호스트>:1080` 또는 `--socks <호스트>:1080` 형식으로 한 번에 지정할 수도 있습니다. 프록시는 Firefox 창을 닫아도 계속 동작하므로 `Ctrl+C`로 종료합니다. 종료하면 실행 중인 Firefox도 함께 종료하고 임시 프로필을 삭제합니다.

아래는 Firefox 대신 `/bin/echo`를 지정해 실행 명령과 생성된 `user.js`를 확인한 화면입니다(이 환경에는 Firefox가 설치되어 있지 않습니다).

![Firefox 실행 명령과 user.js](docs/images/firefox-profile.png)

### 5. 프록시만 사용

```bash
python main.py --proxy-only --verbose --socks-host <SOCKS5 서버 호스트>
```

다른 프로그램의 HTTP 프록시를 `127.0.0.1:18080`으로 지정하면 됩니다.

![프록시 단독 실행과 curl 요청](docs/images/proxy-only.png)

### 주요 옵션

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--socks` | 없음 | `socks5://user:pass@host:port` 또는 `host:port` |
| `--socks-host` / `--socks-port` | 없음 / `1080` | SOCKS5 서버 주소 |
| `--socks-user` / `--socks-pass` | 환경 변수 `NORD_SOCKS_USER` / `NORD_SOCKS_PASS` | SOCKS5 인증 정보 |
| `--listen-host` / `--listen-port` | `127.0.0.1` / `18080` | 로컬 프록시 주소 |
| `--socks-timeout` | `15` | SOCKS5 연결·핸드셰이크 제한 시간(초) |
| `--proxy-only` | 끔 | Firefox 없이 프록시만 실행 |
| `--check-upstream` | 끔 | 업스트림 연결만 확인하고 종료 |
| `--check-host` / `--check-port` | `example.com` / `443` | 업스트림 확인 대상 |
| `--verbose` | 끔 | 요청과 오류 로그 출력 |
| `--firefox-path` | 자동 탐색 | Firefox 실행 파일 경로 |
| `--profile-dir` | 임시 디렉터리 | Firefox 프로필 경로 |
| `--url` | 없음 | 시작할 때 열 주소 |
| `--ff-arg` | 없음 | Firefox 추가 인자(여러 번 지정 가능) |

### 문제 해결

- 브라우저에 `502 Bad Gateway`가 보이면 `--check-upstream`으로 SOCKS5 서버 연결과 인증부터 확인합니다.
- `--proxy-only --verbose`로 실행하면 들어온 요청과 업스트림 오류를 터미널에서 볼 수 있습니다.
- 업스트림 응답이 없을 때 대기 시간을 줄이려면 `--socks-timeout 5`처럼 지정합니다.
- 로그에는 호스트와 포트만 남고 자격 증명은 기록하지 않습니다.

## 기술 스택

| 구분 | 내용 |
|---|---|
| 언어 | Python 3.10 이상 (`str \| None` 타입 표기 사용) |
| 라이브러리 | 표준 라이브러리만 사용: `asyncio`, `argparse`, `socket`, `struct`, `subprocess`, `tempfile`, `urllib.parse` |
| 프로토콜 | SOCKS5 (RFC(Request for Comments) 1928), 사용자 이름/비밀번호 인증 (RFC 1929), HTTP `CONNECT` 프록시 |
| 외부 프로그램 | Firefox, NordVPN SOCKS5 서버 |

버전을 고정한 의존성 파일은 없습니다.

## 문서

- [진행 기록](docs/PROGRESS.md)
