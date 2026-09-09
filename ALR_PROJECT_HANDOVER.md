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

- mean pitch: about **2.24088 mm**
- weighted viewer dark band: about **1.72593 mm**
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

The existing single-K tilt-derived cap remains the best cap position found. A small positive K shift gave no meaningful gain after higher-resolution checking, and larger shifts violate the useful-white visibility target. A rigid two-K cap pair moved together over +/-0.15 mm was worse and was rejected at the cheap centre-only stage.

**Decision: do not add a K-offset parameter.**

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

A broad fast centre-only sweep explored:

- W dose 0.12-0.28 mm
- K dose 0.06-0.18 mm
- S1.0, S1.1, S1.2, S1.3
- V45-V85
- 2,268 coarse combinations

Bad regions were rejected cheaply before detailed tracing. The useful WK basin is strongly concentrated at **S1.30**, approximately W0.21-0.23, K0.12-0.16 and V70-80. Lower scales lose too much angular shielding.

Final high-resolution three-view results show WK does **not** beat WWK on weighted contrast, but it is a serious compact alternative: the useful basin cuts pitch/dark-band size by roughly **36-41%** while losing only about **4-5% weighted contrast**.

Two physically interesting WK points are:

1. **Best weighted optical balance:** `WK / W0.225 / K0.145 / S1.30 / V78 / H0`
   - pitch about **1.3943 mm**
   - weighted dark band about **1.1043 mm**
   - total height **0.4810 mm**
   - B/A/C about **93.58 / 97.31 / 96.17** relative to the current WWK reference
   - pitch about **37.8% smaller** than WWK

2. **Bright compact point:** `WK / W0.220 / K0.120 / S1.30 / V78 / H0`
   - pitch about **1.3166 mm**
   - weighted dark band about **1.0293 mm**
   - total height **0.4420 mm**
   - B/A/C about **99.55 / 104.31 / 95.44**
   - pitch about **41.3% smaller** than WWK

The three-view calculation matters: centre-only WK results looked closer to WWK, but the right-edge viewer is weaker than the left-edge gain, reducing the weighted result. WWK therefore remains the physical and numerical champion until a WK card is printed and viewed.

Complete reusable study source is committed under `studies/ALR_WK_landscape_v1.0/`, with its direct supporting source dependencies also committed normally rather than as reconstruction payloads.

## Physical-height limit

The tall S1.67 test printed poorly. Treat **S1.30 as the current upper physical-height-scale limit** unless new physical evidence supports going higher.

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
