# Evolutionary Trading Bot Arena
## Research, Specification, Junior-Developer Guide, and AI Prompt (Version 2)

*Prepared 3 October 2026. Phase 1 = paper trading only.*

---

# 0. Read this first

**What you are building:** a program called **Arena** that runs **three competing trading bots** on simulated money (50.00 CAD each). Each trading day the bots decide what to buy and sell. Once per week a **Supervisor** ranks the bots by **profit percentage**, eliminates the weakest, and replaces it with a **mutated copy of the strongest**. Nothing here touches real money or a real broker.

**What is in this package**

| Item | What it is |
|---|---|
| This document | Research (Part 1), exact rules (Part 2), step-by-step developer guide (Part 3), troubleshooting (Part 4), test map (Part 5), AI prompt (Part 6), full code listing (Appendix), sources |
| `trading-arena-starter.zip` | The same code as the Appendix, ready to unzip and run |

**Who reads what**
- **Junior developer:** read Part 0, skim Part 1, read Part 2 once, then follow Part 3 step by step. Use Part 4 when something fails.
- **AI coding assistant:** give it this whole document plus the zip, and use the prompt in Part 6.

**Honest status of the code (important):**
- The starter kit was written and tested on **synthetic (fake) price data**. All **32 tests pass**, including a full one-year simulated tournament.
- The two pieces that talk to the internet (Yahoo via `yfinance`, and the optional Alpha Vantage fallback) were **not** tested against the live services. That is why **Step 4 (Day-0 smoke test) is mandatory** before anything else.
- Paper results do not predict live results (see Section 1.5).

**Decisions already made (change them before starting if you disagree)**

| Decision | Choice | Why |
|---|---|---|
| Market | Toronto-listed (TSX) stocks and ETFs, prices in CAD, long-only, one decision per day | No currency conversion, simple legality, matches the owner's CAD budget |
| Paper trading engine | **Our own simulator** (no broker account) | Free, no sign-up, supports 50 CAD accounts and TSX, we control fees and slippage |
| Free data source | **Yahoo Finance via `yfinance`**, saved to local CSV files | Only free option that I found documented as keyless and easy; TSX symbols end in `.TO` (confirmed by the Day-0 test) |
| Optional fallback data | Alpha Vantage free key (small daily quota) | Backup for the daily top-up only |
| Language / tools | Python 3.11+, SQLite, pandas, pytest or unittest | Common, free |
| Real-money trading | **Out of scope** | Needs a separate decision (Part 5) |

---

# 1. Research: paper trading and free data endpoints

*Research date: 3 October 2026. Free tiers change often; re-check a provider's own page before depending on a number.*

## 1.1 Two kinds of "paper trading"

1. **Broker-run simulators.** You open a demo or paper account at a broker. The broker pretends to fill your orders using real prices. Useful if you later want to trade at that broker, but each has sign-up rules and starting balances you cannot always choose.
2. **Your own simulator.** Your program downloads prices and pretends to fill orders itself. You decide the starting cash, fees, and slippage. This is what Arena uses.

## 1.2 Paper-trading options compared

| Option | Cost | Funded account needed? | Has an API? | TSX / CAD? | Fit for 50 CAD bots |
|---|---|---|---|---|---|
| **Own simulator (this project)** | Free | No | n/a | Yes (depends on data) | **Best: chosen** |
| **Alpaca paper-only account** | Free | No. Anyone globally can sign up with an email | Yes (REST) | **No.** US stocks/ETFs/crypto only | Poor now: paper accounts start at $100,000 USD by default and the balance cannot be changed without deleting and recreating the account. Free data is IEX-exchange only. Useful later to rehearse API plumbing |
| **Interactive Brokers (Canada) paper** | Free | **Yes.** The paper account is only available after the live account is approved and funded; the Web API also needs an IBKR Pro account | Yes (TWS or Web API) | Yes | Not now: needs real money in a live account first |
| **Moomoo Canada paper** | Free | Per its own guide, no bank link needed | A reviewer lists an OpenAPI with demo support | Unverified | Possible later; I did not verify details |
| **TradeZero paper** | Free for one month, then needs a funded account | Yes, after 30 days | n/a | US-focused | No |
| **Bank practice accounts** (Scotia iTrade, RBC Direct Investing, Thinkorswim paperMoney) | Free | Sign-up only | No API found | Varies | Manual practice only, not for bots |

**Key facts behind the table**
- Alpaca's own docs say paper-only account holders get only IEX market data, and a third-party review of Alpaca's documentation lists things its paper mode does **not** model: market impact, latency slippage, queue position, regulatory fees, and dividends.
- Alpaca staff said on their forum that Canadians cannot open live accounts because Alpaca lacks Canadian registration, and mentioned a target of regulatory approval around November 2026. Treat that as unconfirmed.
- Interactive Brokers states that the live account must be fully open and funded to use its Web API, even for the associated paper account.

## 1.3 Free market-data endpoints compared

| Source | Free limits (reported) | TSX / Canada coverage | Risks and notes | Role in Arena |
|---|---|---|---|---|
| **Yahoo Finance via `yfinance`** | No key. No official limits; heavy or parallel use triggers HTTP 429 errors or empty replies. Community notes suggest roughly a few hundred requests per day per IP | `.TO` tickers (e.g. `XIU.TO`). **Confirm with Step 4** | **Unofficial**: Yahoo can change things without notice and break the library. The library's own docs say the Yahoo data is for **personal use only** | **Primary** |
| **Alpha Vantage** | Free key. Reviews quote 25 requests/day (older sources say 5 per minute) | A university guide says Canada is covered, but the **TSX symbol format is unverified** | Very small quota | **Optional fallback** for the daily top-up only |
| **Twelve Data** | Free Basic: 800 credits/day, 8 per minute | Free plan documents real-time US markets, forex and crypto. International markets are described as coming with paid tiers | TSX likely needs a paid plan | Not used |
| **Finnhub** | Reviews: 60 calls/minute free | Free-tier scope differs between reviews; TSX unverified | Reviews disagree on delay and history depth | Not used |
| **Tiingo / Massive (formerly Polygon)** | Tiingo about 1,000 requests/day; Massive Basic 5 calls/minute end-of-day | US-focused; TSX unverified | | Not used |
| **Stooq** | Free CSV downloads, no key | TSX coverage unverified | | Not used |

## 1.4 Conclusions

1. **Paper engine:** build our own (Appendix code). No broker account is needed.
2. **Data:** use `yfinance` for the long history and the daily update; cache everything in CSV files so a Yahoo outage never stops a backtest.
3. **Daily schedule:** run once after the TSX close (16:00 Toronto time). The program waits until 17:30 Toronto time so the day's bar is final.
4. **Fallback ladder if Yahoo fails for more than a day:** (a) retry later and update `yfinance` (`pip install -U yfinance`); (b) use Alpha Vantage for the daily top-up after running `scripts/day0_alpha_vantage.py`; (c) escalate to the project owner: options are a paid data plan that includes TSX, or changing the universe to US-listed securities (which needs a spec change for USD/CAD conversion). **Do not improvise a different data source.**
5. **Terms of use:** because Yahoo data via `yfinance` is stated as personal-use only, keep this project private and personal. Do not sell, publish, or redistribute the data or run it as a service.

## 1.5 What paper trading cannot tell you

Simulated fills are always optimistic. Real trading has price impact, delays, partial fills, bid/ask spreads, fees, taxes, and emotions. With 50 CAD, even a small fixed fee per trade can wipe out gains, so the program supports a per-trade commission (test with `--commission 1.00`). Treat all results as learning, not as proof of a profitable strategy.

## 1.6 What is verified and what is not

| Verified by reading provider pages and reviews | Not verified (must be checked by running the code) |
|---|---|
| Alpaca paper-only is open to anyone globally with an email; US-only data; IEX-only free feed; default $100,000 balance | That Yahoo currently serves all 11 `.TO` symbols from your computer (**Step 4**) |
| IBKR paper requires an approved, funded live account | The exact Alpha Vantage format for TSX symbols (`scripts/day0_alpha_vantage.py`) |
| Twelve Data free plan: 800/day, 8/min, US/forex/crypto | Whether any free quota changed after this research date |

---

# 2. Specification (single source of truth)

> Version 2 changes from the first draft are marked **[v2]**. If anything in Part 3 or Part 6 ever disagrees with this Part 2, **Part 2 wins** and you must tell the project owner.

## 2.1 Goal

Build **Arena**: three competing paper-trading bots with one Supervisor. All bots have the same objective, **maximize profit percentage**. Once a week the Supervisor eliminates the weakest bot and replaces it with a mutated copy of the strongest. All trading must be legal (Section 2.11).

## 2.2 Fixed parameters (all live in `config.yaml`)

| Parameter | Value |
|---|---|
| Currency | CAD |
| Starting capital per initial bot | 50.00 CAD |
| Bots alive at any time | 3 |
| Decision frequency | One decision per bot per trading day, made after that day's close |
| Order execution | Market orders filled at the **next trading day's open** adjusted by slippage |
| Slippage | 0.10% against the bot on every fill |
| Commission | 0.00 CAD per trade by default; must also be tested at 1.00 CAD |
| Fractional shares | Allowed; quantity rounded **down** to 4 decimals |
| Direction | Long-only; no shorting, margin, leverage, options, or derivatives |
| Order sizes | Buys are given as a CAD amount ("notional"); sells always sell the **whole** position |
| Weekly evaluation | **[v2]** Performed at the start of processing the **first trading day of the next ISO week**, using the finished week's closing equities. (Same result as "after the last trading day", and needs no holiday calendar.) Liquidation fills at that same day's open |
| Ranking metric | Weekly return **percentage**, never dollars |
| Grace period | A bot cannot be eliminated until it has completed **2** weekly evaluations (`min_weeks_before_elimination = 2`). So the first possible elimination is the evaluation after week 2 |
| Winner eligibility | At least **3 fills** during the week **and** not risk-halted during the week (`min_trades_for_winner = 3`) |
| Top-up policy | `to_50`: a new bot is topped up to 50.00 CAD if the cash it inherits is less than 50.00. Allowed: `none`, `to_50`. In paper mode the top-up is virtual and recorded in the `deposits` table |
| Money arithmetic | `Decimal`, rounded to cents. Never convert money to `float` |
| Randomness | One integer `seed` in config. Mutation uses the seed text `"{seed}:{week}:{parent_id}"`, so results are reproducible |
| Prices | Daily bars, split/dividend-adjusted (`auto_adjust=True`) |

## 2.3 Trading universe (configurable)

`XIU.TO, XIC.TO, VFV.TO, XEQT.TO, ZAG.TO, RY.TO, TD.TO, BNS.TO, ENB.TO, CNQ.TO, SHOP.TO`

A symbol is **tradable on a day** only if (a) it has a price row for that exact day and (b) its 20-day average **dollar volume** (close × volume) is at least 1,000,000 CAD. **[v2] Warm-up:** because of rule (b), nothing is tradable until at least 20 rows exist, so **download at least 400 calendar days of history before the first decision day**.

## 2.4 Architecture (matches the starter kit)

```
trading-arena/
├── config.yaml
├── requirements.txt
├── arena/
│   ├── models.py            # Order, Position, Portfolio, money helpers
│   ├── genomes.py           # gene names, types, initial values, bounds
│   ├── ledger.py            # SQLite tables
│   ├── cli.py               # command line
│   ├── market/
│   │   ├── data.py          # provider (Yahoo) + CSV cache + no-lookahead reads
│   │   ├── paper_broker.py  # simulated fills
│   │   └── alpha_vantage.py # optional fallback
│   ├── bots/                # base.py, momentum.py, mean_reversion.py, rotation.py, factory.py
│   └── supervisor/
│       ├── evolution.py     # mutation + weekly selection (pure functions)
│       └── runner.py        # daily loop, risk, weekly evaluation, births, reports
├── scripts/                 # day0_smoke_test.py, day0_alpha_vantage.py
└── tests/                   # test_core.py, test_backtest.py
```

**No-lookahead rule (critical):** a bot deciding after the close of day D sees data dated ≤ D only. Its orders fill at the **open of the next trading day**.

## 2.5 Bots and genomes

Every bot has `bot_id` (`bot_001`…), `strategy`, `parent_id` (none for the first three), `generation` (0 for the first three), `created_week`, and a **genome** (numbers below). A bot's strategy never changes. **[v2]** Genomes are stored in the database (`bots.genome_json`) and also exported to `genomes/<bot_id>.json` for humans to read.

### Momentum bot (`bot_001`)

| Gene | Type | Initial | Min | Max |
|---|---|---|---|---|
| `lookback_days` | int | 20 | 5 | 60 |
| `entry_threshold` | float | 0.03 | 0.005 | 0.15 |
| `stop_loss` | float | 0.05 | 0.01 | 0.20 |
| `take_profit` | float | 0.08 | 0.02 | 0.40 |
| `max_position_pct` | float | 0.50 | 0.10 | 1.00 |
| `max_open_positions` | int | 2 | 1 | 4 |

Buy a symbol (not held) when its return over `lookback_days` ≥ `entry_threshold`, highest return first (ties by symbol name), until `max_open_positions`. Buy amount = `max_position_pct` × current equity. Sell a held symbol when price ≤ entry × (1 − `stop_loss`), or price ≥ entry × (1 + `take_profit`), or its lookback return is negative.

### Mean-reversion bot (`bot_002`)

| Gene | Type | Initial | Min | Max |
|---|---|---|---|---|
| `ma_days` | int | 20 | 5 | 60 |
| `entry_z` | float | 1.5 | 0.5 | 3.0 |
| `exit_z` | float | 0.0 | -0.5 | 1.0 |
| `stop_loss` | float | 0.06 | 0.01 | 0.20 |
| `max_position_pct` | float | 0.50 | 0.10 | 1.00 |
| `max_open_positions` | int | 2 | 1 | 4 |

z-score = (close − moving average over `ma_days`) ÷ standard deviation over the same window. Buy when z ≤ −`entry_z` (most negative first). Sell when z ≥ `exit_z` or price ≤ entry × (1 − `stop_loss`). Sizing is the same as momentum.

### Rotation bot (`bot_003`)

| Gene | Type | Initial | Min | Max |
|---|---|---|---|---|
| `lookback_days` | int | 30 | 10 | 90 |
| `rebalance_days` | int | 5 | 1 | 20 |
| `top_n` | int | 1 | 1 | 3 |
| `min_return_to_hold` | float | 0.0 | -0.05 | 0.05 |

**[v2]** The bot rebalances on its **first decision day and then every `rebalance_days` trading days after it** (counted from its creation date). On a rebalance day: rank symbols by return over `lookback_days`; the target is the top `top_n` whose return ≥ `min_return_to_hold`; sell held symbols not in the target; buy missing target symbols with equity ÷ `top_n` each. Hold cash if the target is empty.

### Rules common to all bots

- A position cannot be sold on the same day it was bought (minimum holding period: the sell would fill on a later date).
- At most one order per symbol per day (extras are dropped and logged).
- Sells are filled **before** buys on a day; a buy is **shrunk to available cash**; if the result is under 1.00 CAD it is skipped.
- Bots see only price history up to the decision date and their own portfolio.

## 2.6 Supervisor: daily duties

1. Fill yesterday's pending orders at today's open (sells first).
2. Value every bot at today's close: `equity = cash + Σ(shares × close)`; save to `daily_equity`.
3. **Daily-loss halt:** if equity fell more than **10%** versus the previous close, the bot's decisions for the next day may only be sells.
4. **Drawdown halt:** if equity ≤ **60%** of the bot's peak equity, the bot sells everything at the next open and makes no new buys until the next weekly evaluation. **[v2]** The peak resets at every weekly evaluation, so a halted bot cannot be stuck forever.
5. **[v2]** Either halt marks the bot `risk_halted` for that week (this blocks it from being picked as strongest).
6. Drop and log any order that breaks a rule (symbol outside the universe, duplicate symbol, and so on).
7. Write the daily CSV report.

## 2.7 Weekly return

```
E_start = equity at the start of the week (after any funding; a newborn bot's funding amount)
E_end   = equity at the end of the last trading day of the week
return_pct = (E_end - E_start) / E_start * 100      rounded to 2 decimals
```

Funding and top-ups happen only at the start of a bot's life or week, and are part of `E_start`, so they never count as profit.

## 2.8 Weekly evaluation and evolution (exact algorithm)

1. Compute `return_pct` for all 3 active bots; add 1 to each bot's `completed_weeks`.
2. **Eliminable** = bots with `completed_weeks ≥ 2`. **Winner-eligible** = bots with ≥ 3 fills this week and not risk-halted.
3. If either set is empty → **no action this week** (log the reason).
4. **Weakest** = lowest `return_pct` among eliminable. Ties: (a) larger max drawdown, (b) higher bot number.
5. **Strongest** = highest `return_pct` among winner-eligible. Ties: (a) smaller max drawdown, (b) lower bot number.
6. If weakest = strongest → no action (log it). *(This can happen: if the only eligible winner is also the worst eliminable bot, nobody is replaced.)*
7. Mark the weakest `liquidating`; its positions are sold at that day's open. When it holds no positions, its cash is `F`; mark it `eliminated`. (If a sell fails, it is retried the next day.)
8. Create the child: new id, `parent_id` = strongest, `generation` = parent's + 1, same strategy, genome = mutated copy of the parent's **current** genome (2.9), funding = `F`; if `top_up_policy = to_50` and `F < 50.00`, add a deposit of `50.00 − F` (recorded in `deposits`).
9. The strongest bot continues unchanged. Reset every active bot's weekly counters (`E_start` becomes the previous `E_end`).
10. Write the weekly Markdown report (ranking table, decision, child id, genome diff, funding, top-up).

## 2.9 Mutation

For each gene independently, with probability **0.6** the gene is mutated:
- **[v2] Multiplicative genes** (minimum > 0): `new = old × (1 + U(−0.20, +0.20))`.
- **[v2] Additive genes** (minimum ≤ 0: `exit_z`, `min_return_to_hold`): `new = old + U(−0.10, +0.10) × (max − min)`. (Multiplying would leave a 0.0 gene stuck at 0.)
- Clamp to [min, max]. Integer genes are rounded to the nearest integer; if that equals the parent's value, change it by 1 (clamped). **[v2]** Float genes are rounded to 4 decimals.
- If the child equals the parent after all genes are processed, repeat the whole draw.

## 2.10 Ledger (SQLite tables)

`bots`, `orders` (rejects), `fills`, `daily_equity`, `weekly_results`, `deposits`, `events`, and `state` (the saved program state, so a run can resume). See `arena/ledger.py`.

**[v2]** Backtests write to `backtest.db`, live paper trading writes to `arena.db`. They never share a file.

## 2.11 Legal and compliance rules (enforced in code)

1. Cash-account style only: no leverage, margin, shorting, or derivatives.
2. Only symbols in the configured universe that pass the liquidity filter.
3. Market orders only. No wash trades, spoofing, layering, or manipulation.
4. Only public market data. No non-public information of any kind.
5. Phase 1 is paper only. The code contains **no live-broker connection** and the developer must not add one.
6. Every order, fill, and decision is logged.
7. Keep the project personal; do not redistribute Yahoo data. This is not legal or tax advice.

---

# 3. Junior developer guide (follow in order)

> **Rules of the road.** Do not change any rule, number, or formula in Part 2. Do not add a broker connection. Do not skip a step. After each step, check the **"Done when"** line. If a step fails, go to Part 4 (Troubleshooting) before changing anything. If Part 4 does not solve it within an hour, stop and ask the project owner; do not invent a workaround.

## Step 0: What you need (30 minutes)

- A computer (Windows, macOS, or Linux) with internet access.
- **Python 3.11 or newer.** Check: run `python --version` (Windows) or `python3 --version` (macOS/Linux). If it prints a version below 3.11, install a newer one from python.org.
- A code editor (VS Code is fine) and a terminal.
- About 200 MB of free disk space.

**Done when:** `python --version` prints 3.11 or higher.

## Step 1: Create the project and a virtual environment

A *virtual environment* keeps this project's libraries separate from the rest of your computer.

macOS / Linux:
```
unzip trading-arena-starter.zip
cd trading-arena-starter
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows (PowerShell):
```
Expand-Archive trading-arena-starter.zip .
cd trading-arena-starter
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
(If PowerShell refuses to run the activate script, run `Set-ExecutionPolicy -Scope Process RemoteSigned` and try again.)

**Done when:** your terminal prompt starts with `(.venv)` and `pip install` finished without red error text. **Always activate the environment (`source .venv/bin/activate` or `.venv\Scripts\Activate.ps1`) in every new terminal window, and always run commands from the `trading-arena-starter` folder.**

*(If you were not given the zip, create each file from the Appendix at the exact path shown, including the empty `__init__.py` files.)*

## Step 2: Read the layout (15 minutes)

Open the folder in your editor and compare it with the tree in Section 2.4. You will not need to edit code for this task; you will run it and read the output. Open `config.yaml` and read each line (the comments explain them).

**Done when:** you can say in one sentence what `arena/market/paper_broker.py`, `arena/supervisor/evolution.py`, and `arena/supervisor/runner.py` each do.

## Step 3: Run the automated tests (1 minute)

```
python -m unittest discover -s tests -v
```

This runs 32 tests and takes about 35 seconds. A line `refresh failed for BAD: boom (using cache)` is **expected** (a test that simulates a download failure).

**Done when:** the last lines read `Ran 32 tests in ...s` and `OK`. If you see `FAILED` or `ERROR`, go to Part 4. Do not continue until this passes.

## Step 4: Day-0 data check, mandatory (2 minutes)

This tests the one thing I could not test for you: can your computer download TSX prices from Yahoo?

```
python scripts/day0_smoke_test.py
```

Expected output (numbers will differ):
```
XIU.TO: 31 rows, last date 2026-10-02, last close 35.12
VFV.TO: 31 rows, last date 2026-10-02, last close 150.40
RY.TO: 31 rows, last date 2026-10-02, last close 190.10
RESULT: OK
```

**Done when:** it prints `RESULT: OK`. If it prints `PROBLEM`, go to Part 4, entry "Day-0 check fails". **Do not go on until this works.** *(Optional: `ALPHA_VANTAGE_KEY=yourkey python scripts/day0_alpha_vantage.py` tests the fallback provider; skip it unless the owner asks.)*

## Step 5: Download historical prices (about 5 minutes)

```
python -m arena.cli fetch --start 2025-01-01
```

This downloads about 21 months of daily prices for 11 symbols into the `data_cache/` folder, with a 1-second pause between requests so Yahoo does not throttle you. Failed symbols are logged as `refresh failed for ...` and keep any older cached data.

Check what you got:
```
python -c "import pandas as pd, glob; [print(f, len(pd.read_csv(f))) for f in sorted(glob.glob('data_cache/*.csv'))]"
```

**Done when:** you see 11 files, each with roughly 430 or more rows. If any symbol is missing or has far fewer rows, re-run the fetch command once; if it is still missing, go to Part 4.

## Step 6: Run your first backtest (about 1 minute)

A backtest replays history day by day through the same code that live paper trading uses.

```
python -m arena.cli backtest --start 2026-03-02 --end 2026-09-30 --fresh
```

**Done when:** it prints `backtest finished; see reports_backtest/ and backtest.db`. Then confirm:
- `reports_backtest/` contains one `daily_YYYY-MM-DD.csv` per trading day and one `weekly_YYYY-Www.md` per finished week.
- `genomes_backtest/` contains `bot_001.json`, `bot_002.json`, `bot_003.json` and more files for children.

## Step 7: Read the results (30 minutes)

1. Open one weekly report, for example `reports_backtest/weekly_2026-W14.md`. You should see a ranking table and a **Decision** line. After week 1 the decision is always *no action* (nobody has finished the 2-week grace period). From week 2 onward you should see lines such as *eliminate bot_00X; clone-and-mutate bot_00Y*, then an **Evolution** section listing the child, its funding, and its **genome diff**.
2. Inspect the database. With the `sqlite3` tool, or with Python:

```
python - << 'EOF'
import sqlite3
db = sqlite3.connect("backtest.db")
print("Weekly results (latest 6):")
for row in db.execute("SELECT week, bot_id, e_start, e_end, return_pct, trades, rank FROM weekly_results ORDER BY week DESC, rank LIMIT 6"):
    print(row)
print("Evolutions:", db.execute("SELECT count(*) FROM events WHERE type='evolution'").fetchone()[0])
print("Deposits (top-ups):", db.execute("SELECT * FROM deposits").fetchall())
print("Lineage:")
for row in db.execute("SELECT bot_id, parent_id, generation, strategy, status FROM bots ORDER BY bot_id"):
    print(row)
EOF
```
(On Windows PowerShell, save the Python lines in a file `inspect.py` and run `python inspect.py`.)

3. Sanity checks you must confirm and write down: there are always exactly 3 `active` bots after each weekly evaluation; no bot has negative cash; every child has a different genome from its parent.

**Done when:** you have written a short note (5 to 10 lines) with the number of evolutions, how many bots were created, and which strategy family appears most often among winners.

## Step 8: Fee and robustness tests (20 minutes)

Rankings from one week are noisy, so test the system under different conditions. Each command overwrites `backtest.db` (`--fresh`).

```
python -m arena.cli backtest --start 2026-03-02 --end 2026-09-30 --fresh --commission 1.00
python -m arena.cli backtest --start 2026-03-02 --end 2026-09-30 --fresh --seed 1
python -m arena.cli backtest --start 2026-03-02 --end 2026-09-30 --fresh --seed 2
python -m arena.cli backtest --start 2025-09-01 --end 2026-02-27 --fresh
```
After each run, repeat the Step 7 database query and note the final equities and lineage. (Move or copy `backtest.db` and `reports_backtest/` first if you want to keep each run.)

**Done when:** you have a small table with one row per run: window, seed, commission, number of evolutions, best final equity. State in one sentence whether the same strategy family wins in different windows (if winners change randomly, the weekly selection is mostly luck; report this to the owner).

## Step 9: Start live paper trading (10 minutes)

Live paper trading uses real daily prices but fake money, and keeps its own database `arena.db`.

```
python -m arena.cli init
python -m arena.cli run-day
```
`init` creates the three bots (50.00 CAD each). `run-day` downloads the latest prices and processes every finished trading day it has not processed yet. It waits until **17:30 Toronto time** before treating a day as finished.

**Done when:** `run-day` prints `processed YYYY-MM-DD` (or `nothing new to process` on a weekend). Running it twice on the same day is safe: it only processes new days.

## Step 10: Schedule it to run every weekday (15 minutes)

Run `python -m arena.cli run-day` once every weekday at about **18:30 Toronto time**.

- **Linux / macOS (cron):** run `crontab -e` and add (replace the path). Make sure your computer's clock is set to Toronto time.
```
30 18 * * 1-5 cd /home/you/trading-arena-starter && .venv/bin/python -m arena.cli run-day >> run.log 2>&1
```
- **Windows (Task Scheduler):** Create Basic Task → Trigger: Daily, 6:30 PM (then edit the trigger to run only Monday to Friday) → Action: Start a program → Program: `C:\path\trading-arena-starter\.venv\Scripts\python.exe` → Arguments: `-m arena.cli run-day` → Start in: `C:\path\trading-arena-starter`.

If the computer was off for several days, the next run catches up on all missed trading days in order. The computer must be on and online at run time.

**Done when:** the next weekday after 18:30, `run.log` (or Task Scheduler history) shows a successful run and a new `reports/daily_YYYY-MM-DD.csv` exists.

## Step 11: Weekly routine (10 minutes per week)

Every Monday evening, open the newest `reports/weekly_*.md` and check: (1) 3 active bots, (2) the decision is explained, (3) if a child was created, its genome diff is listed, (4) nothing in `run.log` says `ERROR`. Record the week's result in your log. Top-ups are virtual in paper mode: just note the amount from the `deposits` table.

## Step 12: Backups (5 minutes per week)

Copy `arena.db`, `genomes/`, `reports/`, and `config.yaml` to a dated backup folder every Friday. The price cache `data_cache/` can be rebuilt with `fetch`.

## Step 13: Finish Phase 1

Phase 1 is complete when: all 32 tests pass; the Step 7 and Step 8 notes are written; live paper trading has run for **at least 8 weeks** without unexplained errors; and you have sent the owner a one-page summary (final equities, lineage, number of evolutions, fee-stress result, and your honest view on whether winners were consistent or random). **Do not connect any broker or move to real money.**

## Time estimate

Steps 0 to 8 take about one working day. Steps 9 to 12 take about 1 hour to set up, then 15 minutes per week.

---

# 4. Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| `ModuleNotFoundError: No module named 'arena'` | Not in the project folder, or ran a file instead of `-m` | `cd` to `trading-arena-starter` and use `python -m arena.cli ...`. Scripts in `scripts/` must also be run from the project folder |
| `ModuleNotFoundError: No module named 'pandas'` (or `yfinance`, `yaml`) | Virtual environment not active | Activate it (Step 1) and run `pip install -r requirements.txt` |
| Tests fail right after unzipping | Modified files, or Python older than 3.11 | Re-extract the zip into a fresh folder; check `python --version` |
| **Day-0 check fails**: `giving up on XIU.TO: empty result` | Yahoo throttling, no internet, VPN/proxy, or an out-of-date `yfinance` | Check internet; run `pip install -U yfinance`; turn off VPN; wait 30 to 60 minutes (HTTP 429 means "too many requests") and retry. If it still fails after 24 hours, follow the fallback ladder in Section 1.4 and tell the owner |
| Day-0 check says rows < 15 | Partial download | Run it again |
| `zoneinfo.ZoneInfoNotFoundError` | Windows lacks the time-zone database | `pip install tzdata` |
| `backtest.db already exists. Re-run with --fresh` | Safety check | Add `--fresh` (this deletes the old backtest database) |
| `RuntimeError: already initialised` | `arena.db` already has bots | You ran `init` twice. To start over on purpose: back up, then delete `arena.db`, `genomes/`, `reports/`, and run `init` again |
| Backtest shows no trades in the first weeks | Not enough price history before the start date (nothing is tradable until ≥ 20 rows exist, and lookbacks need up to 90) | Fetch from at least 400 calendar days before the backtest start (Step 5 uses `--start 2025-01-01`) |
| Weekly report says *no action* | Normal. Reasons: grace period (the very first evaluation), no bot made ≥ 3 fills, the best bot was risk-halted, or weakest = strongest | Read the reason printed on the Decision line. Only report it if it repeats for many weeks |
| Many `order_rejected` events | Normal: duplicate symbol, minimum holding period, order under 1.00 CAD after shrinking | Open the `events` table; unusual reasons such as `no open price` mean missing data for that day |
| A trading day is missing from reports | Market holiday, or no symbol had a price row that day | Compare with the TSX holiday calendar. If it is not a holiday, run `fetch` again |
| Prices differ slightly from a broker website | Prices are split/dividend-adjusted | Expected |
| `sqlite3.OperationalError: database is locked` | Another run is using the database | Wait a minute; make sure only one scheduled job exists |
| Numbers look off by tiny amounts | Someone used `float` for money | Use `Decimal` everywhere; never edit money code without running the tests |
| `run-day` says `nothing new to process` on a weekday evening | It is before 17:30 Toronto time, or data for today is not yet published | Run again later |

---

# 5. Acceptance tests and phase gate

## 5.1 Map of the 13 acceptance criteria to automated tests

| # | Requirement | Test(s) that prove it |
|---|---|---|
| 1 | 3 bots, 50.00 CAD each, no positions at start | `RulesTests.test_initial_state` |
| 2 | No lookahead | `DataTests.test_history_never_returns_future_rows`, `BacktestTests.test_full_year_invariants` (data spy) |
| 3 | Fill price = next open ± 0.10%; commission applied | `BrokerTests.test_buy_fill_slippage_and_cash`, `test_commission_applied` |
| 4 | Return uses `E_start` including funding; top-up is not profit | `FundingMathTests.test_topup_does_not_change_return`, `RulesTests.test_funding_with_topup` |
| 5 | Ranking by percentage (+6%, −2%, −12% example) | `EvolutionTests.test_example_from_spec`, `test_percentage_not_dollars` |
| 6 | Grace period | `EvolutionTests.test_grace_period` |
| 7 | Winner needs ≥ 3 fills and no halt | `EvolutionTests.test_winner_needs_trades_and_no_halt` |
| 8 | Tie-breaks | `EvolutionTests.test_tie_breaks`, `test_same_bot_skips` |
| 9 | Mutation valid, different, reproducible | `EvolutionTests.test_mutation_valid_and_reproducible`, `test_zero_valued_genes_can_move` |
| 10 | Funding: 44.00 → 6.00 top-up; 57.00 → none | `RulesTests.test_funding_with_topup`, `test_funding_without_topup` |
| 11 | Always exactly 3 live bots | `BacktestTests.test_full_year_invariants` |
| 12 | Risk halts at the thresholds | `RulesTests.test_risk_halts` |
| 13 | Long backtest runs and is reproducible | `BacktestTests.test_reproducible_with_same_seed`, `test_commission_run_completes`, `test_resume_from_saved_state`, plus your real-data run in Step 6 |

## 5.2 Gate before anyone considers real money (not part of this task)

All of these must be true, and the **project owner** must decide separately: (1) at least 8 weeks of live paper results; (2) several backtest windows and seeds showing winners that are consistent rather than random; (3) results still acceptable with a 1.00 CAD commission; (4) the chosen broker's API terms explicitly allow automated trading for individuals in Canada; (5) the owner has checked Canadian securities rules and the CRA's treatment of frequent trading; (6) a size limit the owner is fully willing to lose.

---

# 6. Master prompt for an AI coding assistant

Give the assistant **this entire document and the zip file**, then paste the prompt below as the instruction.

```
ROLE
You are a careful senior Python engineer acting as a project operator. You will set up, verify, and run a paper-trading project called Arena using a provided, already-tested starter kit. You write nothing from scratch unless a step below tells you to.

INPUTS YOU HAVE
1) The document "Evolutionary Trading Bot Arena" (the SPEC is Part 2; the step-by-step is Part 3; troubleshooting is Part 4).
2) trading-arena-starter.zip (the reference implementation, 32 passing tests on synthetic data).

SINGLE SOURCE OF TRUTH
Part 2 of the document. Never change a rule, number, formula, or algorithm in it. If you believe the SPEC contradicts itself or is missing something, STOP and ask me in one numbered list. Otherwise do not ask questions.

HARD RULES
1. Paper trading only. Never add code that places real orders, never request or store broker credentials or API keys other than an optional free Alpha Vantage key I give you.
2. Money uses Decimal. Never use float for money.
3. No lookahead: a bot sees data dated on or before the decision date only; orders fill at the next trading day's open.
4. Ranking and elimination use weekly return percentage, exactly as in Section 2.7 and 2.8.
5. Do not invent results. Every number you report must come from output you actually produced by running a command. If a command cannot run (for example no internet), say so plainly and stop that step.
6. Do not add features, strategies, symbols, or data sources that are not in the SPEC.
7. If you change any file, re-run the full test suite and show the result.

PROCESS (do the steps in order and report after each one)
Step A. Unzip the kit, create a virtual environment, install requirements.txt. Show the commands and the final line of pip output.
Step B. Run: python -m unittest discover -s tests -v. Show the last 5 lines. It must say "Ran 32 tests" and "OK". If not, fix only what is broken, following Part 4, and show the diff.
Step C. Run: python scripts/day0_smoke_test.py. Show the full output. If it does not say RESULT: OK, apply Part 4 (Day-0 check fails), then stop and report; do not continue and do not substitute another data source.
Step D. Run: python -m arena.cli fetch --start 2025-01-01. Then print the row count of every CSV in data_cache/. Report any symbol with fewer than 400 rows.
Step E. Run the first backtest: python -m arena.cli backtest --start 2026-03-02 --end 2026-09-30 --fresh. Show the final lines of output.
Step F. Inspect backtest.db and reports_backtest/: report the number of evolutions, bots created, deposits, the lineage (bot_id, parent_id, generation, strategy, status), and the last three weekly reports in full.
Step G. Run the robustness set from Part 3 Step 8 (commission 1.00; seeds 1 and 2; the earlier window 2025-09-01 to 2026-02-27). Present one table: window, seed, commission, evolutions, best final equity, and which strategy family held the top rank most often.
Step H. Write a final summary of at most 15 lines: what ran, what passed, the numbers, whether winners looked consistent or random, any warnings, and the Phase-1 completion status per Part 3 Step 13. Do not recommend real-money trading.

OUTPUT FORMAT
For each step: the exact commands you ran, the key output, then one line "Result: PASS" or "Result: FAIL (reason)". End with the Step H summary and a checklist mapping the 13 acceptance criteria in Part 5.1 to the test names, each marked Done or Not done.

DEFINITION OF DONE
All 32 tests pass; the Day-0 check printed RESULT: OK; the backtests ran; every reported number came from real command output; no rule in Part 2 was changed.
```

---

# Appendix: complete code listing

All files are also in `trading-arena-starter.zip`. If you type files by hand, create the empty files `arena/__init__.py`, `arena/market/__init__.py`, `arena/bots/__init__.py`, and `arena/supervisor/__init__.py` as well.

### A1. `config.yaml`

```yaml
# Arena configuration. Change values here, never in code.
currency: CAD
start_capital: "50.00"          # string on purpose (Decimal)
slippage: "0.001"               # 0.10% against the bot on every fill
commission: "0.00"              # also test with "1.00"
top_up_policy: to_50            # none | to_50
min_weeks_before_elimination: 2
min_trades_for_winner: 3
daily_loss_halt: 0.10
drawdown_halt_floor: 0.60
min_dollar_volume: 1000000
seed: 42
data_cache_dir: data_cache
report_dir: reports
genome_dir: genomes
universe: [XIU.TO, XIC.TO, VFV.TO, XEQT.TO, ZAG.TO, RY.TO, TD.TO, BNS.TO, ENB.TO, CNQ.TO, SHOP.TO]
```

### A2. `requirements.txt`

```text
pandas>=2.2
numpy>=1.26
pyyaml>=6.0
yfinance>=0.2.50
requests>=2.31
tzdata>=2024.1
pytest>=8.0
```

### A3. `arena/models.py`

```python
"""Shared data types and money helpers."""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Dict, Optional

CENT = Decimal("0.01")
SHARE_STEP = Decimal("0.0001")


def money(x) -> Decimal:
    """Round any number to cents (half-up). Always build Decimals from str(), never from float."""
    return Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)


def floor_shares(x) -> Decimal:
    """Round a share quantity DOWN to 4 decimal places."""
    return Decimal(str(x)).quantize(SHARE_STEP, rounding=ROUND_DOWN)


@dataclass
class Order:
    symbol: str
    side: str                              # "buy" or "sell"
    notional: Optional[Decimal] = None     # CAD to spend (buys only)
    # Sells always sell the WHOLE position. Partial sells are not allowed in v1.


@dataclass
class Position:
    shares: Decimal
    avg_cost: Decimal                      # average fill price incl. slippage
    entry_date: date


@dataclass
class Portfolio:
    cash: Decimal
    positions: Dict[str, Position] = field(default_factory=dict)

    def equity(self, last_prices: Dict[str, Decimal]) -> Decimal:
        total = self.cash
        for sym, pos in self.positions.items():
            total += pos.shares * Decimal(str(last_prices[sym]))
        return money(total)
```

### A4. `arena/genomes.py`

```python
"""Gene definitions: (type, initial, min, max). Source of truth for initial bots, bounds and mutation."""
GENES = {
    "momentum": {
        "lookback_days":      ("int",   20,   5,     60),
        "entry_threshold":    ("float", 0.03, 0.005, 0.15),
        "stop_loss":          ("float", 0.05, 0.01,  0.20),
        "take_profit":        ("float", 0.08, 0.02,  0.40),
        "max_position_pct":   ("float", 0.50, 0.10,  1.00),
        "max_open_positions": ("int",   2,    1,     4),
    },
    "mean_reversion": {
        "ma_days":            ("int",   20,   5,     60),
        "entry_z":            ("float", 1.5,  0.5,   3.0),
        "exit_z":             ("float", 0.0,  -0.5,  1.0),
        "stop_loss":          ("float", 0.06, 0.01,  0.20),
        "max_position_pct":   ("float", 0.50, 0.10,  1.00),
        "max_open_positions": ("int",   2,    1,     4),
    },
    "rotation": {
        "lookback_days":      ("int",   30,   10,    90),
        "rebalance_days":     ("int",   5,    1,     20),
        "top_n":              ("int",   1,    1,     3),
        "min_return_to_hold": ("float", 0.0,  -0.05, 0.05),
    },
}

INITIAL_BOTS = [("bot_001", "momentum"), ("bot_002", "mean_reversion"), ("bot_003", "rotation")]


def initial_genome(strategy: str) -> dict:
    return {name: spec[1] for name, spec in GENES[strategy].items()}
```

### A5. `arena/ledger.py`

```python
"""SQLite ledger (Section 9 of the spec). Plain sqlite3, no ORM."""
import json
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS bots(bot_id TEXT PRIMARY KEY, strategy TEXT, parent_id TEXT, generation INTEGER,
    genome_json TEXT, created_week TEXT, status TEXT, eliminated_week TEXT);
CREATE TABLE IF NOT EXISTS orders(order_id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id TEXT, symbol TEXT,
    side TEXT, notional TEXT, decision_date TEXT, status TEXT, reject_reason TEXT);
CREATE TABLE IF NOT EXISTS fills(fill_id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id TEXT, symbol TEXT, side TEXT,
    fill_date TEXT, price TEXT, quantity TEXT, commission TEXT);
CREATE TABLE IF NOT EXISTS daily_equity(bot_id TEXT, date TEXT, cash TEXT, positions_value TEXT, equity TEXT,
    PRIMARY KEY(bot_id, date));
CREATE TABLE IF NOT EXISTS weekly_results(bot_id TEXT, week TEXT, e_start TEXT, e_end TEXT, return_pct TEXT,
    trades INTEGER, max_drawdown TEXT, risk_halted INTEGER, rank INTEGER, PRIMARY KEY(bot_id, week));
CREATE TABLE IF NOT EXISTS deposits(deposit_id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id TEXT, week TEXT,
    amount TEXT, reason TEXT);
CREATE TABLE IF NOT EXISTS events(event_id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, type TEXT, detail_json TEXT);
CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY, value TEXT);
"""


class Ledger:
    def __init__(self, path: str):
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def q(self, sql, args=()):
        cur = self.db.execute(sql, args)
        self.db.commit()
        return cur

    def event(self, type_: str, **detail):
        self.q("INSERT INTO events(timestamp,type,detail_json) VALUES(?,?,?)",
               (datetime.now(timezone.utc).isoformat(), type_, json.dumps(detail, default=str)))

    def put_state(self, key, obj):
        self.q("INSERT OR REPLACE INTO state(key,value) VALUES(?,?)", (key, json.dumps(obj, default=str)))

    def get_state(self, key, default=None):
        row = self.db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default
```

### A6. `arena/market/data.py`

```python
"""Data layer: provider (network) + CSV cache (disk) + date-clipped reads (no lookahead)."""
import logging
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

log = logging.getLogger("arena.data")
COLS = ["open", "high", "low", "close", "volume"]


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Return df with lowercase OHLCV columns, tz-naive midnight DatetimeIndex, sorted, clean."""
    df = df.copy()
    df.columns = [str(c).lower() for c in df.columns]
    df = df[COLS]
    idx = pd.to_datetime(df.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    df.index = idx.normalize()
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df.dropna()
    df = df[(df["close"] > 0) & (df["open"] > 0)]
    return df


class YahooProvider:
    """Free, unofficial (yfinance). Personal use only. Can break or rate-limit without notice."""
    def __init__(self, pause_seconds: float = 1.0, retries: int = 3):
        self.pause, self.retries = pause_seconds, retries

    def fetch(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        import yfinance as yf                                   # imported here so tests need no network lib
        last_err: Optional[Exception] = None
        for attempt in range(self.retries):
            try:
                df = yf.Ticker(symbol).history(start=start.isoformat(),
                                               end=(end + timedelta(days=1)).isoformat(),  # end is exclusive
                                               auto_adjust=True, actions=False)
                time.sleep(self.pause)
                if df is None or df.empty:
                    raise ValueError(f"empty result for {symbol}")
                return normalize(df)
            except Exception as e:                              # noqa: BLE001
                last_err = e
                wait = 5 * (3 ** attempt)                       # 5s, 15s, 45s
                log.warning("fetch %s failed (%s); retry in %ss", symbol, e, wait)
                time.sleep(wait)
        raise RuntimeError(f"giving up on {symbol}: {last_err}")


class DataStore:
    def __init__(self, cache_dir: str, provider=None):
        self.dir = Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.provider = provider
        self._mem: Dict[str, pd.DataFrame] = {}

    def _path(self, symbol: str) -> Path:
        return self.dir / f"{symbol.replace('/', '_')}.csv"

    def load(self, symbol: str) -> pd.DataFrame:
        if symbol in self._mem:
            return self._mem[symbol]
        p = self._path(symbol)
        if p.exists():
            df = normalize(pd.read_csv(p, index_col=0, parse_dates=True))
        else:
            df = pd.DataFrame(columns=COLS, index=pd.DatetimeIndex([]))
        self._mem[symbol] = df
        return df

    def refresh(self, symbols: List[str], start: date, end: date) -> None:
        """Download [start, end] for each symbol and merge into the cache. Failures keep the old cache."""
        for s in symbols:
            try:
                new = self.provider.fetch(s, start, end)
            except Exception as e:                              # noqa: BLE001
                log.error("refresh failed for %s: %s (using cache)", s, e)
                continue
            merged = pd.concat([self.load(s), new])
            merged = merged[~merged.index.duplicated(keep="last")].sort_index()
            merged.to_csv(self._path(s))
            self._mem[s] = merged

    def history(self, symbol: str, end: date) -> pd.DataFrame:
        """NO-LOOKAHEAD: only rows dated <= end are ever returned."""
        return self.load(symbol).loc[:pd.Timestamp(end)]

    def open_price(self, symbol: str, day: date):
        df = self.load(symbol)
        ts = pd.Timestamp(day)
        return None if ts not in df.index else df.loc[ts, "open"]

    def trading_days(self, symbols: List[str], start: date, end: date) -> List[pd.Timestamp]:
        """Union of dates present in the cache for the given symbols (TSX holidays are simply absent)."""
        days = set()
        for s in symbols:
            idx = self.load(s).loc[pd.Timestamp(start):pd.Timestamp(end)].index
            days |= set(idx)
        return sorted(days)


def is_liquid(df: pd.DataFrame, min_dollar_volume: float = 1_000_000.0, window: int = 20) -> bool:
    if len(df) < window:
        return False
    return float((df["close"] * df["volume"]).iloc[-window:].mean()) >= min_dollar_volume
```

### A7. `arena/market/paper_broker.py`

```python
"""Paper broker: fills orders at the next day's open +/- slippage. No lookahead."""
from datetime import date
from decimal import Decimal
from typing import Dict, List

from arena.models import Order, Portfolio, Position, floor_shares, money


class PaperBroker:
    def __init__(self, slippage: Decimal = Decimal("0.001"), commission: Decimal = Decimal("0.00"),
                 min_order: Decimal = Decimal("1.00")):
        self.slippage = slippage
        self.commission = commission
        self.min_order = min_order

    def execute(self, portfolio: Portfolio, orders: List[Order], fill_date: date,
                opens: Dict[str, Decimal]):
        """Fill `orders` at `fill_date` open prices. Sells are processed BEFORE buys.
        Returns (fills, rejects). Each fill is a dict; each reject is (order, reason)."""
        fills, rejects, seen = [], [], set()
        ordered = [o for o in orders if o.side == "sell"] + [o for o in orders if o.side == "buy"]
        for o in ordered:
            if o.symbol in seen:
                rejects.append((o, "duplicate order for symbol on same day"))
                continue
            seen.add(o.symbol)
            if o.symbol not in opens:
                rejects.append((o, "no open price"))
                continue
            px = Decimal(str(opens[o.symbol]))
            if o.side == "sell":
                pos = portfolio.positions.get(o.symbol)
                if pos is None:
                    rejects.append((o, "nothing to sell"))
                    continue
                if pos.entry_date >= fill_date:
                    rejects.append((o, "minimum holding period"))
                    continue
                fill_px = px * (Decimal("1") - self.slippage)
                gross = pos.shares * fill_px
                portfolio.cash = money(portfolio.cash + gross - self.commission)
                fills.append(dict(symbol=o.symbol, side="sell", price=fill_px, shares=pos.shares,
                                  commission=self.commission, date=fill_date))
                del portfolio.positions[o.symbol]
            else:
                if o.symbol in portfolio.positions:
                    rejects.append((o, "already holding"))
                    continue
                spend = min(o.notional, portfolio.cash)          # shrink to available cash
                if spend - self.commission < self.min_order:
                    rejects.append((o, "order under minimum after shrink"))
                    continue
                fill_px = px * (Decimal("1") + self.slippage)
                shares = floor_shares((spend - self.commission) / fill_px)
                if shares <= 0:
                    rejects.append((o, "zero shares"))
                    continue
                cost = shares * fill_px + self.commission
                portfolio.cash = money(portfolio.cash - cost)
                portfolio.positions[o.symbol] = Position(shares, fill_px, fill_date)
                fills.append(dict(symbol=o.symbol, side="buy", price=fill_px, shares=shares,
                                  commission=self.commission, date=fill_date))
        return fills, rejects
```

### A8. `arena/market/alpha_vantage.py`

```python
"""OPTIONAL fallback provider (Alpha Vantage). UNVERIFIED for TSX symbols: run scripts/day0_alpha_vantage.py first.
Free tier is small (about 25 requests/day per third-party reviews), so use it only for the daily top-up
(outputsize=compact returns about the latest 100 daily bars) and keep yfinance for the long warm-up download."""
import io
import time
from datetime import date

import pandas as pd

from arena.market.data import normalize


class AlphaVantageProvider:
    def __init__(self, api_key: str, symbol_map: dict, pause_seconds: float = 13.0):
        self.key, self.map, self.pause = api_key, symbol_map, pause_seconds   # 13s keeps us under 5 calls/min

    def fetch(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        import requests
        av_symbol = self.map.get(symbol, symbol)
        r = requests.get("https://www.alphavantage.co/query", timeout=30, params=dict(
            function="TIME_SERIES_DAILY", symbol=av_symbol, outputsize="compact",
            datatype="csv", apikey=self.key))
        r.raise_for_status()
        if r.text.lstrip().startswith("{"):                     # JSON error / rate-limit message instead of CSV
            raise RuntimeError(f"Alpha Vantage said: {r.text[:200]}")
        df = pd.read_csv(io.StringIO(r.text), index_col="timestamp", parse_dates=True)
        time.sleep(self.pause)
        return normalize(df).loc[pd.Timestamp(start):pd.Timestamp(end)]
```

### A9. `arena/bots/base.py`

```python
"""Bot interface. A bot sees ONLY: price history up to the decision date, its own portfolio, the date."""
from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
from typing import Dict, List

import pandas as pd

from arena.models import Order, Portfolio


class Bot(ABC):
    def __init__(self, bot_id: str, genome: dict, created_date: date):
        self.bot_id = bot_id
        self.genome = genome
        self.created_date = created_date

    @abstractmethod
    def decide(self, history: Dict[str, pd.DataFrame], portfolio: Portfolio, today: date) -> List[Order]:
        """history[symbol] = DataFrame indexed by date (ascending, last row == today),
        columns: open, high, low, close, volume. Only tradable symbols are included."""

    # ---- helpers shared by all strategies ----
    @staticmethod
    def last_close(history: Dict[str, pd.DataFrame]) -> Dict[str, Decimal]:
        return {s: Decimal(str(df["close"].iloc[-1])) for s, df in history.items()}

    def equity(self, history, portfolio) -> Decimal:
        prices = self.last_close(history)
        # a held symbol may be missing from `history` (became illiquid): value it at 0 is wrong,
        # so the runner must always pass held symbols too. See runner guide.
        return portfolio.equity(prices)
```

### A10. `arena/bots/momentum.py`

```python
from decimal import Decimal
from typing import Dict, List

import pandas as pd

from arena.bots.base import Bot
from arena.models import Order, Portfolio


class MomentumBot(Bot):
    def decide(self, history: Dict[str, pd.DataFrame], portfolio: Portfolio, today) -> List[Order]:
        g = self.genome
        lb = int(g["lookback_days"])
        prices = self.last_close(history)
        equity = portfolio.equity(prices)
        orders: List[Order] = []

        def lookback_return(df):
            if len(df) <= lb:
                return None
            return float(df["close"].iloc[-1] / df["close"].iloc[-1 - lb] - 1.0)

        # 1) exits
        selling = set()
        for sym, pos in portfolio.positions.items():
            px = prices[sym]
            r = lookback_return(history[sym])
            stop = pos.avg_cost * (Decimal("1") - Decimal(str(g["stop_loss"])))
            take = pos.avg_cost * (Decimal("1") + Decimal(str(g["take_profit"])))
            if px <= stop or px >= take or (r is not None and r < 0):
                orders.append(Order(sym, "sell"))
                selling.add(sym)

        # 2) entries
        open_after_exits = len(portfolio.positions) - len(selling)
        slots = int(g["max_open_positions"]) - open_after_exits
        if slots > 0:
            cands = []
            for sym, df in history.items():
                if sym in portfolio.positions:
                    continue
                r = lookback_return(df)
                if r is not None and r >= g["entry_threshold"]:
                    cands.append((r, sym))
            cands.sort(key=lambda t: (-t[0], t[1]))               # highest return first, ties by symbol
            notional = equity * Decimal(str(g["max_position_pct"]))
            for _, sym in cands[:slots]:
                orders.append(Order(sym, "buy", notional=notional.quantize(Decimal("0.01"))))
        return orders
```

### A11. `arena/bots/mean_reversion.py`

```python
from decimal import Decimal
from typing import Dict, List

import pandas as pd

from arena.bots.base import Bot
from arena.models import Order, Portfolio


class MeanReversionBot(Bot):
    @staticmethod
    def zscore(df: pd.DataFrame, n: int):
        if len(df) < n:
            return None
        w = df["close"].iloc[-n:]
        sd = float(w.std(ddof=0))
        if sd == 0:
            return None
        return float((w.iloc[-1] - w.mean()) / sd)

    def decide(self, history: Dict[str, pd.DataFrame], portfolio: Portfolio, today) -> List[Order]:
        g = self.genome
        n = int(g["ma_days"])
        prices = self.last_close(history)
        equity = portfolio.equity(prices)
        orders: List[Order] = []
        selling = set()

        for sym, pos in portfolio.positions.items():
            z = self.zscore(history[sym], n)
            stop = pos.avg_cost * (Decimal("1") - Decimal(str(g["stop_loss"])))
            if prices[sym] <= stop or (z is not None and z >= g["exit_z"]):
                orders.append(Order(sym, "sell"))
                selling.add(sym)

        slots = int(g["max_open_positions"]) - (len(portfolio.positions) - len(selling))
        if slots > 0:
            cands = []
            for sym, df in history.items():
                if sym in portfolio.positions:
                    continue
                z = self.zscore(df, n)
                if z is not None and z <= -g["entry_z"]:
                    cands.append((z, sym))                         # most negative z first
            cands.sort(key=lambda t: (t[0], t[1]))
            notional = (equity * Decimal(str(g["max_position_pct"]))).quantize(Decimal("0.01"))
            for _, sym in cands[:slots]:
                orders.append(Order(sym, "buy", notional=notional))
        return orders
```

### A12. `arena/bots/rotation.py`

```python
from decimal import Decimal
from typing import Dict, List

import pandas as pd

from arena.bots.base import Bot
from arena.models import Order, Portfolio


class RotationBot(Bot):
    def decide(self, history: Dict[str, pd.DataFrame], portfolio: Portfolio, today) -> List[Order]:
        g = self.genome
        lb, every, top_n = int(g["lookback_days"]), int(g["rebalance_days"]), int(g["top_n"])
        if not history:
            return []
        any_df = next(iter(history.values()))
        days_alive = int((any_df.index >= pd.Timestamp(self.created_date)).sum())   # includes today
        if days_alive < 1 or (days_alive - 1) % every != 0:
            return []                                          # not a rebalance day

        prices = self.last_close(history)
        equity = portfolio.equity(prices)
        scored = []
        for sym, df in history.items():
            if len(df) > lb:
                r = float(df["close"].iloc[-1] / df["close"].iloc[-1 - lb] - 1.0)
                if r >= g["min_return_to_hold"]:
                    scored.append((r, sym))
        scored.sort(key=lambda t: (-t[0], t[1]))
        target = [s for _, s in scored[:top_n]]

        orders: List[Order] = [Order(s, "sell") for s in portfolio.positions if s not in target]
        notional = (equity / Decimal(top_n)).quantize(Decimal("0.01"))
        orders += [Order(s, "buy", notional=notional) for s in target if s not in portfolio.positions]
        return orders
```

### A13. `arena/bots/factory.py`

```python
from arena.bots.mean_reversion import MeanReversionBot
from arena.bots.momentum import MomentumBot
from arena.bots.rotation import RotationBot

STRATEGIES = {"momentum": MomentumBot, "mean_reversion": MeanReversionBot, "rotation": RotationBot}


def make_bot(bot_id, strategy, genome, created_date):
    return STRATEGIES[strategy](bot_id, genome, created_date)
```

### A14. `arena/supervisor/evolution.py`

```python
"""Mutation + weekly selection. Pure functions: easy to unit-test."""
import random
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional, Tuple

from arena.genomes import GENES

MUTATE_PROB = 0.6
MULT_RANGE = 0.20      # multiplicative genes: value * (1 + U(-0.20, +0.20))
ADD_RANGE = 0.10       # additive genes (min <= 0): value + U(-0.10, +0.10) * (max - min)


def mutate_genome(strategy: str, parent: dict, seed_text: str) -> dict:
    """Return a mutated copy. Deterministic for the same (parent, seed_text)."""
    rng = random.Random(seed_text)
    specs = GENES[strategy]
    for _attempt in range(1000):
        child = dict(parent)
        for name, (typ, _init, lo, hi) in specs.items():
            if rng.random() >= MUTATE_PROB:
                continue                                   # gene not selected
            old = parent[name]
            if lo <= 0:                                    # additive gene (value may be 0 or negative)
                new = old + rng.uniform(-ADD_RANGE, ADD_RANGE) * (hi - lo)
            else:
                new = old * (1 + rng.uniform(-MULT_RANGE, MULT_RANGE))
            new = min(max(new, lo), hi)
            if typ == "int":
                new = int(round(new))
                if new == old:                             # force a change of at least 1
                    step = rng.choice([-1, 1])
                    new = old + step
                    if not (lo <= new <= hi):
                        new = old - step
                new = min(max(new, lo), hi)
            else:
                new = round(new, 4)
            child[name] = new
        if child != parent:
            return child
    raise RuntimeError("could not produce a different child")   # practically unreachable


@dataclass
class WeekResult:
    bot_id: str
    e_start: Decimal
    e_end: Decimal
    trades: int
    max_drawdown: Decimal          # fraction, e.g. 0.07 = 7 percent, measured inside the week
    risk_halted: bool
    completed_weeks: int           # including this week

    @property
    def return_pct(self) -> Decimal:
        r = (self.e_end - self.e_start) / self.e_start * Decimal("100")
        return r.quantize(Decimal("0.01"))

    @property
    def number(self) -> int:
        return int(self.bot_id.split("_")[1])


def decide_evolution(results: List[WeekResult], min_weeks: int = 2,
                     min_trades: int = 3) -> Tuple[Optional[str], Optional[str], str]:
    """Returns (weakest_id, strongest_id, reason). If no action: (None, None, reason)."""
    eliminable = [r for r in results if r.completed_weeks >= min_weeks]
    winners = [r for r in results if r.trades >= min_trades and not r.risk_halted]
    if not eliminable:
        return None, None, "no bot has completed the minimum weeks yet"
    if not winners:
        return None, None, "no bot is eligible to be strongest"
    weakest = sorted(eliminable, key=lambda r: (r.return_pct, -r.max_drawdown, -r.number))[0]
    strongest = sorted(winners, key=lambda r: (-r.return_pct, r.max_drawdown, r.number))[0]
    if weakest.bot_id == strongest.bot_id:
        return None, None, "weakest and strongest are the same bot"
    return weakest.bot_id, strongest.bot_id, "ok"


def max_drawdown(equities: List[Decimal]) -> Decimal:
    """Largest peak-to-trough fall as a fraction, over the given equity series (include week-start equity)."""
    peak, worst = equities[0], Decimal("0")
    for e in equities:
        peak = max(peak, e)
        if peak > 0:
            worst = max(worst, (peak - e) / peak)
    return worst
```

### A15. `arena/supervisor/runner.py`

```python
"""The Supervisor: runs the daily loop and the weekly evaluation. Same code for backtest and live-paper."""
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pandas as pd
from typing import Dict, List, Optional

from arena.bots.factory import make_bot
from arena.genomes import INITIAL_BOTS, initial_genome
from arena.ledger import Ledger
from arena.market.data import DataStore, is_liquid
from arena.market.paper_broker import PaperBroker
from arena.models import Order, Portfolio, Position, money
from arena.supervisor.evolution import WeekResult, decide_evolution, max_drawdown, mutate_genome


def week_key(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


@dataclass
class BotState:
    bot_id: str
    strategy: str
    genome: dict
    parent_id: Optional[str]
    generation: int
    created_date: str
    created_week: str
    status: str = "active"                       # active | liquidating | eliminated
    cash: str = "0.00"
    positions: Dict[str, dict] = field(default_factory=dict)   # sym -> {shares, avg_cost, entry_date}
    pending: List[dict] = field(default_factory=list)          # orders to fill at next open
    week_start_equity: str = "0.00"
    week_equities: List[str] = field(default_factory=list)
    week_trades: int = 0
    risk_halted_week: bool = False
    dd_halt: bool = False
    peak: str = "0.00"
    prev_close_equity: str = "0.00"
    completed_weeks: int = 0
    daily_halt_today: bool = False

    def portfolio(self) -> Portfolio:
        return Portfolio(cash=D(self.cash), positions={
            s: Position(D(p["shares"]), D(p["avg_cost"]), date.fromisoformat(p["entry_date"]))
            for s, p in self.positions.items()})

    def save_portfolio(self, pf: Portfolio):
        self.cash = str(pf.cash)
        self.positions = {s: dict(shares=str(p.shares), avg_cost=str(p.avg_cost), entry_date=p.entry_date.isoformat())
                          for s, p in pf.positions.items()}


class Arena:
    def __init__(self, cfg: dict, store: DataStore, db_path: str, report_dir: str = "reports",
                 genome_dir: str = "genomes"):
        self.cfg, self.store = cfg, store
        self.ledger = Ledger(db_path)
        self.broker = PaperBroker(D(str(cfg["slippage"])), D(str(cfg["commission"])))
        self.report_dir, self.genome_dir = Path(report_dir), Path(genome_dir)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.genome_dir.mkdir(parents=True, exist_ok=True)
        self.bots: Dict[str, BotState] = {}
        self.meta = {"last_day": None, "next_bot_number": 1, "pending_births": []}
        self._load()

    # ---------- persistence ----------
    def _load(self):
        saved = self.ledger.get_state("bots")
        if saved:
            self.bots = {k: BotState(**v) for k, v in saved.items()}
            self.meta = self.ledger.get_state("meta")

    def _save(self):
        self.ledger.put_state("bots", {k: b.__dict__ for k, b in self.bots.items()})
        self.ledger.put_state("meta", self.meta)

    # ---------- setup ----------
    def init_bots(self, start: date):
        if self.bots:
            raise RuntimeError("already initialised")
        cap = money(self.cfg["start_capital"])
        for bot_id, strat in INITIAL_BOTS:
            self._create_bot(bot_id, strat, initial_genome(strat), None, 0, start, cap)
            self.meta["next_bot_number"] = max(self.meta["next_bot_number"], int(bot_id.split("_")[1]) + 1)
        self._save()

    def _create_bot(self, bot_id, strat, genome, parent, gen, created: date, funding):
        st = BotState(bot_id, strat, genome, parent, gen, created.isoformat(), week_key(created),
                      cash=str(funding), week_start_equity=str(funding), peak=str(funding),
                      prev_close_equity=str(funding))
        self.bots[bot_id] = st
        self.ledger.q("INSERT INTO bots VALUES(?,?,?,?,?,?,?,?)",
                      (bot_id, strat, parent, gen, json.dumps(genome), st.created_week, "active", None))
        (self.genome_dir / f"{bot_id}.json").write_text(json.dumps(
            dict(bot_id=bot_id, strategy=strat, parent_id=parent, generation=gen, genome=genome), indent=2))
        self.ledger.event("bot_created", bot_id=bot_id, parent=parent, funding=str(funding))

    # ---------- main entry ----------
    def process_day(self, day: date):
        last = self.meta["last_day"]
        if last and week_key(date.fromisoformat(last)) != week_key(day):
            self._weekly_evaluation(week_key(date.fromisoformat(last)))
        self._fill(day)
        self._value_and_risk(day)
        self._decide(day)
        self._daily_report(day)
        self.meta["last_day"] = day.isoformat()
        self._save()

    def backtest(self, start: date, end: date):
        for ts in self.store.trading_days(self.cfg["universe"], start, end):
            self.process_day(ts.date())

    # ---------- phases ----------
    def _fill(self, day: date):
        for st in list(self.bots.values()):
            if st.status == "eliminated" or not st.pending:
                continue
            orders = [Order(p["symbol"], p["side"], D(p["notional"]) if p["notional"] else None) for p in st.pending]
            opens = {}
            for o in orders:
                px = self.store.open_price(o.symbol, day)
                if px is not None:
                    opens[o.symbol] = D(str(px))
            pf = st.portfolio()
            fills, rejects = self.broker.execute(pf, orders, day, opens)
            st.save_portfolio(pf)
            st.week_trades += len(fills)
            for f in fills:
                self.ledger.q("INSERT INTO fills(bot_id,symbol,side,fill_date,price,quantity,commission) VALUES(?,?,?,?,?,?,?)",
                              (st.bot_id, f["symbol"], f["side"], day.isoformat(), str(f["price"]), str(f["shares"]), str(f["commission"])))
            for o, why in rejects:
                self.ledger.q("INSERT INTO orders(bot_id,symbol,side,notional,decision_date,status,reject_reason) VALUES(?,?,?,?,?,?,?)",
                              (st.bot_id, o.symbol, o.side, str(o.notional), day.isoformat(), "rejected", why))
                self.ledger.event("order_rejected", bot_id=st.bot_id, symbol=o.symbol, reason=why)
            st.pending = []
        self._process_births(day)

    def _process_births(self, day: date):
        still = []
        for b in self.meta["pending_births"]:
            src, parent = self.bots[b["source"]], self.bots[b["parent"]]
            if src.positions:                                    # liquidation incomplete: retry tomorrow
                src.pending = [dict(symbol=s, side="sell", notional=None) for s in src.positions]
                still.append(b)
                continue
            freed = money(src.cash)
            src.cash, src.status = "0.00", "eliminated"
            self.ledger.q("UPDATE bots SET status='eliminated', eliminated_week=? WHERE bot_id=?", (b["week"], src.bot_id))
            funding, topup = freed, D("0.00")
            if self.cfg["top_up_policy"] == "to_50" and freed < money(self.cfg["start_capital"]):
                topup = money(self.cfg["start_capital"]) - freed
                funding = money(self.cfg["start_capital"])
            new_id = f"bot_{self.meta['next_bot_number']:03d}"
            self.meta["next_bot_number"] += 1
            genome = mutate_genome(parent.strategy, parent.genome, f"{self.cfg['seed']}:{b['week']}:{parent.bot_id}")
            self._create_bot(new_id, parent.strategy, genome, parent.bot_id, parent.generation + 1, day, funding)
            if topup > 0:
                self.ledger.q("INSERT INTO deposits(bot_id,week,amount,reason) VALUES(?,?,?,?)",
                              (new_id, week_key(day), str(topup), "top-up to start capital"))
            self.ledger.event("evolution", eliminated=src.bot_id, parent=parent.bot_id, child=new_id,
                              freed=str(freed), topup=str(topup))
            diff = {k: (parent.genome[k], genome[k]) for k in genome if genome[k] != parent.genome[k]}
            with open(self.report_dir / f"weekly_{b['week']}.md", "a") as f:
                f.write(f"\n## Evolution (executed {day})\n- Eliminated: {src.bot_id}\n- Parent: {parent.bot_id}\n"
                        f"- Child: {new_id} (generation {parent.generation + 1}), funding {funding} CAD "
                        f"(freed {freed}, top-up {topup})\n- Genome diff (parent -> child): {diff}\n")
        self.meta["pending_births"] = still

    def _closes(self, st: BotState, day: date) -> Dict[str, D]:
        out = {}
        for s in st.positions:
            h = self.store.history(s, day)
            out[s] = D(str(h["close"].iloc[-1]))
        return out

    def _value_and_risk(self, day: date):
        for st in self.bots.values():
            if st.status != "active":
                continue
            pf = st.portfolio()
            eq = pf.equity(self._closes(st, day))
            self.ledger.q("INSERT OR REPLACE INTO daily_equity VALUES(?,?,?,?,?)",
                          (st.bot_id, day.isoformat(), str(pf.cash), str(money(eq - pf.cash)), str(eq)))
            st.week_equities.append(str(eq))
            st.peak = str(max(D(st.peak), eq))
            st.daily_halt_today = False
            prev = D(st.prev_close_equity)
            if prev > 0 and (prev - eq) / prev > D(str(self.cfg["daily_loss_halt"])):
                st.daily_halt_today, st.risk_halted_week = True, True
                self.ledger.event("daily_loss_halt", bot_id=st.bot_id, day=day.isoformat())
            if eq <= D(str(self.cfg["drawdown_halt_floor"])) * D(st.peak) and not st.dd_halt:
                st.dd_halt, st.risk_halted_week = True, True
                self.ledger.event("drawdown_halt", bot_id=st.bot_id, day=day.isoformat())
            st.prev_close_equity = str(eq)

    def _decide(self, day: date):
        ts = pd.Timestamp(day)
        tradable = []
        for s in self.cfg["universe"]:
            h = self.store.history(s, day)
            if len(h) and h.index[-1] == ts and is_liquid(h, self.cfg["min_dollar_volume"]):
                tradable.append(s)
        for st in self.bots.values():
            if st.status != "active":
                continue
            pf = st.portfolio()
            syms = list(dict.fromkeys(tradable + list(st.positions)))
            history = {s: self.store.history(s, day) for s in syms if len(self.store.history(s, day))}
            bot = make_bot(st.bot_id, st.strategy, st.genome, date.fromisoformat(st.created_date))
            orders = bot.decide(history, pf, day) if history else []   # warm-up: nothing tradable yet
            if st.dd_halt:
                orders = [Order(s, "sell") for s in st.positions]
            elif st.daily_halt_today:
                orders = [o for o in orders if o.side == "sell"]
            clean, seen = [], set()
            for o in orders:
                if o.symbol not in self.cfg["universe"] or o.symbol in seen:
                    self.ledger.event("order_dropped", bot_id=st.bot_id, symbol=o.symbol)
                    continue
                seen.add(o.symbol)
                clean.append(dict(symbol=o.symbol, side=o.side, notional=str(o.notional) if o.notional else None))
            st.pending = clean

    def _weekly_evaluation(self, week: str):
        active = [s for s in self.bots.values() if s.status == "active"]
        results = []
        for st in active:
            st.completed_weeks += 1
            e_start = D(st.week_start_equity)
            e_end = D(st.week_equities[-1]) if st.week_equities else e_start
            dd = max_drawdown([e_start] + [D(x) for x in st.week_equities])
            results.append(WeekResult(st.bot_id, e_start, e_end, st.week_trades, dd, st.risk_halted_week, st.completed_weeks))
        ranked = sorted(results, key=lambda r: (-r.return_pct, r.number))
        for rank, r in enumerate(ranked, 1):
            self.ledger.q("INSERT OR REPLACE INTO weekly_results VALUES(?,?,?,?,?,?,?,?,?)",
                          (r.bot_id, week, str(r.e_start), str(r.e_end), str(r.return_pct), r.trades,
                           str(r.max_drawdown), int(r.risk_halted), rank))
        weakest, strongest, reason = decide_evolution(results, self.cfg["min_weeks_before_elimination"],
                                                      self.cfg["min_trades_for_winner"])
        lines = [f"# Weekly report {week}\n", "| Rank | Bot | Strategy | Gen | E_start | E_end | Return % | Trades | Max DD | Halted |",
                 "|---|---|---|---|---|---|---|---|---|---|"]
        for rank, r in enumerate(ranked, 1):
            st = self.bots[r.bot_id]
            lines.append(f"| {rank} | {r.bot_id} | {st.strategy} | {st.generation} | {r.e_start} | {r.e_end} | "
                         f"{r.return_pct} | {r.trades} | {(r.max_drawdown * 100).quantize(D('0.01'))}% | {r.risk_halted} |")
        if weakest:
            lines.append(f"\nDecision: eliminate {weakest}; clone-and-mutate {strongest}. "
                         "Liquidation happens at the next trading day's open.")
            self.bots[weakest].status = "liquidating"
            self.bots[weakest].pending = [dict(symbol=s, side="sell", notional=None) for s in self.bots[weakest].positions]
            self.meta["pending_births"].append(dict(source=weakest, parent=strongest, week=week))
            self.ledger.event("weekly_decision", week=week, weakest=weakest, strongest=strongest)
        else:
            lines.append(f"\nDecision: no action this week ({reason}).")
            self.ledger.event("weekly_no_action", week=week, reason=reason)
        (self.report_dir / f"weekly_{week}.md").write_text("\n".join(lines) + "\n")
        for st in active:                                        # reset weekly counters
            e_end = D(st.week_equities[-1]) if st.week_equities else D(st.week_start_equity)
            st.week_start_equity, st.week_equities, st.week_trades = str(e_end), [], 0
            st.risk_halted_week, st.dd_halt, st.peak = False, False, str(e_end)

    def _daily_report(self, day: date):
        rows = ["bot_id,strategy,equity,positions,dd_halt,risk_halted_week"]
        for st in self.bots.values():
            if st.status == "active" and st.week_equities:
                rows.append(f"{st.bot_id},{st.strategy},{st.week_equities[-1]},{'|'.join(st.positions)},{st.dd_halt},{st.risk_halted_week}")
        (self.report_dir / f"daily_{day.isoformat()}.csv").write_text("\n".join(rows) + "\n")
```

### A16. `arena/cli.py`

```python
"""Command line entry point:  python -m arena.cli <command> ..."""
import argparse
import logging
import os
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

import yaml

from arena.market.data import DataStore, YahooProvider
from arena.supervisor.runner import Arena

WARMUP_DAYS = 400      # calendar days of history needed before the first decision day


def load_cfg(path):
    return yaml.safe_load(open(path))


def build(cfg, db, fetcher=True, tag=""):
    store = DataStore(cfg["data_cache_dir"], YahooProvider() if fetcher else None)
    return store, Arena(cfg, store, db, f"{cfg['report_dir']}{tag}", f"{cfg['genome_dir']}{tag}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="arena")
    ap.add_argument("--config", default="config.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch");    f.add_argument("--start", required=True); f.add_argument("--end", default=date.today().isoformat())
    i = sub.add_parser("init");     i.add_argument("--start", default=date.today().isoformat())
    b = sub.add_parser("backtest"); b.add_argument("--start", required=True); b.add_argument("--end", required=True)
    b.add_argument("--fresh", action="store_true", help="delete backtest.db first")
    b.add_argument("--seed", type=int, help="override config seed (for robustness runs)")
    b.add_argument("--commission", help='override commission per trade, e.g. "1.00"')
    sub.add_parser("run-day")
    r = sub.add_parser("report");   r.add_argument("--week", required=True)
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_cfg(a.config)

    if a.cmd == "fetch":
        store, _ = build(cfg, ":memory:")
        store.refresh(cfg["universe"], date.fromisoformat(a.start), date.fromisoformat(a.end))
    elif a.cmd == "init":
        _, arena = build(cfg, "arena.db")
        arena.init_bots(date.fromisoformat(a.start))
        print("initialised 3 bots with", cfg["start_capital"], cfg["currency"], "each")
    elif a.cmd == "backtest":
        if a.seed is not None:
            cfg["seed"] = a.seed
        if a.commission is not None:
            cfg["commission"] = a.commission
        if a.fresh and os.path.exists("backtest.db"):
            os.remove("backtest.db")
        if os.path.exists("backtest.db"):
            raise SystemExit("backtest.db already exists. Re-run with --fresh to overwrite it.")
        store, arena = build(cfg, "backtest.db", fetcher=False, tag="_backtest")
        start, end = date.fromisoformat(a.start), date.fromisoformat(a.end)
        arena.init_bots(start)
        arena.backtest(start, end)
        print("backtest finished; see reports_backtest/ and backtest.db")
    elif a.cmd == "run-day":
        store, arena = build(cfg, "arena.db")
        now = datetime.now(ZoneInfo("America/Toronto"))
        # Only process a day once its daily bar is final: TSX closes 16:00 ET; we wait until 17:30 ET.
        end_day = now.date() if now.time() >= time(17, 30) else now.date() - timedelta(days=1)
        last = arena.meta["last_day"]
        first_new = date.fromisoformat(last) + timedelta(days=1) if last else end_day
        store.refresh(cfg["universe"], end_day - timedelta(days=WARMUP_DAYS), end_day)
        days = store.trading_days(cfg["universe"], first_new, end_day)
        for ts in days:
            arena.process_day(ts.date())
            print("processed", ts.date())
        if not days:
            print("nothing new to process")
    elif a.cmd == "report":
        print(Path(cfg["report_dir"], f"weekly_{a.week}.md").read_text())


if __name__ == "__main__":
    main()
```

### A17. `scripts/day0_smoke_test.py`

```python
"""Day-0 check: can this computer download TSX daily data from Yahoo (via yfinance)?
Run:  python scripts/day0_smoke_test.py
Exit code 0 = OK, 1 = problem (read the printed message)."""
import sys
from datetime import date, timedelta

sys.path.insert(0, ".")
from arena.market.data import YahooProvider  # noqa: E402

SYMBOLS = ["XIU.TO", "VFV.TO", "RY.TO"]
ok = True
prov = YahooProvider(pause_seconds=1.0, retries=2)
for s in SYMBOLS:
    try:
        df = prov.fetch(s, date.today() - timedelta(days=45), date.today())
        print(f"{s}: {len(df)} rows, last date {df.index[-1].date()}, last close {df['close'].iloc[-1]:.2f}")
        if len(df) < 15:
            print(f"  WARNING: expected about 20+ rows for 45 calendar days, got {len(df)}")
            ok = False
    except Exception as e:  # noqa: BLE001
        print(f"{s}: FAILED -> {e}")
        ok = False
print("RESULT:", "OK" if ok else "PROBLEM (see troubleshooting table in the guide)")
sys.exit(0 if ok else 1)
```

### A18. `scripts/day0_alpha_vantage.py`

```python
"""OPTIONAL. Tests whether your free Alpha Vantage key returns Toronto-listed symbols and in which format.
Run:  ALPHA_VANTAGE_KEY=yourkey python scripts/day0_alpha_vantage.py
Read the output, then fill `av_symbol_map` in config.yaml with the format that returned data."""
import os, sys
from datetime import date, timedelta
sys.path.insert(0, ".")
from arena.market.alpha_vantage import AlphaVantageProvider  # noqa: E402

key = os.environ.get("ALPHA_VANTAGE_KEY")
if not key:
    sys.exit("Set ALPHA_VANTAGE_KEY first (free key from alphavantage.co).")
for candidate in ["RY.TRT", "TSX:RY", "RY.TO"]:               # try three possible formats, one call each
    try:
        df = AlphaVantageProvider(key, {}).fetch(candidate, date.today() - timedelta(days=30), date.today())
        print(f"{candidate}: {len(df)} rows, last {df.index[-1].date() if len(df) else 'n/a'}")
    except Exception as e:  # noqa: BLE001
        print(f"{candidate}: no data -> {str(e)[:120]}")
```

### A19. `tests/test_core.py`

```python
import tempfile, unittest
from datetime import date
from decimal import Decimal as D

import numpy as np
import pandas as pd

from arena.bots.factory import make_bot
from arena.genomes import GENES, INITIAL_BOTS, initial_genome
from arena.market.data import DataStore, is_liquid, normalize
from arena.market.paper_broker import PaperBroker
from arena.models import Order, Portfolio, Position, money
from arena.supervisor.evolution import WeekResult, decide_evolution, max_drawdown, mutate_genome


def frame(closes, start="2026-01-05", vol=1_000_000, opens=None):
    idx = pd.bdate_range(start, periods=len(closes))
    c = np.array(closes, dtype=float)
    o = np.array(opens, dtype=float) if opens is not None else c
    return pd.DataFrame({"open": o, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": vol}, index=idx)


class BrokerTests(unittest.TestCase):
    def test_buy_fill_slippage_and_cash(self):
        pf = Portfolio(cash=D("50.00"))
        b = PaperBroker()
        fills, rej = b.execute(pf, [Order("AAA", "buy", D("25.00"))], date(2026, 1, 6), {"AAA": D("10")})
        self.assertEqual(rej, [])
        self.assertEqual(fills[0]["price"], D("10.01"))                # 10 * 1.001
        self.assertEqual(fills[0]["shares"], D("2.4975"))              # floor(25/10.01, 4dp)
        self.assertEqual(pf.cash, money(D("50") - D("2.4975") * D("10.01")))

    def test_commission_applied(self):
        pf = Portfolio(cash=D("50.00"))
        b = PaperBroker(commission=D("1.00"))
        b.execute(pf, [Order("AAA", "buy", D("50.00"))], date(2026, 1, 6), {"AAA": D("10")})
        self.assertLessEqual(pf.cash, D("0.01"))
        self.assertGreaterEqual(pf.cash, D("0.00"))

    def test_buy_shrinks_to_cash(self):
        pf = Portfolio(cash=D("20.00"))
        fills, _ = PaperBroker().execute(pf, [Order("AAA", "buy", D("100.00"))], date(2026, 1, 6), {"AAA": D("10")})
        self.assertEqual(len(fills), 1)
        self.assertGreaterEqual(pf.cash, D("0"))

    def test_skip_when_under_one_dollar(self):
        pf = Portfolio(cash=D("0.50"))
        fills, rej = PaperBroker().execute(pf, [Order("AAA", "buy", D("10.00"))], date(2026, 1, 6), {"AAA": D("10")})
        self.assertEqual(fills, []); self.assertEqual(len(rej), 1)

    def test_sells_before_buys_and_min_holding(self):
        pf = Portfolio(cash=D("0.00"), positions={"AAA": Position(D("5"), D("10"), date(2026, 1, 5))})
        orders = [Order("BBB", "buy", D("40.00")), Order("AAA", "sell")]
        fills, rej = PaperBroker().execute(pf, orders, date(2026, 1, 6), {"AAA": D("10"), "BBB": D("20")})
        self.assertEqual([f["side"] for f in fills], ["sell", "buy"])   # sells first frees cash
        self.assertIn("BBB", pf.positions)
        # same-day sell of a just-bought position is rejected
        fills2, rej2 = PaperBroker().execute(pf, [Order("BBB", "sell")], date(2026, 1, 6), {"BBB": D("20")})
        self.assertEqual(fills2, []); self.assertEqual(rej2[0][1], "minimum holding period")

    def test_duplicate_symbol_rejected(self):
        pf = Portfolio(cash=D("50.00"))
        fills, rej = PaperBroker().execute(pf, [Order("AAA", "buy", D("10")), Order("AAA", "buy", D("10"))],
                                           date(2026, 1, 6), {"AAA": D("10")})
        self.assertEqual(len(fills), 1); self.assertEqual(len(rej), 1)


class DataTests(unittest.TestCase):
    def test_history_never_returns_future_rows(self):
        with tempfile.TemporaryDirectory() as d:
            ds = DataStore(d)
            ds._mem["AAA"] = frame(range(1, 31))
            h = ds.history("AAA", date(2026, 1, 20))
            self.assertLessEqual(h.index.max(), pd.Timestamp("2026-01-20"))

    def test_refresh_merges_and_survives_failure(self):
        class P:
            def fetch(self, s, a, b):
                if s == "BAD":
                    raise RuntimeError("boom")
                return frame([10, 11, 12])
        with tempfile.TemporaryDirectory() as d:
            ds = DataStore(d, P())
            ds.refresh(["AAA", "BAD"], date(2026, 1, 5), date(2026, 1, 9))
            self.assertEqual(len(ds.load("AAA")), 3)
            self.assertEqual(len(ds.load("BAD")), 0)
            ds2 = DataStore(d, P())                                     # reload from disk
            self.assertEqual(len(ds2.load("AAA")), 3)

    def test_normalize_handles_tz_and_names(self):
        idx = pd.date_range("2026-01-05", periods=3, tz="America/Toronto")
        raw = pd.DataFrame({"Open": [1, 2, 3.], "High": [1, 2, 3.], "Low": [1, 2, 3.], "Close": [1, 2, 3.],
                            "Volume": [1, 1, 1]}, index=idx)
        n = normalize(raw)
        self.assertIsNone(n.index.tz); self.assertEqual(list(n.columns), ["open", "high", "low", "close", "volume"])

    def test_liquidity_filter(self):
        self.assertTrue(is_liquid(frame([10] * 25, vol=200_000)))      # 2,000,000 CAD per day
        self.assertFalse(is_liquid(frame([10] * 25, vol=1_000)))


class BotTests(unittest.TestCase):
    def test_momentum_buys_strongest(self):
        g = initial_genome("momentum")
        bot = make_bot("bot_001", "momentum", g, date(2026, 1, 5))
        hist = {"UP": frame(list(np.linspace(10, 12, 30))), "FLAT": frame([10] * 30)}
        orders = bot.decide(hist, Portfolio(cash=D("50")), date(2026, 2, 13))
        self.assertEqual([(o.symbol, o.side) for o in orders], [("UP", "buy")])
        self.assertEqual(orders[0].notional, D("25.00"))               # 50% of 50

    def test_momentum_stop_loss_sells(self):
        g = initial_genome("momentum")
        bot = make_bot("bot_001", "momentum", g, date(2026, 1, 5))
        pf = Portfolio(cash=D("0"), positions={"UP": Position(D("1"), D("20"), date(2026, 1, 6))})
        hist = {"UP": frame(list(np.linspace(10, 12, 30)))}            # price ~12 vs cost 20 -> stop hit
        orders = bot.decide(hist, pf, date(2026, 2, 13))
        self.assertEqual([(o.symbol, o.side) for o in orders], [("UP", "sell")])

    def test_mean_reversion_buys_dip(self):
        g = initial_genome("mean_reversion")
        bot = make_bot("bot_002", "mean_reversion", g, date(2026, 1, 5))
        closes = [10.0] * 19 + [7.0]
        orders = bot.decide({"DIP": frame(closes), "OK": frame([10.0] * 19 + [10.1])}, Portfolio(cash=D("50")), date(2026, 2, 2))
        self.assertEqual([(o.symbol, o.side) for o in orders], [("DIP", "buy")])

    def test_rotation_only_on_rebalance_days(self):
        g = initial_genome("rotation")                                 # rebalance every 5 days, top_n 1
        h = {"A": frame(list(np.linspace(10, 14, 40))), "B": frame([10] * 40)}
        created = h["A"].index[30].date()
        bot = make_bot("bot_003", "rotation", g, created)
        day1 = h["A"].index[30]                                         # days_alive == 1 -> rebalance
        o1 = bot.decide({k: v.loc[:day1] for k, v in h.items()}, Portfolio(cash=D("50")), day1.date())
        self.assertEqual([(o.symbol, o.side) for o in o1], [("A", "buy")])
        day2 = h["A"].index[31]
        o2 = bot.decide({k: v.loc[:day2] for k, v in h.items()}, Portfolio(cash=D("50")), day2.date())
        self.assertEqual(o2, [])
        day6 = h["A"].index[35]                                         # days_alive == 6 -> rebalance
        o6 = bot.decide({k: v.loc[:day6] for k, v in h.items()}, Portfolio(cash=D("50")), day6.date())
        self.assertEqual(len(o6), 1)


class EvolutionTests(unittest.TestCase):
    def wr(self, bid, s, e, trades=5, dd="0.02", halted=False, weeks=2):
        return WeekResult(bid, D(s), D(e), trades, D(dd), halted, weeks)

    def test_example_from_spec(self):
        res = [self.wr("bot_001", "50", "53"), self.wr("bot_002", "50", "49"), self.wr("bot_003", "50", "44")]
        self.assertEqual([r.return_pct for r in res], [D("6.00"), D("-2.00"), D("-12.00")])
        self.assertEqual(decide_evolution(res)[:2], ("bot_003", "bot_001"))

    def test_percentage_not_dollars(self):
        res = [self.wr("bot_001", "100", "104"),            # +4% (+$4)
               self.wr("bot_002", "50", "52.5"),            # +5% (+$2.5) -> strongest by percent
               self.wr("bot_003", "50", "49")]
        self.assertEqual(decide_evolution(res)[1], "bot_002")

    def test_grace_period(self):
        res = [self.wr("bot_001", "50", "53", weeks=1), self.wr("bot_002", "50", "49", weeks=1),
               self.wr("bot_003", "50", "44", weeks=1)]
        self.assertEqual(decide_evolution(res)[:2], (None, None))
        res[2] = self.wr("bot_003", "50", "44", weeks=2)               # only bot_003 eliminable
        self.assertEqual(decide_evolution(res)[:2], ("bot_003", "bot_001"))

    def test_winner_needs_trades_and_no_halt(self):
        res = [self.wr("bot_001", "50", "60", trades=2), self.wr("bot_002", "50", "58", halted=True),
               self.wr("bot_003", "50", "51"), self.wr("bot_004", "50", "47")]
        w, s, _ = decide_evolution(res)
        self.assertEqual((w, s), ("bot_004", "bot_003"))
        # edge case: the only eligible winner is also the weakest -> no action
        res2 = [self.wr("bot_001", "50", "60", trades=2), self.wr("bot_002", "50", "58", halted=True),
                self.wr("bot_003", "50", "51")]
        self.assertEqual(decide_evolution(res2)[:2], (None, None))

    def test_tie_breaks(self):
        res = [self.wr("bot_001", "50", "55", dd="0.03"), self.wr("bot_002", "50", "55", dd="0.01"),
               self.wr("bot_003", "50", "45", dd="0.05"), self.wr("bot_004", "50", "45", dd="0.09")]
        w, s, _ = decide_evolution(res)
        self.assertEqual(s, "bot_002")                                 # same return, smaller drawdown
        self.assertEqual(w, "bot_004")                                 # same return, larger drawdown
        res2 = [self.wr("bot_001", "50", "55"), self.wr("bot_002", "50", "55"),
                self.wr("bot_003", "50", "45"), self.wr("bot_004", "50", "45")]
        w2, s2, _ = decide_evolution(res2)
        self.assertEqual((w2, s2), ("bot_004", "bot_001"))             # full ties: higher id out, lower id wins

    def test_same_bot_skips(self):
        res = [self.wr("bot_001", "50", "55", weeks=2, trades=5)]
        self.assertEqual(decide_evolution(res)[:2], (None, None))

    def test_max_drawdown(self):
        self.assertEqual(max_drawdown([D("50"), D("55"), D("44"), D("50")]), D("0.2"))

    def test_mutation_valid_and_reproducible(self):
        for strat in GENES:
            parent = initial_genome(strat)
            for i in range(200):
                child = mutate_genome(strat, parent, f"seed:{i}")
                self.assertNotEqual(child, parent)
                for name, (typ, _, lo, hi) in GENES[strat].items():
                    self.assertTrue(lo <= child[name] <= hi, (strat, name, child[name]))
                    if typ == "int":
                        self.assertIsInstance(child[name], int)
            self.assertEqual(mutate_genome(strat, parent, "x"), mutate_genome(strat, parent, "x"))

    def test_zero_valued_genes_can_move(self):
        parent = initial_genome("mean_reversion")                       # exit_z starts at 0.0
        moved = any(mutate_genome("mean_reversion", parent, f"s{i}")["exit_z"] != 0.0 for i in range(50))
        self.assertTrue(moved)


class FundingMathTests(unittest.TestCase):
    def test_topup_does_not_change_return(self):
        # child funded with 44 + 6 top-up: e_start must be 50 (funding incl. deposit); end 52.5 -> +5%
        r = WeekResult("bot_004", D("50.00"), D("52.50"), 4, D("0"), False, 1)
        self.assertEqual(r.return_pct, D("5.00"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
```

### A20. `tests/test_backtest.py`

```python
import json, shutil, sqlite3, tempfile, unittest
from datetime import date
from decimal import Decimal as D

import numpy as np
import pandas as pd

from arena.market.data import DataStore
from arena.supervisor.runner import Arena

UNIVERSE = ["XIU.TO", "XIC.TO", "VFV.TO", "XEQT.TO", "ZAG.TO", "RY.TO", "TD.TO", "BNS.TO", "ENB.TO", "CNQ.TO", "SHOP.TO"]
CFG = dict(start_capital="50.00", slippage="0.001", commission="0.00", top_up_policy="to_50",
           min_weeks_before_elimination=2, min_trades_for_winner=3, daily_loss_halt=0.10,
           drawdown_halt_floor=0.60, seed=42, universe=UNIVERSE, min_dollar_volume=1_000_000)


def synth(symbol, days, seed):
    rng = np.random.default_rng(seed)
    r = rng.normal(0.0004, 0.015, len(days))
    close = 20 * np.exp(np.cumsum(r))
    open_ = close * (1 + rng.normal(0, 0.003, len(days)))
    return pd.DataFrame({"open": open_, "high": close * 1.01, "low": close * 0.99, "close": close,
                         "volume": 500_000}, index=days)


def make_store(tmp, spy=None):
    days = pd.bdate_range("2025-01-06", "2025-12-31")
    store = DataStore(tmp)
    for i, s in enumerate(UNIVERSE):
        store._mem[s] = synth(s, days, 100 + i)
    if spy is not None:
        orig = store.history
        def watched(symbol, end):
            spy.append((end, orig(symbol, end).index.max()))
            return orig(symbol, end)
        store.history = watched
    return store


def run(tmp, spy=None, cfg=None):
    store = make_store(tmp + "/cache", spy)
    a = Arena(cfg or CFG, store, tmp + "/arena.db", tmp + "/reports", tmp + "/genomes")
    a.init_bots(date(2025, 1, 6))
    a.backtest(date(2025, 1, 6), date(2025, 12, 31))
    return a


class BacktestTests(unittest.TestCase):
    def test_full_year_invariants(self):
        with tempfile.TemporaryDirectory() as tmp:
            spy = []
            a = run(tmp, spy)
            db = sqlite3.connect(tmp + "/arena.db")
            # no lookahead: every history read ended on/before the requested date
            self.assertTrue(all(mx is pd.NaT or mx <= pd.Timestamp(end) for end, mx in spy))
            # exactly 3 live bots at the end (+ any liquidating one at most)
            alive = [b for b in a.bots.values() if b.status == "active"]
            self.assertEqual(len(alive), 3)
            # at least one evolution happened in a year, and every child came from a parent
            evo = db.execute("SELECT count(*) FROM events WHERE type='evolution'").fetchone()[0]
            self.assertGreater(evo, 0)
            # cash never negative; equity rows exist
            neg = db.execute("SELECT count(*) FROM daily_equity WHERE CAST(cash AS REAL) < 0").fetchone()[0]
            self.assertEqual(neg, 0)
            # weekly results: 3 bots ranked each week with rank 1..3 present
            weeks = db.execute("SELECT week, count(*) FROM weekly_results GROUP BY week").fetchall()
            self.assertTrue(all(c == 3 for _, c in weeks), weeks)
            # funding rule: every child's first equity row is >= 50.00 when top-up policy is to_50 and freed < 50
            for (bid, amt) in db.execute("SELECT bot_id, amount FROM deposits"):
                row = db.execute("SELECT equity FROM daily_equity WHERE bot_id=? ORDER BY date LIMIT 1", (bid,)).fetchone()
                self.assertEqual(D(row[0]), D("50.00"))
            # genome files written; children differ from parent
            for bid, parent in db.execute("SELECT bot_id, parent_id FROM bots WHERE parent_id IS NOT NULL"):
                with open(f"{tmp}/genomes/{bid}.json") as fc, open(f"{tmp}/genomes/{parent}.json") as fp:
                    child, par = json.load(fc)["genome"], json.load(fp)["genome"]
                self.assertNotEqual(child, par)
            print("evolutions:", evo, "| bots ever created:", db.execute("SELECT count(*) FROM bots").fetchone()[0],
                  "| fills:", db.execute("SELECT count(*) FROM fills").fetchone()[0],
                  "| deposits:", db.execute("SELECT count(*) FROM deposits").fetchone()[0])

    def test_reproducible_with_same_seed(self):
        out = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as tmp:
                run(tmp)
                db = sqlite3.connect(tmp + "/arena.db")
                out.append((db.execute("SELECT * FROM weekly_results ORDER BY week, bot_id").fetchall(),
                            db.execute("SELECT bot_id, genome_json FROM bots ORDER BY bot_id").fetchall()))
        self.assertEqual(out[0], out[1])

    def test_commission_run_completes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = dict(CFG, commission="1.00")
            a = run(tmp, cfg=cfg)
            self.assertEqual(len([b for b in a.bots.values() if b.status == "active"]), 3)

    def test_resume_from_saved_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = make_store(tmp + "/cache")
            a = Arena(CFG, store, tmp + "/arena.db", tmp + "/reports", tmp + "/genomes")
            a.init_bots(date(2025, 1, 6))
            a.backtest(date(2025, 1, 6), date(2025, 6, 30))
            b = Arena(CFG, make_store(tmp + "/cache2"), tmp + "/arena.db", tmp + "/reports", tmp + "/genomes")  # reload
            self.assertEqual(b.meta["last_day"], a.meta["last_day"])
            b.backtest(date(2025, 7, 1), date(2025, 12, 31))
            self.assertEqual(len([x for x in b.bots.values() if x.status == "active"]), 3)


def fresh_arena(tmp):
    store = make_store(tmp + "/cache")
    a = Arena(CFG, store, tmp + "/arena.db", tmp + "/reports", tmp + "/genomes")
    a.init_bots(date(2025, 1, 6))
    return a


class RulesTests(unittest.TestCase):
    def test_initial_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = fresh_arena(tmp)
            self.assertEqual(sorted(a.bots), ["bot_001", "bot_002", "bot_003"])
            for st in a.bots.values():
                self.assertEqual((D(st.cash), st.positions, st.status), (D("50.00"), {}, "active"))

    def test_risk_halts(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = fresh_arena(tmp)
            day = date(2025, 3, 3)
            close = D(str(a.store.history("XIU.TO", day)["close"].iloc[-1]))
            st = a.bots["bot_001"]
            st.cash = "0.00"
            st.positions = {"XIU.TO": dict(shares=str(D("100") / close), avg_cost=str(close), entry_date="2025-01-06")}
            # Case 1: equity ~100, previous close 130 (-23% day) and peak 200 (equity < 60% of peak) -> both halts
            st.prev_close_equity, st.peak = "130.00", "200.00"
            a._value_and_risk(day)
            self.assertTrue(st.daily_halt_today and st.dd_halt and st.risk_halted_week)
            a._decide(day)
            self.assertEqual([(o["symbol"], o["side"]) for o in st.pending], [("XIU.TO", "sell")])   # sell-all, no buys
            # Case 2: only the daily-loss halt -> buys are removed, sells allowed
            st.dd_halt, st.risk_halted_week, st.peak, st.prev_close_equity = False, False, "100.00", "130.00"
            a._value_and_risk(day)
            self.assertTrue(st.daily_halt_today and not st.dd_halt)
            a._decide(day)
            self.assertTrue(all(o["side"] == "sell" for o in st.pending))

    def _birth(self, freed):
        with tempfile.TemporaryDirectory() as tmp:
            a = fresh_arena(tmp)
            a.bots["bot_003"].status, a.bots["bot_003"].cash = "liquidating", freed
            a.meta["pending_births"].append(dict(source="bot_003", parent="bot_001", week="2025-W10"))
            a._process_births(date(2025, 3, 10))
            child = a.bots["bot_004"]
            deposits = a.ledger.q("SELECT amount FROM deposits").fetchall()
            return child, deposits, a.bots["bot_003"]

    def test_funding_with_topup(self):                      # freed 44.00 -> child 50.00, deposit 6.00
        child, deposits, old = self._birth("44.00")
        self.assertEqual((D(child.cash), D(child.week_start_equity), deposits, old.status),
                         (D("50.00"), D("50.00"), [("6.00",)], "eliminated"))
        self.assertEqual((child.parent_id, child.generation, child.strategy), ("bot_001", 1, "momentum"))

    def test_funding_without_topup(self):                   # freed 57.00 -> child 57.00, no deposit
        child, deposits, _ = self._birth("57.00")
        self.assertEqual((D(child.cash), deposits), (D("57.00"), []))


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

### A21. `README.md`

```markdown
# Arena starter kit

Evolutionary paper-trading bot arena (3 bots, weekly elimination, profit-percentage ranking).
Read `trading-bot-arena-spec-and-prompt.md` first. Quick start:

    python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    python -m unittest discover -s tests -v                 # must end with OK
    python scripts/day0_smoke_test.py                       # must print RESULT: OK
    python -m arena.cli fetch --start 2025-01-01
    python -m arena.cli backtest --start 2026-03-02 --end 2026-09-30 --fresh

PAPER TRADING ONLY. There is deliberately no broker connection in this code.
```

### A22. `.gitignore`

```text
.venv/
__pycache__/
data_cache/
reports*/
genomes*/
*.db
run.log
```


---

# Sources

Provider pages and reviews read during research (3 October 2026). Figures are paraphrased and may have changed.

- Alpaca account plans (paper-only account, IEX data): https://alpaca.markets/deprecated/docs/trading-on-alpaca/account-plans
- Alpaca forum, market data for Canadians: https://forum.alpaca.markets/t/market-data-for-canadians/11916
- Alpaca forum, data subscription in Canada: https://forum.alpaca.markets/t/is-the-market-data-subscription-available-in-canada/19519
- Review of Alpaca paper-trading limits: https://blog.traderspost.io/article/alpaca-paper-trading
- Interactive Brokers, Web API access for individuals: https://www.interactivebrokers.com/docs/web-api/trading/getting-started/trading-access-for-individuals
- Interactive Brokers Knowledge Base, paper trading accounts: https://ibkb.interactivebrokers.com/tag/paper-trader
- Savvy New Canadians, paper trading platforms in Canada: https://www.savvynewcanadians.com/best-paper-trading-platforms-canada/
- Finder Canada, paper trading: https://www.finder.com/ca/stock-trading/paper-trading
- BrokerChooser, algorithmic trading brokers in Canada: https://brokerchooser.com/best-brokers/best-brokers-for-algo-trading-in-canada
- Moomoo Canada paper trading guide: https://www.moomoo.com/ca/learn/detail-moomoo-paper-trading-118129-251230015
- TradeZero paper trading: https://tradezero.com/en-ca/free-paper-trading
- yfinance documentation (personal-use notice): https://ranaroussi.github.io/yfinance/
- Scrapfly, Yahoo Finance API guide (unofficial, rate limits): https://scrapfly.io/blog/posts/guide-to-yahoo-finance-api
- Twelve Data pricing: https://twelvedata.com/pricing
- Twelve Data plan coverage (Trial/Basic): https://support.twelvedata.com/en/articles/5335783-trial
- APILayer, free financial market APIs compared: https://blog.apilayer.com/12-best-financial-market-apis-for-real-time-data-in-2026/
- DEV Community, free stock APIs compared: https://dev.to/nexgendata/best-free-stock-market-apis-and-data-tools-in-2026-a-developers-honest-comparison-1926
- Pepperdine library guide to Alpha Vantage: https://infoguides.pepperdine.edu/finance/stockmarketapis
