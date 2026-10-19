# Stock Miner 원본 데이터 자동 업로드

Stock Miner는 `JYP-COWRK`의 별도 페이지입니다. `AI-stock-orchestrator`의
`Stock momentum report` Actions와는 연결되지 않습니다. 키움 원본 수집에는
키움에 허용 IP가 등록된 실행 환경과 인증키가 필요합니다.

## PC가 꺼져 있어도 자동 수집하기

고정 IP Linux 서버에서 수집·DART 보강·검증·업로드를 실행할 수 있도록
서버용 클라이언트와 예약 설정을 추가했습니다. [서버 설치 안내](cloud/README.md)를 따릅니다.
서버 생성, 키움 허용 IP 등록, 서버에서 인증키 입력과 첫 실제 업로드 확인은 필요합니다.
현재 코드를 추가한 것만으로 서버가 가동되지는 않습니다.
서버 첫 업로드가 성공한 뒤 기존 PC 예약을 중지합니다.

아래는 기존 Windows PC 예약 방식입니다.

## 최초 설정: 등록된 PC에서 한 번

1. 이 저장소를 그 PC에서 최신으로 받습니다. (`git pull origin main`)
2. 기존처럼 키움 `kwcli`/Python `kiwoom` 모듈 인증과 `DART_API_KEY` 환경변수가
   같은 Windows 사용자에게 준비돼 있는지 확인합니다. 키를 저장소에 넣지 않습니다.
3. 먼저 PowerShell에서 저장소 폴더로 이동해 수동 실행합니다.

   ```powershell
   python scripts/publish_stock_miner.py
   ```

4. 성공 메시지와 사이트의 `키움 시세·수급` 시각이 바뀐 것을 확인한 뒤,
   같은 PowerShell에서 아래 작업을 한 번 등록합니다.

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts/install_stock_miner_task.ps1
   ```

등록 후 평일 09:20, 14:20, 16:30에 수집·DART 보강·검증·분할·GitHub 업로드를
실행합니다. PC가 켜져 있고 같은 사용자가 로그인해 있어야 합니다. GitHub
푸시 인증도 PC에 구성되어야 합니다. 실패하면 기존 게시 데이터는 그대로
유지되며, 사이트에는 오래된 데이터 경고가 표시됩니다. 실행 로그는 PC의
`stock-miner-logs` 폴더에 저장됩니다.

페이지의 `업로드 확인` 버튼은 GitHub에 이미 게시된 파일을 다시 읽습니다.
키움 데이터 수집이나 GitHub 업로드를 직접 실행하지 않습니다.

