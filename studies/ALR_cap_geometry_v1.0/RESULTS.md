# ALR cap geometry study v1.0

Date: 9 September 2026

## Purpose

Test whether the top black cap on the current WWK physical winner can be repositioned, or replaced by a rigid two-K pair, to hide more exposed white and improve contrast without materially reducing useful projector return.

No G-code or 3MF outputs are archived for this study. Development and ray tracing were performed locally; this file records only the durable result.

## New operational reference

Current physical winner and now the optimisation reference:

- layer map: `WWK`
- W material dose: `0.24 mm`
- K cap dose: `0.16 mm`
- physical-height scale: `1.30`
- visibility: `77%`
- horizontal rotation: `0%`
- current single-K cap at its existing v158 tilt-derived position

New viewer scoring for future optical studies:

- centre viewer: 2/3 weight
- viewer aligned with left screen edge: 1/6 weight
- viewer aligned with right screen edge: 1/6 weight
- viewer distance and eye height otherwise unchanged

Final high-resolution reference calculation used 1536 viewer rays, 128 bead segments, 768 ambient directions, a 3x3 local card grid and all three viewer positions.

Against the historical KWK / L0.20 / S1.2 / V70 / H0 reference, the new weighted reference gives:

- brightness index: **104.55**
- ambient index: **90.40**
- contrast index: **115.65**
- mean pitch: **2.24044 mm**
- weighted viewer dark band: **1.72529 mm**

Per-view new-reference indices against the historical reference:

| Viewer | Brightness | Ambient | Contrast |
|---|---:|---:|---:|
| Left edge | 60.19 | 75.65 | 79.57 |
| Centre | 102.75 | 90.41 | 113.65 |
| Right edge | 132.32 | 99.88 | 132.48 |
| 2/3 centre + 1/6 left + 1/6 right | **104.55** | **90.40** | **115.65** |

For future optimisation this WWK geometry is normalised to **100 / 100 / 100** for weighted brightness / ambient / contrast. The older KWK case remains the historical reference only.

## Cap search

### Single K

The current single-K cap was swept broadly from -0.30 to +0.30 mm relative to its existing tilt-derived position using a low-cost centre-view screen, followed by finer tests around the current position.

Negative movement exposed more useful white and could increase brightness, but generally increased ambient return by a similar or larger amount. The promising-looking fine positions were promoted to the full three-view trace:

| Single-K offset | Weighted brightness | Weighted ambient | Weighted contrast |
|---:|---:|---:|---:|
| -0.030 mm | 106.77 | 107.16 | 99.64 |
| -0.020 mm | 104.49 | 104.66 | 99.84 |
| -0.010 mm | 102.26 | 102.34 | 99.93 |
| 0.000 mm control | **100.00** | **100.00** | **100.00** |

Positive movement hides more white. Larger positive shifts fail the V77 useful-white visibility requirement. A +0.005 mm shift initially appeared to gain about 0.1% contrast at moderate resolution, but finer white-surface sampling showed it is not valid across the card at V77.

The last clearly feasible positive shift tested at high resolution was +0.0025 mm:

- brightness: **99.443**
- ambient: **99.433**
- contrast: **100.010**

The approximately +0.01% contrast difference is too small to regard as a real improvement and costs about 0.56% brightness. It is treated as numerical equivalence, not a new winner.

### Rigid KK pair

Two K beads were kept at fixed W-to-W spacing and moved together as a rigid pair. Zero offset means directly above the two W roads below. The permitted pair shift was -0.15 to +0.15 mm.

The complete rigid-KK family was screened centre-only first. None beat the current single-K control. The best refined region remained below the control contrast (about 98.3 at best), while the more-covering positions including direct-over-WW fail the V77 useful-white visibility requirement. Per the agreed staged strategy, no KK candidate was promoted to the expensive three-view trace.

## Conclusion

The existing single-K tilt-derived cap remains the best geometry found. Adding a second K or moving the single K further into the white does not produce a meaningful gain at V77. No converter geometry change is justified from this study.

The important durable change is the new three-view scoring rule and the re-baselining of WWK / 0.24 / C0.16 / S1.30 / V77 / H0 as the 100-point operational reference.