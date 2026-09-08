# ALR thin-cap WWK prediction v1.0

## Scope

Analysis-only study of a WWK optical head in PETG using the reconstructed v156 mapped-white spacing/scoring model. The two W tiers retain normal WWK geometry. Only the final top K road is made thinner. No printer converter, G-code or 3MF was generated.

Common reference: **PETG KWK, 0.20 mm dose, S1.2, V70, H0, piece 1-2, v156 spacing** = 100 brightness / 100 ambient pickup / 100 contrast index. High-resolution local-model mean pitch: **1.326 mm**. Mean centre-viewer dark band: **1.044 mm**.

Central material assumptions are inherited unchanged from material model v1.2: PETG eta=1.57, GGX roughness alpha=0.22, white effective body return 0.75, black effective body return 0.025. These are modelling priors, not spool measurements.

## Main result

The thin K cap works strongly relative to normal full-cap WWK.

At **W=0.24 mm, K cap=0.10 mm, S1.2, V60** the high-resolution prediction is brightness **122.90**, ambient **113.85**, contrast **107.94**, mean pitch **1.842 mm**, and mean viewer dark band **1.374 mm**.

Compared with normal full-cap WWK at the same W dose and V60, this cuts pitch by **15.5%** and viewer dark band by **18.8%**, while raising predicted brightness by **15.2%** and changing contrast by only **-0.24%**.

That is the cleanest validation of the idea: most of full WWK's contrast survives while a large part of its spacing/shadow penalty disappears.

## High-resolution selected cases

| Case | Mean pitch mm | Dark band mm | Brightness | Ambient pickup | Contrast | Actual visible-white fraction |
|---|---:|---:|---:|---:|---:|---:|
| Current KWK reference | 1.326 | 1.044 | 100.00 | 100.00 | 100.00 | — |
| Full-cap WWK, W0.24/K0.24, V60 | 2.182 | 1.692 | 106.68 | 98.59 | 108.20 | 0.602 |
| Thin cap W0.24/K0.10, V40 | 1.653 | 1.246 | 119.91 | 117.84 | 101.75 | 0.402 |
| Thin cap W0.24/K0.10, V45 | 1.700 | 1.277 | 121.25 | 116.82 | 103.79 | 0.452 |
| Thin cap W0.24/K0.10, V50 | 1.748 | 1.309 | 122.17 | 115.78 | 105.51 | 0.502 |
| Thin cap W0.24/K0.10, V55 | 1.796 | 1.342 | 122.66 | 114.81 | 106.84 | 0.552 |
| Thin cap W0.24/K0.10, V60 | 1.842 | 1.374 | 122.90 | 113.85 | 107.94 | 0.602 |
| Thin cap W0.22/K0.10, V50 | 1.676 | 1.216 | 134.76 | 133.99 | 100.57 | 0.502 |
| W0.22/K0.10, V50, +0.05 mm pitch | 1.726 | 1.250 | 135.36 | 132.48 | 102.18 | 0.556 |

## Shadow / visibility sweep

The broad study covered V35 through V80 in 5-point steps, W doses 0.20/0.22/0.24 mm, K-cap doses from 0.06 mm through full height, and explicit pitch offsets around promising states.

For **W0.24/K0.10**, the medium-resolution 9-position sequence is:

| V | Pitch mm | Dark band mm | Brightness | Ambient | Contrast |
|---:|---:|---:|---:|---:|---:|
| 35 | 1.605 | 1.215 | 117.96 | 118.95 | 99.17 |
| 40 | 1.653 | 1.246 | 119.71 | 117.75 | 101.66 |
| 45 | 1.700 | 1.277 | 121.08 | 116.82 | 103.65 |
| 50 | 1.748 | 1.309 | 122.01 | 115.81 | 105.35 |
| 55 | 1.796 | 1.341 | 122.52 | 114.81 | 106.72 |
| 60 | 1.842 | 1.374 | 122.92 | 113.94 | 107.88 |
| 65 | 1.890 | 1.408 | 122.73 | 112.97 | 108.64 |
| 70 | 1.936 | 1.443 | 122.35 | 111.98 | 109.26 |
| 75 | 1.981 | 1.476 | 121.90 | 111.20 | 109.62 |
| 80 | 2.038 | 1.514 | 123.16 | 111.65 | 110.31 |

V40 is the smallest-shadow high-resolution W0.24/K0.10 state that still beats the current reference in both brightness and contrast: **+19.9% brightness and +1.75% contrast**, with a dark band **+19.3%** wider than the current reference. V50 gives **+5.51% contrast** at **+22.2% brightness**, but a **+25.4%** wider viewer band.

The lower-dose **W0.22/K0.10/V50** case is also notable: brightness **134.76**, contrast **100.57**, dark band **1.216 mm**. It is extremely bright and almost contrast-neutral, but it still does not beat the current reference on viewer-shadow width.

## Cap-height sweep

At W0.24/V50, 0.10 mm is a useful knee. High-resolution checks give:

- K0.08: brightness 122.08, contrast 103.76, dark band 1.299 mm.
- K0.10: brightness 122.17, contrast 105.51, dark band 1.309 mm.
- K0.12: brightness 120.31, contrast 106.16, dark band 1.346 mm.

Moving 0.08→0.10 gains about 1.75 contrast points for only 0.010 mm more viewer band. Moving 0.10→0.12 adds only 0.65 more contrast points while adding 0.036 mm of band and reducing brightness. Thus **0.10 mm is a strong first physical cap-height candidate**, with 0.08 and 0.12 mm useful neighbours.

## Explicit pitch probes

The spacing probes show that nominal V is not a separate optical magic variable. W0.24/K0.10 V40 with +0.10 mm pitch reaches actual white exposure ~0.505 and scores brightness **122.21**, contrast **105.62**, dark band **1.312 mm**—almost the same physical/optical state as V50 auto-spacing. Likewise V45 +0.05 mm converges on the same region.

So future optimisation should treat **physical pitch and actual visible-white fraction** as the primary state variables. The nominal V setting is mainly the solver's route to that state.

## What this did and did not achieve

Thin-cap WWK materially improves WWK. It can preserve essentially all full-WWK contrast while cutting WWK's pitch and viewer-shadow penalty by roughly one fifth, or it can be pushed tighter while still retaining strong brightness and some contrast gain versus the current KWK reference.

However, **none of the auto-spacing cases retaining at least reference contrast beat the current KWK reference's 1.044 mm viewer dark band**. The best high-resolution contrast-retaining thin-cap state here is W0.22/K0.10/V50 at about **1.216 mm**, still **16.5% wider** than the current reference.

## Numerical verification and limitations

- Full-height K reproduces standard WWK geometry and pitch in automated tests.
- W-tier sample geometry is invariant to K-cap height by construction and test.
- The complete coarse sweep produced 270 auto-spacing states and 434 explicit pitch probes.
- Selected cases were recomputed at 1536 viewer rays, 128 bead segments, 768 ambient directions, 9 card positions and 3 viewer offsets.
- All 12 automated source/result checks pass.

This remains a local reconstructed v156 model, not full curved-lattice regeneration and not a physical photometric measurement. Material coefficients, bead deformation, transmission, multiple inter-ridge reflections and real room lighting remain uncalibrated.
