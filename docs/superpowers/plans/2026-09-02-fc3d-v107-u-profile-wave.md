# FC3D v1.107 U-Profile Wave Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build v1.107 so Layer 4 is tiled by local-u wave-profile roads with converging around-arc spacing and complete-set resets.

**Architecture:** Keep v1.106 immutable as the exact predecessor and create a compact v1.107 source-transform wrapper that SHA-256-gates the predecessor, advances all revision labels to 107, and injects replacement Layer-4 geometry/emission/audit functions before invoking the transformed predecessor. Preserve existing A1 support, filler, packaging and finish machinery. Validate on GitHub Actions because the current ChatGPT `/mnt/data` mount is unreliable.

**Tech Stack:** Python 3, standard library, NumPy, Pillow, GitHub Actions, existing `3dprintv1.179.py`.

**Spec:** `docs/superpowers/specs/2026-09-02-fc3d-v107-u-profile-wave-design.md`

## Global Constraints

- Never modify or reissue v1.106; changed wrapper is v1.107.
- `+u = mirror_frame_global(...)["b_unit"]`; optical front is `-u,+Z`; hidden/return are `+u`.
- Wave peak 0.300 mm = 0.250 optical rise + 0.050 hidden rise.
- Wave extrusion F3000; E is based on intended 3D segment length.
- Logical G1 Z stays constant on Layer 4; physical profile height uses G29.1.
- New set starts at >=0.600 mm centres and as close as possible; same sample count within set; reset only after a complete cell when minimum adjacent spacing reaches ~0.400 mm; next set uses fewer roads.
- Preserve 25% valley fill and +0.795/-0.800/0.160 optical pressure mechanics.
- Human slicer preview is the final print-release gate.

---

### Task 1: RED direction/topology regression

**Files:**
- Create: `test_v107_contract.py`
- Create: `.github/workflows/v107-ci.yml`

**Interfaces:**
- Consumes predecessor `3dprint_black_mirror_wave_grid_v1.106.py`.
- Produces a test that requires v1.107 u-profile markers/functions and explicitly identifies the v1.106 full-contour topology as rejected.

- [ ] **Step 1: Write the failing test**

The test must assert that v1.106 contains the rejected `FC3D_V1106_WAVE_ARC` topology, that v1.107 exists, and that v1.107 contains `FC3D_V1107_U_PROFILE_SEG`, a local-u orientation audit, rear version 107, and no active `FC3D_V1106_WAVE_ARC` emission.

- [ ] **Step 2: Run test to verify RED**

Run in Actions: `python test_v107_contract.py`.
Expected before v1.107 exists: FAIL because `3dprint_black_mirror_wave_grid_v1.107.py` is missing.

- [ ] **Step 3: Commit RED evidence**

Commit test/workflow before production wrapper.

### Task 2: Build local-u geometry and wave-set sampler

**Files:**
- Create: `3dprint_black_mirror_wave_grid_v1.107.py`

**Interfaces:**
- Consumes v1.106 exact bytes and its `mirror_frame_global`, `integrate_b_front_global`, `_advance_b_rise_global`, `_waveset_outer_reference_curve`, clipping helpers and A1 constants.
- Produces `generate_u_profile_wave_sets(piece)` containing sets, cells, per-road 3D profiles and spacing reports.

- [ ] **Step 1: SHA-gate and version transform predecessor**

Require SHA-256 `a7e14bf818033aff390f69fd0e27368a8917a8a60dbb9c29c5d1a5c308814e80`, then advance source markers/version/default output/rear text to 107 before injection.

- [ ] **Step 2: Add fixed-fraction contour sampling**

Compute contour arclength, choose `intervals=floor(length/0.600)` with at least one interval, and sample normalized fractions `i/intervals`. This guarantees initial spacing is not tighter than 0.600 mm. Reuse the same fractions throughout a set.

- [ ] **Step 3: Build one complete u-profile road at each sampled valley point**

Use fine local integration: +u low lead; `integrate_b_front_global(...,0.250,0.05)` for exact -u rising front; +u hidden run in <=0.05-mm XY steps while h rises linearly by 0.050; +u return in <=0.05-mm XY steps while h falls to zero. Store role with every segment.

- [ ] **Step 4: Advance complete inward cells and apply set reset**

Advance the valley contour by the full local profile endpoint relation. Keep sample fractions unchanged until minimum adjacent sample spacing on the new valley contour <=0.402 mm. Finish that full cell, then recompute a lower interval count at the new contour to restore >=0.600 mm start spacing.

- [ ] **Step 5: Run geometry self-checks**

Require nonempty sets, decreasing road count at every convergence reset, peak <=0.3000001, set-start min spacing >=0.600-tolerance, and set-end spacing <=0.402 for every zero-gap reset.

### Task 3: Emit the corrected Layer-4 roads

**Files:**
- Modify through injected overrides in `3dprint_black_mirror_wave_grid_v1.107.py`.

**Interfaces:**
- Consumes `generate_u_profile_wave_sets(piece)`.
- Produces `_explicit_mirror_wave_layer_gcode` replacement with `FC3D_V1107_U_PROFILE_*` markers.

- [ ] **Step 1: Emit one pressure cycle per complete u-profile**

Travel safely, set starting G29.1, move to start, reprime +0.795, emit all profile segments at F3000, retract -0.800 before the final 0.160-mm moving dry tail, then safe travel.

- [ ] **Step 2: Carry profile height through fine G29.1 changes**

Before each fine XY extrusion segment, set G29.1 to the segment endpoint physical height while retaining constant logical G1 Z. Marker records role, start/end physical h, intended 3D length and E.

- [ ] **Step 3: Preserve all non-wave Layer-4/base mechanics**

Do not change support, 25% filler, startup, package metadata, rear text placement, arrow transform or finish-tail architecture except version labels and physical-peak accounting.

### Task 4: Direction and spacing audits

**Files:**
- Add overrides/functions in `3dprint_black_mirror_wave_grid_v1.107.py`.
- Create: `independent_v107_audit.py`.

**Interfaces:**
- Consumes generated `.gcode.3mf` plus geometric report.
- Produces fail-closed audit results for local-u direction, spacing, pressure, Z representation and package contract.

- [ ] **Step 1: Audit every emitted positive-E segment**

At the XY midpoint compute `u=b_unit` and `a=a_unit`. Require optical-front dot-u < -cos(3°), hidden/return/lead dot-u > cos(3°), expected physical-h sign, and tangential dominance absent.

- [ ] **Step 2: Audit set packing**

Require start spacing near/above 0.600, monotonic convergence within each set, complete-cell reset only, and lower road count after each convergence reset.

- [ ] **Step 3: Audit preserved release contract**

ZIP test, MD5 sidecar, four logical layers, A1 Mini/external black PETG/no AMS, startup thermal order, no tower/H2C/Vortek executable content, pressure sequence, peak/finish clearance and rear `107`/arrow-only transform.

### Task 5: GREEN dry/full generation and target comparison

**Files:**
- Update: `.github/workflows/v107-ci.yml`

**Interfaces:**
- Produces Orca and Studio v1.107 packages plus audit JSON/log artifacts.

- [ ] **Step 1: Run source regression**

`python test_v107_contract.py` must PASS.

- [ ] **Step 2: Run dry validation**

`python 3dprint_black_mirror_wave_grid_v1.107.py --source 3dprintv1.179.py --piece 1-2 --dry-validate`

- [ ] **Step 3: Generate Orca package**

`python 3dprint_black_mirror_wave_grid_v1.107.py --source 3dprintv1.179.py --piece 1-2 --slicer-target orca --output black_a_only_u_profile_wave_sets_valleyfill25_1_2_v1.107.gcode.3mf`

- [ ] **Step 4: Independently audit Orca package**

`python independent_v107_audit.py black_a_only_u_profile_wave_sets_valleyfill25_1_2_v1.107.gcode.3mf`

- [ ] **Step 5: Generate and audit Studio package**

Use the same command with `--slicer-target studio` and `_studio` output suffix; run the same independent audit.

- [ ] **Step 6: Compare executable G-code**

Normalize only the producer/header metadata expected to differ; otherwise require the executable model stream to match.

- [ ] **Step 7: Upload both packages and audit reports as Actions artifacts**

These remain candidates pending human Layer-4 slicer preview.

### Task 6: Human release gate

**Files:** none.

- [ ] **Step 1: Inspect Layer 4 in Orca/Bambu Studio**

Confirm the roads visibly run inward/outward in local-u sawtooth profiles rather than as five long constant-height arcs; confirm no missing large regions.

- [ ] **Step 2: Only then mark v1.107 print candidate**

If preview disagrees with the intended topology, reject the candidate even if all numerical audits pass.