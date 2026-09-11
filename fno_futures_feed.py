"""
fno_futures_feed.py
--------------------
NSE/BSE Futures data via Angel One's SmartAPI - same broker account as
your NSE equity and MCX commodity bots (F&O is just another exchange
segment: NFO for NSE derivatives, BFO for BSE derivatives).

FUTURES ONLY - not options. See the README for why options don't fit
this bot's VWAP/RSI/ADX scoring framework the way futures do.

Like MCX commodities, a stock/index future has a monthly expiry (last
Thursday of the month) - "RELIANCE" isn't directly tradeable, the actual
instrument is "RELIANCE28NOV24FUT", which expires and gets replaced.
This resolves the current active contract(s) per underlying dynamically
every trading day, exactly like the commodity bot - no expiry is ever
hardcoded.

Two instrument types are involved:
  - FUTSTK: stock futures (NFO segment)
  - FUTIDX: index futures (NFO for Nifty/BankNifty/etc, BFO for Sensex/Bankex)
"""

import json
import logging
import threading
import time
from datetime import datetime, timedelta

import pandas as pd
import requests

import config

log = logging.getLogger("fno_feed")

try:
    from SmartApi import SmartConnect
    import pyotp
    SMARTAPI_AVAILABLE = True
except ImportError:
    SMARTAPI_AVAILABLE = False
    log.warning("smartapi-python / pyotp not installed - live F&O data disabled.")


class FnOFuturesFeed:
    def __init__(self):
        self.smart_connect = None
        self.feed_token = None
        self._logged_in = False
        # resolved tradeable symbol -> {"token":..., "base":..., "exch_seg":...}
        self.instrument_map = {}
        self.live_ltp = {}
        self._lock = threading.Lock()

    def login(self) -> bool:
        if config.DRY_RUN:
            log.info("[FNO] DRY_RUN=true, skipping real login")
            return True
        if not SMARTAPI_AVAILABLE:
            log.error("[FNO] SmartApi SDK not installed, cannot log in")
            return False
        if not all([config.ANGEL_API_KEY, config.ANGEL_CLIENT_CODE,
                    config.ANGEL_PIN, config.ANGEL_TOTP_SECRET]):
            log.error("[FNO] Missing one or more ANGEL_* environment variables")
            return False
        try:
            self.smart_connect = SmartConnect(api_key=config.ANGEL_API_KEY)
            totp = pyotp.TOTP(config.ANGEL_TOTP_SECRET).now()
            session = self.smart_connect.generateSession(
                config.ANGEL_CLIENT_CODE, config.ANGEL_PIN, totp
            )
            if not session or not session.get("status"):
                log.error(f"[FNO] Login failed: {session}")
                return False
            self.feed_token = self.smart_connect.getfeedToken()
            self._logged_in = True
            log.info("[FNO] Login successful")
            return True
        except Exception as e:
            log.error(f"[FNO] Login exception: {e}")
            return False

    # ------------------------------------------------------------------ #
    # Contract resolution - same pattern as the MCX commodity bot, but
    # generalized to handle TWO exchange segments (NFO/BFO) and TWO
    # instrument types (FUTSTK for stocks, FUTIDX for indices) in one pass.
    # `underlyings` is a list of dicts: {"name":, "exch_seg":, "instrumenttype":}
    # ------------------------------------------------------------------ #
    def resolve_active_contracts(self, underlyings: list) -> list:
        try:
            cache_path = config.INSTRUMENT_CACHE_PATH
            try:
                with open(cache_path) as f:
                    master = json.load(f)
                import os
                age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
                if age_hours > 20:
                    raise FileNotFoundError("cache stale, forcing re-download")
                log.info(f"[FNO] Using cached instrument master ({len(master)} rows)")
            except (FileNotFoundError, json.JSONDecodeError):
                log.info("[FNO] Downloading fresh instrument master...")
                resp = requests.get(config.ANGEL_INSTRUMENT_MASTER_URL, timeout=60)
                resp.raise_for_status()
                master = resp.json()
                import os
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                with open(cache_path, "w") as f:
                    json.dump(master, f)
                log.info(f"[FNO] Cached fresh instrument master ({len(master)} rows)")
        except Exception as e:
            log.error(f"[FNO] Failed to load instrument master: {e} - cannot resolve contracts")
            return []

        today = datetime.now().date()
        # index by (name, exch_seg, instrumenttype) so stock vs index underlyings
        # with the same name never collide, and NFO vs BFO stay separate
        by_key = {(u["name"], u["exch_seg"], u["instrumenttype"]): [] for u in underlyings}

        for row in master:
            exch = row.get("exch_seg")
            itype = row.get("instrumenttype")
            key = (row.get("name", "").upper(), exch, itype)
            if key not in by_key:
                continue
            expiry_str = row.get("expiry", "")
            try:
                expiry_date = datetime.strptime(expiry_str, "%d%b%Y").date()
            except (ValueError, TypeError):
                continue
            if expiry_date < today:
                continue
            by_key[key].append({
                "token": row["token"],
                "symbol": row.get("symbol", key[0]),
                "expiry": expiry_date,
                "exch_seg": exch,
            })

        resolved_symbols = []
        self.instrument_map = {}
        skipped = []

        for (name, exch_seg, itype), contracts in by_key.items():
            contracts.sort(key=lambda c: c["expiry"])
            chosen = contracts[:config.CONTRACTS_PER_UNDERLYING]
            if not chosen:
                skipped.append(f"{name}({exch_seg}/{itype})")
                continue
            for c in chosen:
                self.instrument_map[c["symbol"]] = {
                    "token": c["token"], "base": name, "exch_seg": c["exch_seg"],
                }
                resolved_symbols.append(c["symbol"])

        if skipped:
            log.warning(
                f"[FNO] No active unexpired contracts found for {len(skipped)} underlying(s): "
                f"{skipped[:15]}{'...' if len(skipped) > 15 else ''}. Common reasons: not "
                f"actually F&O-enabled (SEBI periodically adds/removes stocks from the F&O "
                f"list), delisted, or a naming mismatch with the live instrument master."
            )
        log.info(f"[FNO] Resolved {len(resolved_symbols)} active contracts across "
                 f"{len(underlyings) - len(skipped)}/{len(underlyings)} underlyings")
        return resolved_symbols

    def token_for(self, symbol: str):
        entry = self.instrument_map.get(symbol)
        return entry["token"] if entry else None

    def exch_for(self, symbol: str):
        entry = self.instrument_map.get(symbol)
        return entry["exch_seg"] if entry else "NFO"

    # ------------------------------------------------------------------ #
    # Historical candles (REST)
    # ------------------------------------------------------------------ #
    def get_historical_candles(self, symbol: str, minutes_back: int = 375, retry: bool = True) -> pd.DataFrame:
        if config.DRY_RUN:
            return self._mock_candles(symbol)
        if not self._logged_in:
            log.error(f"[FNO] Not logged in - cannot fetch real candles for {symbol}")
            return pd.DataFrame()

        token = self.token_for(symbol)
        if not token:
            log.error(f"[FNO] No instrument token found for {symbol}")
            return pd.DataFrame()

        try:
            now = datetime.now()
            from_dt = now - timedelta(minutes=minutes_back)
            params = {
                "exchange": self.exch_for(symbol),
                "symboltoken": token,
                "interval": config.CANDLE_INTERVAL,
                "fromdate": from_dt.strftime("%Y-%m-%d %H:%M"),
                "todate": now.strftime("%Y-%m-%d %H:%M"),
            }
            resp = self.smart_connect.getCandleData(params)
            if not resp or not resp.get("status"):
                if retry:
                    log.warning(f"[FNO] getCandleData failed for {symbol}, retrying once in 3s: {resp}")
                    time.sleep(3)
                    return self.get_historical_candles(symbol, minutes_back, retry=False)
                log.error(f"[FNO] getCandleData failed for {symbol} after retry: {resp}")
                return pd.DataFrame()

            rows = resp["data"]
            df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = df[col].astype(float)
            return df.sort_values("timestamp").reset_index(drop=True)
        except Exception as e:
            if retry:
                log.warning(f"[FNO] Exception fetching candles for {symbol}, retrying once in 3s: {e}")
                time.sleep(3)
                return self.get_historical_candles(symbol, minutes_back, retry=False)
            log.error(f"[FNO] Exception fetching candles for {symbol} after retry: {e}")
            return pd.DataFrame()

    def _mock_candles(self, symbol: str) -> pd.DataFrame:
        import numpy as np
        n = 60
        base = 100 + (hash(symbol) % 20000)
        rng = np.random.default_rng(abs(hash(symbol)) % (2**32))
        closes = base + np.cumsum(rng.normal(0, base * 0.003, n))
        highs = closes + rng.uniform(0, base * 0.003, n)
        lows = closes - rng.uniform(0, base * 0.003, n)
        opens = closes - rng.normal(0, base * 0.002, n)
        volumes = rng.integers(1000, 100000, n)
        now = datetime.now()
        timestamps = [(now - timedelta(minutes=5 * (n - i))).isoformat() for i in range(n)]
        return pd.DataFrame({
            "timestamp": timestamps, "open": opens, "high": highs,
            "low": lows, "close": closes, "volume": volumes,
        })

    def get_live_ltp(self, symbol: str):
        with self._lock:
            return self.live_ltp.get(symbol)


feed = FnOFuturesFeed()
