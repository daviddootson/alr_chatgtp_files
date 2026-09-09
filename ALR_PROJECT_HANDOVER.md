# ALR project handover

Updated: 9 September 2026.

## Current converter

The latest printer-facing converter is **`3dprint_black_mirror_wave_grid_v1.159.py`**. It is a complete standalone converter revision committed directly on `main`; it does not load or patch v156/v157/v158 at runtime. Its only separate project Python source dependency is canonical `3dprintv1.179.py` selected with `--source`.

v159 source SHA-256: `f73b1a7f10fc97c1f9fb9112bb7ab38c0fcfa4cc73da91899df820cda66fd57a`.

Do not use v157 for thin-cap printing. v158 fixed its executable cap-Z error; v159 consolidates the established v158 behaviour into a readable standalone source.

Standing source-history rule: every finished new script revision must be committed **in full as a normal directly accessible source file**. Transport payloads, patches, archives, reconstruction mechanisms and workflow artifacts do not count as the finished revision.

## Current physical champion and operational reference

Current physical champion, based on the user's printed/viewed card:

**WWK / W0.24 / K0.16 / S1.30 / V77 / H0**

The current model reference is this same geometry, normalised to **B/A/C = 100/100/100** for future optimisation.

High-resolution three-view reference geometry:

- mean pitch: about **2.24044 mm**
- weighted viewer dark band: about **1.72529 mm**
- total optical height: **0.832 mm**

Viewer-dependent model scoring now uses three horizontal viewer positions:

- centre: **2/3** weight
- viewer aligned with left screen edge: **1/6**
- viewer aligned with right screen edge: **1/6**

Keep the individual per-view scores as diagnostics as well as the weighted result. These are model predictions, not physical measurements.

## Current reduced-cap physical test

The selected new K0.10 physical card is:

**WWK / W0.24 / K0.10 / S1.30 / V75 / H0**

Use v159:

```cmd
py 3dprint_black_mirror_wave_grid_v1.159.py --source 3dprintv1.179.py --piece 1-2 --layer-map wwk --layer-height-mm 0.24 --cap-height-mm 0.10 --physical-height-scale 1.3 --visibility-percent 75 --horizontal-percent 0 --slicer-target orca
```

The V65-V85 reduced-cap sweep is recorded in `studies/ALR_height_reduction_v1.0/V_SWEEP_K010.md`. V75 was selected as the better balanced physical test rather than simply choosing the smallest V65 geometry.

## Cap-position study

`studies/ALR_cap_geometry_v1.0/RESULTS.md`

The existing single-K tilt-derived cap remains the best cap position found for the current WWK champion. A small positive K shift gave no meaningful gain after higher-resolution checking, and larger shifts violate the useful-white visibility target. A rigid two-K cap pair moved together over +/-0.15 mm was worse and was rejected at the cheap centre-only stage.

**Decision for WWK: do not add a K-offset parameter.**

## Height-reduction result

`studies/ALR_height_reduction_v1.0/RESULTS.md`

Aggressively reducing both W tiers, e.g. W0.15/K0.08, destroys too much ambient rejection. Reducing mainly the top K cap is much cheaper optically. W0.24/K0.10 is the clean practical reduced-height direction.

## WK architecture landscape

`studies/ALR_WK_landscape_v1.0/RESULTS.md`

WK is the compact 2-1 pyramid:

```text
    K
  K W
```

The original broad search established that WK can cut feature size dramatically, but S1.3 points generally lost several percent weighted contrast versus WWK. S1.4 improved that trade and became the first selected WK physical-test direction.

## WK best-search follow-up

`studies/ALR_WK_best_search_v1.1/RESULTS.md`

A new staged search revisited WK with the user's hard centre-brightness floor of 95% and preference for lower ambient rather than contrast obtained by simply raising both brightness and ambient. The search extended W/K/S/V through S1.55 and then added WK-specific geometry controls: common W-road shift, rear bottom-K support shift and top-K cap offset.

The strongest ambient-biased high-resolution model candidate that still improves centre brightness is:

**WK / W0.20 / K0.13 / S1.55 / V76 / H0**

with:

- W road **+0.025 mm** forward
- rear bottom K support **-0.240 mm** rearward
- top K cap **+0.005 mm** forward

High-resolution centre result relative to the current WWK reference:

- brightness **100.87**
- ambient **86.84**
- contrast **116.16**

Three-view weighted result:

- brightness **98.56**
- ambient **87.31**
- contrast **112.88**

Mean pitch is about **1.53247 mm** and weighted dark band about **1.23024 mm**, roughly 31.6% and 28.7% smaller than WWK respectively.

A brighter all-round S1.55 alternative uses W +0.025 mm, rear support -0.200 mm and the canonical cap position. It predicts centre B/A/C **103.04 / 89.25 / 115.45** and weighted B/A/C **101.01 / 89.84 / 112.43**, with pitch about **1.48654 mm**.

Useful lower-scale checkpoints are also recorded in the study: S1.4 gives only a modest gain, S1.5 reaches about +13% centre contrast with maintained centre brightness, and S1.525 reaches about +14.6% centre contrast. All of these remain model predictions until physically printed.

Important physical caution: S1.55 has not been physically validated. Its individual road heights are not extreme (W about 0.310 mm, K about 0.2015 mm), but the higher scale changes bead cross-section/volume distribution. The poor S1.67 print means scale-based model gains must not be accepted without a physical card.

## Physical-height evidence

The tall S1.67 test printed poorly. The current proven physical champion remains S1.30. S1.4/S1.5/S1.55 directions are model or pending-physical-test territory and should not replace the proven physical limit until print quality is observed directly.

## Repository workflow

Read `AGENTS.md` for standing rules. In summary:

- develop/test locally;
- publish only finished work;
- keep GitHub lightweight;
- commit every finished script revision in full under its actual filename;
- do not routinely preserve generated G-code/3MF or raw trace dumps;
- keep supporting scripts when they are genuinely reusable;
- no individual file over 50,000,000 bytes;
- verify important GitHub files after publication before reporting completion;
- distinguish physical observations, model predictions and generated/audited software results.

Repository: `daviddootson/alr_chatgtp_files`.
Latest converter: `3dprint_black_mirror_wave_grid_v1.159.py`.
Canonical emitter dependency: `3dprintv1.179.py`.
