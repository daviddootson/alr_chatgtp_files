# ALR height reduction study v1.0

Date: 9 September 2026

## Purpose

Test how much the current WWK feature height can be reduced before optical performance becomes unacceptable, while also quantifying the resulting line pitch / viewer dark-band reduction.

Current operational reference is WWK / W0.24 / K0.16 / S1.30 / V77 / H0 with the existing single-K tilt-derived cap. It is normalised here to B/A/C = 100/100/100. The study uses the established centre-heavy three-view model for detailed candidates (centre 2/3, left 1/6, right 1/6).

The agreed rough-screen rule was that a reduced-height candidate should be no worse than 10%. For screening this was treated conservatively as brightness >=90, ambient return <=110, and contrast >=90 relative to the current reference.

## First test: W0.15 / K0.08 / S1.30 / V77

This aggressive reduction was screened first with low ray count and centre viewing only.

- current total optical height: 0.832 mm
- proposed total optical height: 0.494 mm (-40.6%)
- current rough pitch: 2.2395 mm
- proposed rough pitch: 1.6253 mm (-27.4%)
- rough dark band: 1.0511 mm versus 1.7379 mm (-39.5%)
- brightness: 161.9
- ambient return: 211.6
- contrast: 76.5

It fails the 10% rule decisively. Increasing V / opening the spacing did not rescue it: even around V90-V98 contrast remained only about 78-79 while ambient return remained about twice the current reference. No expensive three-view calculation was justified for this geometry.

## Small independent W/K rough search

A deliberately small grid was then used to see whether height reduction is viable if most of the reduction comes from the black cap rather than the two white tiers.

The strongest rough candidates retained near-full W height and reduced K height. The aggressive edge of the 10% screening envelope was around W0.235 / K0.10.

## Detailed three-view checks

Promising cases were recalculated with all three viewer positions and the 2/3 centre + 1/6 left + 1/6 right weighted score.

| Geometry | Total height mm | Pitch mm | Weighted dark band mm | Brightness | Ambient | Contrast |
|---|---:|---:|---:|---:|---:|---:|
| Current W0.24/K0.16 | 0.832 | 2.2408 | 1.7257 | 100.00 | 100.00 | 100.00 |
| W0.24/K0.10 | 0.754 | 2.0939 | 1.5905 | 104.46 | 106.04 | 98.51 |
| W0.235/K0.10 | 0.741 | 2.0716 | 1.5620 | 108.44 | 109.83 | 98.74 |
| W0.24/K0.08 | 0.728 | 2.0846 | 1.5825 | 103.65 | 107.63 | 96.30 |

All figures above are model predictions, not physical measurements.

## Interpretation

Reducing the height of the two W tiers is expensive optically because it removes much of the angular shielding that produces the ALR black level. The W0.15/K0.08 geometry gains compactness but loses far too much ambient rejection and contrast.

Reducing mainly the K cap is much more effective. W0.24/K0.10 is the clean practical candidate: total height falls about 9.4%, pitch about 6.6%, and weighted dark band about 7.8%, while contrast is down only about 1.5% and ambient return rises about 6.0%.

W0.235/K0.10 is the aggressive 10%-limit candidate: total height about 10.9% lower, pitch about 7.6% lower and dark band about 9.5% lower, with brightness +8.4%, ambient +9.8%, and contrast -1.3%. Because ambient is almost exactly at the screening ceiling, it has little robustness margin.

## Decision

Do not pursue W0.15/K0.08. If a shorter-feature physical card is wanted, W0.24/K0.10 is the preferred next print; W0.235/K0.10 is the more aggressive model candidate but sits near the agreed ambient-loss boundary.
