# Thin-cap WWK brightness/contrast trade v1.1

Date: 2026-09-08

Reference: PETG KWK, W dose 0.20 mm, S1.2, V70, H0, v156 spacing = B/A/C 100/100/100, pitch ~1.326 mm, viewer dark band ~1.044 mm.

Fresh high-resolution reruns used the same resolution as the prior verification set: 768 viewer rays, 80 bead segments, 384 ambient directions, 3x3 card positions, three viewer offsets.

## Around 115% brightness

Candidate: WWK, W dose 0.24 mm, K cap dose 0.165 mm, S1.2, V75, H0, with +0.050 mm pitch relative to the local automatic visibility solve.

- Mean pitch: 2.178650 mm
- Mean viewer dark band: 1.651705 mm
- Brightness index: 114.8160
- Ambient index: 103.4280
- Contrast index: 111.0106
- Mean actual white fraction: 0.804563

This is the strong trade candidate: about +14.8% brightness and +11.0% contrast versus reference, for about +3.4% ambient pickup.

## Ambient-matched candidate

Candidate: WWK, W dose 0.24 mm, K cap dose 0.213 mm, S1.2, V80, H0, automatic spacing.

- Mean pitch: 2.313729 mm
- Mean viewer dark band: 1.771262 mm
- Brightness index: 111.1202
- Ambient index: 100.0085
- Contrast index: 111.1107

This is effectively ambient-neutral relative to the reference while gaining about +11.1% brightness and +11.1% contrast. The cost is substantially wider pitch/viewer shadow.

## Nearby lower-shadow ambient-matched variant

Candidate: WWK, W dose 0.24 mm, K cap dose 0.205 mm, S1.2, V75, H0, +0.025 mm pitch.

- Mean pitch: 2.254842 mm
- Mean viewer dark band: 1.728373 mm
- Brightness index: 110.5200
- Ambient index: 99.9085
- Contrast index: 110.6212

This gives up ~0.6 brightness point to reduce the shadow modestly while keeping ambient slightly below reference.

## Conclusion

Within the thin-cap WWK space tested, the Pareto front is approximately:

- B~115 requires A~103-104 and gives C~111.
- A~100 allows B~110.5-111.1 and C~110.6-111.1.

No tested configuration reached B~115 while holding A~100.

These are optical-model predictions, not physical measurements.
