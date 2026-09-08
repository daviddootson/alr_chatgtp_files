# ALR project handover

Updated: 8 September 2026.

## Latest agreed direction

Retain the v155/v156 mapped-white visibility spacing mathematics in the latest converter. The user accepts that a card based on earlier v154 settings will have somewhat different spacing and predicted optical performance when produced through the latest converter. Do not revert the production converter to v154 mathematics solely to recover a small model-predicted contrast difference.

The optical scores discussed so far are predictions, not calibrated measurements of the printed screen. The comparison favoured the newer rule for most of the recovered candidates at unchanged numerical settings; it did not establish that one rule is universally superior after separate optimisation.

## Completed comparison available from the originating conversation

Study: `ALR_shadow_comparison_v1.1`.

- Twelve recovered candidate configurations were compared under both spacing rules, with additional explicitly labelled controls and a reference-derived diagnostic.
- The study is a reconstructed local ray-tracing comparison, not a complete regeneration of the curved-road lattice or G-code.
- The original v154 KWK / 0.20 mm dose / S1.2 / profile V70 card remains the historical reference.
- The v154-derived white-only variant proposed earlier has not been tested in this study.
- No printer converter or printer output was modified by this study.

The delivered ZIP is `ALR_shadow_comparison_v1.1.zip` (126687 bytes; SHA-256 `181b0515426f247e464aac030849fdb880e2f65a75c91ac9d0116eeea6a400f6`). It contains the study script, tests, recovered candidate inputs, results, reports, verification history and checksums.

Archive status at this handover commit: the ZIP has been verified as readable in the current conversation workspace. This commit saves the handover only; it does NOT claim that the study scripts or results have already been uploaded to this repository. That archive upload remains outstanding.

## Repository workflow requested by the user

The standing completion and publication rules are in `AGENTS.md`. Always publish finished work without waiting for a separate reminder. Do not upload or commit any file over 50 MB (50,000,000 bytes per file). Check actual file sizes first; list oversized exclusions, their sizes and regeneration instructions in the checkpoint manifest or handover. Do not bypass this limit through splitting, encoding, archives or Git LFS without explicit user permission.

Carry out investigation, calculations, development and testing in the local working environment. Do not use GitHub as the scratch workspace while solving a problem.

After a piece of work is finished, commit its completed scripts, inputs, output data, reports, tests and verification records to this repository. Include the exact settings, reproducible run commands, dependencies and a handover explaining the conclusions, limitations, current decision and remaining work. Preserve earlier checkpoints rather than overwriting their meaning.

Increment script revisions whenever their code is changed. Keep filenames, internal version labels, output names and example commands consistent with the revision.

Before reporting an upload as complete, verify the saved commit and repository contents. State explicitly when only a handover or partial archive has been uploaded. Do not equate repository search results with files present in a local calculation workspace.

## Starting a new conversation

Read `AGENTS.md`, this handover and the relevant completed checkpoint files before continuing the work. Fetch the actual scripts and data required for any calculation. Treat old conversation summaries as context, not substitutes for executable inputs or verified numerical results.

The user's established repository for this project is `daviddootson/alr_chatgtp_files`. The latest converter named in this decision is `3dprint_black_mirror_wave_grid_v1.156.py`, with canonical emitter `3dprintv1.179.py`.
