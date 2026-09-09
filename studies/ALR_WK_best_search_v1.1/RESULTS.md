# ALR WK best-search follow-up v1.1

Date: 9 September 2026

## Goal

Search the compact `WK` 2-1 architecture for a materially better optical trade than the current physical/operational WWK benchmark, with a hard centre-brightness floor of 95%. The preferred direction is lower centre ambient return, with maintained or improved centre brightness, rather than contrast gains caused only by increasing both brightness and ambient.

Reference remains `WWK / W0.24 / K0.16 / S1.30 / V77 / H0`, normalised to B/A/C = 100/100/100. High-resolution reference mean pitch is 2.24044 mm and weighted viewer dark band is about 1.72529 mm.

## Search sequence

The search used staged rejection:

1. Revisited the established WK W/K/S/V basin, extending the scale exploration through S1.55.
2. Promoted only centre candidates that stayed near/above the 95% brightness floor.
3. Added WK-specific geometry controls: common white-road shift, rear black-support shift, and top-K cap offset.
4. Narrowed around promising combinations.
5. Confirmed finalists at 1536 viewer rays, 128 bead segments, 768 ambient directions, 3x3 card positions, dense white-visibility sampling and the established three-view weighting (left 1/6, centre 2/3, right 1/6).

All values are model predictions, not physical measurements.

## Main result

The geometry mechanisms stack strongly in WK. The best ambient-biased candidate that still improves centre brightness is:

**WK / W0.20 / K0.13 / S1.55 / V76 / H0**

with geometry offsets:

- leading W road: **+0.025 mm** forward
- rear bottom K support: **-0.240 mm** rearward
- top K cap: **+0.005 mm** forward from the canonical tilt-derived position

High-resolution result relative to the current WWK reference at each same viewing position:

| View | Brightness | Ambient | Contrast |
|---|---:|---:|---:|
| Left edge | 115.46 | 92.98 | 124.18 |
| Centre | **100.87** | **86.84** | **116.16** |
| Right edge | 89.09 | 85.96 | 103.64 |
| Weighted 1/6 - 2/3 - 1/6 | **98.56** | **87.31** | **112.88** |

Geometry:

- mean pitch: **1.53247 mm** (about 31.6% smaller than WWK)
- weighted dark band: **1.23024 mm** (about 28.7% smaller)
- total WK optical height: **0.5115 mm**

This is the strongest result matching the stated centre objective: centre brightness is slightly higher than the benchmark while centre ambient return is about 13.2% lower, producing about 16.2% higher centre contrast.

## Brighter all-round alternative

A less ambient-biased but brighter candidate is:

**WK / W0.20 / K0.13 / S1.55 / V76**, W +0.025 mm, rear support -0.200 mm, cap unchanged.

- centre B/A/C: **103.04 / 89.25 / 115.45**
- weighted B/A/C: **101.01 / 89.84 / 112.43**
- pitch: **1.48654 mm**
- weighted dark band: **1.18484 mm**

This case improves weighted brightness as well as lowering weighted ambient and still gives a large centre-contrast gain.

## Lower-scale checkpoints

The same geometry concept remains useful at lower scale, with reduced model gain:

| Candidate | Pitch mm | Centre B | Centre A | Centre C | Weighted B | Weighted A | Weighted C |
|---|---:|---:|---:|---:|---:|---:|---:|
| S1.40: W0.22/K0.14/V74, W +0.010, support -0.120, cap -0.020 | 1.39779 | 101.80 | 97.03 | 104.92 | 100.44 | 97.23 | 103.30 |
| S1.50: W0.20/K0.14/V76, W +0.015, support -0.240, cap 0 | 1.50007 | 100.18 | 88.79 | 112.84 | 98.45 | 89.31 | 110.23 |
| S1.525: W0.195/K0.125/V76, W +0.015, support -0.220, cap +0.010 | 1.48501 | 101.07 | 88.19 | 114.60 | 98.86 | 88.75 | 111.40 |
| S1.55 ambient-biased | 1.53247 | 100.87 | 86.84 | 116.16 | 98.56 | 87.31 | 112.88 |
| S1.55 brighter alternative | 1.48654 | 103.04 | 89.25 | 115.45 | 101.01 | 89.84 | 112.43 |

## Physical caution

S1.55 is more aggressive in bead-shape scaling than the previously selected S1.4 WK card and has not been physically validated. However, its individual physical road heights are not extreme: W height is 0.20 x 1.55 = 0.310 mm and K height is 0.13 x 1.55 = 0.2015 mm, close to the current WWK champion's W height of 0.312 mm and K height of 0.208 mm. The higher scale still changes cross-section shape/volume distribution, so print quality must be proven physically before treating the model result as a new champion.

## Conclusion

WK still has substantial unexplored value. The best model result found here is no longer a marginal compactness trade: it predicts a meaningful centre improvement with **slightly higher brightness, materially darker ambient return and roughly +16% centre contrast**, while retaining much smaller pitch and dark-band dimensions than WWK.

The current WWK card remains the physical champion until a modified-WK geometry is implemented and printed.
