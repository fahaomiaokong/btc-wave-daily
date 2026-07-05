# Analysis Playbook

## Goal

Generate a wave-structure observation that can be posted to X with a chart. The output should resemble a concise conditional analyst note, not a trading signal.

For wave-label rules, read `wave-rules.md` first. This playbook mainly governs chart style, text style, and output behavior.

## Method Fusion

- Elliott Wave International: use hard rules, preferred/alternate counts, and invalidation levels.
- ElliottWaveTrader: emphasize Fibonacci relationships, confirmation levels, and path tracking.
- Elliott Wave Forecast: use equal-leg target zones, 3/7/11 swing thinking, and support/resistance boxes in later versions.
- Chinese "波浪理论学习" style: express the result as monitor points, "if crossed", "if not crossed", "still correcting", and "if broken, this wave has ended".

## Output Philosophy

Every conclusion must be convertible into:

- condition,
- level,
- implication,
- invalidation or next review point.

Avoid absolute predictions. Prefer:

```text
监测点 115.82。如果能冲过去，反弹级别扩大，并有望冲击 121.24。
如果 115.82 过不去，则仍在调整内。
```

Do not name a pivot "1浪顶", "3浪顶", or "5浪终点" unless the script has explicitly validated the full wave rule set for that count. In v0.1, use neutral labels such as `关键前高`, `关键前低`, `高点`, and `低点`.

Use unadjusted OHLC High/Low values for visual wave pivots. Adjusted close is useful for return studies, but wave charts should mark the visible high/low that traders see on the chart.

## Strict Wave Labels

Only draw `(1)-(5)` when the six pivots validate a standard impulse in the selected direction.

For a bearish impulse from `p0 high -> p1 low -> p2 high -> p3 low -> p4 high -> p5 low`:

- Wave 2 must not retrace beyond the start of wave 1: `p2 < p0`.
- Wave 3 must not be the shortest of waves 1, 3, and 5.
- Wave 4 must not overlap wave 1 territory in a standard impulse: `p4 < p1`.
- Wave 3 must make a new low beyond wave 1: `p3 < p1`.

If any hard rule fails, do not draw black `(1)-(5)`. Use neutral high/low labels and conditional levels instead.

For MSTR-style corrections, prefer this hierarchy:

1. Large correction: `A-B-C`.
2. Complex B wave when visible: red `W-X-Y-X-Z`.
3. C wave: black impulse `(1)-(5)` only if strict impulse rules pass.
4. Projection: show `黑1=黑5` target from wave 4.

For short BTC-style decline charts like the uploaded July 1 reference:

- When a recent decline validates as a bearish impulse, draw the active C-wave or fifth sub-wave path in purple and label `(1)-(5)`.
- Keep only enough prior context to show the preceding channel or corrective lead-in; the active purple five-wave path must be visually dominant.
- State the wave-5 starting point, which is the wave-4 pivot. If the rebound cannot reclaim that point, the fifth-wave downside pressure remains.
- Show the `1=5` projection as the next downside observation level, and state that a rebound is first considered after the fifth wave is complete.
- If price has already reclaimed the wave-4 pivot after a validated bearish `(1)-(5)`, downgrade the "wave 5 extension" scenario and switch the note to rebound validation. Keep the language compact and conditional.
- In that reclaimed-wave-4 case, use this target hierarchy:
  - first rebound target: prior wave `(1)` low,
  - high-probability core resistance zone: `0.786` retracement of `p0 high -> p5 low`, bracketed with prior wave `(2)` high,
  - stronger rebound level: C-wave start / `p0` high,
  - failure level: wave `(5)` low; breaking it reopens downside extension.

Compact reclaimed-wave-4 wording:

```text
$SYMBOL YYYY年M月D日波浪结构观察：

按大级别A-B-C调整观察，紫线是C浪内部下跌推动，当前可标为(1)-(5)。

C浪起点约 P0，(1) P1，(2) P2，(3) P3，(4) P4，当前(5)低点约 P5。
最新价约 CURRENT，已经重新站上(4)浪高点 P4，原先5浪继续延伸的判断需要降级，暂按(5)浪低点已经出现来观察反弹结构。
反弹目标先看 P1，核心压力区看 CORE_LOW-CORE_HIGH，这是当前较高概率目标。若继续站上 CORE_HIGH，再看 P0 附近；若跌破 P5，反弹失败，下跌延伸重开。

只分析，不建议交易。
```

For chart-left text, keep this same order but allow wrapping. The most important visible lines are: structure, `(1)-(5)` pivots, reclaimed-wave-4 conclusion, and the compact target sentence. Avoid adding the old `1=5` downside target to the main note once wave `(4)` has been reclaimed; keep it only as a chart level or JSON scenario if useful for validation history.

## Required Levels

- `start`: recent swing low/high where the current rebound or pullback began.
- `monitor`: nearest key swing level that changes the wave interpretation.
- `target`: next projected level if monitor breaks.
- `invalidation`: level that invalidates the current minor path.

## Chart Style

- Title: `<SYMBOL> <NAME_OPTIONAL> <YYYY年M月D日>`.
- Horizon behavior:
  - `短期` means about 1 year of daily bars. Use it for tight current-wave interpretation and concise support/monitor conclusions.
  - `长期` means about 2-3 years of daily bars for stocks/ETFs, and full-cycle history for BTC/ETH-style crypto. Stock/ETF long charts should keep the full 2-3 year visible window instead of cropping back to only the latest few months. Draw a thinner background wave path through the earlier major swing pivots, then use thicker lines for the active wave structure. Use it to show the prior major rise, the current corrective skeleton, and higher-degree Fibonacci context.
  - `上市以来` / `listing` means full available history from the first yfinance trading day. Use this for recent IPOs and new listings such as CRCL, where the IPO spike and post-IPO decline are part of the primary wave structure. Do not crop away the IPO high/low.
- Historical price: thick black line.
- For reference-style wave charts, use a TradingView-like candlestick background instead of a single price line. Keep wave paths above candles.
- Crop the chart to the active wave-analysis region. Keep only a small amount of prior context; avoid showing long unused historical data on the left.
- Major path: red line.
- Minor/forward path: black line.
- Draw two forward paths when possible:
  - solid black: scenario A,
  - dashed black: scenario B.
- Limit forward paths to about 63 trading days, roughly the next 2-3 months. Show future dates on the x-axis instead of stretching the path without date labels.
- Do not label pivots as `(1)(2)(3)` unless the algorithm has explicitly validated that wave count. Use neutral `高点` / `低点` labels for v0.1.
- Current price/support: green dashed line.
- Monitor: red/pink dashed line.
- Target: orange dashed line.
- Invalidation: blue dashed line.
- Fibonacci retracement levels: gray dashed lines for 0.236, 0.382, and 0.5.
- For a prior main upswing such as `low -> high`, draw the prior upswing retracement levels on their own light-blue dashed lines:
  - 0.382,
  - 0.5,
  - 0.618,
  - 0.786.
- Put the prior upswing retracement numbers next to their corresponding Fibonacci lines, not in a separate legend. Mark the likely observation zone beside the relevant line, commonly `0.618 高概率`; mark `0.786 跌破看延伸` when it is the next downside threshold.
- Use blue text for the explanatory note.
- Keep the chart note short. The left note should usually fit in 5-8 visual lines: prior completed/active structure, current wave label, key conclusion, and next support/monitor. Put longer reasoning in the Markdown post, not on the image.
- Put the explanatory note on the left, close to the chart, leaving only about 3-4 Chinese characters of visual gap before the plot.
- Include the disclaimer once in red at the lower-right of the chart: `只分析，不建议交易`.

## Corrective-Structure Layout

When a prior rise into a key high is followed by an unclear decline:

- If the prior rise validates as a full impulse, describe it first as completed: `此前主升浪从 LOW 上涨到 HIGH，按照推动浪规则，五浪已经结束。`
- Draw the validated main upswing itself as a red `1-2-3-4-5` path from the cycle low to the cycle high. The fifth-wave high must be the post-cycle maximum, not a local recent high.
- After the validated fifth-wave high, draw the corrective path downward from that exact high. First identify the major corrective skeleton, not every small pivot. Use `A-B-C` when the decline is a simple correction; use `W-X-Y` when the first decline is complex, the X wave is a partial retracement, and Y breaks below W. For `W-X-Y`, W should be the lowest low before the selected X retracement, not a later higher low. Keep lower-degree `a/b/c` labels secondary or omit them if they clutter the chart.
- If the prior rise does not validate as a full impulse, describe the prior rise as a candidate only: `此前一段从 LOW 上涨到 HIGH，暂看上一段上升浪末端/候选5浪高点。`
- If the prior rise does not pass full impulse validation, explicitly say it is not forced into `1-5`.
- Compute prior-rise retracement levels from `LOW -> HIGH`:
  - 0.382 = `HIGH - (HIGH - LOW) * 0.382`
  - 0.5 = `HIGH - (HIGH - LOW) * 0.5`
  - 0.618 = `HIGH - (HIGH - LOW) * 0.618`
  - 0.786 = `HIGH - (HIGH - LOW) * 0.786`
- For ordinary stock/ETF charts, choose the prior-rise `LOW` as the lowest visible/effective swing low before the selected `HIGH` inside the fetched analysis window. Do not use a later local low merely because it fits a candidate wave count. The retracement tool should measure the visible main upswing that a chart reader sees.
- Choose the prior-rise `HIGH` as the highest visible/effective swing high after that low in the fetched analysis window, not a lower recent rebound high.
- If the current correction breaks the initially selected prior low, do not keep using that broken low as the main upswing origin. Search further left for the nearest earlier swing low below the current correction low. If no earlier swing low remains unbroken, use the lowest swing low before the key high and treat the retracement as a broader-degree reference.
- For long-cycle crypto symbols such as `BTC-USD`, fetch a longer history (`max` or at least one full cycle) and prefer the cycle low before the key high as the main upswing origin. For BTC-style cycles, search roughly the four years before the key high and use the lowest swing low in that window. Do not use a local two-year low if the visible structure clearly belongs to a larger cycle rise, and do not use the all-time earliest exchange low when the current structure belongs to a later cycle.
- If current price is near 0.618, state that 0.618 is the higher-probability observation zone. If 0.618 breaks, use 0.786 as the next extension watch.
- If the post-high decline does not validate as an impulse, prefer `W-X-Y` / internal `A-B-C` candidate labels over forced numeric waves.
- Do not reuse crypto/BTC fixed levels or wording in stock/ETF templates. Every text line and chart level must come from the current symbol's own `levels`, `main_upswing`, `main_impulse`, or `correction` object.
- For stock/ETF charts like the GOOG reference, when a completed/extended upswing is followed by a three-swing pullback and price has not broken the pullback low, label the pullback as `a-b-c / candidate 5-2` rather than forcing `W-X-Y`. State both conditions: if the pullback low holds, the prior advance can still continue into the next upward wave; if that low breaks, the whole prior red/orange advance is treated as finished and a larger correction is underway.
- Label every visible swing pivot. Use major correction labels (`W`, `X`, `Y?`, `C/W`) around the active key-high correction. For earlier unvalidated swings, use candidate lowercase sequences such as `a1/b1/c1`, `a2/b2/c2` rather than forced numeric impulse labels.
- Add one compact conclusion sentence after the active structure, following this pattern: `结论：SUPPORT有反弹条件；不过MONITOR，仍按当前浪内部反弹。下方支撑/目标看NEXT。`

## Commentary Template

```text
$SYMBOL YYYY年M月D日波浪结构观察：

红线是主级别浪，黑线是小级别路径。
当前从 START 附近开始小级别反弹。

监测点 MONITOR。
情景A：突破 MONITOR，反弹级别扩大，下一步按小3浪/反弹延伸观察 TARGET。
情景B：跌破 INVALIDATION，反弹路径失效，下一步按C浪/更大级别调整观察。
如果 MONITOR 过不去，则仍在调整内。

只分析，不建议交易。
```

## Version Plan

- v0.1: yfinance, ZigZag pivots, chart, Chinese post, JSON.
- v0.2: weekly/daily/hourly multi-degree counts.
- v0.3: Fibonacci blue-box/equal-leg target zones.
- v0.4: walk-forward validation.
- v0.5: X post variants and hashtag suggestions.
