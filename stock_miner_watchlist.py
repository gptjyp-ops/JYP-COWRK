"""Shared fixed watchlist for market and news collection."""
import json
import re
from pathlib import Path

WATCHLIST = Path(__file__).resolve().parent / "data" / "stock-miner-watchlist.json"

def load_watchlist():
    if not WATCHLIST.exists():
        return []
    payload = json.loads(WATCHLIST.read_text(encoding="utf-8"))
    stocks = payload["stocks"]
    result, seen = [], set()
    for stock in stocks:
        code, name = str(stock["code"]).strip().upper(), str(stock["name"]).strip()
        if not re.fullmatch(r"[0-9A-Z]{6}", code) or not name:
            raise ValueError("고정 관심종목 코드·이름 형식 오류")
        if code not in seen:
            result.append({"code": code, "name": name, "fixed_watch": True})
            seen.add(code)
    return result

def include_watchlist(rows):
    result = [dict(row) for row in rows]
    by_code = {str(row["code"]): row for row in result}
    for stock in load_watchlist():
        if stock["code"] in by_code:
            by_code[stock["code"]]["fixed_watch"] = True
        else:
            row = dict(stock, sources=[])
            result.append(row)
            by_code[stock["code"]] = row
    return result
