"""Collect Stock Miner on the Kiwoom registered PC and publish validated JSON."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "stock-miner-data.json"
DATA = ROOT / "data"
META = DATA / "stock-miner-v4-meta.json"
PARTS = [DATA / f"stock-miner-v4-part{i}.json" for i in (1, 2, 3)]
AUDIT = DATA / "stock-miner-v4-audit.json"
PUBLISH_FILES = [META, *PARTS, AUDIT]


def run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def recent_timestamp(value: str, label: str, max_age_minutes: int) -> None:
    stamp = datetime.fromisoformat(value)
    current = datetime.now(stamp.tzinfo)
    if not current - timedelta(minutes=max_age_minutes) <= stamp <= current + timedelta(minutes=5):
        raise ValueError(f"{label} 수집 시각이 최근 {max_age_minutes}분이 아닙니다: {value}")


def main() -> None:
    # Never overwrite a local edit or stage unrelated files from this repository.
    run("git", "pull", "--ff-only", "origin", "main")
    run(sys.executable, "stock_miner_collect.py")
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

    DATA.mkdir(exist_ok=True)
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
        # News and trends workflows may have pushed while collection was running.
        run("git", "pull", "--rebase", "origin", "main")
        run("git", "push", "origin", "main")
    print(f"게시 완료: 키움 {payload['generated_at']} / DART {payload['generated_at_dart']} / {len(stocks)}종목")


if __name__ == "__main__":
    main()

