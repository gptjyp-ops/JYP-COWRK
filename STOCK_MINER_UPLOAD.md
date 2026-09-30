# Stock Miner 원본 데이터 자동 업로드

Stock Miner는 `JYP-COWRK`의 별도 페이지입니다. `AI-stock-orchestrator`의
`Stock momentum report` Actions와는 연결되지 않습니다. 키움 원본 수집은
키움 API에 등록한 Windows PC와 그 PC의 로컬 자격 증명이 필요합니다.

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
