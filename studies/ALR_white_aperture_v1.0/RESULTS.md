# ALR WWK white-aperture / rear-support study v1.0

Date: 9 September 2026

## Goal

Keep the current physical champion fixed at `WWK / W0.24 / K0.16 / S1.30 / V77 / H0` and search geometry changes that preferentially lower centre ambient return while maintaining or improving centre brightness. Centre brightness below 95% of the current reference was a hard rejection rule.

The search first screened common white-road offsets, differential upper/lower white stagger, rear black-support offsets, and combinations. Weak candidates were rejected with low-ray centre-only tracing. Promising candidates were re-run on a 3x3 local card grid and then at 1536 viewer rays, 128 bead segments, 768 ambient directions, dense white-visibility sampling and all three viewing positions.

## Main finding

The useful mechanism is to separate the rear black support staircase slightly from the white optical column. Moving the rear black support roads rearward reduces ambient return with very little effect on useful projector return. A tiny forward shift of both white roads can then recover or slightly improve brightness.

The best ambient-biased micro-result is:

**both W roads +0.004 mm; rear black support roads -0.175 mm; top K cap unchanged**

High-resolution result, indexed to the current geometry at the same viewing position:

| View | Brightness | Ambient | Contrast |
|---|---:|---:|---:|
| Left edge | 101.91 | 95.38 | 106.85 |
| Centre | **100.02** | **97.27** | **102.83** |
| Right edge | 99.38 | 98.51 | 100.88 |
| Weighted 1/6 - 2/3 - 1/6 | 99.96 | 97.34 | 102.69 |

Mean pitch changes from about 2.24044 mm to 2.26855 mm (+1.25%).

A slightly brighter alternative is:

**both W roads +0.0075 mm; rear black support roads -0.18 mm**

- centre B/A/C: **100.73 / 97.87 / 102.92**
- weighted B/A/C: **100.62 / 97.95 / 102.73**
- pitch about **2.27555 mm** (+1.57%)

A stronger brightness-biased alternative, `W +0.010 / support -0.18`, gives centre B/A/C about **101.33 / 98.44 / 102.94**.

## Interpretation and printability

The selected geometry no longer forms a fully contiguous solid 3-2-1 cross-section. The rear black support branch moves rearward, leaving a narrow black-floor trench between it and the white optical column. For `W +0.004 / support -0.175`, the nominal centre-to-centre gap between the nearest rear support and leading white road is about 0.579 mm, corresponding to roughly a 0.179 mm clear slot for nominal 0.4 mm bead width.

The elevated roads remain well supported vertically: the upper W remains almost directly over the lower W, the K cap remains over the upper W, and the upper rear K support remains over the lower rear K support. The model therefore treats the geometry as printable, but the physical slot width and bead spreading need a real card to validate.

## Decision

This is the first geometry study in this series to achieve the preferred direction at centre: **ambient lower while useful brightness is maintained/slightly improved**. No production converter change has yet been made. The next implementation step should add a controlled geometry mode for a physical A/B test rather than changing the default champion geometry immediately.

All values are optical-model predictions, not physical measurements.
