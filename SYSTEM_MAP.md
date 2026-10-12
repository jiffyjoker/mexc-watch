# MEXC desk — SYSTEM MAP (read first every session; update with every change)
Source of truth: box `/workspace/mexc-watch/SYSTEM_MAP.md` (copy in repo jiffyjoker/mexc-watch). Rules live in `RULES.md` — this file maps the system, it does not restate rules. Last verified against code: 2026-10-13 00:30 local time.

## 1. Flow
```mermaid
flowchart TD
  subgraph GH[GitHub Actions - public repo jiffyjoker/mexc-watch]
    SCAN[mexc-scan scan.yml: self-relaunching, 11 x 30-min chunks]
    WS[live.py stage1: websocket push.tickers, hot coins near 24h level; REST poll if ws down]
    S2[live.py stage2: 5s after each 15m close, breakout rules + gates]
    REST[scan.py every 5 min: breakout/retest/sweep/btc_move/oi_surge; OI+funding gates; writes levels.json, oi.json]
    WD[watchdog.yml: cron 7,37 + self-chain loop; restarts mexc-scan, else scanner_down wake; backup trigger for review]
    RV[review.yml 21:00 UTC = 7am local time: scores wakes 1h/4h/12h -> reviews/DATE.md + daily_review wake]
    CPI[cpi-watch.yml: Wed 14 Oct BTC move watcher, cap 4 wakes]
    SCAN --> WS --> S2
    SCAN --> REST
  end
  S2 -->|webhook| R[mexc-research-signal routine: vets per RULES.md; logs last_signal_decision.json]
  REST -->|webhook| R
  WD -->|webhook| R
  RV -->|webhook| R
  CPI -->|webhook| R
  R -->|limit + stop + 4R safety TP| MEXC[(MEXC USDT-M account)]
  subgraph BOX[Box /workspace/mexc-watch, kept alive by supervise.sh]
    G[guard.py every 60s: missing-stop repair, trail at 1R to BE+0.15% then 1 ATR15m behind best, tighten-only, 4R TP; stale-order cancel; 3-loss/day brake.json; api_outage wake]
    W[watch.py every 30s: box breakout watcher + position_closed wakes]
  end
  MEXC <--> G
  MEXC --> W -->|webhook| R
  subgraph RT[Box routines]
    KA[mexc-keep-awake every 4h at :53: box scripts + scan run alive]
    CW[CPI Wednesday watch: 14 Oct 10:15/10:31/10:40/10:55pm local time]
    SC[Start CPI watcher: Wed 14 Oct 6:07pm local time]
    WK[Weekly MEXC improvement: Sun 7pm local time, first 18 Oct]
  end
  KA -.-> SCAN
  KA -.-> G
  SC -.-> CPI
```

## 2. Components
| Component | Does | Lives | Health check | Restart |
|---|---|---|---|---|
| mexc-scan | 5-min REST signals + live websocket stage1/2 | repo `scan.yml`, `scan.py`, `live.py`, `common.py` | `gh run list -R jiffyjoker/mexc-watch -w mexc-scan -L 3` (one in_progress, newest step <45 min) | `gh workflow run mexc-scan -R jiffyjoker/mexc-watch` |
| watchdog | heartbeat, restart scan, `scanner_down` | `watchdog.yml`, `watchdog.py` | `gh run list -R jiffyjoker/mexc-watch -w watchdog -L 3` | `gh workflow run watchdog -R jiffyjoker/mexc-watch -f loop=true` |
| daily-review | score wakes, commit `reviews/` | `review.yml`, `review.py` | `ls /workspace/mexc-gh/reviews` after `git pull`; `gh run list -w daily-review -L 2 -R jiffyjoker/mexc-watch` | `gh workflow run daily-review -R jiffyjoker/mexc-watch` |
| cpi-watch | Wed CPI BTC watch (cron `50 11 14 10 *` UTC + dispatch) | `cpi-watch.yml`, `cpi_watch.py` | `gh run list -w cpi-watch -L 2 -R jiffyjoker/mexc-watch` | `gh workflow run cpi-watch -R jiffyjoker/mexc-watch` (test: `-f test=true`) |
| rate-test | ad-hoc probe runner | `rate-test.yml`, `bench.py`, `ws_probe.py` | n/a | dispatch only |
| guard.py | stops/trailing/brake/outage | box | `pgrep -af "python3 guard.py"`; `tail -5 /workspace/mexc-watch/guard.log`; `cat guard_state.json brake.json` | supervise.sh restarts within 60s |
| watch.py | box breakout + close alerts | box | `pgrep -af "python3 watch.py"`; `tail -5 watch.log` | supervise.sh |
| supervise.sh | keeps guard+watch alive | box | `pgrep -af supervise.sh`; `tail supervise.log` | `cd /workspace/mexc-watch && setsid nohup bash supervise.sh >/dev/null 2>&1 &` |
| Webhook secrets | WEBHOOK_URL / WEBHOOK_AUTH (repo secrets) = box env MEXC_RESEARCH_WEBHOOK_* | GitHub secrets / box env | `gh secret list -R jiffyjoker/mexc-watch` (names only — never print values) | `gh secret set` from env, no echo |
| Routines | research-signal, keep-awake, CPI watch, Start CPI watcher, Weekly improvement | Grok Bot routines | routine list | re-enable only if the owner asked |

State: repo actions/cache key `seen-<run_id>[-chunk]` holds seen.json, oi.json, wakes.json. Box: state.json (watch arming), guard_state.json, brake.json, trades.csv, last_signal_decision.json.

## 3. Rules (summary — details in RULES.md)
- Risk 5% of live equity at the stop; A+ up to 7%; 2.5% after 2 straight losses; pause after 4. Isolated 10x default, max 3 open, ≥ half the book free.
- Gates: side = day's direction; no-chase location measured at ARM time (close 2h before break: 0.50–0.85 long / 0.15–0.50 short) and ≤1% past level; breakouts/retests dropped if OI 6h < −1% or funding ≥ ±0.05% in trade direction.
- Exit: trailing stop default (BE+fees at 1R, then 1 ATR(15m) behind best, tighten-only), safety TP 4R. Nobody else moves a stop.

## 4. Decision log
| Date | Decision | Evidence |
|---|---|---|
| 2026-10-12 | Repo public (free unlimited Actions minutes) | — |
| 2026-10-12 | Self-relaunching workflow_dispatch loop instead of cron | GitHub schedule cron never fired |
| 2026-10-12 | OI history self-built from holdVol (oi.json) | 1h usable ~11pm 12 Oct, 6h ~3:30am 13 Oct |
| 2026-10-12 | Websocket two-stage scan (REST signals kept) | Live test caught XRP short breakout within seconds |
| 2026-10-12 | Arm-time location gate | Old check passed 9/129 breakouts (7d), arm-time 94/129, avg +0.21R vs +0.16R |
| 2026-10-12 | Rate limits OK | Back-to-back scans on GitHub runner, ~10× normal: 0 HTTP 429 in 1184 requests |
| 2026-10-12 | Kept 15m close trigger (not earlier triggers) | Early triggers caught more, made less per trade |
| 2026-10-12 | Trailing stop = default exit (the owner approved) | 14d/94 filtered trades: +16.1R vs +14.2R fixed, DD 10.8R vs 12.0R; built version +23.6R on 127; 4000 sim paths: never loosened |
| 2026-10-12 | 6pm–7am entry window DEFERRED | +14.2R → +19.8R, but gains concentrated in last week; ask the owner Sun 18 Oct |

## 5. Open / pending
- Sun 18 Oct 7pm: re-run backtests with extra week; ask the owner on entry window.
- OI gate and oi_surge untestable until OI history accrues (started 12 Oct).
- live.py REST fallback (ws drop) never exercised live.
- Wed 14 Oct: Start CPI watcher 6:07pm, CPI watch routine 10:15pm+.
- HYPE short (opened 11:48pm 12 Oct) = first live trailing-stop trade; confirm guard TRAIL log at +1R.

## 6. Session start checklist
1. Read this file, then RULES.md.
2. `gh run list -R jiffyjoker/mexc-watch -L 8` — mexc-scan in_progress, watchdog recent, no failures.
3. `pgrep -af "guard.py|watch.py|supervise.sh"`; `tail -5 /workspace/mexc-watch/{guard,watch,supervise}.log`.
4. Open positions/stops: `cat guard_state.json brake.json`; verify on MEXC each position has a stop + TP.
5. `cat last_signal_decision.json`; latest `reviews/*.md`.
6. After any change: update RULES.md (if rule), this file (sections 2/4/5), and commit the repo copy.
