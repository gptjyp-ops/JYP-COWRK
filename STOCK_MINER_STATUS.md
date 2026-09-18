# Stock Miner 진행상태

업데이트: 2026-09-18

## 현재 완료

- 키움 REST API / `kwcli` 설치 및 로컬 인증 성공
- 등록된 PC에서 키움 API 실제 종목 조회 성공
- `stock_miner_collect.py` 수집기 v2 작성
- 외국인 연속순매수 후보 수집
- 최근 5일 외국인 / 기관 / 개인 순매수 집계
- 일봉 기반 현재가, 거래량 배수, 20일선/60일선 이격 계산
- 1차 발굴 점수 및 단계(집중관찰/관찰/대기) 계산
- 일반 개별주 필터 추가
  - ETF/펀드, ETN, 리츠, 스팩, 우선주, Reg.S 제외
  - 일반 6자리 숫자 코드만 허용
  - 500원 미만 제외
  - 당일 변동 ±20% 초과 제외
  - 60개 이상 일봉 데이터 요구
- `stock-miner.html` GitHub Pages 대시보드 작성
- JSON 기반 실제 데이터 로딩, 검색/점수/수급/거래량/이평선 필터 제공

## 현재 GitHub 데이터 상태

`data/stock-miner-data.json`은 아직 collector v1에서 생성한 40종목 데이터입니다.
따라서 ETF/리츠 등 v2 필터가 아직 실제 JSON에는 반영되지 않았습니다.

다음에 사용자 PC에서 최신 `stock_miner_collect.py` v2를 실행해 새 `stock-miner-data.json`을 만든 뒤 GitHub 데이터 파일을 교체해야 합니다.

## 다음 단계

1. 로컬에서 collector v2 재실행
2. 새 JSON의 `version`이 `stock-miner-collector-v2`인지 확인
3. 새 JSON을 `data/stock-miner-data.json`에 반영
4. DART OpenAPI 키 연결
5. 실적(영업이익/증감)과 긍정·위험 공시를 점수에 합산
6. 테마/업종 자동 분류 추가
7. PC 자동 실행 → GitHub JSON 자동 업로드 → GitHub Pages 자동 갱신 구성

## 보안/구조 메모

키움은 등록 IP 제한 때문에 GitHub-hosted Actions에서 직접 호출하지 않고, 등록된 사용자 PC에서 키움 API를 호출한 뒤 결과 JSON만 GitHub로 올리는 구조를 사용합니다. App Key/Secret은 로컬 자격 증명 저장소에서 관리하며 저장소나 웹페이지에 넣지 않습니다.
