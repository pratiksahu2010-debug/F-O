# NSE/BSE F&O Futures Alert Bot

Uses the SAME Angel One broker account as your NSE equity and MCX
commodity bots - F&O is just another exchange segment (NFO for NSE
derivatives, BFO for BSE derivatives).

Not investment advice - a technical screening tool. Backtest before
trusting this with real capital.

## ⚠️ Futures only - not options. Here's why.

"F&O" usually means both futures and options, but this bot covers
**futures only**, deliberately. Every bot built so far scores symbols
using VWAP + RSI + ADX + EMA - a framework that measures a *price*
trending relative to volume-weighted fair value. That works for stocks,
crypto, commodities, and futures, because they all track an underlying
price directly.

An option's premium doesn't work that way. It's driven by moneyness
(how far the strike is from the current price), time decay (an option
loses value daily just from the passage of time, independent of price
direction), and implied volatility. VWAP on an option's LTP doesn't mean
"fair value" the way it does on a stock - the same 10-point score would
produce numbers that *look* like a signal without actually measuring
what a real options strategy needs to measure (which strike, how much
time decay risk, whether IV is rich or cheap).

If you want options coverage, that needs a different design from scratch
- strike selection logic, Greeks, IV-relative-value comparisons - not a
retrofit of this scoring system. Happy to build that separately if you
want it; ask and I'll scope it properly rather than bolt it on.

## What this bot covers: 126 futures

- **120 stock futures** - F&O-eligible large/mid-cap NSE stocks (NFO
  segment). This list changes periodically as SEBI/NSE adds or removes
  stocks from F&O eligibility - if one gets removed, it shows up in the
  boot log's "no active unexpired contracts found" warning rather than
  breaking anything.
- **6 index futures** - Nifty, Bank Nifty, FinNifty, Midcap Nifty (NFO
  segment), Sensex, Bankex (BFO segment - different exchange, handled
  correctly by the code).

## Dynamic contract resolution (same engine as the MCX commodity bot)

A stock/index future has a monthly expiry (last Thursday) -
`RELIANCE` isn't tradeable on its own; the real instrument is something
like `RELIANCE26SEP2026FUT`, which expires and gets replaced. This bot
never hardcodes an expiry - `fno_futures_feed.py` reads Angel One's
instrument master, finds the current unexpired contract(s) for every
underlying, and re-resolves automatically every morning at market open.
Verified in testing to correctly: exclude expired contracts, pick the
correct near-month contract, and keep NFO/BFO segments and futures/
options instrument types separate even when names would otherwise
collide.

## Setup

**1. Angel One credentials** - same ones as your NSE/MCX bots. If
running this alongside those bots simultaneously on one account, see the
session-limit caveat in the other bots' READMEs (multiple concurrent
logins on one Angel One account may not be supported - check with them).

**2. Telegram bot:** @BotFather → `/newbot` → save token; message it once
→ get chat id via `getUpdates` or @userinfobot.

**3. Environment variables on Render:**
```
DRY_RUN=false
TELEGRAM_TOKEN=...
TELEGRAM_CHAT_ID=...
ANGEL_API_KEY=...
ANGEL_CLIENT_CODE=...
ANGEL_PIN=...
ANGEL_TOTP_SECRET=...
```
Start with `DRY_RUN=true` first - mock symbols, synthetic data, zero
real Angel One calls.

**4. Deploy:** push to its own repo → Render → New Web Service or
Blueprint → Build `pip install -r requirements.txt` → Start
`gunicorn main:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`.

**5. Verify - in this order:**
```
/health              - confirms service up, shows underlying + resolved contract counts
/resolve_contracts   - forces contract resolution immediately after first real deploy
/telegram_test       - sends a test message
/status              - full diagnostic incl. exactly which contracts resolved
/trigger?force=true  - runs a scan immediately, ignoring market hours
```

Check `/resolve_contracts` right after your first non-DRY_RUN deploy, for
the same reason as the commodity bot - it depends on Angel One's live
instrument master matching the field names this code expects
(`name`, `expiry`, `instrumenttype`, `exch_seg`).

## Market hours

Normal NSE/BSE equity hours: 9:15 AM - 3:30 PM IST, Monday-Friday - NOT
the extended hours MCX commodities use.

## Adjusting coverage

- `config.STOCK_FUTURES_NAMES` / `bots_config/stock_futures_list.json` -
  edit the 120 stock names without touching code.
- `config.CONTRACTS_PER_UNDERLYING` - default 1 (near month only, where
  F&O futures volume concentrates). Raise to 2 to also track next-month.

## Known limitations

- No persistent disk on Render's free/Starter tier - data resets on
  redeploy unless you add a paid disk.
- Instrument master field-name assumptions verified against a synthetic
  test, not Angel One's live data (sandboxed network couldn't reach it) -
  check `/resolve_contracts` after your first real deploy.
- No backtesting included.

## Signal staggering (if running alongside your other bots)

This bot's scans are offset by **12 minutes** within each 15-minute
cycle (`config.SCAN_OFFSET_MINUTES = 12`), so it scans at
:12, :27, :42, :57 past each hour -
never landing on the same minute as your other 4 bots. This spreads out
Telegram alerts across a rotating 3-minute-apart schedule instead of all
5 bots firing (and potentially alerting) in the same few seconds:

```
:00 -> nse_bot1        :03 -> nse_bot2        :06 -> nse_bot3
:09 -> commodity_bot   :12 -> fno_bot          (repeats every 15 min)
```

If you add a 6th bot later, give it `SCAN_OFFSET_MINUTES = 13` or similar
(anything not already used by the other 5) to keep the rotation clean.
