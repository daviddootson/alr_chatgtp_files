# ALR project handover

Updated: 8 September 2026.

## Latest agreed direction

The latest printer-facing converter is `3dprint_black_mirror_wave_grid_v1.157.py`. It is a bounded compatibility wrapper around v1.156 and adds an adjustable `--cap-height-mm` for the final/top K tier only. v1.156 remains unchanged and is required beside v1.157.

The first intended physical thin-cap test is **WWK / W dose 0.22 mm / K cap dose 0.10 mm / S1.2 / V50 / H0**, using the normal v1.156 mapped-white spacing logic with the reduced K blocker height. The two W tiers keep their v1.156 geometry and material dose; only the final K tier becomes shallower.

Exact command:

```cmd
py 3dprint_black_mirror_wave_grid_v1.157.py --source 3dprintv1.179.py --piece 1-2 --layer-map wwk --layer-height-mm 0.22 --cap-height-mm 0.10 --physical-height-scale 1.2 --visibility-percent 50 --horizontal-percent 0 --slicer-target orca
```

For those settings, the intended physical tier heights are W=0.264 mm, W=0.264 mm, K=0.120 mm. The local optical study predicted about 1.676 mm pitch, ~1.216 mm viewer dark band, ~134.8 brightness index and ~100.6 contrast index against the current PETG KWK/v156 baseline. These are model predictions, not physical measurements.

Retain the v155/v156 mapped-white visibility spacing mathematics. Do not revert the production converter to the v154 whole-profile law solely to recover the historical 102.3 prediction.

## v1.157 implementation checkpoint

`3dprint_black_mirror_wave_grid_v1.157.py` adds `--cap-height-mm` as material-dose height for the final/top K tier. If omitted, cap height defaults to `--layer-height-mm`, preserving v1.156 optical geometry/dose while emitting a v1.157-labelled package. An explicit cap is rejected unless the layer map ends in K.

The reduced cap is represented in projector blocker geometry, cap draw extrusion, support top Z, travel height, colour-change tower schedule, rear marking, output naming and audit metadata. The cap base/XY registration is unchanged, so the lower W tiers remain exactly on the established v1.156 geometry.

Local verification before publication: 8 pytest checks passed and Python compilation passed. The committed converter was fetched back and its Git blob SHA matched the locally verified canonical copy. Canonical converter SHA-256: `22e1b5d54b8c3dc6dd53ce8ceba0e628b3a835deda2ea263f6f0cd382218be7c`.

The implementation source, tests and checkpoint note have been published to the repository. Full generated G-code/3MF integration still requires running the converter with the local v1.156 and canonical `3dprintv1.179.py`; no print result has yet been measured for v1.157.

## Completed optical comparisons

Study: `ALR_shadow_comparison_v1.1`.

- Twelve recovered candidate configurations were compared under both spacing rules, with additional explicitly labelled controls and a reference-derived diagnostic.
- The study is a reconstructed local ray-tracing comparison, not a complete regeneration of the curved-road lattice or G-code.
- The original v154 KWK / 0.20 mm dose / S1.2 / profile V70 card remains the historical reference.
- The v154-derived white-only variant was not adopted.

Study: `ALR_material_comparison_v1.2`.

- Material-aware PETG/PLA estimates introduced diffuse plus angle-dependent surface reflection for white and black.
- PETG remained the working material choice. Physical H40 results and the model both indicate that useful directional/specular return is an important brightness component.

Study: `ALR_compact_kkwwk_v1.0`.

- A 3-3-3-2-1 compact pedestal proved that the lower wide 5-4 K skirt is not required for KKWWK brightness and that compact KKWWK can approach WWK physical pitch.
- The five-tier silhouette still creates a larger viewer dark band, so height rather than base width becomes the dominant limitation.

Study: `ALR_thincap_wwk_v1.0`.

- Thin-cap WWK keeps the two useful W tiers at full height while reducing only the final K cap.
- Around K=0.10 mm the model showed a strong trade: much tighter spacing/smaller viewer shadow than full-height WWK while retaining high brightness.
- W0.22/K0.10/V50 was selected as the first practical print candidate.

## Repository workflow requested by the user

The standing completion and publication rules are in `AGENTS.md`. Always publish finished work without waiting for a separate reminder. Do not upload or commit any file over 50 MB (50,000,000 bytes per file). Check actual file sizes first; list oversized exclusions, their sizes and regeneration instructions in the checkpoint manifest or handover. Do not bypass this limit through splitting, encoding, archives or Git LFS without explicit user permission.

Carry out investigation, calculations, development and testing in the local working environment. Do not use GitHub as the scratch workspace while solving a problem.

After a piece of work is finished, commit its completed scripts, inputs, output data, reports, tests and verification records to this repository. Include the exact settings, reproducible run commands, dependencies and a handover explaining the conclusions, limitations, current decision and remaining work. Preserve earlier checkpoints rather than overwriting their meaning.

Whenever a script changes, increment its version and keep filenames, internal version labels, output names, audit labels and example commands consistent with the revision.

Before reporting an upload as complete, verify the saved commit and repository contents. State explicitly when only a handover or partial archive has been uploaded. Do not equate repository search results with files present in a local calculation workspace.

## Starting a new conversation

Read `AGENTS.md`, this handover and the relevant completed checkpoint files before continuing the work. Fetch the actual scripts and data required for any calculation. Treat old conversation summaries as context, not substitutes for executable inputs or verified numerical results.

Repository: `daviddootson/alr_chatgtp_files`.
Latest converter: `3dprint_black_mirror_wave_grid_v1.157.py`.
Dependencies: `3dprint_black_mirror_wave_grid_v1.156.py` and canonical `3dprintv1.179.py`.
