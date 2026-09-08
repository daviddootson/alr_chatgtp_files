# ALR project handover

Updated: 8 September 2026.

## Latest agreed direction

The latest printer-facing converter is `3dprint_black_mirror_wave_grid_v1.158.py`. It wraps v1.157/v1.156 and retains the adjustable `--cap-height-mm` for the final/top K tier.

v1.157 must not be used for printing thin-cap output: direct audit of a generated WWK package found that its tier-3 marker/descent moved to the intended thin-cap top Z while the executable SUPPORT_SEG and SUPPORT_DRY_TAIL Z words remained at the old full-height v1.156 top. v1.158 corrects those executable coordinates and adds a fail-closed actual-G-code tier-Z/cap-dose audit.

The user physically tested the tall S1.67 thin-cap direction and reported unacceptable print quality. Treat **S1.30 as the current upper limit for physical-height scale** unless later physical evidence supports going higher.

The current recommended scale-limited test is **WWK / W0.24 / K0.16 / S1.30 / V77 / H0**, using normal automatic v158 spacing. Fresh 1024-ray verification predicts B/A/C **106.010 / 90.408 / 117.257**, mean pitch **2.240781 mm**, mean viewer dark band **1.740621 mm**, total optical height **0.8320 mm**, W physical height **0.3120 mm each** and K-cap physical height **0.2080 mm**. These are model predictions, not physical measurements.

This scale-limited point nearly reproduces the failed S1.67 card's predicted brightness and pitch/shadow size, but not its extreme ambient rejection. The failed S1.67 comparison geometry predicted B/A/C **105.699 / 81.569 / 129.582**, pitch **2.241735 mm**, dark band **1.773366 mm**. Moving height from S-scale into material dose is therefore not optically equivalent in the current bead/profile model.

Retain the v155/v156 mapped-white visibility spacing mathematics. Do not revert the production converter to the v154 whole-profile law solely to recover the historical 102.3 prediction.

## Thin-cap optical checkpoints

Original practical candidate: **WWK / W0.22 / K0.10 / S1.2 / V50 / H0**, predicted about B/A/C **134.8 / 134.0 / 100.6**, pitch ~1.676 mm, viewer dark band ~1.216 mm.

Contrast-oriented points from `brightness_contrast_trade_v1.1.md`:

- **~115 brightness trade:** W0.24 / K0.165 / S1.2 / V75 / H0 with +0.050 mm local pitch: B/A/C **114.816 / 103.428 / 111.011**, pitch **2.178650 mm**, dark band **1.651705 mm**.
- **Ambient-matched:** W0.24 / K0.213 / S1.2 / V80 / H0 automatic spacing: B/A/C **111.120 / 100.009 / 111.111**, pitch **2.313729 mm**, dark band **1.771262 mm**.
- Nearby lower-shadow ambient-matched: W0.24 / K0.205 / V75 / +0.025 mm local pitch: B/A/C **110.520 / 99.908 / 110.621**, pitch **2.254842 mm**, dark band **1.728373 mm**.

Darkest-ambient search `dark_ambient_search_v1.2.md` minimized ambient subject to brightness >=105 and found a tall-model optimum around W0.20 / K0.115 / S1.68 / V75 with B/A/C **105.455 / 81.088 / 130.049**. This direction is now physically disfavoured because the S1.67 print-quality test failed.

Scale-limited follow-up `scale_limited_search_v1.3.md` constrained S<=1.30 and shifted height into material dose. The darkest verified S<=1.30 point at B>=105 was W0.2355 / K0.195 / S1.30 / V77, B/A/C **105.038 / 90.114 / 116.561**, pitch **2.318747 mm**, dark band **1.806869 mm**. It is not preferred over the cleaner W0.24/K0.16/S1.30/V77 test because its ambient improvement is only ~0.29 index points while brightness margin and shadow are worse.

## v1.158 implementation checkpoint

`3dprint_black_mirror_wave_grid_v1.158.py` is the corrected thin-cap implementation. It requires v1.157 and v1.156 beside it, plus canonical `3dprintv1.179.py` selected with `--source`.

The reduced cap is represented in projector blocker geometry, cap draw extrusion, support top Z, executable support-segment/dry-tail Z, travel height, colour-change tower schedule, rear marking, output naming and audit metadata. The cap base/XY registration is unchanged, so the lower W tiers retain the established v1.156 geometry.

The v1.158 regression test specifically rejects the v1.157 failure mode where the cap marker/descent is thin but executable extrusion remains at the old full-height Z.

## Completed optical comparisons

- `ALR_shadow_comparison_v1.1`: reconstructed v154/v156 spacing comparison; historical v154 KWK / 0.20 / S1.2 / profile V70 remains historical reference only.
- `ALR_material_comparison_v1.2`: material-aware PETG/PLA estimates; PETG remains the working material; physical H40 and the model indicate directional/specular return is important.
- `ALR_compact_kkwwk_v1.0`: 3-3-3-2-1 pedestal showed the wide lower K skirt is not required for KKWWK brightness, but five-tier height still dominates viewer-shadow penalty.
- `ALR_thincap_wwk_v1.0`: thin top-K cap retains two full W tiers while reducing cap height; subsequent trade studies are archived in the same study directory.

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
