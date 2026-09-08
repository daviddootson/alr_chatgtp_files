# Thin-cap WWK scale-limited search v1.3

Date: 2026-09-08

Constraint added after physical print-quality failure at S1.67: **physical-height scale <= 1.30**. The search therefore moved height into material dose instead of scale. H0 remained fixed. W dose was explored up to the converter limit region, K-cap dose and visibility were varied broadly, and promising candidates were rechecked over the 3x3 piece-1-2 sample and three viewer offsets.

Reference: PETG KWK / W0.20 / S1.2 / V70 / H0 / v156 spacing = B/A/C 100/100/100, pitch ~1.326 mm, viewer dark band ~1.044 mm.

Failed tall-card comparison target: WWK / W0.20 / K0.12 / S1.67 / V72 / H0. Fresh 1024-ray verification gives B/A/C 105.699 / 81.569 / 129.582, mean pitch 2.241735 mm, mean viewer dark band 1.773366 mm, total optical height 0.8684 mm. This is a model prediction for the geometry; the physical print itself was reported to have unacceptable print quality.

## Recommended clean S<=1.30 point

**WWK / W0.24 / K0.16 / S1.30 / V77 / H0 / automatic spacing**

Fresh final verification: 1024 viewer rays, 96 bead segments, 512 ambient directions, 3x3 card positions, three viewer offsets.

- Brightness index: **106.010**
- Ambient index: **90.408**
- Contrast index: **117.257**
- Mean pitch: **2.240781 mm**
- Mean viewer dark band: **1.740621 mm**
- Mean actual white fraction: 0.772121
- Total optical height above base: **0.8320 mm**
- Physical W tier height: **0.3120 mm each**
- Physical K-cap height: **0.2080 mm**

This nearly reproduces the failed S1.67 card's pitch and brightness while slightly reducing predicted viewer dark-band width. It does **not** reproduce the tall card's ambient rejection: ambient is ~90.4 rather than ~81.6, so contrast is ~117.3 rather than ~129.6.

## Darkest verified S<=1.30 point at brightness >=105

A denser refinement found:

**WWK / W0.2355 / K0.195 / S1.30 / V77 / H0 / automatic spacing**

- Brightness: **105.038**
- Ambient: **90.114**
- Contrast: **116.561**
- Mean pitch: **2.318747 mm**
- Mean viewer dark band: **1.806869 mm**
- Total optical height: **0.8658 mm**

This is only ~0.29 ambient-index points darker than the clean W0.24/K0.16 case, but it is much closer to the 105% brightness floor and carries a larger shadow. It is therefore not the preferred physical test.

A safer margin variant, W0.236 / K0.190 / S1.30 / V77, gives B/A/C 105.320 / 90.265 / 116.678, pitch 2.308224 mm, dark band 1.797514 mm.

## Main conclusion

Moving height from S-scale into material dose **does recover the useful brightness and overall silhouette/pitch** surprisingly well, but does not reproduce the S1.67 model's unusually strong ambient rejection. At comparable total height, the scale parameter changes the bead aspect/profile and therefore the effective surface-normal distribution; material dose is not optically interchangeable with physical-height scale in this model.

For physical testing, W0.24/K0.16/S1.30/V77 is the recommended compromise because it is simple, has ~1 percentage point more brightness margin than the strict 105 floor, and has a smaller predicted shadow than the darker decimal-dose refinements.

All numbers are reconstructed optical-model predictions, not calibrated physical measurements.
