# Stock Miner: PC 없이 고정 IP 서버에서 자동 수집

상태: 서버용 코드와 예약 설정 준비 완료. 서버 생성·인증키 입력·허용 IP 등록·실제 첫 업로드는 별도 설정이 필요합니다.
코드를 저장소에 추가한 것만으로 서버가 생성되거나 예약 작업이 켜지지는 않습니다.

## 실행 구조

항상 켜져 있는 고정 공인 IP Linux 서버 → 키움 조회 → DART 보강 → 기존 검증 → GitHub 업로드 → Stock Miner 페이지.
집 PC와 Windows 로그인은 필요하지 않습니다. 서버가 실제로 켜져 있어야 합니다.

키움은 허용 IP에서만 인증합니다. 일반 GitHub 호스팅 러너의 IP는 바뀌므로
이 수집기를 ubuntu-latest에 예약하는 것만으로는 안정적으로 운영할 수 없습니다.

- 키움 공식 안내: https://openapi.kiwoom.com/intro/serviceInfo
- GitHub 러너 IP 안내: https://docs.github.com/en/actions/reference/runners/github-hosted-runners#ip-addresses
- 실행 시각: 한국시간 평일 09:20, 14:20, 16:30.
- 실패하면 최대 3회 추가 재시도합니다. 다음 예약은 별도로 실행됩니다.
- 매번 임시 복제본에서 작업하므로 실패한 중간 파일이 다음 실행을 막지 않습니다.
- 뉴스는 기존 GitHub Actions 자동 수집을 계속 사용합니다.
- 서버 수집기는 시세·순위·차트·수급 5개 조회 API만 호출할 수 있습니다.
- Windows 수집기는 STOCK_MINER_AUTH=env를 지정하지 않으면 기존 방식 그대로 동작합니다.

## 먼저 필요한 것

1. 고정 공인 IPv4가 있는 Ubuntu 24.04 LTS 서버와 관리자 SSH 접속.
2. 키움 REST API의 허용 IP에 서버의 실제 외부 송신 IP 등록.
   IP나 키를 바꿀 때는 집 PC용 기존 등록을 무작정 삭제하지 마세요.
3. 키움 앱키·시크릿키와 DART 키. 키는 서버에서만 입력하고 채팅이나 저장소에 넣지 않습니다.
4. 이 저장소에 업로드할 서버 전용 GitHub SSH deploy key.

서버 구입·유료 결제·계정 개설은 이 파일로 실행되지 않습니다.

## Ubuntu 서버 최초 설치

아래 명령은 집 PC가 아니라 **선택한 서버의 SSH 터미널**에서 실행합니다.

```bash
sudo apt-get update
sudo apt-get install -y git python3-venv openssh-client
sudo useradd --system --create-home --home-dir /opt/stock-miner --shell /bin/bash stockminer
sudo -u stockminer git clone https://github.com/gptjyp-ops/JYP-COWRK.git /opt/stock-miner/repo
sudo -u stockminer python3 -m venv /opt/stock-miner/venv
sudo -u stockminer /opt/stock-miner/venv/bin/pip install 'requests>=2.32,<3'
sudo -u stockminer mkdir -m 700 /opt/stock-miner/.ssh
sudo -u stockminer ssh-keygen -t ed25519 -N '' -f /opt/stock-miner/.ssh/id_ed25519 -C stock-miner-server
sudo cat /opt/stock-miner/.ssh/id_ed25519.pub
```

출력된 **.pub 공개키만** GitHub 저장소 Settings → Deploy keys → Add deploy key에 등록하고
Allow write access를 선택합니다. 개인키 파일은 서버 밖으로 복사하지 않습니다.
등록 후 서버에서 다음 명령으로 GitHub 연결을 확인합니다.

```bash
sudo -u stockminer ssh -T git@github.com
```

최초 연결의 호스트 키는 GitHub 공식 fingerprint와 대조한 후 수락하세요.
인증 성공 메시지가 나오면 정상입니다(ssh -T는 성공 메시지가 있어도 종료코드 1을 반환할 수 있습니다).
공식 fingerprint: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints

```bash
sudo install -o root -g root -m 600 /opt/stock-miner/repo/cloud/stock-miner.env.example /etc/stock-miner.env
sudo nano /etc/stock-miner.env
```

파일의 KIWOOM_APP_KEY / KIWOOM_SECRET_KEY / DART_API_KEY 값을 입력합니다.
키움 등록 IP와 서버의 실제 송신 IP가 일치하는지 확인한 다음 서비스 파일을 설치합니다.

```bash
sudo install -m 644 /opt/stock-miner/repo/cloud/stock-miner.service /etc/systemd/system/stock-miner.service
sudo install -m 644 /opt/stock-miner/repo/cloud/stock-miner.timer /etc/systemd/system/stock-miner.timer
sudo systemctl daemon-reload
sudo systemctl start stock-miner.service
sudo journalctl -u stock-miner.service -n 60 --no-pager
```

**먼저 게시 완료 메시지와 사이트의 키움·DART 갱신 시각을 확인한 뒤** 예약을 켭니다.

```bash
sudo systemctl enable --now stock-miner.timer
systemctl list-timers stock-miner.timer --no-pager
```

실제 업로드와 다음 실행 시각을 확인한 뒤에만 집 PC의 중복 작업을 끕니다.
Windows PowerShell:

```powershell
Disable-ScheduledTask -TaskName 'Stock Miner Daily Upload'
```

## 운영 확인

```bash
systemctl status stock-miner.timer --no-pager
systemctl show stock-miner.service -p Result -p ExecMainStatus
sudo journalctl -u stock-miner.service --since today --no-pager
```

환경변수 누락은 종료코드 78로 중단합니다. 누락을 고친 뒤 수동 실행하세요.
인증 오류는 앱키·시크릿키·키움의 서버 허용 IP를 확인하고, Git 업로드 오류는 deploy key의 쓰기 권한을 확인합니다.
서버 재시작 후 timer는 다시 활성화됩니다. 서버가 꺼져 있는 동안 놓친 장중 작업을 한꺼번에 실행하지 않습니다.
GitHub Pages 반영은 업로드 직후 잠시 걸릴 수 있습니다.

중지: `sudo systemctl disable --now stock-miner.timer`.
서버 가동에 문제가 있으면 기존 Windows 작업을 다시 켜서 임시 복구할 수 있습니다.
