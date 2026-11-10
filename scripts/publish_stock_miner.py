"""Collect Stock Miner on the Kiwoom registered PC and publish validated JSON."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from stock_miner_observations import update as update_observations
from stock_miner_watchlist import load_watchlist
from stock_miner_momentum import priority, timestamp
SOURCE = ROOT / "stock-miner-data.json"
DATA = ROOT / "data"
META = DATA / "stock-miner-v4-meta.json"
PARTS = [DATA / f"stock-miner-v4-part{i}.json" for i in (1, 2, 3)]
AUDIT = DATA / "stock-miner-v4-audit.json"
OBSERVATIONS = DATA / "stock-miner-observations.json"
COLLECTOR_STATUS = DATA / "stock-miner-collector-status.json"
PUBLISH_FILES = [META, *PARTS, AUDIT, OBSERVATIONS, COLLECTOR_STATUS]


def run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def write_collector_status(status: str, message: str, *, error_code: str | None = None,
                           action_required: bool = False) -> None:
    DATA.mkdir(exist_ok=True)
    payload = {
        "attempted_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": status,
        "source": "Kiwoom REST API",
        "message": message,
        "action_required": action_required,
    }
    if error_code:
        payload["error_code"] = error_code
    COLLECTOR_STATUS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def publish_status_only() -> None:
    run("git", "add", str(COLLECTOR_STATUS.relative_to(ROOT)))
    changed = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode
    if changed == 0:
        return
    if changed != 1:
        raise RuntimeError("수집기 상태 변경 확인에 실패했습니다.")
    run("git", "-c", "user.name=stock-miner-pc", "-c",
        "user.email=stock-miner-pc@users.noreply.github.com", "commit",
        "-m", "data: update Stock Miner collector status")
    try:
        run("git", "push", "origin", "main")
    except subprocess.CalledProcessError:
        run("git", "pull", "--rebase", "origin", "main")
        run("git", "push", "origin", "main")


def preflight_kiwoom() -> None:
    # The current Windows setup uses the official REST API with environment
    # credentials. Do not publish the user's public IP or any credential.
    import os
    if not os.environ.get("KIWOOM_APP_KEY") or not os.environ.get("KIWOOM_SECRET_KEY"):
        return
    from stock_miner_cloud_client import CloudClient, KiwoomError
    try:
        CloudClient().check_auth()
    except KiwoomError as exc:
        detail = str(exc)
        if "8050" in detail or "IP가 등록되지 않았습니다" in detail:
            write_collector_status(
                "ip_not_registered",
                "키움 허용 IP 갱신 필요",
                error_code="8050",
                action_required=True,
            )
        else:
            write_collector_status(
                "auth_error",
                "키움 인증 사전점검 실패",
                action_required=True,
            )
        publish_status_only()
        raise


def recent_timestamp(value: str, label: str, max_age_minutes: int) -> None:
    stamp = datetime.fromisoformat(value)
    current = datetime.now(stamp.tzinfo)
    if not current - timedelta(minutes=max_age_minutes) <= stamp <= current + timedelta(minutes=5):
        raise ValueError(f"{label} 수집 시각이 최근 {max_age_minutes}분이 아닙니다: {value}")


def main() -> None:
    # Never overwrite a local edit or stage unrelated files from this repository.
    run("git", "pull", "--ff-only", "origin", "main")
    preflight_kiwoom()
    try:
        run(sys.executable, "stock_miner_collect.py")
    except subprocess.CalledProcessError:
        write_collector_status("collection_error", "키움 수집 실행 실패", action_required=True)
        publish_status_only()
        raise
    write_collector_status("ok", "키움 인증 및 수집 정상", action_required=False)
    collected = json.loads(SOURCE.read_text(encoding="utf-8"))
    recent_timestamp(collected["generated_at"], "키움", 10)
    if collected.get("version") != "stock-miner-collector-v3" or not collected.get("stocks"):
        raise ValueError("키움 결과가 비어 있거나 버전이 맞지 않아 업로드하지 않습니다.")

    run(sys.executable, "dart_enrich.py")
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    recent_timestamp(payload["generated_at"], "키움", 90)
    recent_timestamp(payload["generated_at_dart"], "DART", 10)
    stocks = payload.get("stocks", [])
    if payload.get("version") != "stock-miner-v4-dart" or not stocks:
        raise ValueError("DART 보강 결과가 비어 있거나 버전이 맞지 않아 업로드하지 않습니다.")
    if payload.get("dart", {}).get("status") != "연결 완료":
        raise ValueError("DART 연결 실패: 업로드하지 않습니다.")
    if len(payload.get("dart", {}).get("errors", [])) > len(stocks) // 2:
        raise ValueError("DART 종목 조회 오류가 절반을 넘어 업로드하지 않습니다.")

    news_path = DATA / "news-momentum.json"
    news = json.loads(news_path.read_text(encoding="utf-8")) if news_path.exists() else {}
    now = timestamp(payload["generated_at_dart"])
    for stock in stocks:
        stock["observation_priority"] = priority(stock, news.get("stocks", {}).get(stock["code"]), now)
    if not OBSERVATIONS.exists():
        raise ValueError("관찰 비교 등록 파일이 없습니다.")
    history = json.loads(OBSERVATIONS.read_text(encoding="utf-8"))
    history = update_observations(history, stocks, payload.get("market_audit", {}), news, payload["generated_at_dart"], load_watchlist())
    DATA.mkdir(exist_ok=True)
    OBSERVATIONS.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    for index, path in enumerate(PARTS):
        segment = stocks[index * len(stocks) // 3:(index + 1) * len(stocks) // 3]
        path.write_text(json.dumps(segment, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    meta = {key: payload[key] for key in (
        "generated_at", "generated_at_dart", "version", "note", "count",
        "filtered_count", "source_counts", "dart", "collector_revision",
        "collection_started_at", "source_diagnostics", "collection_limits", "data_quality", "errors",
    ) if key in payload}
    meta["count"] = len(stocks)
    meta["parts"] = [path.name for path in PARTS]
    meta["audit_file"] = AUDIT.name
    AUDIT.write_text(json.dumps({"generated_at": payload["generated_at"], "collector_revision": payload.get("collector_revision"), "stocks": payload.get("market_audit", {})}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    META.write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if sum(len(json.loads(path.read_text(encoding="utf-8"))) for path in PARTS) != len(stocks):
        raise ValueError("분할 데이터 개수가 맞지 않아 업로드하지 않습니다.")

    run("git", "add", *(str(path.relative_to(ROOT)) for path in PUBLISH_FILES))
    changed = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode
    if changed == 0:
        print("업로드할 변경 사항이 없습니다.")
        return
    if changed != 1:
        raise RuntimeError("Git 변경 사항 확인에 실패했습니다.")
    run("git", "-c", "user.name=stock-miner-pc", "-c",
        "user.email=stock-miner-pc@users.noreply.github.com", "commit",
        "-m", "data: update Stock Miner from registered PC")
    try:
        run("git", "push", "origin", "main")
    except subprocess.CalledProcessError:
        # News/trends/watch-price workflows may push while collection is running.
        # Preserve unrelated local edits while replaying only our committed data update.
        run("git", "fetch", "origin", "main")
        run("git", "-c", "user.name=stock-miner-pc", "-c",
            "user.email=stock-miner-pc@users.noreply.github.com",
            "rebase", "--autostash", "origin/main")
        run("git", "push", "origin", "main")
    print(f"게시 완료: 키움 {payload['generated_at']} / DART {payload['generated_at_dart']} / {len(stocks)}종목")


if __name__ == "__main__":
    main()


