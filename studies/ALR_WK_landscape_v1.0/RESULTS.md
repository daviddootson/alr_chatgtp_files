# ALR WK landscape study v1.0

Date: 9 September 2026

## Purpose

Explore the remaining compact 2-1 `WK` pyramid architecture against the current physical/operational benchmark, using broad fast rejection followed by detailed centre-biased three-view ray tracing.

Current benchmark: `WWK / W0.24 / K0.16 / S1.30 / V77 / H0`, normalised to B/A/C = 100/100/100. Final benchmark geometry in this study: pitch 2.24088 mm, weighted viewer dark band 1.72593 mm, total optical height 0.832 mm.

`WK` is modelled as a 2-1 pyramid: bottom tier `K W` (rear/support black plus one leading white working road), with one tilt-derived `K` cap above.

## Search strategy

Broad centre-only low-ray sweep:

- W dose: 0.12 to 0.28 mm in 0.02 mm steps
- K dose: 0.06 to 0.18 mm in 0.02 mm steps
- physical-height scale: S1.0, S1.1, S1.2, S1.3
- visibility/shadow target: V45 to V85 in 5-point steps
- 2,268 combinations tested

Clearly weak regions were rejected before three-view work. The useful region concentrated strongly at S1.3, around W0.21-0.23, K0.12-0.17 and V70-80.

A finer centre-only search then covered W0.20-0.24, K0.11-0.17, S1.25/S1.30 and V64-82. Only the best centre-screen candidates were promoted to three-view calculations. A final micro-refinement around the best basin tested intermediate K values and V77-79.

## Broad landscape result

The lower scale values are not competitive on contrast. Best rough centre-only contrast by scale was approximately:

| Scale | Best rough centre-only contrast index | Interpretation |
|---|---:|---|
| S1.0 | 69.4 | reject |
| S1.1 | 87.3 | reject |
| S1.2 | 94.0 | usable but inferior |
| S1.3 | ~99.9 | promising region |

This makes S1.30 the clear WK working scale within the current physically accepted scale limit.

## Final high-resolution three-view results

Final checks used 1536 viewer rays, 128 bead segments, 768 ambient directions, a 3x3 local card grid, and the established viewer weighting: centre 2/3, left edge 1/6, right edge 1/6.

All B/A/C indices are relative to the current WWK benchmark = 100/100/100.

| WK geometry | Pitch mm | Dark band mm | Total height mm | B | A | C |
|---|---:|---:|---:|---:|---:|---:|
| **W0.225 / K0.145 / S1.30 / V78** | **1.3943** | **1.1043** | **0.4810** | **93.58** | **97.31** | **96.17** |
| W0.225 / K0.140 / S1.30 / V78 | 1.3809 | 1.0922 | 0.4745 | 94.17 | 98.00 | 96.09 |
| W0.225 / K0.150 / S1.30 / V78 | 1.4077 | 1.1169 | 0.4875 | 92.81 | 96.56 | 96.12 |
| W0.225 / K0.160 / S1.30 / V76 | 1.4170 | 1.1284 | 0.5005 | 91.50 | 95.37 | 95.95 |
| **W0.220 / K0.120 / S1.30 / V78** | **1.3166** | **1.0293** | **0.4420** | **99.55** | **104.31** | **95.44** |
| W0.225 / K0.130 / S1.30 / V72 | 1.3000 | 1.0270 | 0.4615 | 95.52 | 100.29 | 95.24 |

### Refined best-contrast WK point

`WK / W0.225 / K0.145 / S1.30 / V78 / H0` is the best refined weighted-contrast point found in the local basin.

Relative to the WWK benchmark:

- pitch: -37.8%
- weighted dark band: -36.0%
- total optical height: -42.2%
- brightness: -6.4%
- ambient return: -2.7%
- contrast: -3.8%

Per-view contrast indices are approximately left 106.45, centre 97.59, right 92.55. The three-view weighting therefore exposes a real left/right asymmetry that the centre-only sweep hides.

### Bright compact WK point

`WK / W0.220 / K0.120 / S1.30 / V78 / H0` keeps weighted brightness essentially unchanged while pushing feature size harder:

- pitch: -41.25%
- weighted dark band: -40.36%
- total optical height: -46.88%
- brightness: -0.45%
- ambient return: +4.31%
- contrast: -4.56%

Per-view contrast indices are approximately left 111.60, centre 97.05, right 89.80. It therefore has a slightly weaker right-edge result than the refined-best-contrast case.

## Interpretation

WK does not beat the current WWK benchmark on weighted contrast, so WWK remains the numerical and physical champion. However, WK is far more successful than a simple tier-count reduction might suggest: the best WK basin stays within about 4-5% weighted contrast while reducing ridge pitch and viewer dark-band size by roughly 36-41%.

The three-view model is important here. Centre-only tracing made several WK cases look essentially equal to WWK, but the right-edge viewer loses more than the left gains, reducing the weighted result to roughly C95-96.

The broad search also shows that WK needs the full S1.30 geometry to work well. Lowering scale to S1.0-S1.1 destroys too much angular shielding; S1.2 improves substantially but still does not reach the S1.3 basin.

## Decision / physical candidates

WWK remains the benchmark. No production converter change is required merely from this optical study.

Two WK cards are worth considering physically:

1. **Best optical balance:** `WK / W0.225 / K0.145 / S1.30 / V78 / H0` — retains the strongest weighted contrast found while cutting pitch ~38%.
2. **Maximum compactness with benchmark-like brightness:** `WK / W0.220 / K0.120 / S1.30 / V78 / H0` — cuts pitch ~41%, keeps brightness essentially unchanged, but accepts ~4.6% weighted contrast loss and a slightly weaker right-edge result.

All values are model predictions, not physical measurements. A WK geometry should not replace the current physical champion until printed and viewed.
