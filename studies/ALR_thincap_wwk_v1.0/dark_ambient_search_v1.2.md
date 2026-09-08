# Thin-cap WWK darkest-ambient search v1.2

Date: 2026-09-08

Reference: PETG KWK, W dose 0.20 mm, S1.2, V70, H0, v156 spacing = B/A/C 100/100/100, pitch ~1.326 mm, viewer dark band ~1.044 mm.

Objective: minimize uniform ambient index subject to brightness index >=105. H0 fixed. Broad search covered W dose, K-cap dose, physical height scale, visibility and spacing variations. Production-relevant refinement then restricted to automatic v156/v158 visibility spacing (no artificial additive pitch offset).

Several thousand coarse cases were screened across approximately W=0.18-0.28 mm, K cap=0.06 mm up to W dose, S=1.0-1.70, V=45-95, plus explicit spacing probes. Promising regions were re-run over the 3x3 piece-1-2 card sample and three viewer offsets. Final candidates were checked at 1024 viewer rays, 96 bead segments and 512 ambient directions.

## Best directly printable auto-spacing point found

WWK / W0.200 / K0.115 / S1.68 / V75 / H0

- Pitch offset: 0 (normal automatic spacing; directly expressible in v1.158)
- Mean pitch: 2.262364 mm
- Mean viewer dark band: 1.789348 mm
- Actual target-white fraction mean: 0.752803
- Brightness index: 105.4549
- Ambient index: 81.0884
- Contrast index: 130.0493
- Total optical height above base: 0.8652 mm
- Physical W tier height: 0.3360 mm each
- Physical K-cap height: 0.1932 mm

Relative to reference this predicts +5.45% brightness, -18.91% uniform ambient pickup, and +30.05% image/ambient contrast index. The cost is a much wider pitch and viewer dark band.

V75.5 was essentially identical (B=105.4339, A=81.0858, C=130.0275), so V75 is preferred as the cleaner setting and has slightly more brightness/contrast margin.

## Nearby alternative with slightly smaller shadow

WWK / W0.200 / K0.120 / S1.67 / V72 / H0

- Mean pitch: 2.241735 mm
- Mean viewer dark band: 1.773366 mm
- Brightness index: 105.6993
- Ambient index: 81.5691
- Contrast index: 129.5825

This gives up ~0.48 ambient-index points versus the darkest point, but gains ~0.24 brightness points and trims ~0.016 mm from the predicted viewer dark band.

## Comparison to earlier candidates

- Thin-cap W0.22/K0.10/S1.2/V50: about B134.8 / A134.0 / C100.6.
- 115%-brightness trade candidate: about B114.8 / A103.4 / C111.0.
- Earlier ambient-matched candidate: about B111.1 / A100.0 / C111.1.
- New darkest-auto candidate: B105.45 / A81.09 / C130.05.

These are reconstructed optical-model predictions, not physical measurements. S1.68 is substantially taller than the established S1.2 baseline, so printability/shape fidelity should be physically checked before treating the prediction as validated hardware performance.
