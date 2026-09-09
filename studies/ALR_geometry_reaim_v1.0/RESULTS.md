# ALR WWK geometry re-aim study v1.0

Date: 9 September 2026

## Purpose

Test whether the strong right-side viewing result of the current WWK physical champion can be shifted toward the centre by changing geometry only, while locking the current print/material settings:

- `WWK`
- W dose `0.24 mm`
- K cap dose `0.16 mm`
- physical-height scale `S1.30`
- visibility `V77`
- horizontal setting `H0`

The two experimental geometry controls were:

1. **Arc factor**: `1.0` is the current curved-road field; below 1 flattens the arc toward parallel/flat-road orientation; above 1 increases curvature.
2. **Pyramid tilt offset**: `0 deg` is the current calculated pyramid lean; positive values add extra lean in the tested direction.

These are analysis-only geometry variables. No production converter parameter was added.

## Search strategy

A broad low-ray centre-only screen first covered substantial arc flattening/extra curvature and approximately +/-8 degrees of pyramid tilt. Clearly weaker regions were rejected. A finer search then concentrated around the current arc and small positive tilt offsets. Promising cases were promoted to three-view calculations using the established centre-heavy weighting (left 1/6, centre 2/3, right 1/6), and the finalists were confirmed at 1536 viewer rays, 128 bead segments, 768 ambient directions, a 3x3 card grid and dense white-visibility sampling.

The current operational reference remained the physical champion geometry and was normalised to 100 at each viewing position for change comparisons.

## Main finding

The current arc curvature is already very close to the centre-contrast optimum. Large flattening or extra curvature reduced centre contrast. The useful lever is a small increase in pyramid lean.

A positive tilt of roughly +2.25 to +3 degrees transfers some of the right-side advantage toward the left and centre. Centre brightness rises strongly, but ambient return also rises strongly, so the centre contrast gain is modest.

### Final high-resolution candidates

Indices below are relative to the current geometry at the same viewing position.

| Geometry | Pitch mm | Left B | Centre B | Right B | Left A | Centre A | Right A | Left C | Centre C | Right C | Weighted B | Weighted A | Weighted C |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Current arc 1.000 / tilt +0.000 | 2.24044 | 100.00 | 100.00 | 100.00 | 100.00 | 100.00 | 100.00 | 100.00 | 100.00 | 100.00 | 100.00 | 100.00 | 100.00 |
| Arc 1.000 / tilt +2.250 | 2.26254 | 129.04 | 112.06 | 105.16 | 115.23 | 111.42 | 109.34 | 111.99 | **100.57** | 96.18 | 111.22 | 111.37 | 99.87 |
| Arc 1.000 / tilt +2.500 | 2.26441 | 132.35 | 113.36 | 105.66 | 117.00 | 112.68 | 110.37 | 113.13 | **100.60** | 95.74 | 112.44 | 112.63 | 99.82 |
| Arc 1.000 / tilt +3.000 | 2.26893 | 138.44 | 115.97 | 106.62 | 120.38 | 115.24 | 112.41 | 115.00 | **100.63** | 94.85 | 114.81 | 115.17 | 99.69 |
| Arc 1.020 / tilt +2.250 | 2.26037 | 126.87 | 112.08 | 106.80 | 114.74 | 111.57 | 109.71 | 110.57 | **100.46** | 97.35 | 111.56 | 111.50 | **100.05** |
| Arc 1.035 / tilt +2.375 | 2.25877 | 126.76 | 112.74 | 108.24 | 115.16 | 112.30 | 110.52 | 110.07 | **100.39** | 97.94 | 112.38 | 112.21 | **100.15** |
| Arc 1.015 / tilt +2.625 | 2.26405 | 132.06 | 114.06 | 107.14 | 117.40 | 113.42 | 111.15 | 112.49 | **100.56** | 96.40 | 113.28 | 113.35 | 99.94 |

## Interpretation

The geometry can indeed shift the contrast distribution away from the right side, but there is no large hidden centre-contrast gain. The existing geometry is already close to the centre optimum.

The strongest centre-focused result is approximately **+0.6% centre contrast**, accompanied by roughly **+12 to +16% centre brightness** and a similar increase in centre ambient return. The right-side contrast falls by roughly 4-5%, while left-side contrast improves strongly.

A slightly more curved arc combined with a smaller tilt gives the cleanest all-round compromise. `arc factor 1.035 / tilt +2.375 deg` gives about **+0.39% centre contrast**, **+12.7% centre brightness**, only about **-2.1% right-side contrast**, and approximately **+0.15% weighted contrast**. `arc 1.020 / tilt +2.250 deg` is a similarly balanced point.

The aggressive flattening cases can move the sweet spot leftward much more strongly, but centre contrast then declines; they are not improvements.

## Decision

Do not change the production converter yet. The study shows a real re-aiming effect, but the contrast improvement at centre is small. If a geometry-adjusted physical card is desired, the best model candidates are:

1. **Balanced:** arc factor `1.035`, tilt offset `+2.375 deg`.
2. **Centre-biased:** current arc `1.000`, tilt offset about `+2.5 to +3.0 deg`.

The current WWK physical champion remains the operational reference until a physical print proves otherwise. All figures here are model predictions, not physical measurements.
