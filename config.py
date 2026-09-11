"""
config.py
---------
NSE/BSE F&O FUTURES alert bot (stock futures + index futures - NOT
options, see README for why). Uses the SAME Angel One broker account as
your NSE equity and MCX commodity bots (F&O is just another exchange
segment: NFO for NSE derivatives, BFO for BSE derivatives).

120 stock futures (F&O-eligible large/mid caps) + 6 index futures
(Nifty, Bank Nifty, FinNifty, Midcap Nifty, Sensex, Bankex) = 126 total
underlyings, each resolved to its current active near-month contract(s)
dynamically - see fno_futures_feed.py.
"""

import os
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

BOT_ID = "FNO1"
BOT_NAME = "NSE/BSE F&O FUTURES ALERT BOT"
TELEGRAM_DISPLAY_NAME = "@FnOFuturesAlertBot"

# ---------------------------------------------------------------------------
# Stock futures universe (NFO segment, FUTSTK instrument type) - 120
# F&O-eligible large/mid-cap stocks. This list can and does change over
# time as SEBI/NSE periodically adds or removes stocks from F&O eligibility
# based on liquidity/market-cap criteria - if a stock gets removed from
# F&O, it will simply show up in the "no active unexpired contracts found"
# boot warning rather than breaking anything.
#
# Override via bots_config/stock_futures_list.json (flat JSON array of
# stock names, NOT full contract symbols) without touching code.
# ---------------------------------------------------------------------------
_BUILT_IN_STOCK_FUTURES = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "SBIN", "HINDUNILVR", "ITC",
    "BHARTIARTL", "KOTAKBANK", "LT", "AXISBANK", "BAJFINANCE", "MARUTI", "SUNPHARMA", "TITAN",
    "ASIANPAINT", "WIPRO", "ULTRACEMCO", "NESTLEIND", "ADANIPORTS", "ADANIENT", "NTPC",
    "POWERGRID", "ONGC", "JSWSTEEL", "TATASTEEL", "TATAMOTORS", "TECHM", "HCLTECH", "HDFCLIFE",
    "SBILIFE", "BAJAJFINSV", "COALINDIA", "GRASIM", "INDUSINDBK", "BRITANNIA", "CIPLA",
    "DRREDDY", "EICHERMOT", "HINDALCO", "APOLLOHOSP", "BPCL", "DIVISLAB", "HEROMOTOCO", "UPL",
    "M&M", "TATACONSUM", "BAJAJ-AUTO", "ABFRL", "AUBANK", "ADANIGREEN", "ADANIPOWER",
    "AMBUJACEM", "APOLLOTYRE", "ASHOKLEY", "AUROPHARMA", "BANDHANBNK", "BANKBARODA", "BEL",
    "BHEL", "BIOCON", "BOSCHLTD", "CANBK", "CHOLAFIN", "CONCOR", "COROMANDEL", "CUB", "DABUR",
    "DALBHARAT", "DEEPAKNTR", "DIXON", "DLF", "ESCORTS", "EXIDEIND", "FEDERALBNK", "GAIL",
    "GLENMARK", "GMRINFRA", "GODREJCP", "GODREJPROP", "HAL", "HAVELLS", "HINDPETRO",
    "HINDCOPPER", "IDEA", "IDFCFIRSTB", "IEX", "IGL", "INDHOTEL", "INDIAMART", "INDIGO",
    "IRCTC", "JINDALSTEL", "JUBLFOOD", "LICHSGFIN", "LUPIN", "MCDOWELL-N", "MFSL", "MGL",
    "MOTHERSON", "MPHASIS", "MRF", "MUTHOOTFIN", "NATIONALUM", "NAVINFLUOR", "NMDC",
    "OBEROIRLTY", "OFSS", "PAGEIND", "PEL", "PERSISTENT", "PETRONET", "PFC", "PIDILITIND",
    "PIIND", "PNB", "POLYCAB", "RBLBANK", "RECLTD"
]

# Index futures universe - mixed exchange segments: NSE indices trade on
# NFO, BSE indices trade on BFO. This distinction matters for both
# contract resolution AND the getCandleData exchange parameter.
# Override via bots_config/index_futures_list.json (a JSON array of
# {"name":, "exch_seg":} objects) without touching code.
_BUILT_IN_INDEX_FUTURES = [
    {"name": "NIFTY", "exch_seg": "NFO"},
    {"name": "BANKNIFTY", "exch_seg": "NFO"},
    {"name": "FINNIFTY", "exch_seg": "NFO"},
    {"name": "MIDCPNIFTY", "exch_seg": "NFO"},
    {"name": "SENSEX", "exch_seg": "BFO"},
    {"name": "BANKEX", "exch_seg": "BFO"},
]

_INDEX_LIST_PATH = BASE_DIR / "bots_config" / "index_futures_list.json"
_INDEX_FUTURES = _BUILT_IN_INDEX_FUTURES
try:
    with open(_INDEX_LIST_PATH) as f:
        _index_override = json.load(f)
    if isinstance(_index_override, list) and len(_index_override) > 0:
        _INDEX_FUTURES = _index_override
        print(f"[config] Loaded {len(_INDEX_FUTURES)} index futures from override file")
    else:
        print(f"[config] index_futures_list.json empty/invalid, using built-in list ({len(_INDEX_FUTURES)})")
except (FileNotFoundError, json.JSONDecodeError):
    print(f"[config] index_futures_list.json not found, using built-in list ({len(_INDEX_FUTURES)}) - this is fine")

_STOCK_LIST_PATH = BASE_DIR / "bots_config" / "stock_futures_list.json"
STOCK_FUTURES_NAMES = _BUILT_IN_STOCK_FUTURES
try:
    with open(_STOCK_LIST_PATH) as f:
        _override = json.load(f)
    if isinstance(_override, list) and len(_override) > 0:
        STOCK_FUTURES_NAMES = _override
        print(f"[config] Loaded {len(STOCK_FUTURES_NAMES)} stock futures from override file")
    else:
        print(f"[config] stock_futures_list.json empty/invalid, using built-in list ({len(STOCK_FUTURES_NAMES)})")
except (FileNotFoundError, json.JSONDecodeError):
    print(f"[config] stock_futures_list.json not found, using built-in list ({len(STOCK_FUTURES_NAMES)}) - this is fine")

# Combine into the single list resolve_active_contracts() consumes:
# {"name":, "exch_seg":, "instrumenttype":}
UNDERLYINGS = (
    [{"name": s, "exch_seg": "NFO", "instrumenttype": "FUTSTK"} for s in STOCK_FUTURES_NAMES]
    + [{"name": i["name"], "exch_seg": i["exch_seg"], "instrumenttype": "FUTIDX"} for i in _INDEX_FUTURES]
)

# How many nearest unexpired monthly contracts to track per underlying.
# 1 = near month only (highest liquidity, matches how most F&O futures
# volume concentrates). Raise to 2 to also track next-month contracts.
CONTRACTS_PER_UNDERLYING = 1

# ---------------------------------------------------------------------------
# Strict rule thresholds - same as the NSE equity bots. Futures track
# their underlying closely (small basis spread), so equity-style bands
# are appropriate here, unlike commodities/crypto which needed wider bands.
# ---------------------------------------------------------------------------
RSI_LONG_MIN, RSI_LONG_MAX = 40, 65
RSI_SHORT_MIN, RSI_SHORT_MAX = 35, 60
ADX_MIN = 25
VWAP_MAX_DISTANCE_PCT = 2.0
CONFIDENCE_HIGH_PCT = 0.5
CONFIDENCE_MEDIUM_PCT = 1.5
VOLUME_LOOKBACK = 20
EMA_FAST, EMA_SLOW = 9, 21
RSI_PERIOD = 14
ADX_PERIOD = 14

SCORE_ALERT_THRESHOLD = 8
EARLY_SIGNAL_ENABLED = True
EARLY_SCORE_MIN = 6
EARLY_COOLDOWN_HOURS = 1
COOLDOWN_HOURS = 2

CANDLE_INTERVAL = "FIVE_MINUTE"
SCAN_INTERVAL_MINUTES = 15
SCAN_OFFSET_MINUTES = 12     # staggers this bot's scan start relative to other bots
                             # sharing your Telegram/reading attention, so 5 bots
                             # running simultaneously don't all alert in the same
                             # few seconds. Each bot in your 5-bot setup should use
                             # a DIFFERENT offset (e.g. 0, 3, 6, 9, 12) - see the
                             # README for the full staggering scheme.

# F&O trades during normal NSE/BSE equity market hours - NOT the extended
# hours MCX commodities use.
MARKET_OPEN = "09:15"
MARKET_CLOSE = "15:30"
MORNING_RESET_TIME = "09:10"       # also triggers daily contract re-resolution
DAILY_SUMMARY_TIME = "15:45"
ERROR_SUMMARY_TIME = "16:00"
TIMEZONE = "Asia/Kolkata"

MAX_CONSECUTIVE_FAILS_BROKEN = 3
MAX_CONSECUTIVE_FAILS_DISABLE = 5

SQLITE_PATH = str(BASE_DIR / "data" / "alerts.db")

# ---------------------------------------------------------------------------
# Telegram - set in Render's Environment tab, NEVER in this file
# ---------------------------------------------------------------------------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

# ---------------------------------------------------------------------------
# Angel One SmartAPI - SAME credentials as your NSE equity / MCX bots.
# Set in Render's Environment tab, NEVER in this file.
# ---------------------------------------------------------------------------
ANGEL_API_KEY = os.environ.get("ANGEL_API_KEY", "").strip()
ANGEL_CLIENT_CODE = os.environ.get("ANGEL_CLIENT_CODE", "").strip()
ANGEL_PIN = os.environ.get("ANGEL_PIN", "").strip()
ANGEL_TOTP_SECRET = os.environ.get("ANGEL_TOTP_SECRET", "").strip()

ANGEL_INSTRUMENT_MASTER_URL = (
    "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"
)
INSTRUMENT_CACHE_PATH = str(BASE_DIR / "data" / "instrument_master.json")

DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"
PORT = int(os.environ.get("PORT", "10000"))


def validate_and_report():
    print("=" * 60)
    print(f"[config] BOT: {BOT_NAME}")
    print(f"[config] DRY_RUN: {DRY_RUN}")
    print(f"[config] Underlyings: {len(STOCK_FUTURES_NAMES)} stock futures + "
          f"{len(_INDEX_FUTURES)} index futures = {len(UNDERLYINGS)} total, "
          f"{CONTRACTS_PER_UNDERLYING} contract(s) each")
    checks = [
        ("TELEGRAM_TOKEN", TELEGRAM_TOKEN), ("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID),
        ("ANGEL_API_KEY", ANGEL_API_KEY), ("ANGEL_CLIENT_CODE", ANGEL_CLIENT_CODE),
        ("ANGEL_PIN", ANGEL_PIN), ("ANGEL_TOTP_SECRET", ANGEL_TOTP_SECRET),
    ]
    any_missing = False
    for name, value in checks:
        if value:
            print(f"[config]   {name}: SET (length {len(value)})")
        else:
            print(f"[config]   {name}: *** MISSING OR EMPTY *** - set this in Render > Environment")
            any_missing = True
    if any_missing and not DRY_RUN:
        print("[config] WARNING: one or more required env vars are missing and DRY_RUN is false.")
    print("=" * 60)


validate_and_report()
