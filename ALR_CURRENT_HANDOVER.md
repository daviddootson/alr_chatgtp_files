# ALR project: current handover

Updated: 2026-09-08. Handover revision: 1.0.

## Agreed engineering direction

Keep the v155/156 mapped-white spacing maths in the current converter. The user accepts that a corresponding version of the v154 reference made through the newer converter will have slightly different geometry and predicted optical performance.

Do not revert to the v154 whole-profile spacing law merely to recover the old 102.3 contrast-index prediction. Do not assume that the same numerical visibility percentage produces the same spacing in both versions. Use appropriately selected newer-model settings and compare physical prints with the original reference.

The study is a prediction, not measured proof of printed-screen performance. The paired test favoured the newer law in most recovered cases at unchanged percentage inputs; it does not prove that v156 is universally better after independent optimisation of both laws.

The proposed new white-only v154 variant was not evaluated. The latest decision does not require implementing that variant or repeating the extensive search.

## Completed comparison: what was actually calculated

Study: ALR shadow comparison v1.1.

Twelve recoverable historical candidate configurations were evaluated under both spacing laws, plus the physical-reference configuration, an excluded historical control under both laws, and a separately labelled reference-derived diagnostic: 28 evaluations total. This is not a recovered globally ranked top twenty.

The original scoring program was not preserved. The replacement is a local reconstructed-model comparison, not an exact rerun of that program and not full curved-road G-code/lattice regeneration. It samples nine positions of piece 1-2 and three viewer positions. Uncalibrated bead shape and material optical properties remain important limitations.

### Key saved predictions

Indices are normalised to the newly calculated v154 reference at 100. Lower ambient pickup is better. Contrast index 102.31 means approximately 2.31% improvement, not a 102.31% increase.

| Configuration | Brightness | Ambient pickup | Contrast index | Dark band, mm |
|---|---:|---:|---:|---:|
| KWK / 0.20 mm / S1.2 / v154 profile V70: reference | 100.00 | 100.00 | 100.00 | 1.153 |
| KWK / 0.205 mm / S1.2 / newer white V84 / H0 | 97.87 | 96.83 | 101.07 | 1.156 |
| KWK / 0.205 mm / S1.2 / v154 profile V84 / H0 | 82.45 | 85.50 | 96.43 | 1.462 |
| KWK / 0.205 mm / S1.2 / v154 profile V70 / H0: diagnostic | 98.04 | 95.83 | 102.31 | 1.176 |

The diagnostic changes only the reference dose from 0.20 to 0.205 mm. It is not asserted to be the exact previously unrecorded winning command. The V84 newer-model row is a recorded comparison candidate; this handover does not establish a new user-approved printer command.

At unchanged numerical percentages, substituting v154 produced ten contrast reductions, one marginal increase with brightness/dark-band penalties, and one unchanged result because the minimum-pitch floor controlled spacing.

No new printer converter, G-code, or 3MF was produced by this study. Historical cases above S1.2 were retained for comparison, not recommended under the latest recorded S1.2 physical-trial ceiling.

## Relevant existing repository sources

Repository: daviddootson/alr_chatgtp_files.

The converter source snapshot used for the study was commit 44dbcb8c71d7c5f84decc2eb733f461936a02364:

- 3dprint_black_mirror_wave_grid_v1.154.py
- 3dprint_black_mirror_wave_grid_v1.155.py
- 3dprint_black_mirror_wave_grid_v1.156.py
- 3dprintv1.179.py (canonical underlying generator)

The reconstructed analysis program is separate from these printer converters.

## Agreed working and publication workflow

Carry out development, investigation, calculations and tests locally. Do not use the GitHub repository or GitHub Actions as the live problem-solving workspace.

After completing a task, publish the finished scripts and all associated inputs, raw results, summaries, tests, verification evidence and rerun instructions to this repository. Include source versions, assumptions, limitations, checksums and an updated handover so a later conversation can continue without the previous chat workspace.

Keep historical outputs and their provenance. Clearly distinguish recovered historical numbers, new model predictions, full generated-geometry audits and physical measurements. Do not claim that a file is archived until its committed contents have been verified.

Whenever a script changes, increment its version and keep filenames, internal version labels, output names, audit labels and example commands consistent. Do not silently overwrite a historical script version. Do not publish credentials, unrelated personal information or private reasoning.

## Archive status at this checkpoint

This checkpoint commits this handover only. It does NOT establish that the complete study scripts and data have already been uploaded.

The completed delivered bundle is ALR_shadow_comparison_v1.1.zip, containing 16 files. Its SHA-256 is:

181b0515426f247e464aac030849fdb880e2f65a75c91ac9d0116eeea6a400f6

The bundle contains the analysis script, HTML/Markdown reports, README, SHA256SUMS, candidate manifest, raw and normalised results, tests and coarse/fine verification history. The ZIP integrity was checked before preparing this checkpoint.

The outstanding publication step is to commit that complete finished bundle or all its exact contents, verify the repository copy, and update this archive-status section. Do not request an unavailable original historical scorer or a nonexistent historical top-twenty download; the user authorised using the candidates recoverable from history.
