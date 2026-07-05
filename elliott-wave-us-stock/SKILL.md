---
name: elliott-wave-us-stock
description: Generate conditional Elliott Wave analysis for US stocks and market ETFs from ticker symbols. Use when asked to analyze a US stock, ETF, or Yahoo Finance symbol with Elliott Wave, create a wave chart, produce Chinese X/Twitter-ready commentary, identify monitor/target/invalidation levels, or save chart/Markdown/JSON artifacts using yfinance data.
---

# Elliott Wave US Stock

## Quick Start

Use `scripts/elliott_wave_chart.py` to generate a conditional wave map from a ticker:

```bash
python scripts/elliott_wave_chart.py NVDA --out reports
```

The script creates:

- `reports/charts/<SYMBOL>_<DATE>_wave.png`
- `reports/posts/<SYMBOL>_<DATE>_wave.md`
- `reports/data/<SYMBOL>_<DATE>_wave.json`

Use `--horizon`, `--period`, `--interval`, and `--sensitivity` when the user asks for a different time horizon:

```bash
python scripts/elliott_wave_chart.py PLTR --horizon short --interval 1d --sensitivity 0.07 --out reports
python scripts/elliott_wave_chart.py NVDA --horizon long --interval 1d --out reports
python scripts/elliott_wave_chart.py CRCL --horizon listing --interval 1d --out reports
```

Horizon mapping:

- User says `短期`: use `--horizon short`, about 1 year of daily bars.
- User says `长期`: use `--horizon long`, about 3 years of daily bars for stocks and ETFs; use full-cycle `max` history for long-cycle crypto symbols such as `BTC-USD` and `ETH-USD`.
- User says `上市以来`, or the ticker is a recent IPO/SPAC/new listing where the IPO move matters: use `--horizon listing`, which fetches `max` and keeps the chart visible from the first available trading day.
- If the user gives an explicit period, use `--period` and let it override the horizon.

## Workflow

1. Fetch bars from yfinance.
2. Detect swing pivots with a ZigZag-style threshold.
3. Classify the active structure only after checking Elliott Wave rules.
4. Build a conditional wave map, not a deterministic prediction.
5. Generate:
   - a chart styled for X posts,
   - concise Chinese commentary,
   - a structured JSON record for later validation.
6. Keep all conclusions conditional: "if price breaks X", "if X cannot be crossed", "if price falls below Y".

## Interpretation Rules

Read `references/wave-rules.md` before changing wave labeling logic. Read `references/analysis-playbook.md` before changing text templates or chart conventions.

Core requirements:

- Separate major and minor degree paths when possible.
- Use red paths for the major wave and black paths for the minor/forward path.
- Always include monitor, target, and invalidation levels when enough pivots exist.
- If a recent rise into a high is followed by a correction, mark the prior rise's Fibonacci retracement levels on the chart lines and identify the highest-probability observation zone, usually 0.618 unless price has already broken it.
- Anchor the prior main upswing from the lowest effective swing low before the terminal high in the chosen analysis window; do not use the screenshot's visible low or a later local low just because it fits a count. Label these Fibonacci levels as `回撤位`, not `回测位`.
- Limit forward scenario paths to roughly the next 2-3 months.
- Put explanatory Chinese text on the left and keep it close to the chart, with only a small gap.
- For short BTC-style charts where a validated C-wave bearish impulse has likely completed and price reclaims wave `(4)`, use the compact rebound-target note from `references/analysis-playbook.md`: identify the A-B-C / C-wave `(1)-(5)` structure first, then state that the wave-5 extension count is downgraded, then give the first rebound target, the high-probability core resistance zone, the stronger rebound level, and the failure level.
- Put the disclaimer `只分析，不建议交易` once, in red, at the chart's lower-right corner.
- Output "current high-quality wave structure is unclear" when pivots do not support a clean count.
- Do not provide buy/sell instructions. Use the disclaimer: `只分析，不建议交易`.

## Validation

After changing the script, run at least:

```bash
python scripts/elliott_wave_chart.py SPY --out /tmp/ew-smoke
python scripts/elliott_wave_chart.py NVDA --out /tmp/ew-smoke
python scripts/elliott_wave_chart.py PLTR --out /tmp/ew-smoke
```

Check that PNG, Markdown, and JSON files are created, the chart is not blank, Chinese text renders, and every scenario has a condition.
