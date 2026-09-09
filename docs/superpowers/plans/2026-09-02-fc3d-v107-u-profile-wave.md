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
- Wave extrusion F3000; E is based on true 3D segment length.
- **Wave height is emitted as real coordinated G1 X/Y/Z motion.** Do not staircase the wave with G29.1. Existing G29.1 support-fill compensation remains unchanged.
- Orca is the authoritative preview path for this experiment because it previews the moving-Z wave correctly without confusing the layer structure.
- Moving Z during the wave is physically accepted by the printer and is required for the optical profile.
- New set starts at >=0.600 mm centres and as close as possible; same sample count within a set; reset only after a complete cell when minimum adjacent spacing reaches ~0.400 mm; next set uses fewer roads.
- Preserve 25% valley fill and +0.795/-0.800/0.160 optical pressure mechanics.
- Human Orca slicer preview is the final print-release gate.

---

### Task 1: RED direction/topology regression

**Files:**
- Create: `test_v107_contract.py`
- Create: `.github/workflows/v107-ci.yml`

- [x] **Step 1: Write the failing test**
- [x] **Step 2: Run test to verify RED** — failed specifically because v1.107 was absent after first verifying exact v1.106 SHA-256.
- [x] **Step 3: Commit RED evidence before production code**

### Task 2: Build local-u geometry and wave-set sampler

**Files:**
- Create: `3dprint_black_mirror_wave_grid_v1.107.py`

- [ ] **Step 1: SHA-gate and version-transform predecessor**

Require SHA-256 `a7e14bf818033aff390f69fd0e27368a8917a8a60dbb9c29c5d1a5c308814e80`, then advance source markers/version/default output/rear text to 107 before runtime execution.

- [ ] **Step 2: Sample each transverse contour with a fixed road count per set**

Choose the integer sample count that puts the new set as close as possible to 0.600-mm centres without making it tighter than 0.600 mm. Reuse those normalized transverse positions throughout that set.

- [ ] **Step 3: Build one complete local-u profile per transverse sample**

Each road is: +u valley lead; exact local `-u,+Z` optical climb to +0.250; `+u,+Z` shallow hidden section to +0.300; `+u,-Z` return to valley. Geometry may be locally subdivided to follow the varying true u field, but the emitted motion is genuine XYZ, not height-offset stair stepping.

- [ ] **Step 4: Advance inward and reset only at complete-set boundaries**

Keep road count fixed while inward convergence reduces adjacent spacing from about 0.600 toward 0.400 mm. Finish the complete inward cell where zero nominal gap is reached; then begin the next set with fewer roads so its outer/start spacing returns to about 0.600 mm. Never delete a road partway around an arc.

- [ ] **Step 5: Geometry self-checks**

Require non-empty geometry, peak <=0.3000001, correct u signs, start spacing >=0.600-tolerance, convergence toward 0.400, and decreasing road count at convergence resets.

### Task 3: Emit corrected wave roads

- [ ] **Step 1: One pressure cycle per complete u-profile**

Travel to road start, +0.795 reprime, emit profile at F3000, -0.800 retract before final 0.160-mm moving dry tail, then safe travel.

- [ ] **Step 2: Direct XYZ wave motion**

Every positive-E wave segment carries X/Y/Z. Optical front: `-u,+Z`; hidden top: `+u,+Z`; return: `+u,-Z`; lead: `+u` at valley Z. Extrusion uses sqrt(dx^2+dy^2+dz^2).

- [ ] **Step 3: Preserve non-wave mechanics**

Do not change base/support, 25% filler, startup, package metadata, rear text placement, arrow-only flip or finish-tail architecture except revision labels and true peak accounting.

### Task 4: Direction, direct-Z and spacing audits

**Files:**
- Create: `independent_v107_audit.py`

- [ ] **Step 1: Audit actual emitted positive-E segments against local u/a**

At each segment midpoint require optical-front dot-u negative and near -1; lead/hidden/return dot-u positive and near +1; tangential dominance must fail.

- [ ] **Step 2: Audit direct moving Z**

Require positive-E wave moves to carry direct Z changes with the expected sign. Fail if the wave is synthesized through G29.1 height fragments.

- [ ] **Step 3: Audit wave-set packing**

Require ~0.600-mm start centres, inward convergence, zero-gap threshold around 0.400 mm, complete-set reset only, and fewer roads after reset.

- [ ] **Step 4: Preserve package/release audits**

ZIP/MD5, A1 Mini black Generic PETG external spool/no AMS, startup thermal order, no tower/H2C/Vortek executable remnants, pressure sequence, true peak/finish clearance, rear `107` and arrow-only transform.

### Task 5: GREEN dry/full Orca generation

- [ ] `python test_v107_contract.py`
- [ ] `python 3dprint_black_mirror_wave_grid_v1.107.py --source 3dprintv1.179.py --piece 1-2 --dry-validate`
- [ ] `python 3dprint_black_mirror_wave_grid_v1.107.py --source 3dprintv1.179.py --piece 1-2 --slicer-target orca --output black_a_only_u_profile_wave_sets_valleyfill25_1_2_v1.107.gcode.3mf`
- [ ] `python independent_v107_audit.py black_a_only_u_profile_wave_sets_valleyfill25_1_2_v1.107.gcode.3mf`
- [ ] Upload candidate package and audit reports as Actions artifacts.

Studio compatibility may be checked afterward, but it must not constrain the geometry back to constant-Z. Orca is the authoritative preview route for v1.107.

### Task 6: Human release gate

- [ ] Inspect Layer 4 in Orca and confirm the actual roads visibly run inward/outward as local-u sawtooth profiles rather than as a handful of constant-height arcs.
- [ ] Only after that preview agrees with the intended topology may v1.107 be considered a print candidate.