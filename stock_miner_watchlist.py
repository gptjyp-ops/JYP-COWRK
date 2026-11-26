"""Shared fixed watchlist plus source-tagged monitoring lists."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WATCHLIST = ROOT / "data" / "stock-miner-watchlist.json"
MTN_PICKS = ROOT / "data" / "mtn-picks.json"


def _clean_stock(stock, *, fixed_watch=False, mtn_pick=False):
    code, name = str(stock["code"]).strip().upper(), str(stock["name"]).strip()
    if not re.fullmatch(r"[0-9A-Z]{6}", code) or not name:
        raise ValueError("관심종목 코드·이름 형식 오류")
    row = {"code": code, "name": name}
    if fixed_watch:
        row["fixed_watch"] = True
    if mtn_pick:
        row["mtn_pick"] = True
        row["mtn_mentions"] = int(stock.get("mentions") or 0)
        row["mtn_last_seen"] = stock.get("last_seen")
        row["mtn_part"] = stock.get("latest_part")
        row["mtn_theme"] = stock.get("theme")
        row["mtn_url"] = stock.get("latest_url")
    return row


def load_watchlist():
    if not WATCHLIST.exists():
        return []
    payload = json.loads(WATCHLIST.read_text(encoding="utf-8"))
    result, seen = [], set()
    for stock in payload.get("stocks") or []:
        row = _clean_stock(stock, fixed_watch=True)
        if row["code"] not in seen:
            result.append(row)
            seen.add(row["code"])
    return result


def load_mtn_picks():
    if not MTN_PICKS.exists():
        return []
    payload = json.loads(MTN_PICKS.read_text(encoding="utf-8"))
    result, seen = [], set()
    for stock in payload.get("stocks") or []:
        try:
            row = _clean_stock(stock, mtn_pick=True)
        except (KeyError, ValueError, TypeError):
            continue
        if row["code"] not in seen:
            result.append(row)
            seen.add(row["code"])
    return result


def load_monitoring_stocks():
    result, by_code = [], {}
    for stock in load_watchlist() + load_mtn_picks():
        code = stock["code"]
        if code in by_code:
            by_code[code].update({k: v for k, v in stock.items() if k not in ("code", "name")})
            continue
        row = dict(stock)
        result.append(row)
        by_code[code] = row
    return result


def include_watchlist(rows):
    result = [dict(row) for row in rows]
    by_code = {str(row["code"]): row for row in result}
    for stock in load_monitoring_stocks():
        if stock["code"] in by_code:
            by_code[stock["code"]].update({k: v for k, v in stock.items() if k not in ("code", "name")})
        else:
            row = dict(stock, sources=[])
            result.append(row)
            by_code[stock["code"]] = row
    return result
