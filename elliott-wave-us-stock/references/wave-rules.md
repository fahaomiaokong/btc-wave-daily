# Wave Labeling Rules

This reference condenses the wave-labeling standards used by this skill. It is based on the uploaded Chinese Elliott Wave materials and the technical-analysis book's emphasis on combining wave structure with Fibonacci and oscillator confirmation.

## Label Only After Validation

Never draw numeric wave labels just because pivots alternate. First classify the structure, then validate the rules for that structure. If validation fails, use neutral labels or a candidate corrective structure.

## Motive / Impulse Waves

Draw `1-2-3-4-5` only for a validated motive wave.

## Choosing The Start Of A Main Upswing

For a visible main upswing, the start is not chosen because it makes a later candidate count easier. First choose the analysis degree/window, then choose the effective swing low before the terminal high in that same window.

For ordinary stock/ETF charts:

- Use the lowest visible/effective swing low before the selected high inside the fetched analysis window.
- Use the highest visible/effective swing high after that low as the terminal high.
- Only after choosing these two anchors may the script test whether the internal pivots validate a `1-2-3-4-5` impulse.
- If validation fails, keep the low-to-high Fibonacci retracement as a main-swing reference, but do not force numeric labels.

For crypto or full-cycle charts, use the cycle low before the selected high for the current cycle, not the all-time earliest exchange low.

Hard rules for a standard impulse:

- Wave 2 never retraces beyond the start of wave 1.
- Wave 3 is never the shortest among waves 1, 3, and 5.
- Wave 4 does not enter wave 1 price territory in a standard impulse.
- Wave 3 should exceed the end of wave 1.

For a bearish impulse `p0 high -> p1 low -> p2 high -> p3 low -> p4 high -> p5 low`:

- `p2 < p0`
- `p3 < p1`
- `wave3 >= min(wave1, wave5)`
- `p4 < p1`

Only after these pass may the chart draw black `(1)-(5)`.

## Corrective Waves

Corrections are three-wave structures or variants:

- Simple correction: `A-B-C`
- Zigzag: usually `5-3-5`
- Flat: usually `3-3-5`
- Triangle: `A-B-C-D-E`
- Combination: `W-X-Y` or `W-X-Y-X-Z`

When a correction is unclear, use candidate labels and condition levels; do not force a count.

## MSTR-Style Pattern

For charts like the uploaded MSTR example:

- Green line: `A` wave.
- Red line: complex `B` wave, often `W-X-Y-X-Z`.
- Black line: `C` wave.
- If C validates as an impulse, label black `(1)-(5)`.
- Project black wave 5 using `black 1 = black 5`, measured from wave 4.
- If price reclaims wave 4, the wave 5 extension idea must be reevaluated.

## Fibonacci Use

Fibonacci levels are supporting evidence, not a substitute for wave rules.

Common references:

- Wave 2: 0.5, 0.618, 0.786 retracement of wave 1.
- Wave 4: 0.236 or 0.382 retracement of wave 3.
- Wave 3: often extends toward 1.618 of wave 1.
- Wave 5: often relates to wave 1 by equality or 0.618/1.0 extension.
- C wave: often equals A, or extends to 1.618 times A.

## Oscillator Confirmation

RSI and composite indicators can confirm or warn about counts, especially near wave 3, wave 5, and C-wave endings. They must not override hard wave rules.
