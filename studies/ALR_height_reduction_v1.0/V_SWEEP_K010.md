# Reduced-cap visibility sweep: WWK / W0.24 / K0.10 / S1.30 / H0

Date: 9 September 2026

## Purpose

Test whether changing the visibility/shadow target helps the reduced-cap geometry after W0.24/K0.10 was identified as the preferred shorter-feature candidate. Sweep V65 through V85 in 2-point increments.

Current operational reference remains WWK / W0.24 / K0.16 / S1.30 / V77 / H0 = B/A/C 100/100/100 using the centre-heavy three-view weighting (centre 2/3, left 1/6, right 1/6).

The existing W0.24/K0.10/V77 reduced-cap card is the local comparison point.

## Staged trace

All requested values V65,67,...,85 were first screened with a low-cost centre-view trace. V81, V83 and V85 are not geometrically feasible because the single K cap itself prevents that much useful-white visibility.

The useful V65-V77 region was then run with the full three-view model. A final high-resolution confirmation was performed for V65 versus V77.

## Detailed three-view sweep

Indices below are relative to the current operational champion (W0.24/K0.16/V77 = 100/100/100).

| V | Pitch mm | Weighted dark band mm | Brightness | Ambient | Contrast |
|---:|---:|---:|---:|---:|---:|
| 65 | 1.9802 | 1.5071 | 104.65 | 107.54 | 97.31 |
| 67 | 1.9992 | 1.5203 | 104.87 | 107.33 | 97.70 |
| 69 | 2.0180 | 1.5342 | 104.80 | 107.02 | 97.93 |
| 71 | 2.0379 | 1.5485 | 104.83 | 106.73 | 98.22 |
| 73 | 2.0562 | 1.5620 | 104.77 | 106.51 | 98.36 |
| 75 | 2.0758 | 1.5762 | 104.77 | 106.29 | 98.57 |
| 77 | 2.0939 | 1.5905 | 104.46 | 106.04 | 98.51 |

V79 was screened but not promoted because it increases pitch and did not improve the optical trade versus V77. V81+ are infeasible as noted above.

## Final high-resolution confirmation

Using 1536 viewer rays, 128 bead segments, 768 ambient directions, a 3x3 local card grid and all three viewer positions:

- Current champion W0.24/K0.16/V77: pitch 2.24088 mm, dark band 1.72593 mm, B/A/C 100/100/100.
- Reduced cap W0.24/K0.10/V77: pitch 2.09401 mm, dark band 1.59036 mm, B/A/C 104.585 / 106.128 / 98.546.
- Reduced cap W0.24/K0.10/V65: pitch 1.98061 mm, dark band 1.50735 mm, B/A/C 104.722 / 107.563 / 97.359.

Relative to the reduced-cap V77 card, V65 changes:

- pitch: -5.4%
- weighted dark band: -5.2%
- brightness: +0.13%
- ambient return: +1.35%
- contrast: -1.20%

Relative to the current physical champion, V65 remains well inside the agreed 10% envelope: brightness +4.7%, ambient +7.6%, contrast -2.6%.

## Conclusion

Lowering the visibility target does help the reduced-cap geometry. Within the requested V65-V85 range, V65 gives the smallest features while staying comfortably inside the 10% optical-loss rule. It is therefore the strongest compact-feature candidate from this sweep.

The current physical champion is not replaced until a physical print confirms the trade. Model predictions are not physical measurements.