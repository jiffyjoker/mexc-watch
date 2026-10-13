# Sentiment validation — 2026-10-14 00:40 AEST
All public data. ~140 X reads used (free built-in reads). Nothing here trades or wakes.

## 1. X history access
search_posts_all full-archive works 3, 6, 12 and 15 months back (tested Oct 2025, Jul 2025); max 25 results/call.
get_posts_counts_recent: last 7 days only (start_time earlier is rejected) -> untestable as a daily series.

## 2. Analyst calls (score_calls.py -> calls.json, score_calls.json)
18 accounts, Apr 14 - Oct 7 2026, ~4-6 time-sliced searches each (sample, not complete history).
Direction = bull/bear keyword vote (heuristic, not hand-labelled); one call per account/coin/day; price returns vs MEXC 1h closes, no fees.
All calls: n=494, 62% bullish; directional avg +0.18% (1d), +0.37% (3d), +0.30% (7d). Always-long on the same timestamps: +0.25 / +0.44 / +0.77 -> calls add nothing over long drift.
Best: MerlijnTrader n=36 avg3d +1.64% t2.6 p(random sign)=0.004 (78% bullish; Bonferroni over 18 accounts p~0.07, not significant).
Worst: scottmelker n=21 -1.06%, DaanCrypto n=61 -0.42%. Target-before-invalidation only parseable on 44 calls (overall ~34%).

## 3. Crowd sentiment (crowd.py -> crowd.json)
Daily top-25 relevant posts '(bitcoin OR $BTC) (bullish OR bearish)', 1 Sep - 12 Oct (41 days).
corr(score, next-day BTC) = -0.31 (t~-2.0, contrarian). Split: first 20 days contrarian +1.04%/day t2.15, last 21 days -0.46% t-1.63 -> sign flips, fails.

## 4. Funding extremes, 365d 1h top-50 (bt_funding.py -> bt_funding.json), fees+funding, H1 pick / H2 validate
Every variant fails H2: BTC own-funding 5/10% pctl (1d/3d), market-avg funding pctl -> BTC, cross-sectional abs >=0.05/0.10%, per-coin 5% pctl.
Notable: per-coin 5% pctl 3d H1 +1.28% (t4.8) -> H2 -0.84% (t-3.8): regime flip, not an edge.

## Verdict
No signal passes. Nothing added to paper books.
