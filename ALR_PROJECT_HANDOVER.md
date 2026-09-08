# ALR project handover

Updated: 8 September 2026.

## Latest agreed direction

The latest printer-facing converter is `3dprint_black_mirror_wave_grid_v1.158.py`. It wraps v1.157/v1.156 and retains the adjustable `--cap-height-mm` for the final/top K tier.

v1.157 must not be used for printing thin-cap output: direct audit of a generated WWK package found that its tier-3 marker/descent moved to the intended thin-cap top Z while the executable SUPPORT_SEG and SUPPORT_DRY_TAIL Z words remained at the old full-height v1.156 top. v1.158 corrects those executable coordinates and adds a fail-closed actual-G-code tier-Z/cap-dose audit.

The original practical thin-cap candidate was **WWK / W0.22 / K0.10 / S1.2 / V50 / H0**, predicted at about B/A/C 134.8/134.0/100.6, pitch ~1.676 mm, viewer dark band ~1.216 mm against the current PETG KWK/v156 baseline. These are model predictions, not physical measurements.

A high-resolution trade study found two more contrast-oriented operating points:

- **~115 brightness trade:** WWK / W0.24 / K0.165 / S1.2 / V75 / H0, with +0.050 mm pitch above the local auto-visibility solve: B/A/C **114.816 / 103.428 / 111.011**, mean pitch **2.178650 mm**, mean viewer dark band **1.651705 mm**.
- **Ambient-matched:** WWK / W0.24 / K0.213 / S1.2 / V80 / H0, automatic spacing: B/A/C **111.120 / 100.009 / 111.111**, mean pitch **2.313729 mm**, mean viewer dark band **1.771262 mm**.
- Nearby lower-shadow ambient-matched variant: W0.24 / K0.205 / V75 / +0.025 mm pitch: B/A/C **110.520 / 99.908 / 110.621**, pitch **2.254842 mm**, dark band **1.728373 mm**.

### Darkest-ambient search v1.2

A broad follow-up search minimized uniform ambient subject to **brightness >=105%**. H0 was fixed. Several thousand coarse cases were screened across W dose, K-cap dose, physical height scale, visibility and spacing; promising regions were refined across the full 3x3 piece-1-2 sample and three viewer offsets. Final candidates were checked at 1024 viewer rays, 96 bead segments and 512 ambient directions.

The best **directly printable with normal automatic v158 spacing** found was:

- **WWK / W0.200 / K0.115 / S1.68 / V75 / H0**
- B/A/C **105.455 / 81.088 / 130.049**
- mean pitch **2.262364 mm**
- mean viewer dark band **1.789348 mm**
- physical W height **0.3360 mm** each; physical K-cap height **0.1932 mm**

Relative to the current PETG KWK/v156 reference, this predicts roughly **+5.45% useful brightness, -18.91% uniform ambient pickup and +30.05% contrast index**. The cost is a much wider pitch/viewer dark band. S1.68 is also substantially taller than the established S1.2 baseline, so printability and shape fidelity remain a physical-test question.

A nearby slightly smaller-shadow alternative is **W0.200 / K0.120 / S1.67 / V72 / H0**, predicting B/A/C **105.699 / 81.569 / 129.582**, pitch **2.241735 mm**, dark band **1.773366 mm**.

The detailed result is archived in `studies/ALR_thincap_wwk_v1.0/dark_ambient_search_v1.2.md` and selected final points in `dark_ambient_selected_v1.2.csv`.

Retain the v155/v156 mapped-white visibility spacing mathematics. Do not revert the production converter to the v154 whole-profile law solely to recover the historical 102.3 prediction.

## v1.158 implementation checkpoint

`3dprint_black_mirror_wave_grid_v1.158.py` is the corrected thin-cap implementation. It requires v1.157 and v1.156 beside it, plus canonical `3dprintv1.179.py` selected with `--source`.

The reduced cap is represented in projector blocker geometry, cap draw extrusion, support top Z, executable support-segment/dry-tail Z, travel height, colour-change tower schedule, rear marking, output naming and audit metadata. The cap base/XY registration is unchanged, so the lower W tiers retain the established v1.156 geometry.

The v1.158 regression test specifically rejects the v1.157 failure mode where the cap marker/descent is thin but executable extrusion remains at the old full-height Z.

## Completed optical comparisons

Study: `ALR_shadow_comparison_v1.1`.
- Twelve recovered candidate configurations were compared under both spacing rules.
- Reconstructed local ray-tracing comparison, not full curved-road lattice/G-code.
- Historical v154 KWK / 0.20 / S1.2 / profile V70 remains the historical reference only.

Study: `ALR_material_comparison_v1.2`.
- Material-aware PETG/PLA estimates introduced diffuse plus angle-dependent surface reflection.
- PETG remains the working material. Physical H40 and the model indicate useful directional/specular return is important.

Study: `ALR_compact_kkwwk_v1.0`.
- 3-3-3-2-1 compact pedestal showed lower wide 5-4 K skirt is not required for KKWWK brightness.
- Five-tier silhouette still creates the dominant viewer-shadow penalty.

Study: `ALR_thincap_wwk_v1.0`.
- Keeps two W tiers full height while reducing only final K cap.
- K~0.10 gives a strong brightness/shadow trade versus full-height WWK.
- `brightness_contrast_trade_v1.1.md` records B~115 and A~100 trade points.
- `dark_ambient_search_v1.2.md` records the broad brightness>=105 ambient-minimization search and final directly-printable auto-spacing candidates.

## Repository workflow requested by the user

The standing completion and publication rules are in `AGENTS.md`. Always publish finished work without waiting for a separate reminder. Do not upload or commit any file over 50 MB (50,000,000 bytes per file). Check actual byte sizes first; list oversized exclusions, sizes, reason and regeneration instructions. Do not bypass through splitting, encoding, archives or Git LFS without explicit user permission.

Carry out investigation, calculations, development and testing locally. Do not use GitHub as scratch workspace.

After each finished task, commit completed scripts, inputs, output data, reports, tests and verification records. Include exact settings, reproducible commands, dependencies, assumptions, limitations and a handover. Preserve earlier checkpoints.

Whenever a script changes, increment revision and keep filenames, internal version labels, output names, audit labels and examples consistent.

Before reporting an upload as complete, verify the saved commit and repository contents. Clearly distinguish model predictions, generated-geometry audits and physical measurements.

## Starting a new conversation

Read `AGENTS.md`, this handover and relevant completed checkpoint files. Fetch actual scripts/data required for calculations; do not treat conversation summaries as substitutes for executable inputs.

Repository: `daviddootson/alr_chatgtp_files`.
Latest converter: `3dprint_black_mirror_wave_grid_v1.158.py`.
Dependencies: v1.157, v1.156 and canonical `3dprintv1.179.py`.
