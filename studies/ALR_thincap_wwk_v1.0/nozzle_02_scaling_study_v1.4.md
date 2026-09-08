# Thin-cap WWK 0.4 -> 0.2 mm nozzle geometric scaling study v1.4

Date: 2026-09-08

## Physical checkpoint promoted to current working best

The user physically printed **WWK / V75 / W dose 0.24 mm / S1.2 / K cap 0.165 mm / H0** with the 0.4-mm road architecture and reported: great black, good colour response, fairly bright, and substantially better than their commercial ALR screen. The remaining problem is feature size.

This study asks whether a 0.2-mm nozzle/road architecture can make the same optical structure at approximately half linear size.

## Scaling rule tested

For exact geometric scaling, road width and material-dose heights are all divided by two while S, V and H remain unchanged:

- road width: 0.400 -> 0.200 mm
- W dose: 0.240 -> 0.120 mm
- K cap dose: 0.165 -> 0.0825 mm
- physical scale: S1.2 unchanged
- visibility: V75 unchanged
- H0 unchanged

This makes the physical W height 0.288 -> 0.144 mm, cap physical height 0.198 -> 0.099 mm, and total optical height 0.774 -> 0.387 mm. The 3-2-1 base footprint shrinks 1.200 -> 0.600 mm.

The user-specified minimum material-dose layer height is 0.08 mm. The chosen physical best is unusually convenient because its exactly halved cap dose is 0.0825 mm, just above that floor.

## Model change

The existing thin-cap v156 reconstructed model was generalized from fixed 0.4-mm roads to a selectable road width. All width-dependent geometry was scaled: half-width blocker radius, 3-2-1 road centres/footprint, physical-clearance floor, white-surface samples, finite blockers and periodic pitch. The same dimensionless bead exponent was retained at equal S, which is the geometric-similarity assumption.

Scores remain normalized to the current PETG 0.4-mm KWK / 0.20 / S1.2 / V70 / H0 reference = B/A/C 100/100/100.

## Highest-resolution check of the physically successful case

Final check: 1536 viewer rays, 128 bead segments, 768 ambient directions, 3x3 card positions and three viewer offsets.

| case | road width | W dose | K cap | S | V | Brightness | Ambient | Contrast | mean pitch | mean viewer dark band | optical height |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Current physical best | 0.400 | 0.240 | 0.165 | 1.2 | 75 | 115.543 | 104.182 | 110.905 | 2.128650 | 1.591531 | 0.774 |
| Exact half-scale 0.2 | 0.200 | 0.120 | 0.0825 | 1.2 | 75 | 115.576 | 104.192 | 110.926 | 1.064990 | 0.796192 | 0.387 |

The optical scores are effectively unchanged (<0.04 index-point differences). Pitch and viewer dark band are essentially halved. The residual non-exact half in pitch is from the slowly varying screen/projector field over finite absolute distances; it is only about 0.06%.

## Other top/control cases

Fresh 1024-ray / 96-segment / 512-ambient comparisons:

| geometry | 0.4-mm result B/A/C | 0.2-mm scaled result B/A/C | 0.4 pitch | 0.2 pitch | 0.4 dark | 0.2 dark | note |
|---|---|---|---:|---:|---:|---:|---|
| KWK reference, L0.20 S1.2 V70 | 100/100/100 | 100.02/99.96/100.05 | 1.3256 | 0.6630 | 1.0256 | 0.5129 | exact half scaling works |
| WWK W0.24 K0.165 S1.2 V75 | 115.56/104.11/110.99 | 115.55/104.12/110.98 | 2.1286 | 1.0650 | 1.5916 | 0.7962 | exact half; cap 0.0825 is legal |
| WWK W0.24 K0.16 S1.3 V77 | 106.01/90.41/117.26 | 105.98/90.40/117.24 | 2.2408 | 1.1211 | 1.7167 | 0.8589 | exact half; K cap lands exactly at 0.08 floor |
| WWK W0.22 K0.10 S1.2 V50 | 134.70/133.94/100.57 | 126.59/124.24/101.89 | 1.6759 | 0.9088 | 1.1994 | 0.6642 | exact half would require K0.05; 0.08 floor changes geometry |

For the last row, the mathematically exact but **unprintable under the 0.08-mm rule** half-scale cap K0.05 would predict B/A/C about 134.83/133.94/100.66, pitch 0.8384 mm and dark band 0.5998 mm. Raising the cap to the allowed 0.08 mm sacrifices some brightness but improves rejection/contrast and increases pitch/shadow.

## Useful 0.2-mm variants around the physical best

At W0.120 / S1.2 / V75:

- K0.080: B~115.98 / A~104.58 / C~110.90, pitch ~1.0588 mm, dark ~0.7905 mm.
- K0.0825 exact half: B~115.41 / A~104.13 / C~110.83 at medium resolution, pitch ~1.0650 mm, dark ~0.7963 mm. Highest-res scoring returns B~115.58 / A~104.19 / C~110.93.
- K0.085: B~114.91 / A~103.60 / C~110.91, pitch ~1.0712 mm, dark ~0.8019 mm.
- K0.090: B~113.61 / A~102.56 / C~110.77, pitch ~1.0838 mm, dark ~0.8136 mm.
- K0.100: B~111.44 / A~100.65 / C~110.72, pitch ~1.1092 mm, dark ~0.8367 mm.

Thus the small-nozzle architecture also gives a useful cap-height trade while remaining around half the current physical feature size.

## Main conclusion

**The user's physically successful WWK V75 / W0.24 / K0.165 / S1.2 / H0 geometry is almost an ideal candidate for exact 2:1 miniaturisation.** Its half-height cap is 0.0825 mm, narrowly above the 0.08-mm minimum, so the whole 3-2-1 cross-section can be scaled almost exactly by 50% without hitting the layer floor.

Under geometric optics, the model predicts essentially identical brightness, ambient rejection and contrast, while pitch, silhouette height, base footprint and predicted viewer dark band all shrink to approximately half.

The important remaining uncertainty is physical printing, not ray geometry: a 0.2-mm nozzle must actually produce a roughly 0.2-mm road with a bead profile geometrically similar to the successful 0.4-mm version. Flow, PETG surface finish, nozzle-tip flattening, filament swaps and path/chord tolerances may prevent exact similarity.

## Converter implications if implemented

The current v1.158 printer converter is still a 0.4-mm-road implementation. A proper 0.2-mm revision should not merely change slicer nozzle diameter. It should scale the optical engine's road width and all width-dependent planning/audits to 0.2 mm: road-centre spacing, 3-2-1 footprint, finite blocker half-width, physical-gap floor, full-arc halo/clearance, print-width metadata and extrusion calibration. Curve/chord planning and small geometric tolerances should also be reviewed for half-size roads rather than assumed suitable unchanged.

No printer-facing converter was changed by this study.
