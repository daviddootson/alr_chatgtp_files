# FC3D / ALR repository instructions

Repository: `daviddootson/alr_chatgtp_files`.
Standing user rules refined on 9 September 2026.

Read this file and `ALR_PROJECT_HANDOVER.md` when continuing this project.

## Development workflow

Carry out investigation, calculations, development, ray tracing, generated-file checks and debugging locally. Do not use GitHub or GitHub Actions as the live problem-solving, dependency-recovery or scratch workspace.

Only update GitHub after a task or script revision is finished.

## What to publish

Keep GitHub fast and lightweight. The priority is:

- finished converter / supporting scripts;
- concise revision or study notes explaining what changed and why;
- a small, useful regression-test set;
- genuinely reusable helper scripts, workflows or configuration;
- concise handover updates needed to continue the project.

Do **not** routinely commit generated G-code or 3MF files, ray-trace dumps, temporary CSVs, encoded transport payloads, dependency-recovery bundles, replay outputs, caches or one-off debugging material. Generated printer files are disposable validation artifacts unless the user explicitly asks to preserve one.

Do not duplicate unchanged dependencies merely for a checkpoint. If a canonical dependency such as `3dprintv1.179.py` is unchanged, record its version/checksum where useful and reuse the known local copy rather than repeatedly reconstructing or re-reading it.

## Testing strategy

Testing must remain robust but proportionate to the change. Prefer coverage of distinct failure modes over large numbers of near-duplicate tests.

Typical strategy:

- focused unit/regression tests for changed behaviour;
- one principal end-to-end case using the current physically important settings;
- a few additional cases only when they exercise genuinely different code paths;
- direct generated-G-code/package audit of mechanics actually affected by the revision;
- one deliberate failure case for important fail-closed checks.

Scale testing upward for genuinely architectural/high-risk changes, but stop once the evidence is strong enough. Do not multiply tests merely to increase the count.

## Mandatory 50 MB per-file limit

Do not upload or commit any file larger than 50 MB. Use a conservative limit of 50,000,000 bytes per file.

Do not bypass this rule by splitting or encoding an oversized file, hiding it inside an archive, or using Git LFS unless the user explicitly authorises an exception. Do not rewrite history merely to apply this rule retroactively.

## Integrity and versioning

Review the publication set before uploading. Never publish credentials, unrelated personal information, private reasoning, temporary caches or unrelated workspace files.

Whenever a script changes, increment its version and keep filenames, internal version labels, output names, audit labels and example commands consistent. Preserve earlier checkpoints and their provenance.

Verify the saved GitHub commit and important file contents after publishing. Only then report the checkpoint as uploaded.

Keep historical values, model predictions, generated-geometry audits and physical measurements clearly distinguished.
