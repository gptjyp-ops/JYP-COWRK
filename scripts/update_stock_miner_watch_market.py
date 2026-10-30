"""Refresh Stock Miner watchlist OHLC/chart data without the registered Kiwoom PC.

This file intentionally updates only public market-price data. Kiwoom investor-flow
and discovery data keep their own timestamps and are never presented as fresh when
this fallback runs.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
WATCHLIST = ROOT / "data" / "stock-miner-watchlist.json"
OUT = ROOT / "data" / "stock-miner-watch-market.json"
KST = timezone(timedelta(hours=9))


def valid_frame(frame):
    required = {"Open", "High", "Low", "Close", "Volume"}
    return frame is not None and not frame.empty and required.issubset(frame.columns) and len(frame.dropna(subset=["Close"])) >= 20


def fetch_symbol(code: str):
    last_error = None
    for suffix in (".KS", ".KQ"):
        symbol = code + suffix
        try:
            frame = yf.download(
                symbol, period="6mo", interval="1d", auto_adjust=False,
                progress=False, threads=False, timeout=25,
            )
            if hasattr(frame.columns, "levels"):
                frame.columns = frame.columns.get_level_values(0)
            frame = frame.dropna(subset=["Close"])
            if valid_frame(frame):
                return symbol, frame
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.15)
    raise RuntimeError(last_error or "Yahoo Finance 일봉 없음")


def one_stock(item: dict) -> dict:
    code = str(item["code"])
    symbol, frame = fetch_symbol(code)
    frame = frame.tail(70)
    close = frame["Close"].astype(float)
    open_s = frame["Open"].astype(float)
    high_s = frame["High"].astype(float)
    low_s = frame["Low"].astype(float)
    volume = frame["Volume"].astype(float)

    latest = float(close.iloc[-1])
    previous = float(close.iloc[-2]) if len(close) > 1 else latest
    ma5 = float(close.tail(5).mean())
    ma20 = float(close.tail(20).mean())
    ma60 = float(close.tail(60).mean()) if len(close) >= 60 else float(close.mean())
    avg20 = float(volume.iloc[-21:-1].mean()) if len(volume) >= 21 else float(volume.tail(20).mean())
    vol_ratio = float(volume.iloc[-1]) / avg20 if avg20 > 0 else 0.0

    chart = []
    for idx, row in frame.tail(30).iterrows():
        chart.append({
            "date": idx.strftime("%Y%m%d"),
            "open": round(float(row["Open"])),
            "high": round(float(row["High"])),
            "low": round(float(row["Low"])),
            "price": round(float(row["Close"])),
            "volume": round(float(row["Volume"])),
        })

    return {
        "code": code,
        "name": item.get("name", code),
        "symbol": symbol,
        "source": "Yahoo Finance",
        "quote_date": frame.index[-1].strftime("%Y%m%d"),
        "open": round(float(open_s.iloc[-1])),
        "high": round(float(high_s.iloc[-1])),
        "low": round(float(low_s.iloc[-1])),
        "close": round(latest),
        "change": round((latest / previous - 1) * 100 if previous else 0.0, 2),
        "volume": round(float(volume.iloc[-1])),
        "vol_ratio": round(vol_ratio, 2),
        "ma5": round(ma5, 2),
        "ma20": round(ma20, 2),
        "ma60": round(ma60, 2),
        "chart": chart,
    }


def main():
    watch = json.loads(WATCHLIST.read_text(encoding="utf-8")).get("stocks", [])
    previous = {}
    if OUT.exists():
        try:
            previous = json.loads(OUT.read_text(encoding="utf-8")).get("stocks", {})
        except Exception:
            previous = {}

    stocks, errors = {}, []
    for item in watch:
        code = str(item.get("code", "")).strip()
        if not code or not code.isdigit():
            errors.append({"code": code, "name": item.get("name"), "error": "일반 종목코드 아님"})
            continue
        try:
            stocks[code] = one_stock(item)
        except Exception as exc:
            if code in previous:
                stocks[code] = previous[code]
                stocks[code]["preserved_previous"] = True
            errors.append({"code": code, "name": item.get("name"), "error": str(exc)[:240]})
        time.sleep(0.15)

    if not stocks:
        raise RuntimeError("관심종목 시세를 한 종목도 갱신하지 못했습니다.")

    payload = {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "version": "stock-miner-watch-market-v1",
        "source": "Yahoo Finance",
        "note": "관심종목 가격·OHLC·일봉 차트 보조 데이터. 키움 수급·발굴 데이터와 별도.",
        "count": len(stocks),
        "watch_count": len(watch),
        "errors": errors,
        "stocks": stocks,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"watch market updated: {len(stocks)}/{len(watch)}, errors={len(errors)}")


if __name__ == "__main__":
    main()
