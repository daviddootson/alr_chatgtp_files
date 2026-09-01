#!/usr/bin/env python3
"""
FC3D ALR A-only six-pack A1 Mini successor wrapper, revision v1.98.

This file deliberately leaves the known v1.91 geometry source untouched. At runtime it
loads that fixed base wrapper from the same directory, performs a
fail-closed source upgrade in memory, regression-tests the tower-removal change,
then executes the upgraded wrapper with the original command line.

Why this form exists
--------------------
The fixed base source is the large established geometry wrapper. The v1.98 change
retains the proven v1.97 A1 executable path and replaces the metadata/config shell
with the known-working Orca 2.5.0 A1 Mini single-PETG reference contract:
  * preserve single-material tower removal for all known v1.179 tower ownership forms;
  * normalize project/G-code metadata from the known-working Orca A1 Mini cube;
  * map one PETG Black filament to the external-spool/no-AMS A1 contract;
  * add OrcaSlicer package metadata using Orca's own native 3MF convention;
  * replace stale H2C/AMS config arrays rather than patching warning strings piecemeal;
  * make the later A1 Mini converter audit-only for tower content;
  * replace the compact A1 Mini startup with A1-native ordering:
      warm/home -> physical brush wipe -> 140 C ABL -> 255 C -> conditioning;
  * leave the nozzle retracted by 0.400 mm before the canonical model;
  * strengthen package, temperature, pressure-state and H2C-leak audits;
  * advance every wrapper/version/rear-texture marker to revision 97.

The optical geometry and per-arc pressure constants are not rewritten.
"""

from __future__ import annotations

import ast
import hashlib
import os
import re
import sys
import tempfile
import types
import zipfile
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

SCRIPT_VERSION = "3dprint_black_mirror_wave_grid_v1.98"
REVISION = 98
BASE_REVISION = 91
BASE_SCRIPT_VERSION = "3dprint_black_mirror_wave_grid_v1.91"
EXPECTED_EMITTER = "3dprintv1.179"

START_MARKER = "; WIPE_TOWER_START DIRECT_SOLID_V4"
END_MARKER = "; WIPE_TOWER_END DIRECT_SOLID_V4"


NEW_REPLACE_CONFIG_COMMENT = 'def _replace_config_comment(gcode: str, key: str, value: str) -> str:\n    pat = re.compile(rf"^; {re.escape(key)} = .*?$", re.M)\n    replacement = f"; {key} = {value}"\n    if pat.search(gcode):\n        # Callable replacement is deliberate: re.sub replacement strings parse\n        # backslash escapes, which would turn literal \\\\n config separators into\n        # physical newlines and leak startup markers into the header namespace.\n        return pat.sub(lambda _m: replacement, gcode, count=1)\n    end = gcode.find("; CONFIG_BLOCK_END")\n    if end < 0:\n        raise RuntimeError("V1.98 A1 MINI: CONFIG_BLOCK_END missing")\n    return gcode[:end] + replacement + "\\n" + gcode[end:]'


NEW_TOWER_POLICY = 'def apply_dynamic_tower_policy(output: Path) -> dict:\n    """Remove every known v1.179 tower operation for this one-material A1 job.\n\n    v1.179 has more than one tower representation.  In addition to the usual\n    ``WIPE_TOWER_START/END DIRECT_SOLID_V4`` block, same-layer scheduler work can\n    emit ``DIRECT_SOLID_V156_SECONDARY`` blocks and an undelimited primary\n    structural fill beginning at ``FC3D_TOWER_PRIMARY_STRUCTURAL_FILL`` and\n    ending only when ``FC3D_TOWER_LAYER_COMPLETE_V129`` is emitted.\n\n    Never scrub an in-owner ``FC3D_TOWER_SLOT`` marker by itself: it can own real\n    extrusion. Remove all four v1.179 ownership forms first. Only after those\n    owners are gone may an exact standalone slot-comment line be scrubbed without\n    consuming neighbouring motion; then fail closed if any tower marker survives.  After deleting a tower, neutralise only the stale XY\n    seed on the first canonical checked hop by converting that XYZ hop to Z-only.\n    """\n    output = Path(output)\n    gcode_name = "Metadata/plate_1.gcode"\n    with zipfile.ZipFile(output, "r") as z:\n        if gcode_name not in z.namelist():\n            raise RuntimeError(f"DYNAMIC TOWER POLICY: generated package lacks {gcode_name}")\n        gcode = z.read(gcode_name).decode("utf-8", errors="replace")\n\n    m_active = re.search(\n        r";\\s*FC3D_V169_JOB_ACTIVE_MATERIALS\\s+([A-Z]+(?:[ \\t,]+[A-Z]+)*)",\n        gcode,\n    )\n    if not m_active:\n        raise RuntimeError("DYNAMIC TOWER POLICY: active-material marker not found")\n    active_materials = [\n        x for x in re.split(r"[ \\t,]+", m_active.group(1).strip())\n        if x and x.lower() != "none"\n    ]\n    if not active_materials:\n        raise RuntimeError("DYNAMIC TOWER POLICY: parsed zero active materials")\n\n    lines = gcode.splitlines()\n    tower_start_re = re.compile(\n        r"^;\\s*WIPE_TOWER_START\\s+(DIRECT_SOLID_[A-Za-z0-9_]+)(?:\\s|$)"\n    )\n    tower_end_re = re.compile(\n        r"^;\\s*WIPE_TOWER_END\\s+(DIRECT_SOLID_[A-Za-z0-9_]+)(?:\\s|$)"\n    )\n    post_start = "; WIPE_START FC3D_PPSPV47_POST_TOWER_SAFE_LIFTED"\n    post_end = "; WIPE_END FC3D_PPSPV47_POST_TOWER_SAFE_LIFTED"\n    exit_safe = "; FC3D_PPSPV47_TOWER_EXIT_ALREADY_LIFTED_NEXT_TRAVEL_SAFE"\n    scheduler_primary = "; FC3D_TOWER_PRIMARY_STRUCTURAL_FILL"\n    scheduler_complete = "; FC3D_TOWER_LAYER_COMPLETE_V129"\n    hop_marker = "FC3D_PPSPV62_STUDIO_SAFE_VERTICAL_CHECKED_HOP"\n    model_end = "; V4_MODEL_END"\n\n    # Validate every explicit tower delimiter before changing anything.  The ID\n    # must match, not merely the number of starts and ends.\n    open_tower_id = None\n    starts_before = 0\n    ends_before = 0\n    tower_id_counts = {}\n    for line_no, line in enumerate(lines, start=1):\n        s = line.strip()\n        ms = tower_start_re.match(s)\n        me = tower_end_re.match(s)\n        if ms:\n            if open_tower_id is not None:\n                raise RuntimeError(\n                    f"DYNAMIC TOWER POLICY: nested tower START at line {line_no}: "\n                    f"open={open_tower_id} new={ms.group(1)}"\n                )\n            open_tower_id = ms.group(1)\n            starts_before += 1\n            tower_id_counts[open_tower_id] = tower_id_counts.get(open_tower_id, 0) + 1\n            continue\n        if me:\n            ends_before += 1\n            if open_tower_id is None:\n                raise RuntimeError(\n                    f"DYNAMIC TOWER POLICY: tower END without START at line {line_no}: {me.group(1)}"\n                )\n            if me.group(1) != open_tower_id:\n                raise RuntimeError(\n                    f"DYNAMIC TOWER POLICY: mismatched tower END at line {line_no}: "\n                    f"open={open_tower_id} end={me.group(1)}"\n                )\n            open_tower_id = None\n    if open_tower_id is not None:\n        raise RuntimeError(\n            f"DYNAMIC TOWER POLICY: unterminated tower block before patch: {open_tower_id}"\n        )\n    if starts_before != ends_before:\n        raise RuntimeError(\n            "DYNAMIC TOWER POLICY: mismatched tower delimiter counts before patch: "\n            f"{starts_before} START / {ends_before} END"\n        )\n\n    post_starts_before = sum(1 for line in lines if line.strip().startswith(post_start))\n    post_ends_before = sum(1 for line in lines if line.strip().startswith(post_end))\n    if post_starts_before != post_ends_before:\n        raise RuntimeError(\n            "DYNAMIC TOWER POLICY: mismatched optional post-tower wipe delimiters before patch: "\n            f"{post_starts_before} START / {post_ends_before} END"\n        )\n\n    if len(active_materials) >= 2:\n        return {\n            "policy": "multi_material_tower_unchanged",\n            "active_materials": active_materials,\n            "active_material_count": len(active_materials),\n            "tower_removed": False,\n            "original_tower_blocks": starts_before,\n            "original_tower_block_ids": dict(sorted(tower_id_counts.items())),\n            "original_post_tower_wipes": post_starts_before,\n            "removed_tower_blocks": 0,\n            "removed_scheduler_primary_fill_groups": 0,\n            "removed_scheduler_primary_fill_markers": 0,\n            "removed_scheduler_completion_markers": 0,\n            "removed_post_tower_wipes": 0,\n            "sanitized_tower_exit_hops": 0,\n            "tower_exits_without_following_hop": 0,\n            "removed_tower_lines": 0,\n        }\n\n    out = []\n    in_tower_id = None\n    in_post = False\n    in_scheduler_completion = False\n    pending_exit = False\n    need_hop_motion = False\n    removed_blocks = 0\n    removed_post = 0\n    removed_lines = 0\n    removed_scheduler_groups = 0\n    removed_scheduler_primary_markers = 0\n    removed_scheduler_completion_markers = 0\n    sanitized_hops = 0\n    exits_without_hop = 0\n\n    motion_re = re.compile(r"^\\s*G[01]\\b", re.I)\n    x_re = re.compile(r"\\bX[-+]?\\d")\n    y_re = re.compile(r"\\bY[-+]?\\d")\n    z_value_re = re.compile(r"\\bZ([-+]?(?:\\d+(?:\\.\\d+)?|\\.\\d+)(?:[eE][-+]?\\d+)?)")\n    f_value_re = re.compile(r"\\bF([-+]?(?:\\d+(?:\\.\\d+)?|\\.\\d+)(?:[eE][-+]?\\d+)?)")\n\n    for line_no, line in enumerate(lines, start=1):\n        s = line.strip()\n        ms = tower_start_re.match(s)\n        me = tower_end_re.match(s)\n\n        # Scheduler completion primary fills are not explicitly delimited by\n        # WIPE_TOWER markers.  Once the first primary-fill marker appears, the\n        # remainder of complete_same_layer_scheduler_tower() belongs to tower\n        # completion until its authoritative LAYER_COMPLETE marker.\n        if in_scheduler_completion:\n            removed_lines += 1\n            if s.startswith(scheduler_primary):\n                removed_scheduler_primary_markers += 1\n            if ms:\n                removed_blocks += 1\n            if s.startswith(scheduler_complete):\n                removed_scheduler_completion_markers += 1\n                in_scheduler_completion = False\n                pending_exit = True\n                continue\n            if (\n                s.startswith("; CHANGE_LAYER")\n                or s.startswith("; FEATURE:")\n                or s.startswith(model_end)\n            ):\n                raise RuntimeError(\n                    "DYNAMIC TOWER POLICY: scheduler primary fill reached model/layer boundary "\n                    f"without {scheduler_complete!r}; line {line_no}: {line!r}"\n                )\n            continue\n\n        if in_tower_id is not None:\n            removed_lines += 1\n            if ms:\n                raise RuntimeError(f"DYNAMIC TOWER POLICY: nested tower START at line {line_no}")\n            if me:\n                if me.group(1) != in_tower_id:\n                    raise RuntimeError(\n                        f"DYNAMIC TOWER POLICY: mismatched tower END at line {line_no}: "\n                        f"open={in_tower_id} end={me.group(1)}"\n                    )\n                in_tower_id = None\n                pending_exit = True\n            continue\n\n        if in_post:\n            removed_lines += 1\n            if s.startswith(post_start):\n                raise RuntimeError(f"DYNAMIC TOWER POLICY: nested post-tower WIPE_START at line {line_no}")\n            if s.startswith(post_end):\n                in_post = False\n            continue\n\n        # Generic ownership for every explicitly delimited DIRECT_SOLID tower\n        # family (V4, V4_FILLER, V156_SECONDARY, and future named variants).\n        if ms:\n            in_tower_id = ms.group(1)\n            removed_blocks += 1\n            removed_lines += 1\n            continue\n        if me:\n            raise RuntimeError(f"DYNAMIC TOWER POLICY: tower END without START at line {line_no}")\n\n        # Undelimited scheduler primary completion.  Do not scrub its slot line\n        # alone: the following G-code is real tower extrusion and is removed as\n        # one owned completion group through FC3D_TOWER_LAYER_COMPLETE_V129.\n        if s.startswith(scheduler_primary):\n            in_scheduler_completion = True\n            removed_scheduler_groups += 1\n            removed_scheduler_primary_markers += 1\n            removed_lines += 1\n            continue\n\n        # If all primary slots were already used, scheduler completion may consist\n        # only of delimited secondary blocks followed by this marker.  Remove the\n        # marker, but open no new exit episode unless tower geometry was removed.\n        if s.startswith(scheduler_complete):\n            removed_scheduler_completion_markers += 1\n            removed_lines += 1\n            continue\n\n        # POST_TOWER_SAFE_LIFTED is optional: only a tool-change exit emits it.\n        if s.startswith(post_start):\n            if not pending_exit:\n                raise RuntimeError(\n                    f"DYNAMIC TOWER POLICY: orphan post-tower WIPE_START at line {line_no}"\n                )\n            in_post = True\n            removed_post += 1\n            removed_lines += 1\n            continue\n        if s.startswith(post_end):\n            raise RuntimeError(f"DYNAMIC TOWER POLICY: post-tower WIPE_END without START at line {line_no}")\n\n        # This marker describes the deleted tool-change post-wipe state.\n        if pending_exit and s.startswith(exit_safe):\n            removed_lines += 1\n            continue\n\n        # The first canonical checked hop after a deleted tower owns the stale\n        # tower XY seed.  Keep its marker and rewrite exactly its first XYZ move.\n        if pending_exit and hop_marker in s:\n            pending_exit = False\n            need_hop_motion = True\n            out.append(line)\n            continue\n\n        if need_hop_motion and motion_re.match(s) and (\n            x_re.search(s) or y_re.search(s) or z_value_re.search(s)\n        ):\n            mz = z_value_re.search(s)\n            if mz is None or not (x_re.search(s) or y_re.search(s)):\n                raise RuntimeError(\n                    "DYNAMIC TOWER POLICY: expected first checked-hop motion to carry stale XY and Z; "\n                    f"line {line_no}: {line!r}"\n                )\n            mf = f_value_re.search(s)\n            feed = f" F{mf.group(1)}" if mf else ""\n            out.append(\n                f"G1 Z{mz.group(1)}{feed} ; FC3D_V198_TOWER_EXIT_HOP_SANITIZED_Z_ONLY"\n            )\n            sanitized_hops += 1\n            need_hop_motion = False\n            continue\n\n        # Feed-only/E-only commands and Z-only lifts are safe after tower deletion.\n        # A move carrying X or Y before the checked-hop marker is not safe because\n        # the generated planner may still be using the now-deleted tower XY state.\n        if pending_exit and motion_re.match(s) and (x_re.search(s) or y_re.search(s)):\n            raise RuntimeError(\n                "DYNAMIC TOWER POLICY: XY motion after removed tower before checked-hop marker; "\n                f"line {line_no}: {line!r}"\n            )\n\n        if pending_exit and s.startswith(model_end):\n            exits_without_hop += 1\n            pending_exit = False\n\n        out.append(line)\n\n    if in_tower_id is not None:\n        raise RuntimeError(f"DYNAMIC TOWER POLICY: unterminated tower block at EOF: {in_tower_id}")\n    if in_scheduler_completion:\n        raise RuntimeError(\n            "DYNAMIC TOWER POLICY: unterminated scheduler primary-fill completion at EOF"\n        )\n    if in_post:\n        raise RuntimeError("DYNAMIC TOWER POLICY: unterminated optional post-tower wipe at EOF")\n    if need_hop_motion:\n        raise RuntimeError("DYNAMIC TOWER POLICY: checked-hop marker had no following motion before EOF")\n    if pending_exit:\n        raise RuntimeError("DYNAMIC TOWER POLICY: removed tower exit remained unresolved at EOF")\n    if removed_blocks != starts_before or removed_post != post_starts_before:\n        raise RuntimeError(\n            "DYNAMIC TOWER POLICY: removal counts mismatch: "\n            f"tower {removed_blocks}/{starts_before}, optional_post {removed_post}/{post_starts_before}"\n        )\n\n    # v1.98: all real v1.179 FC3D_TOWER_SLOT emission owners have now been\n    # removed above.  Any exact slot marker that remains is therefore standalone\n    # commentary (the predecessor policy also scrubbed this form).  Remove the\n    # comment only; never consume neighbouring motion.\n    standalone_slot_re = re.compile(r"^\\s*;\\s*FC3D_TOWER_SLOT(?:\\s|$)")\n    standalone_slot_comments = [line for line in out if standalone_slot_re.match(line)]\n    if standalone_slot_comments:\n        out = [line for line in out if not standalone_slot_re.match(line)]\n        removed_lines += len(standalone_slot_comments)\n\n    new_gcode = "\\n".join(out) + "\\n"\n    tower_tokens = (\n        "WIPE_TOWER_START DIRECT_SOLID_",\n        "WIPE_TOWER_END DIRECT_SOLID_",\n        "FEATURE: DIRECT_SOLID_PRIME_TOWER",\n        "DIRECT_SOLID_PRIME_TOWER_V57",\n        "PRIME_TOWER_PPV64_CONTINUOUS_STUDIO_X",\n        "PRIME_TOWER_V169_CANONICAL_FILLER",\n        "FC3D_TOWER_PRIMARY_STRUCTURAL_FILL",\n        "FC3D_TOWER_SECONDARY_GAPS_V156",\n        "FC3D_TOWER_LAYER_COMPLETE_V129",\n        "FC3D_TOWER_FILL_NO_SWAP",\n        "FC3D_PPV64_SOLID_WHITE_TOWER_BASE",\n        "WIPE_START FC3D_PPSPV47_POST_TOWER_SAFE_LIFTED",\n        "WIPE_END FC3D_PPSPV47_POST_TOWER_SAFE_LIFTED",\n        "FC3D_PPSPV47_TOWER_EXIT_ALREADY_LIFTED_NEXT_TRAVEL_SAFE",\n        "FC3D_V150_TOWER_PRESSURE_STATE",\n        "reason=TOWER_TRAVEL",\n        "PPSPV53 tower XY",\n    )\n    leaked = [tok for tok in tower_tokens if tok in new_gcode]\n    residual_slot_markers = [\n        line for line in out if standalone_slot_re.match(line)\n    ]\n    if residual_slot_markers:\n        raise RuntimeError(\n            "DYNAMIC TOWER POLICY: exact FC3D_TOWER_SLOT marker survived standalone scrub: "\n            f"{residual_slot_markers[:5]}"\n        )\n    if leaked:\n        leak_context = [\n            (i + 1, line) for i, line in enumerate(out)\n            if any(tok in line for tok in leaked)\n        ]\n        raise RuntimeError(\n            "DYNAMIC TOWER POLICY: tower lifecycle content survived removal: "\n            f"{leaked}; first_lines={leak_context[:8]}"\n        )\n\n    if new_gcode != gcode:\n        _replace_zip_members(output, {gcode_name: new_gcode.encode("utf-8")})\n\n    return {\n        "policy": "single_material_remove_all_known_tower_owners_and_sanitize_checked_exit_hop",\n        "active_materials": active_materials,\n        "active_material_count": len(active_materials),\n        "tower_removed": bool(removed_blocks or removed_scheduler_groups),\n        "original_tower_blocks": starts_before,\n        "original_tower_block_ids": dict(sorted(tower_id_counts.items())),\n        "original_post_tower_wipes": post_starts_before,\n        "removed_tower_blocks": removed_blocks,\n        "removed_scheduler_primary_fill_groups": removed_scheduler_groups,\n        "removed_scheduler_primary_fill_markers": removed_scheduler_primary_markers,\n        "removed_scheduler_completion_markers": removed_scheduler_completion_markers,\n        "removed_standalone_slot_comments": len(standalone_slot_comments),\n        "removed_post_tower_wipes": removed_post,\n        "sanitized_tower_exit_hops": sanitized_hops,\n        "tower_exits_without_following_hop": exits_without_hop,\n        "removed_tower_lines": removed_lines,\n        "tower_markers_after": 0,\n    }\n'




NEW_CONVERTER_TOWER_AUDIT = 'def _strip_prime_tower_blocks(lines):\n    """Audit-only at the A1 conversion boundary.\n\n    All tower deletion belongs to apply_dynamic_tower_policy().  Any surviving\n    explicit, scheduler, filler or post-tower lifecycle marker is fatal here.\n    """\n    rows = list(lines)\n    forbidden = (\n        "WIPE_TOWER_START DIRECT_SOLID_",\n        "WIPE_TOWER_END DIRECT_SOLID_",\n        "FEATURE: DIRECT_SOLID_PRIME_TOWER",\n        "DIRECT_SOLID_PRIME_TOWER_V57",\n        "PRIME_TOWER_PPV64_CONTINUOUS_STUDIO_X",\n        "PRIME_TOWER_V169_CANONICAL_FILLER",\n        "FC3D_TOWER_PRIMARY_STRUCTURAL_FILL",\n        "FC3D_TOWER_SECONDARY_GAPS_V156",\n        "FC3D_TOWER_LAYER_COMPLETE_V129",\n        "FC3D_TOWER_FILL_NO_SWAP",\n        "FC3D_PPV64_SOLID_WHITE_TOWER_BASE",\n        "WIPE_START FC3D_PPSPV47_POST_TOWER_SAFE_LIFTED",\n        "WIPE_END FC3D_PPSPV47_POST_TOWER_SAFE_LIFTED",\n        "FC3D_PPSPV47_TOWER_EXIT_ALREADY_LIFTED_NEXT_TRAVEL_SAFE",\n        "FC3D_V150_TOWER_PRESSURE_STATE",\n        "reason=TOWER_TRAVEL",\n        "PPSPV53 tower XY",\n    )\n    slot_re = re.compile(r"^\\s*;\\s*FC3D_TOWER_SLOT(?:\\s|$)")\n    hits = [\n        (i + 1, line) for i, line in enumerate(rows)\n        if any(tok in line for tok in forbidden) or slot_re.match(line)\n    ]\n    if hits:\n        raise RuntimeError(\n            "V1.98 A1 MINI: tower lifecycle incomplete before package conversion; "\n            f"first surviving lines={hits[:8]}"\n        )\n    return rows, 0\n'



NEW_A1_START = 'def _a1mini_start_gcode() -> str:\n    """Reduced A1 Mini single-material start derived from Orca A1 Mini ordering.\n\n    Keep the nozzle below PETG print temperature during cleaning/probing, enable\n    the ABL mesh before G29, commit the completed probe, then block at 255 C and\n    condition the already-loaded black PETG in the unused front bed margin.\n    Conditioning exits retracted by 0.400 mm for the canonical model contract.\n    """\n    return "\\n".join([\n        "; FC3D_V198_A1MINI_START",\n        "; machine: A1 mini / single 0.4 mm nozzle / black PETG",\n        "M1002 gcode_claim_action : 2",\n        "M17",\n        "G90",\n        "M83",\n        "M220 S100",\n        "M221 S100",\n        "M104 S170",\n        f"M140 S{A1_MINI_BED_C}",\n        "G28",\n\n        "; FC3D_V198_A1MINI_NOZZLE_WIPE_START",\n        "M1002 gcode_claim_action : 14",\n        "M104 S170",\n        "M106 S255",\n        "M211 S",\n        "M211 X0 Y0 Z0",\n        "M83",\n        "G1 E-1.000 F500",\n        "M109 S170",\n        "M104 S140",\n        "G1 Z5.000 F3000",\n        "G1 X25.000 Y175.000 F30000",\n        "G1 Z0.200 F30000",\n        "G1 Y185.000 F30000",\n        "G91",\n        "G1 X-30.000 F30000",\n        "G1 Y-2.000",\n        "G1 X27.000",\n        "G1 Y1.500",\n        "G1 X-28.000",\n        "G1 Y-2.000",\n        "G1 X30.000",\n        "G1 Y1.500",\n        "G1 X-30.000",\n        "G90",\n        "M83",\n        "G1 Z5.000 F3000",\n        "M211 R",\n        "M106 S0",\n        "; FC3D_V198_A1MINI_NOZZLE_WIPE_END",\n\n        "; A1 native thermal/ABL ordering",\n        "M104 S0",\n        f"M190 S{A1_MINI_BED_C}",\n        "M109 S140",\n        "G1 Z5.000 F3000",\n        "G29.2 S1",\n        "G1 X10.000 Y10.000 F20000",\n        "M1002 gcode_claim_action : 1",\n        "G29 A1 X20 Y20 I140 J140",\n        "M400",\n        "M500",\n        "G29.1 Z-0.02 ; Textured PEI",\n\n        "; FC3D_V198_A1MINI_CONDITION_START",\n        "G90",\n        "M83",\n        "G0 X10.000 Y5.000 Z2.000 F12000",\n        f"M104 S{A1_MINI_NOZZLE_C}",\n        f"M109 S{A1_MINI_NOZZLE_C}",\n        "G92 E0",\n        "G0 Z0.300 F900",\n        "G1 X20.000 Y5.000 E1.000 F1200 ; recover wipe retract while moving",\n        "G1 X50.000 Y5.000 E1.200 F1200 ; short single-material conditioning line",\n        f"G1 E-{A_RETRACT_MM:.3f} F1800 ; leave canonical model retracted",\n        "G0 Z2.000 F900",\n        "; FC3D_V198_A1MINI_CONDITION_END state=RETRACTED",\n        "M106 S0",\n        "M1002 gcode_claim_action : 0",\n        "; FC3D_V198_A1MINI_START_END",\n    ])'




NEW_A1_END = r'''
def _a1mini_end_gcode(final_z: float) -> str:
    # Relative lift can never command beyond the A1 Mini's 180-mm Z envelope.
    clearance = max(0.0, 180.0 - float(final_z) - 0.20)
    lift = min(5.0, clearance)
    rows = [
        "; FC3D_V198_A1MINI_END",
        "M400",
        "G92 E0",
        "G1 E-0.8 F1800",
        "M104 S0",
        "M140 S0",
        "M106 S0",
    ]
    if lift > 1e-6:
        rows += ["G91", f"G1 Z{lift:.3f} F900", "G90"]
    rows += [
        "G1 X0 Y180 F12000",
        "M400",
        "M18 X Y Z",
        "; FC3D_V198_A1MINI_END_DONE",
        "; EXECUTABLE_BLOCK_END",
    ]
    return "\n".join(rows)
'''.strip()


NEW_A1_AUDIT = 'def audit_a1mini_orca_package(output: Path, removed_tower_blocks: int = 0) -> dict:\n    output = Path(output)\n    with zipfile.ZipFile(output, "r") as z:\n        gbytes = z.read("Metadata/plate_1.gcode")\n        g = gbytes.decode("utf-8")\n        project = json.loads(z.read("Metadata/project_settings.config").decode("utf-8"))\n        root = ET.fromstring(z.read("Metadata/slice_info.config"))\n        md5 = z.read("Metadata/plate_1.gcode.md5").decode("ascii").strip().lower()\n\n    expected_project = {\n        "printer_model": A1_MINI_PRINTER_NAME,\n        "printer_settings_id": A1_MINI_PRINTER_PRESET,\n        "print_settings_id": A1_MINI_PROCESS_PRESET,\n        "printer_structure": "i3",\n        "printable_area": ["0x0", "180x0", "180x180", "0x180"],\n        "printable_height": "180",\n        "nozzle_diameter": ["0.4"],\n        "nozzle_type": ["stainless_steel"],\n        "nozzle_volume": ["92"],\n        "nozzle_volume_type": ["Standard"],\n        "default_nozzle_volume_type": ["Standard"],\n        "enable_prime_tower": "0",\n        "prime_tower_enable_framework": "0",\n        "curr_bed_type": "Textured PEI Plate",\n    }\n    for key, expected in expected_project.items():\n        if project.get(key) != expected:\n            raise RuntimeError(\n                f"V1.98 A1 MINI AUDIT: project {key}={project.get(key)!r}, expected {expected!r}"\n            )\n\n    lines = g.splitlines()\n    exec_starts = [i for i, line in enumerate(lines) if line.strip() == "; EXECUTABLE_BLOCK_START"]\n    exec_ends = [i for i, line in enumerate(lines) if line.strip() == "; EXECUTABLE_BLOCK_END"]\n    if len(exec_starts) != 1 or len(exec_ends) != 1 or exec_starts[0] >= exec_ends[0]:\n        raise RuntimeError(\n            "V1.98 A1 MINI AUDIT: executable block boundary invalid: "\n            f"starts={exec_starts} ends={exec_ends}"\n        )\n    exec_start_i = exec_starts[0]\n    exec_end_i = exec_ends[0]\n    executable_lines = lines[exec_start_i + 1:exec_end_i]\n    executable = "\\n".join(executable_lines)\n    forbidden = (\n        "machine: H2C",\n        "Vortek",\n        "FC3D_PPSPV43_FULL_H2C_SWAP_START",\n        "M640.8",\n        "G151 ",\n        "M481 ",\n        "FEATURE: DIRECT_SOLID_PRIME_TOWER",\n        "WIPE_TOWER_START DIRECT_SOLID_",\n        "WIPE_TOWER_END DIRECT_SOLID_",\n        "WIPE_TOWER_END DIRECT_SOLID_V4",\n        "PRIME_TOWER_PPV64_CONTINUOUS_STUDIO_X",\n        "FC3D_TOWER_PRIMARY_STRUCTURAL_FILL",\n        "FC3D_TOWER_SECONDARY_GAPS_V156",\n        "FC3D_TOWER_LAYER_COMPLETE_V129",\n        "WIPE_START FC3D_PPSPV47_POST_TOWER_SAFE_LIFTED",\n        "WIPE_END FC3D_PPSPV47_POST_TOWER_SAFE_LIFTED",\n        "FC3D_PPSPV47_TOWER_EXIT_ALREADY_LIFTED_NEXT_TRAVEL_SAFE",\n        "FC3D_V150_TOWER_PRESSURE_STATE",\n        "reason=TOWER_TRAVEL",\n        "PPSPV53 tower XY",\n    )\n    leaked = [x for x in forbidden if x in executable]\n    exact_slot_lines = [\n        line for line in executable.splitlines()\n        if re.match(r"^\\s*;\\s*FC3D_TOWER_SLOT(?:\\s|$)", line)\n    ]\n    if exact_slot_lines:\n        leaked.append("FC3D_TOWER_SLOT_MARKER")\n    if leaked:\n        raise RuntimeError(\n            f"V1.98 A1 MINI AUDIT: forbidden H2C/tower executable content {leaked}; "\n            f"slot_lines={exact_slot_lines[:5]}"\n        )\n\n    for required in (\n        "; FC3D_V198_A1MINI_START",\n        "; FC3D_V198_A1MINI_NOZZLE_WIPE_START",\n        "; FC3D_V198_A1MINI_NOZZLE_WIPE_END",\n        "; FC3D_V198_A1MINI_CONDITION_START",\n        "; FC3D_V198_A1MINI_CONDITION_END state=RETRACTED",\n        "; FC3D_V198_A1MINI_END",\n    ):\n        if required not in executable:\n            raise RuntimeError(f"V1.98 A1 MINI AUDIT: required executable marker missing: {required}")\n    for required in (\n        "; enable_prime_tower = 0",\n        "; prime_tower_enable_framework = 0",\n    ):\n        if required not in g:\n            raise RuntimeError(f"V1.98 A1 MINI AUDIT: required config missing: {required}")\n\n    # A1 Mini is single-nozzle: reject H2C-style thermal-head targeting.\n    thermal_head_leaks = [\n        line for line in executable.splitlines()\n        if re.match(r"^\\s*M10[49]\\b", line, re.I) and re.search(r"\\bT[01]\\b", line, re.I)\n    ]\n    if thermal_head_leaks:\n        raise RuntimeError(\n            "V1.98 A1 MINI AUDIT: T0/T1 thermal-head command leaked into A1 job: "\n            f"{thermal_head_leaks[:6]}"\n        )\n\n    exec_range = range(exec_start_i + 1, exec_end_i)\n    try:\n        start_i = next(i for i in exec_range if lines[i].strip() == "; FC3D_V198_A1MINI_START")\n        wipe_start_i = next(i for i in range(start_i + 1, exec_end_i) if lines[i].strip() == "; FC3D_V198_A1MINI_NOZZLE_WIPE_START")\n        wipe_end_i = next(i for i in range(wipe_start_i + 1, exec_end_i) if lines[i].strip() == "; FC3D_V198_A1MINI_NOZZLE_WIPE_END")\n        g29_i = next(i for i in range(wipe_end_i + 1, exec_end_i) if re.match(r"^\\s*G29\\s+A1\\b", lines[i]))\n        cond_start_i = next(i for i in range(g29_i + 1, exec_end_i) if lines[i].strip() == "; FC3D_V198_A1MINI_CONDITION_START")\n        cond_end_i = next(i for i in range(cond_start_i + 1, exec_end_i) if lines[i].strip() == "; FC3D_V198_A1MINI_CONDITION_END state=RETRACTED")\n        first_layer_i = next(i for i in range(cond_end_i + 1, exec_end_i) if lines[i].strip() == "; CHANGE_LAYER")\n        a1_end_i = next(i for i in range(first_layer_i + 1, exec_end_i) if lines[i].strip() == "; FC3D_V198_A1MINI_END")\n    except StopIteration as exc:\n        raise RuntimeError("V1.98 A1 MINI AUDIT: executable startup/model ordering marker missing") from exc\n\n    if not (start_i < wipe_start_i < wipe_end_i < g29_i < cond_start_i < cond_end_i < first_layer_i < a1_end_i < exec_end_i):\n        raise RuntimeError(\n            "V1.98 A1 MINI AUDIT: startup ordering invalid: "\n            f"start={start_i}, wipe={wipe_start_i}:{wipe_end_i}, G29={g29_i}, "\n            f"condition={cond_start_i}:{cond_end_i}, model={first_layer_i}, "\n            f"end={a1_end_i}, exec={exec_start_i}:{exec_end_i}"\n        )\n\n    # Real brush use from the current A1 Mini profile: rear brush reaches Y185.\n    wipe_block = lines[wipe_start_i:wipe_end_i + 1]\n    if not any(re.search(r"\\bY185(?:\\.0+)?\\b", line) for line in wipe_block):\n        raise RuntimeError("V1.98 A1 MINI AUDIT: physical A1 brush wipe does not reach Y185")\n    wipe_170_waits = [\n        line for line in wipe_block\n        if re.match(r"^\\s*M109\\b", line, re.I)\n        and re.search(r"\\bS170(?:\\.0+)?(?:\\s|$)", line, re.I)\n    ]\n    if len(wipe_170_waits) != 1:\n        raise RuntimeError(\n            f"V1.98 A1 MINI AUDIT: expected exactly one blocking M109 S170 in wipe, got {wipe_170_waits}"\n        )\n\n    def nozzle_target(line):\n        if not re.match(r"^\\s*M10[49]\\b", line, re.I):\n            return None\n        m = re.search(r"\\bS(-?\\d+(?:\\.\\d+)?)\\b", line, re.I)\n        return float(m.group(1)) if m else None\n\n    # ABL must be after a blocking 140-C wait, explicitly enabled, and before\n    # the final 255-C wait. The current A1 Mini sequence synchronizes/saves the\n    # completed probe before applying the Textured-PEI trim.\n    pre_g29 = lines[start_i:g29_i]\n    if not any(line.strip() == "G29.2 S1" for line in pre_g29):\n        raise RuntimeError("V1.98 A1 MINI AUDIT: G29.2 S1 missing before ABL")\n    waits_140 = [i for i, line in enumerate(pre_g29, start_i) if re.match(r"^\\s*M109\\b", line, re.I) and abs((nozzle_target(line) or -999) - 140.0) < 1e-6]\n    if not waits_140:\n        raise RuntimeError("V1.98 A1 MINI AUDIT: no blocking M109 S140 before ABL")\n\n    post_g29_before_model = lines[g29_i + 1:first_layer_i]\n    if not any(line.strip() == "M400" for line in post_g29_before_model):\n        raise RuntimeError("V1.98 A1 MINI AUDIT: M400 missing after ABL")\n    if not any(line.strip() == "M500" for line in post_g29_before_model):\n        raise RuntimeError("V1.98 A1 MINI AUDIT: M500 missing after ABL")\n\n    final_waits = [\n        i for i in range(g29_i + 1, first_layer_i)\n        if re.match(r"^\\s*M109\\b", lines[i], re.I)\n        and abs((nozzle_target(lines[i]) or -999) - float(A1_MINI_NOZZLE_C)) < 1e-6\n    ]\n    if not final_waits:\n        raise RuntimeError(f"V1.98 A1 MINI AUDIT: no blocking M109 S{A1_MINI_NOZZLE_C} after ABL")\n    final_heat_i = final_waits[-1]\n\n    lowered_after_final = []\n    for i in range(final_heat_i + 1, first_layer_i):\n        target = nozzle_target(lines[i])\n        if target is not None and target < float(A1_MINI_NOZZLE_C) - 1e-6:\n            lowered_after_final.append((i + 1, lines[i]))\n    if lowered_after_final:\n        raise RuntimeError(\n            "V1.98 A1 MINI AUDIT: nozzle target lowered after final print-temperature wait: "\n            f"{lowered_after_final[:6]}"\n        )\n\n    condition_block = lines[cond_start_i:cond_end_i + 1]\n    positive_xy_e = []\n    for line in condition_block:\n        if not re.match(r"^\\s*G[01]\\b", line):\n            continue\n        if not (re.search(r"\\bX-?\\d", line) or re.search(r"\\bY-?\\d", line)):\n            continue\n        me = re.search(r"\\bE(-?\\d+(?:\\.\\d+)?)\\b", line)\n        if me and float(me.group(1)) > 0:\n            positive_xy_e.append(line)\n    if len(positive_xy_e) != 2:\n        raise RuntimeError(\n            "V1.98 A1 MINI AUDIT: expected exactly two positive-E XY conditioning moves, "\n            f"got {positive_xy_e}"\n        )\n    # The conditioning line is deliberately confined to the unused front strip.\n    # The model/card begins much farther back on this coupon; fail closed rather\n    # than allowing a future edit to drag the purge line through the card.\n    for line in positive_xy_e:\n        mx = re.search(r"\\bX(-?\\d+(?:\\.\\d+)?)\\b", line)\n        my = re.search(r"\\bY(-?\\d+(?:\\.\\d+)?)\\b", line)\n        if mx is None or my is None:\n            raise RuntimeError(\n                "V1.98 A1 MINI AUDIT: conditioning extrusion must carry explicit X and Y: "\n                f"{line}"\n            )\n        x = float(mx.group(1)); y = float(my.group(1))\n        if not (0.0 <= x <= 180.0 and 0.0 <= y <= 10.0):\n            raise RuntimeError(\n                "V1.98 A1 MINI AUDIT: conditioning extrusion escaped safe front strip "\n                f"X=0..180 Y=0..10: {line}"\n            )\n    e_only_changes = [\n        line for line in condition_block\n        if re.match(r"^\\s*G1\\b", line)\n        and re.search(r"\\bE[-+]?\\d", line)\n        and not re.search(r"\\b[XYZ][-+]?\\d", line)\n    ]\n    if not e_only_changes or not re.search(r"\\bE-0\\.400(?:\\D|$)", e_only_changes[-1]):\n        raise RuntimeError(\n            "V1.98 A1 MINI AUDIT: final conditioning E-only state change is not -0.400 retract: "\n            f"{e_only_changes[-3:]}"\n        )\n\n    p = root.find("plate")\n    if p is None:\n        raise RuntimeError("V1.98 A1 MINI AUDIT: slice_info has no plate")\n    meta = {n.attrib.get("key"): n.attrib.get("value") for n in p.findall("metadata")}\n    if meta.get("printer_model_id") != A1_MINI_MODEL_ID or meta.get("nozzle_diameters") != "0.4":\n        raise RuntimeError(f"V1.98 A1 MINI AUDIT: slice machine metadata {meta}")\n    if meta.get("has_filament_switcher") != "false":\n        raise RuntimeError(f"V1.98 A1 MINI AUDIT: has_filament_switcher={meta.get(\'has_filament_switcher\')!r}")\n    nozzles = [n.attrib for n in p.findall("nozzle")]\n    expected_nozzles = [{"id": "0", "extruder_id": "1", "nozzle_diameter": "0.4", "volume_type": "Standard"}]\n    if nozzles != expected_nozzles:\n        raise RuntimeError(f"V1.98 A1 MINI AUDIT: nozzle record {nozzles}")\n\n    actual_md5 = hashlib.md5(gbytes).hexdigest()\n    if actual_md5 != md5:\n        raise RuntimeError(\n            f"V1.98 A1 MINI AUDIT: gcode MD5 mismatch package={md5} actual={actual_md5}"\n        )\n\n    model = g.split("; CHANGE_LAYER", 1)[-1].split("; V4_MODEL_END", 1)[0]\n    model_motion = "\\n".join(\n        line for line in model.splitlines()\n        if re.match(r"^\\s*G[01]\\b", line, re.I)\n    )\n    xs = [float(m.group(1)) for m in re.finditer(r"\\bX(-?\\d+(?:\\.\\d+)?)", model_motion)]\n    ys = [float(m.group(1)) for m in re.finditer(r"\\bY(-?\\d+(?:\\.\\d+)?)", model_motion)]\n    if not xs or not ys or min(xs) < 0 or max(xs) > 180 or min(ys) < 0 or max(ys) > 180:\n        raise RuntimeError(\n            "V1.98 A1 MINI AUDIT: model outside bed "\n            f"X={min(xs) if xs else None}..{max(xs) if xs else None} "\n            f"Y={min(ys) if ys else None}..{max(ys) if ys else None}"\n        )\n\n    return {\n        "printer": A1_MINI_PRINTER_PRESET,\n        "model_id": A1_MINI_MODEL_ID,\n        "envelope_mm": [180, 180, 180],\n        "nozzle": "0.4 mm Standard stainless",\n        "prime_tower_present": False,\n        "removed_tower_blocks_at_converter": removed_tower_blocks,\n        "model_xy_mm": [min(xs), max(xs), min(ys), max(ys)],\n        "probe_nozzle_c": 140,\n        "final_nozzle_c": A1_MINI_NOZZLE_C,\n        "condition_xy_e_moves": len(positive_xy_e),\n        "condition_exit_retract_mm": A_RETRACT_MM,\n        "sanitized_tower_exit_hops": g.count("FC3D_V198_TOWER_EXIT_HOP_SANITIZED_Z_ONLY"),\n        "md5": md5,\n    }'



NEW_REFERENCE_METADATA_NORMALIZER = 'def normalize_a1mini_orca_reference_metadata(output: Path) -> dict:\n    """Normalize non-executable metadata to the working Orca A1 Mini reference.\n\n    The embedded templates are copied byte-for-byte from the user\'s Orca 2.5.0\n    cube that successfully printed through Bambu Connect.  Only metadata/config\n    is replaced here.  The already-audited executable A1 startup/model/end block\n    is not reconstructed or resliced.\n    """\n    import base64, zlib\n    output = Path(output)\n    gname = "Metadata/plate_1.gcode"\n    pname = "Metadata/project_settings.config"\n    sname = "Metadata/slice_info.config"\n    plate_name = "Metadata/plate_1.json"\n    seq_name = "Metadata/filament_sequence.json"\n    model_settings_name = "Metadata/model_settings.config"\n    model_name = "3D/3dmodel.model"\n    required = (gname, pname, sname, plate_name, seq_name, model_settings_name, model_name)\n    with zipfile.ZipFile(output, "r") as z:\n        missing = [n for n in required if n not in z.namelist()]\n        if missing:\n            raise RuntimeError(f"V1.98 ORCA REFERENCE METADATA: missing members {missing}")\n        old_g = z.read(gname).decode("utf-8", errors="strict")\n        old_project = json.loads(z.read(pname).decode("utf-8"))\n        slice_root = ET.fromstring(z.read(sname))\n        plate = json.loads(z.read(plate_name).decode("utf-8"))\n        model_settings_root = ET.fromstring(z.read(model_settings_name))\n        model_text = z.read(model_name).decode("utf-8", errors="strict")\n\n    native_project = json.loads(zlib.decompress(base64.b64decode(\'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\')).decode("utf-8"))\n    native_config = zlib.decompress(base64.b64decode(\'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\')).decode("utf-8")\n\n    # Keep only truthful FC3D process-display values that are useful in Orca\'s\n    # preview UI.  Machine, filament, AMS and enum values come from the native\n    # A1 Mini reference instead of the inherited H2C template.\n    preserve_project_keys = (\n        "layer_height", "initial_layer_print_height", "initial_layer_line_width",\n        "line_width", "outer_wall_line_width", "inner_wall_line_width",\n        "sparse_infill_line_width", "top_surface_line_width", "support_line_width",\n        "print_sequence", "spiral_mode",\n    )\n    preserved_project = {k: old_project[k] for k in preserve_project_keys if k in old_project}\n    project = dict(native_project)\n    project.update(preserved_project)\n    project.update({\n        "printer_model": A1_MINI_PRINTER_NAME,\n        "printer_settings_id": A1_MINI_PRINTER_PRESET,\n        "print_settings_id": A1_MINI_PROCESS_PRESET,\n        "print_compatible_printers": [A1_MINI_PRINTER_PRESET],\n        "printer_structure": "i3",\n        "printable_area": ["0x0", "180x0", "180x180", "0x180"],\n        "printable_height": "180",\n        "nozzle_diameter": ["0.4"],\n        "nozzle_type": ["stainless_steel"],\n        "nozzle_volume": ["92"],\n        "nozzle_volume_type": ["Standard"],\n        "default_nozzle_volume_type": ["Standard"],\n        "printer_extruder_id": ["1"],\n        "print_extruder_id": ["1"],\n        "printer_extruder_variant": ["Direct Drive Standard"],\n        "print_extruder_variant": ["Direct Drive Standard"],\n        "filament_settings_id": ["Generic PETG @BBL A1M"],\n        "filament_type": ["PETG"],\n        "filament_colour": ["#000000"],\n        "filament_multi_colour": ["#000000"],\n        "filament_ids": ["GFG99"],\n        "filament_map": ["1"],\n        "filament_map_2": ["1"],\n        "filament_nozzle_map": ["0"],\n        "physical_extruder_map": ["0"],\n        "extruder_ams_count": ["1#0|4#0", ""],\n        "enable_prime_tower": "0",\n        "prime_tower_enable_framework": "0",\n        "curr_bed_type": "Textured PEI Plate",\n        "ensure_vertical_shell_thickness": "ensure_all",\n        "raft_first_layer_expansion": "2",\n        "prime_tower_brim_width": "3",\n        "machine_start_gcode": _a1mini_start_gcode() + "\\n",\n        "machine_end_gcode": _a1mini_end_gcode(_mirror_wave_peak_z_mm()) + "\\n",\n    })\n    # Native Orca does not carry this legacy negative sentinel.  Its presence\n    # caused Orca 2.5.0\'s invalid-range toast in the previous output.\n    project.pop("prime_tower_lift_height", None)\n\n    # Replace the complete CONFIG_BLOCK with the known-working A1/Orca block.\n    a = old_g.find("; CONFIG_BLOCK_START")\n    b0 = old_g.find("; CONFIG_BLOCK_END")\n    if a < 0 or b0 < 0 or b0 <= a:\n        raise RuntimeError("V1.98 ORCA REFERENCE METADATA: CONFIG_BLOCK boundaries missing")\n    b = b0 + len("; CONFIG_BLOCK_END")\n    new_g = old_g[:a] + native_config + old_g[b:]\n\n    # Preserve a small set of truthful FC3D process-display values from the old\n    # config while keeping all machine/filament topology native A1 Mini.\n    preserve_config_keys = preserve_project_keys\n    for key in preserve_config_keys:\n        m = re.search(rf"^; {re.escape(key)} = (.*)$", old_g, re.M)\n        if m:\n            new_g = _replace_config_comment(new_g, key, m.group(1))\n    for key, value in {\n        "enable_prime_tower": "0",\n        "prime_tower_enable_framework": "0",\n        "curr_bed_type": "Textured PEI Plate",\n        "ensure_vertical_shell_thickness": "ensure_all",\n        "raft_first_layer_expansion": "2",\n        "prime_tower_brim_width": "3",\n        "machine_start_gcode": _a1mini_start_gcode().replace("\\n", "\\\\n"),\n        "machine_end_gcode": _a1mini_end_gcode(_mirror_wave_peak_z_mm()).replace("\\n", "\\\\n"),\n    }.items():\n        new_g = _replace_config_comment(new_g, key, value)\n\n    # Header filament identity also becomes one logical A1 external-spool PETG.\n    header_patch = {\n        "filament": "1",\n        "filament_density": "1.27",\n        "filament_diameter": "1.75",\n    }\n    for key, value in header_patch.items():\n        pat = re.compile(rf"^; {re.escape(key)}:\\s*.*$", re.M)\n        if len(pat.findall(new_g)) != 1:\n            raise RuntimeError(f"V1.98 ORCA REFERENCE METADATA: expected one header {key} line")\n        new_g = pat.sub(lambda _m, k=key, v=value: f"; {k}: {v}", new_g, count=1)\n\n    # Orca/Bambu config values that select one PETG on the external spool.\n    config_contract = {\n        "default_filament_profile": \'"Bambu PLA Basic @BBL A1M"\',\n        "filament_settings_id": \'"Generic PETG @BBL A1M"\',\n        "filament_colour": "#000000",\n        "filament_type": "PETG",\n        "filament_ids": "GFG99",\n        "filament_map": "1",\n        "filament_map_2": "0",\n        "filament_nozzle_map": "0",\n        "filament_extruder_variant": \'"Direct Drive Standard"\',\n        "filament_max_volumetric_speed": "8",\n        "filament_flow_ratio": "0.95",\n        "extruder_ams_count": "1#0|4#0;",\n        "physical_extruder_map": "0",\n        "single_extruder_multi_material": "1",\n        "printer_extruder_id": "1",\n        "print_extruder_id": "1",\n        "printer_extruder_variant": \'"Direct Drive Standard"\',\n        "print_extruder_variant": \'"Direct Drive Standard"\',\n        "extruder_max_nozzle_count": "1",\n        "extruder_nozzle_stats": "Standard#1",\n        "extruder_variant_list": \'"Direct Drive Standard"\',\n        "extruder_type": "Direct Drive",\n        "extruder_offset": "0x0",\n        "extruder_colour": "#000000",\n        "extruder_printable_area": "",\n        "extruder_printable_height": "0",\n    }\n    for key, value in config_contract.items():\n        new_g = _replace_config_comment(new_g, key, value)\n\n    # Slice-info header: reproduce Orca\'s own package identity convention.\n    header = slice_root.find("header")\n    if header is None:\n        header = ET.Element("header")\n        slice_root.insert(0, header)\n    header_items = {n.attrib.get("key"): n for n in header.findall("header_item")}\n    for key, value in (\n        ("X-BBL-Client-Type", "slicer"),\n        ("X-BBL-Client-Version", "02.08.01.55"),\n        ("OrcaSlicer-Version", "2.5.0-dev"),\n    ):\n        node = header_items.get(key)\n        if node is None:\n            node = ET.SubElement(header, "header_item", key=key, value=value)\n        else:\n            node.set("value", value)\n\n    plate_node = slice_root.find("plate")\n    if plate_node is None:\n        raise RuntimeError("V1.98 ORCA REFERENCE METADATA: slice_info has no plate")\n    meta_nodes = {n.attrib.get("key"): n for n in plate_node.findall("metadata") if n.attrib.get("key")}\n    for key, value in (\n        ("printer_model_id", "N1"),\n        ("nozzle_diameters", "0.4"),\n        ("nozzle_volume_type", "0"),\n        ("has_filament_switcher", "false"),\n        ("filament_maps", "1"),\n        ("limit_filament_maps", "0"),\n    ):\n        node = meta_nodes.get(key)\n        if node is None:\n            ET.SubElement(plate_node, "metadata", key=key, value=value)\n        else:\n            node.set("value", value)\n    old_fil = plate_node.find("filament")\n    used_m = old_fil.attrib.get("used_m", "0.00") if old_fil is not None else "0.00"\n    used_g = old_fil.attrib.get("used_g", "0.00") if old_fil is not None else "0.00"\n    for node in list(plate_node.findall("filament")):\n        plate_node.remove(node)\n    ET.SubElement(plate_node, "filament", {\n        "id": "1", "tray_info_idx": "GFG99", "type": "PETG", "color": "#000000",\n        "used_m": used_m, "used_g": used_g, "group_id": "0",\n        "nozzle_diameter": "0.40", "volume_type": "Standard",\n        "used_for_object": "true", "used_for_support": "false",\n    })\n    for node in list(plate_node.findall("nozzle")):\n        plate_node.remove(node)\n    ET.SubElement(plate_node, "nozzle", {\n        "id": "0", "extruder_id": "1", "nozzle_diameter": "0.4", "volume_type": "Standard",\n    })\n    layer_lists = plate_node.find("layer_filament_lists")\n    if layer_lists is not None:\n        existing_ranges = [n.attrib.get("layer_ranges") for n in list(layer_lists) if n.attrib.get("layer_ranges")]\n        for node in list(layer_lists):\n            layer_lists.remove(node)\n        layer_ranges = existing_ranges[0] if existing_ranges else f"0 {PHYSICAL_LAYER_COUNT - 1}"\n        ET.SubElement(layer_lists, "layer_filament_list", filament_list="0", layer_ranges=layer_ranges)\n\n    # plate_1.json follows the exact native A1 Mini representation.\n    plate["bed_type"] = "textured_plate"\n    plate["filament_colors"] = ["#000000"]\n    plate["filament_ids"] = [0]\n    plate["first_extruder"] = 0\n    plate["nozzle_diameter"] = 0.4000000059604645\n\n    # External-spool/no-AMS filament sequence from the successful cube.\n    seq = {"plate_1": {"nozzle_sequence": [0], "optimal_assignment": [0], "sequence": [1]}}\n\n    # model_settings.config must agree with the same single logical filament.\n    ms_plate = model_settings_root.find("plate")\n    if ms_plate is None:\n        raise RuntimeError("V1.98 ORCA REFERENCE METADATA: model_settings has no plate")\n    ms_meta = {n.attrib.get("key"): n for n in ms_plate.findall("metadata") if n.attrib.get("key")}\n    for key, value in (("filament_maps", "1"), ("filament_volume_maps", "0")):\n        node = ms_meta.get(key)\n        if node is None:\n            ET.SubElement(ms_plate, "metadata", key=key, value=value)\n        else:\n            node.set("value", value)\n    if "fc3d_active_filament_one_based" in ms_meta:\n        ms_meta["fc3d_active_filament_one_based"].set("value", "1")\n\n    # Native Orca 2.5.0 retains a BambuStudio Application metadata item and adds\n    # its own OrcaSlicer item.  Reproduce that convention exactly; do not invent\n    # a non-native Application value.\n    app_pat = re.compile(r\'<metadata name="Application">.*?</metadata>\')\n    if len(app_pat.findall(model_text)) != 1:\n        raise RuntimeError("V1.98 ORCA REFERENCE METADATA: 3D model Application metadata missing/ambiguous")\n    model_text = app_pat.sub(\'<metadata name="Application">BambuStudio-02.08.01.55</metadata>\', model_text, count=1)\n    orca_pat = re.compile(r\'<metadata name="OrcaSlicer">.*?</metadata>\')\n    if orca_pat.search(model_text):\n        model_text = orca_pat.sub(\'<metadata name="OrcaSlicer">2.5.0-dev</metadata>\', model_text, count=1)\n    else:\n        app_line = \'<metadata name="Application">BambuStudio-02.08.01.55</metadata>\'\n        model_text = model_text.replace(app_line, app_line + \'\\n <metadata name="OrcaSlicer">2.5.0-dev</metadata>\', 1)\n\n    replacements = {\n        gname: new_g.encode("utf-8"),\n        pname: json.dumps(project, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),\n        sname: ET.tostring(slice_root, encoding="utf-8", xml_declaration=True),\n        plate_name: json.dumps(plate, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),\n        seq_name: json.dumps(seq, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),\n        model_settings_name: ET.tostring(model_settings_root, encoding="utf-8", xml_declaration=True),\n        model_name: model_text.encode("utf-8"),\n    }\n    _replace_zip_members(output, replacements)\n    return audit_a1mini_orca_reference_metadata(output)\n'

NEW_REFERENCE_METADATA_AUDIT = 'def audit_a1mini_orca_reference_metadata(output: Path) -> dict:\n    """Fail-closed audit against the successfully printed Orca A1 Mini reference."""\n    output = Path(output)\n    with zipfile.ZipFile(output, "r") as z:\n        project = json.loads(z.read("Metadata/project_settings.config").decode("utf-8"))\n        gbytes = z.read("Metadata/plate_1.gcode")\n        g = gbytes.decode("utf-8", errors="strict")\n        slice_root = ET.fromstring(z.read("Metadata/slice_info.config"))\n        plate = json.loads(z.read("Metadata/plate_1.json").decode("utf-8"))\n        seq = json.loads(z.read("Metadata/filament_sequence.json").decode("utf-8"))\n        model_settings = ET.fromstring(z.read("Metadata/model_settings.config"))\n        model_text = z.read("3D/3dmodel.model").decode("utf-8", errors="strict")\n        md5 = z.read("Metadata/plate_1.gcode.md5").decode("ascii").strip().lower()\n\n    expected_project = {\n        "printer_model": "Bambu Lab A1 mini",\n        "printer_settings_id": "Bambu Lab A1 mini 0.4 nozzle",\n        "print_settings_id": "0.20mm Standard @BBL A1M",\n        "printer_structure": "i3",\n        "nozzle_diameter": ["0.4"],\n        "nozzle_type": ["stainless_steel"],\n        "nozzle_volume": ["92"],\n        "nozzle_volume_type": ["Standard"],\n        "default_nozzle_volume_type": ["Standard"],\n        "filament_settings_id": ["Generic PETG @BBL A1M"],\n        "filament_type": ["PETG"],\n        "filament_colour": ["#000000"],\n        "filament_ids": ["GFG99"],\n        "filament_map": ["1"],\n        "filament_map_2": ["1"],\n        "filament_nozzle_map": ["0"],\n        "physical_extruder_map": ["0"],\n        "extruder_ams_count": ["1#0|4#0", ""],\n        "ensure_vertical_shell_thickness": "ensure_all",\n        "raft_first_layer_expansion": "2",\n        "prime_tower_brim_width": "3",\n        "enable_prime_tower": "0",\n        "prime_tower_enable_framework": "0",\n        "curr_bed_type": "Textured PEI Plate",\n    }\n    wrong = {k: (project.get(k), v) for k, v in expected_project.items() if project.get(k) != v}\n    if wrong:\n        raise RuntimeError(f"V1.98 ORCA REFERENCE AUDIT: project mismatch {wrong}")\n    if "prime_tower_lift_height" in project:\n        raise RuntimeError("V1.98 ORCA REFERENCE AUDIT: legacy negative prime_tower_lift_height survived")\n    if "H2C" in json.dumps(project, ensure_ascii=False):\n        raise RuntimeError("V1.98 ORCA REFERENCE AUDIT: H2C project metadata survived")\n\n    config_expect = {\n        "ensure_vertical_shell_thickness": "ensure_all",\n        "raft_first_layer_expansion": "2",\n        "prime_tower_brim_width": "3",\n        "filament_settings_id": \'"Generic PETG @BBL A1M"\',\n        "filament_type": "PETG",\n        "filament_colour": "#000000",\n        "filament_ids": "GFG99",\n        "filament_map": "1",\n        "filament_map_2": "0",\n        "filament_nozzle_map": "0",\n        "extruder_ams_count": "1#0|4#0;",\n        "physical_extruder_map": "0",\n        "enable_prime_tower": "0",\n        "prime_tower_enable_framework": "0",\n    }\n    cfg_a = g.find("; CONFIG_BLOCK_START")\n    cfg_b = g.find("; CONFIG_BLOCK_END")\n    if cfg_a < 0 or cfg_b <= cfg_a:\n        raise RuntimeError("V1.98 ORCA REFERENCE AUDIT: CONFIG_BLOCK missing")\n    cfg_text = g[cfg_a:cfg_b]\n    if "H2C" in cfg_text:\n        raise RuntimeError("V1.98 ORCA REFERENCE AUDIT: H2C G-code config metadata survived")\n    for key, expected in config_expect.items():\n        m = re.search(rf"^; {re.escape(key)} = (.*)$", cfg_text, re.M)\n        if not m or m.group(1) != expected:\n            raise RuntimeError(\n                f"V1.98 ORCA REFERENCE AUDIT: G-code config {key}={m.group(1) if m else None!r}, expected {expected!r}"\n            )\n    if re.search(r"^; raft_first_layer_expansion = -", cfg_text, re.M):\n        raise RuntimeError("V1.98 ORCA REFERENCE AUDIT: invalid negative raft_first_layer_expansion survived")\n    for key, expected in (("filament", "1"), ("filament_density", "1.27"), ("filament_diameter", "1.75")):\n        m = re.search(rf"^; {re.escape(key)}:\\s*(.*)$", g, re.M)\n        if not m or m.group(1).strip() != expected:\n            raise RuntimeError(f"V1.98 ORCA REFERENCE AUDIT: header {key}={m.group(1) if m else None!r}")\n\n    header = slice_root.find("header")\n    h = {n.attrib.get("key"): n.attrib.get("value") for n in header.findall("header_item")} if header is not None else {}\n    if h.get("X-BBL-Client-Version") != "02.08.01.55" or h.get("OrcaSlicer-Version") != "2.5.0-dev":\n        raise RuntimeError(f"V1.98 ORCA REFERENCE AUDIT: slice header {h}")\n    p = slice_root.find("plate")\n    if p is None:\n        raise RuntimeError("V1.98 ORCA REFERENCE AUDIT: slice plate missing")\n    meta = {n.attrib.get("key"): n.attrib.get("value") for n in p.findall("metadata")}\n    if meta.get("printer_model_id") != "N1" or meta.get("nozzle_diameters") != "0.4" or meta.get("has_filament_switcher") != "false" or meta.get("filament_maps") != "1":\n        raise RuntimeError(f"V1.98 ORCA REFERENCE AUDIT: slice metadata {meta}")\n    fil = [n.attrib for n in p.findall("filament")]\n    if len(fil) != 1 or fil[0].get("id") != "1" or fil[0].get("type") != "PETG" or fil[0].get("color") != "#000000" or fil[0].get("group_id") != "0":\n        raise RuntimeError(f"V1.98 ORCA REFERENCE AUDIT: slice filament {fil}")\n    nozzles = [n.attrib for n in p.findall("nozzle")]\n    if nozzles != [{"id": "0", "extruder_id": "1", "nozzle_diameter": "0.4", "volume_type": "Standard"}]:\n        raise RuntimeError(f"V1.98 ORCA REFERENCE AUDIT: slice nozzle {nozzles}")\n    if seq != {"plate_1": {"nozzle_sequence": [0], "optimal_assignment": [0], "sequence": [1]}}:\n        raise RuntimeError(f"V1.98 ORCA REFERENCE AUDIT: filament sequence {seq}")\n    if plate.get("bed_type") != "textured_plate" or plate.get("filament_colors") != ["#000000"] or plate.get("filament_ids") != [0] or plate.get("first_extruder") != 0:\n        raise RuntimeError(f"V1.98 ORCA REFERENCE AUDIT: plate JSON mapping {plate.get(\'bed_type\')!r}/{plate.get(\'filament_colors\')!r}/{plate.get(\'filament_ids\')!r}/{plate.get(\'first_extruder\')!r}")\n    ms_plate = model_settings.find("plate")\n    ms = {n.attrib.get("key"): n.attrib.get("value") for n in ms_plate.findall("metadata")} if ms_plate is not None else {}\n    if ms.get("filament_maps") != "1" or ms.get("filament_volume_maps") != "0":\n        raise RuntimeError(f"V1.98 ORCA REFERENCE AUDIT: model_settings filament maps {ms}")\n    if \'<metadata name="Application">BambuStudio-02.08.01.55</metadata>\' not in model_text or \'<metadata name="OrcaSlicer">2.5.0-dev</metadata>\' not in model_text:\n        raise RuntimeError("V1.98 ORCA REFERENCE AUDIT: native Orca 3MF identity metadata missing")\n    actual_md5 = hashlib.md5(gbytes).hexdigest()\n    if actual_md5 != md5:\n        raise RuntimeError(f"V1.98 ORCA REFERENCE AUDIT: MD5 {md5} != {actual_md5}")\n    return {\n        "reference": "working Orca 2.5.0 A1 Mini PETG cube",\n        "printer": "Bambu Lab A1 mini 0.4 nozzle",\n        "filament": "Generic PETG / black / external spool",\n        "ams": False,\n        "filament_sequence": [1],\n        "nozzle_sequence": [0],\n        "ensure_vertical_shell_thickness": "ensure_all",\n        "raft_first_layer_expansion": 2,\n        "orca_3mf_metadata": "2.5.0-dev",\n        "gcode_md5": actual_md5,\n    }\n'


def _base_wrapper_path() -> Path:
    here = Path(__file__).resolve()
    current_tag = f"v1.{REVISION:02d}"
    base_tag = f"v1.{BASE_REVISION:02d}"
    if current_tag not in here.name:
        raise RuntimeError(f"{SCRIPT_VERSION}: filename must contain {current_tag}: {here.name}")
    base = here.with_name(here.name.replace(current_tag, base_tag, 1))
    if not base.exists():
        raise FileNotFoundError(
            f"{SCRIPT_VERSION}: required known base wrapper not found beside this file: {base.name}"
        )
    return base



def _replace_function(source: str, name: str, replacement: str) -> str:
    tree = ast.parse(source)
    matches = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if len(matches) != 1:
        raise RuntimeError(f"{SCRIPT_VERSION}: expected exactly one top-level function {name}, found {len(matches)}")
    node = matches[0]
    lines = source.splitlines(keepends=True)
    start = node.lineno - 1
    end = node.end_lineno
    replacement_text = replacement.rstrip() + "\n\n"
    return "".join(lines[:start]) + replacement_text + "".join(lines[end:])


def _literal_assignments(source: str) -> Dict[str, object]:
    tree = ast.parse(source)
    out: Dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value_node = node.value
            for target in targets:
                if isinstance(target, ast.Name):
                    try:
                        out[target.id] = ast.literal_eval(value_node)
                    except Exception:
                        pass
    return out


def _upgrade_source(predecessor_source: str) -> str:
    base_values = _literal_assignments(predecessor_source)
    actual_base_version = base_values.get("SCRIPT_VERSION")
    if actual_base_version != BASE_SCRIPT_VERSION:
        raise RuntimeError(
            f"{SCRIPT_VERSION}: expected base {BASE_SCRIPT_VERSION!r}, got {actual_base_version!r}"
        )

    old_dotted = f"v1.{BASE_REVISION:02d}"
    new_dotted = f"v1.{REVISION:02d}"
    old_upper = f"V1{BASE_REVISION:02d}"
    new_upper = f"V1{REVISION:02d}"
    old_lower = f"v1{BASE_REVISION:02d}"
    new_lower = f"v1{REVISION:02d}"

    source = predecessor_source
    for old, new in ((old_dotted, new_dotted), (old_upper, new_upper), (old_lower, new_lower)):
        source = source.replace(old, new)

    source = re.sub(
        r'(?m)^(\s*REAR_VERSION_TEXT\s*=\s*)"\d+"\s*$',
        rf'\1"{REVISION}"',
        source,
        count=1,
    )
    # The predecessor carried an older dry-validation message despite its own revision.
    source = re.sub(
        r"DRY V1\.\d+ VALIDATION: PASS",
        f"DRY V1.{REVISION:02d} VALIDATION: PASS",
        source,
    )

    source = _replace_function(source, "apply_dynamic_tower_policy", NEW_TOWER_POLICY)
    source = _replace_function(source, "_strip_prime_tower_blocks", NEW_CONVERTER_TOWER_AUDIT)
    source = _replace_function(source, "_replace_config_comment", NEW_REPLACE_CONFIG_COMMENT)
    source = _replace_function(source, "_a1mini_start_gcode", NEW_A1_START)
    source = _replace_function(source, "_a1mini_end_gcode", NEW_A1_END)
    source = _replace_function(source, "audit_a1mini_orca_package", NEW_A1_AUDIT)

    # Add the native Orca/A1 metadata normalizer and audit to the transformed module.
    source = source.rstrip() + "\n\n" + NEW_REFERENCE_METADATA_NORMALIZER.rstrip() + "\n\n" + NEW_REFERENCE_METADATA_AUDIT.rstrip() + "\n"
    old_main = '    reports["a1mini_package"] = convert_package_to_a1mini_orca(known.output)\n    reports["slicer_target_metadata"] = apply_slicer_target_metadata(known.output, known.slicer_target)\n    reports["a1mini_final"] = audit_a1mini_orca_package(known.output)'
    new_main = '    reports["a1mini_package"] = convert_package_to_a1mini_orca(known.output)\n    reports["a1mini_reference_metadata"] = normalize_a1mini_orca_reference_metadata(known.output)\n    reports["slicer_target_metadata"] = apply_slicer_target_metadata(known.output, known.slicer_target)\n    reports["a1mini_final"] = audit_a1mini_orca_package(known.output)\n    reports["a1mini_reference_final"] = audit_a1mini_orca_reference_metadata(known.output)'
    if old_main not in source:
        raise RuntimeError(f"{SCRIPT_VERSION}: main A1 metadata call sequence target not found")
    source = source.replace(old_main, new_main, 1)
    source = source.replace(
        '"card_geometry", "a1mini_package", "slicer_target_metadata", "a1mini_final"):',
        '"card_geometry", "a1mini_package", "a1mini_reference_metadata", "slicer_target_metadata", "a1mini_final", "a1mini_reference_final"):',
        1,
    )

    # Stale predecessor sweep is fail-closed.
    stale = [tok for tok in (old_dotted, old_upper, old_lower) if tok in source]
    if stale:
        raise RuntimeError(f"{SCRIPT_VERSION}: stale predecessor version token(s) survived: {stale}")

    values = _literal_assignments(source)
    required_values = {
        "SCRIPT_VERSION": SCRIPT_VERSION,
        "REAR_VERSION_TEXT": str(REVISION),
        "A_INNER_NOMINAL_HEIGHT_MM": 0.080,
        "A_MAIN_NOMINAL_HEIGHT_MM": 0.140,
        "A_REPRIME_MM": 0.395,
        "A_RETRACT_MM": 0.400,
        "A_ENDPOINT_DRY_TAIL_MM": 0.160,
        "A_BOND_Z_SHIFTS_MM": (-0.025, -0.020, -0.015, -0.010, -0.005, 0.000),
        "A_BOND_PACK_COUNT": 6,
        "B_ENABLED": False,
    }
    for key, expected in required_values.items():
        actual = values.get(key)
        if actual != expected:
            raise RuntimeError(
                f"{SCRIPT_VERSION}: preserved geometry/pressure contract failed for {key}: "
                f"actual={actual!r}, expected={expected!r}"
            )

    compile(source, f"<{SCRIPT_VERSION}-transformed>", "exec")
    return source


def _extract_function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    matches = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(matches) != 1:
        raise RuntimeError(f"self-test: expected one {name}, found {len(matches)}")
    node = matches[0]
    lines = source.splitlines(keepends=True)
    return "".join(lines[node.lineno - 1:node.end_lineno])


def _zip_replace_for_test(path: Path, replacements: Dict[str, bytes]) -> None:
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with zipfile.ZipFile(path, "r") as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        seen = set()
        for info in zin.infolist():
            data = replacements.get(info.filename, zin.read(info.filename))
            if info.filename in replacements:
                seen.add(info.filename)
            zout.writestr(info, data)
        missing = set(replacements) - seen
        if missing:
            raise RuntimeError(f"self-test package missing {sorted(missing)}")
    os.replace(tmp, path)


def _synthetic_tower_gcode(exit_mode: str = "same_tool", tower_count: int = 1) -> str:
    """Synthetic topology copied from actual v1.179 tower exits.

    same_tool mirrors the real V152/V124 no-post-wipe sequence observed in
    generated FC3D G-code. tool_change adds the optional PPSPV47 post wipe.
    """
    if exit_mode not in {"same_tool", "tool_change"}:
        raise ValueError(exit_mode)
    if tower_count < 1:
        raise ValueError(tower_count)
    rows = [
        "; FC3D_V169_JOB_ACTIVE_MATERIALS W",
        "; EXECUTABLE_BLOCK_START",
    ]
    for idx in range(tower_count):
        z = 0.280 + idx * 0.280
        hop = z + 0.900
        rows += [
            "; CHANGE_LAYER",
            f"; DIRECT_LAYER V4 physical={idx} z={z:.3f}",
            "G1 E-0.400 F1800 ; layer enters retracted",
            START_MARKER + " W",
            "; PRIME_TOWER_PPV64_CONTINUOUS_STUDIO_X",
            "; FEATURE: DIRECT_SOLID_PRIME_TOWER_V57",
            f"G1 X194.500 Y{227.800 + idx:.3f} E0.100 F1200",
            "; FC3D_TOWER_SLOT 0",
            "; FC3D_V150_TOWER_PRESSURE_STATE state=RETRACTED reason=main_tower_extrusion_complete",
            END_MARKER,
        ]
        if exit_mode == "tool_change":
            rows += [
                "; WIPE_START FC3D_PPSPV47_POST_TOWER_SAFE_LIFTED",
                "; FC3D_V150_TOWER_PRESSURE_STATE state=RETRACTED reason=tower_print_stop",
                "G1 F48000",
                f"G1 Z{hop:.3f} F60000 ; PPSPV62 lift after immediate tower retract",
                f"G1 X136.500 Y{234.400 + idx:.3f} F48000 ; FC3D_V150 lifted post-tower wipe while already retracted",
                "; FC3D_V150_TOWER_PRESSURE_STATE state=RETRACTED reason=post_tower_wipe_complete",
                "; WIPE_END FC3D_PPSPV47_POST_TOWER_SAFE_LIFTED",
                "; FC3D_PPSPV47_TOWER_EXIT_ALREADY_LIFTED_NEXT_TRAVEL_SAFE",
            ]
        else:
            rows += [
                "; FC3D_V152_RETRACT_NOOP state=0 original=G1 E-0.40000 F1800 ; FC3D_V124_TOWER_EXIT_PRESSURE_ISOLATION_RETRACT",
            ]
        model_y = 40.0 + idx * 20.0
        rows += [
            "; FEATURE: DIRECT_DETERMINISTIC_ROADS_W",
            "; LINE_WIDTH: 0.400",
            "M204 S500",
            "G1 F6300",
            "; FC3D_RASTER_SCANLINE_DIRECTION mode=serpentine reverse=0 fixed=40.000",
            f"; FC3D_PPSPV62_STUDIO_SAFE_VERTICAL_CHECKED_HOP reason=LOCAL_RASTER hop=0.900",
            f"G1 X135.500 Y{227.800 + idx:.3f} Z{hop:.3f} F60000",
            f"G1 X54.400 Y{model_y:.3f} Z{hop:.3f} F60000",
            f"G1 X54.400 Y{model_y:.3f} Z{z:.3f} F6000",
            "G1 E0.400 F1800 ; prime model",
            f"G1 X70.000 Y{model_y:.3f} E0.200 F1200",
        ]
    rows += ["; V4_MODEL_END", ""]
    return "\n".join(rows)






def _synthetic_scheduler_tower_gcode(include_primary: bool = True, include_secondary: bool = True) -> str:
    """Model v1.179 complete_same_layer_scheduler_tower output around a real model hop."""
    rows = [
        "; FC3D_V169_JOB_ACTIVE_MATERIALS W",
        "; CHANGE_LAYER",
        "; DIRECT_LAYER V4 physical=1 logical=1 z=0.200",
        "; FEATURE: DIRECT_DETERMINISTIC_ROADS_W",
        "G1 X50.000 Y40.000 Z0.200 F60000",
        "G1 E0.400 F1800",
        "G1 X70.000 Y40.000 E0.200 F15000",
        "G1 E-0.400 F1800",
    ]
    if include_primary:
        rows += [
            "; FC3D_TOWER_PRIMARY_STRUCTURAL_FILL material=W slot=1/1",
            "; FC3D_TOWER_SLOT material=W canonical_slot=W slot=1/1 role=primary",
            "G1 X130.000 Y228.000 Z1.100 F60000",
            "G1 E0.400 F1800",
            "G1 X145.000 Y228.000 E0.200 F15000",
            "G1 E-0.400 F1800",
        ]
    if include_secondary:
        rows += [
            "; WIPE_TOWER_START DIRECT_SOLID_V156_SECONDARY W",
            "; FC3D_TOWER_SECONDARY_GAPS_V156 material=W slot=1/1 role=secondary_fill prime=0 connector_policy=isolated_horizontal",
            "; FC3D_TOWER_SLOT material=W canonical_slot=W slot=1/1 role=secondary_fill",
            "G1 X130.500 Y228.400 Z1.100 F60000",
            "G1 E0.400 F1800",
            "G1 X144.500 Y228.400 E0.180 F15000",
            "G1 E-0.400 F1800",
            "; WIPE_TOWER_END DIRECT_SOLID_V156_SECONDARY",
        ]
    rows += [
        "; FC3D_TOWER_LAYER_COMPLETE_V129 primary_used=none secondary_used=none slots=W",
        "; FEATURE: DIRECT_DETERMINISTIC_ROADS_W",
        "M204 S500",
        "G1 F6300",
        "G1 Z1.100 F6000 ; safe Z-only layer/tower clearance is allowed before checked hop",
        "; FC3D_PPSPV62_STUDIO_SAFE_VERTICAL_CHECKED_HOP reason=LOCAL_RASTER hop=0.900",
        "G1 X145.000 Y228.400 Z1.100 F60000",
        "G1 X54.400 Y60.000 Z1.100 F60000",
        "G1 X54.400 Y60.000 Z0.200 F6000",
        "G1 E0.400 F1800",
        "G1 X70.000 Y60.000 E0.200 F15000",
        "; V4_MODEL_END",
        "",
    ]
    return "\n".join(rows)

def _run_tower_function(function_source: str, gcode_text: str):
    with tempfile.TemporaryDirectory(prefix="fc3d_v198_regression_") as td:
        package = Path(td) / "test.gcode.3mf"
        with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("Metadata/plate_1.gcode", gcode_text.encode("utf-8"))
        ns = {
            "Path": Path,
            "re": re,
            "zipfile": zipfile,
            "_replace_zip_members": _zip_replace_for_test,
        }
        exec(compile(function_source, "<tower-policy-self-test>", "exec"), ns)
        report = ns["apply_dynamic_tower_policy"](package)
        with zipfile.ZipFile(package, "r") as z:
            output = z.read("Metadata/plate_1.gcode").decode("utf-8")
        return output, report



def _run_regression_tests(predecessor_source: str, transformed_source: str) -> None:
    # RED: the known v1.91 policy deletes from the inner tower feature and leaves
    # an orphan outer START on the real same-tool/no-post topology.
    predecessor_fn = _extract_function_source(predecessor_source, "apply_dynamic_tower_policy")
    same_one = _synthetic_tower_gcode("same_tool", 1)
    predecessor_out, _ = _run_tower_function(predecessor_fn, same_one)
    if START_MARKER not in predecessor_out or END_MARKER in predecessor_out:
        raise RuntimeError(
            f"{SCRIPT_VERSION}: red regression did not reproduce the v1.91 orphan-START topology"
        )

    fixed_fn = _extract_function_source(transformed_source, "apply_dynamic_tower_policy")

    # RED/GREEN previous-revision regression: a standalone exact FC3D_TOWER_SLOT comment can
    # survive after its owning tower geometry has already been removed.  It is
    # commentary only and must be scrubbed without consuming neighbouring model motion.
    standalone_fixture = _synthetic_tower_gcode("same_tool", 1).replace(
        "; V4_MODEL_END",
        "; FC3D_TOWER_SLOT material=W canonical_slot=W slot=1/1 role=audit_commentary\n; V4_MODEL_END",
        1,
    )
    fixed_standalone, standalone_report = _run_tower_function(fixed_fn, standalone_fixture)
    if standalone_report.get("removed_standalone_slot_comments") != 1:
        raise RuntimeError(f"{SCRIPT_VERSION}: standalone slot commentary was not removed: {standalone_report}")
    if re.search(r"^\s*;\s*FC3D_TOWER_SLOT(?:\s|$)", fixed_standalone, re.M):
        raise RuntimeError(f"{SCRIPT_VERSION}: standalone FC3D_TOWER_SLOT marker survived")
    if "G1 X54.400 Y40.000 Z1.180 F60000" not in fixed_standalone:
        raise RuntimeError(f"{SCRIPT_VERSION}: standalone-slot scrub damaged neighbouring model motion")

    # GREEN scheduler ownership: v1.179 can emit a primary structural tower fill
    # without WIPE_TOWER delimiters, then V156 secondary blocks.  Remove the
    # whole owned completion region; do not merely scrub FC3D_TOWER_SLOT.
    fixed_sched, sched_report = _run_tower_function(
        fixed_fn, _synthetic_scheduler_tower_gcode(True, True)
    )
    if sched_report.get("removed_scheduler_primary_fill_groups") != 1:
        raise RuntimeError(f"{SCRIPT_VERSION}: scheduler primary group was not removed: {sched_report}")
    if sched_report.get("original_tower_block_ids", {}).get("DIRECT_SOLID_V156_SECONDARY") != 1:
        raise RuntimeError(f"{SCRIPT_VERSION}: V156 scheduler block was not recognised: {sched_report}")
    if sched_report.get("sanitized_tower_exit_hops") != 1:
        raise RuntimeError(f"{SCRIPT_VERSION}: scheduler exit hop was not sanitized: {sched_report}")
    for token in (
        "FC3D_TOWER_PRIMARY_STRUCTURAL_FILL",
        "FC3D_TOWER_SLOT",
        "FC3D_TOWER_SECONDARY_GAPS_V156",
        "DIRECT_SOLID_V156_SECONDARY",
        "X145.000 Y228.400 Z1.100",
    ):
        if token in fixed_sched:
            raise RuntimeError(f"{SCRIPT_VERSION}: scheduler regression leaked {token!r}")
    if "G1 Z1.100 F6000 ; safe Z-only layer/tower clearance is allowed before checked hop" not in fixed_sched:
        raise RuntimeError(f"{SCRIPT_VERSION}: scheduler regression removed a safe Z-only move")
    if "G1 X54.400 Y60.000 Z1.100 F60000" not in fixed_sched:
        raise RuntimeError(f"{SCRIPT_VERSION}: scheduler regression damaged real model XY")

    # V156-only completion is also legal when all primary slots were already used.
    fixed_secondary, secondary_report = _run_tower_function(
        fixed_fn, _synthetic_scheduler_tower_gcode(False, True)
    )
    if secondary_report.get("removed_tower_blocks") != 1 or secondary_report.get("sanitized_tower_exit_hops") != 1:
        raise RuntimeError(f"{SCRIPT_VERSION}: V156-only scheduler regression wrong: {secondary_report}")
    if "FC3D_TOWER_SLOT" in fixed_secondary or "DIRECT_SOLID_V156_SECONDARY" in fixed_secondary:
        raise RuntimeError(f"{SCRIPT_VERSION}: V156-only scheduler tower survived")

    # An undelimited primary fill without the authoritative completion marker is
    # unknown ownership and must fail closed before model/layer content can be lost.
    malformed_scheduler = _synthetic_scheduler_tower_gcode(True, False).replace(
        "; FC3D_TOWER_LAYER_COMPLETE_V129 primary_used=none secondary_used=none slots=W",
        "; deliberately missing scheduler completion marker",
        1,
    )
    try:
        _run_tower_function(fixed_fn, malformed_scheduler)
    except RuntimeError as exc:
        if "scheduler primary fill reached model/layer boundary" not in str(exc) and "unterminated scheduler" not in str(exc):
            raise
    else:
        raise RuntimeError(f"{SCRIPT_VERSION}: malformed scheduler primary fill was accepted")

    # GREEN A: exact real failure class: two towers: two towers,
    # zero post-wipes. Both towers must be removed and both stale hops sanitized.
    fixed_same, same_report = _run_tower_function(
        fixed_fn, _synthetic_tower_gcode("same_tool", 2)
    )
    if same_report.get("original_tower_blocks") != 2 or same_report.get("original_post_tower_wipes") != 0:
        raise RuntimeError(f"{SCRIPT_VERSION}: same-tool regression topology report wrong: {same_report}")
    if same_report.get("sanitized_tower_exit_hops") != 2:
        raise RuntimeError(f"{SCRIPT_VERSION}: same-tool regression did not sanitize two exits: {same_report}")
    for token in (START_MARKER, END_MARKER, "DIRECT_SOLID_PRIME_TOWER_V57", "Y227.800 Z1.180", "Y228.800 Z1.460"):
        if token in fixed_same:
            raise RuntimeError(f"{SCRIPT_VERSION}: same-tool green regression leaked {token!r}")
    if fixed_same.count("FC3D_V198_TOWER_EXIT_HOP_SANITIZED_Z_ONLY") != 2:
        raise RuntimeError(f"{SCRIPT_VERSION}: same-tool green regression Z-only count wrong")
    if "FC3D_V152_RETRACT_NOOP" not in fixed_same:
        raise RuntimeError(f"{SCRIPT_VERSION}: same-tool green regression removed pressure-state NOOP comment")
    if "G1 X54.400 Y40.000 Z1.180 F60000" not in fixed_same or "G1 X54.400 Y60.000 Z1.460 F60000" not in fixed_same:
        raise RuntimeError(f"{SCRIPT_VERSION}: same-tool green regression damaged real model safe-Z travels")

    # GREEN B: tool-change exit has the optional post-tower wipe. Remove it,
    # remove its stale exit marker, then sanitize the same checked model hop.
    fixed_tool, tool_report = _run_tower_function(
        fixed_fn, _synthetic_tower_gcode("tool_change", 1)
    )
    if tool_report.get("removed_post_tower_wipes") != 1 or tool_report.get("sanitized_tower_exit_hops") != 1:
        raise RuntimeError(f"{SCRIPT_VERSION}: tool-change regression report wrong: {tool_report}")
    for token in (
        START_MARKER,
        END_MARKER,
        "FC3D_PPSPV47_POST_TOWER_SAFE_LIFTED",
        "FC3D_PPSPV47_TOWER_EXIT_ALREADY_LIFTED_NEXT_TRAVEL_SAFE",
        "X136.500 Y234.400",
        "X135.500 Y227.800 Z1.180",
    ):
        if token in fixed_tool:
            raise RuntimeError(f"{SCRIPT_VERSION}: tool-change green regression leaked {token!r}")
    if "G1 Z1.180 F60000 ; FC3D_V198_TOWER_EXIT_HOP_SANITIZED_Z_ONLY" not in fixed_tool:
        raise RuntimeError(f"{SCRIPT_VERSION}: tool-change green regression did not sanitize stale hop")
    if "G1 X54.400 Y40.000 Z1.180 F60000" not in fixed_tool:
        raise RuntimeError(f"{SCRIPT_VERSION}: tool-change green regression damaged real model travel")

    # Malformed marker topology must still fail closed.
    malformed = _synthetic_tower_gcode("same_tool", 1).replace(END_MARKER, "; deliberately missing tower end", 1)
    try:
        _run_tower_function(fixed_fn, malformed)
    except RuntimeError as exc:
        if "mismatched tower delimiters" not in str(exc) and "unterminated tower" not in str(exc):
            raise
    else:
        raise RuntimeError(f"{SCRIPT_VERSION}: malformed tower topology was accepted")




def _registered_exec(source: str, module_name: str, filename: str):
    """Execute source in a real registered module (required by dataclasses)."""
    if module_name in sys.modules:
        raise RuntimeError(f"{SCRIPT_VERSION}: runtime module name already registered: {module_name}")
    mod = types.ModuleType(module_name)
    mod.__file__ = filename
    mod.__package__ = None
    sys.modules[module_name] = mod
    try:
        exec(compile(source, filename, "exec"), mod.__dict__)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    if sys.modules.get(module_name) is not mod:
        sys.modules.pop(module_name, None)
        raise RuntimeError(f"{SCRIPT_VERSION}: runtime module registration was lost during exec")
    return mod


def _run_a1_config_and_ordering_regression_test() -> None:
    """Integration regression for config escaping and executable-only ordering."""
    import json
    import xml.etree.ElementTree as ET
    # First prove the replacement helper preserves literal backslash-n separators.
    ns = {"re": re}
    exec(compile(NEW_REPLACE_CONFIG_COMMENT, "<a1-config-replacer-test>", "exec"), ns)
    replacer = ns["_replace_config_comment"]
    original = "; machine_start_gcode = old\n; CONFIG_BLOCK_END\n"
    value = "; FC3D_V198_A1MINI_START\\n; FC3D_V198_A1MINI_NOZZLE_WIPE_START\\nG29 A1 X20 Y20 I140 J140"
    patched = replacer(original, "machine_start_gcode", value)
    if len(patched.splitlines()) != 2 or patched.splitlines()[0].count("\\n") != 2:
        raise RuntimeError(
            f"{SCRIPT_VERSION}: A1 config serialization regression expanded literal \\n: {patched!r}"
        )

    # Build a complete package with deliberately misleading pre-executable marker
    # lines. The final audit must ignore them and validate only the real executable block.
    start_ns = {
        "A1_MINI_BED_C": 70,
        "A1_MINI_NOZZLE_C": 255,
        "A_RETRACT_MM": 0.400,
    }
    exec(compile(NEW_A1_START, "<a1-start-test>", "exec"), start_ns)
    start = start_ns["_a1mini_start_gcode"]()
    end_ns = {}
    exec(compile(NEW_A1_END, "<a1-end-test>", "exec"), end_ns)
    end = end_ns["_a1mini_end_gcode"](0.280)

    header = [
        "; HEADER_BLOCK_START",
        "; enable_prime_tower = 0",
        "; prime_tower_enable_framework = 0",
        # These emulate the exact namespace pollution seen in the failed revision.
        "; machine_start_gcode = ; FC3D_V198_A1MINI_START",
        "; FC3D_V198_A1MINI_NOZZLE_WIPE_START",
        "; FC3D_V198_A1MINI_NOZZLE_WIPE_END",
        "G29 A1 X20 Y20 I140 J140",
        "; FC3D_V198_A1MINI_CONDITION_START",
        "; FC3D_V198_A1MINI_CONDITION_END state=RETRACTED",
        "; CONFIG_BLOCK_END",
        "; EXECUTABLE_BLOCK_START",
    ]
    model = [
        "; CHANGE_LAYER",
        "; DIRECT_LAYER V4 physical=0 z=0.280",
        "; FEATURE: DIRECT_DETERMINISTIC_ROADS_W",
        "G1 X40.000 Y40.000 Z0.280 F6000",
        "G1 X60.000 Y40.000 E0.200 F3000",
        "; V4_MODEL_END",
    ]
    g = "\n".join(header) + "\n" + start + "\n" + "\n".join(model) + "\n" + end + "\n"
    gb = g.encode("utf-8")
    project = {
        "printer_model": "Bambu Lab A1 mini",
        "printer_settings_id": "Bambu Lab A1 mini 0.4 nozzle",
        "print_settings_id": "0.20mm Standard @BBL A1M",
        "printer_structure": "i3",
        "printable_area": ["0x0", "180x0", "180x180", "0x180"],
        "printable_height": "180",
        "nozzle_diameter": ["0.4"],
        "nozzle_type": ["stainless_steel"],
        "nozzle_volume": ["92"],
        "nozzle_volume_type": ["Standard"],
        "default_nozzle_volume_type": ["Standard"],
        "enable_prime_tower": "0",
        "prime_tower_enable_framework": "0",
        "curr_bed_type": "Textured PEI Plate",
    }
    root = ET.Element("config")
    plate = ET.SubElement(root, "plate")
    for key, value in (
        ("printer_model_id", "N1"),
        ("nozzle_diameters", "0.4"),
        ("has_filament_switcher", "false"),
    ):
        ET.SubElement(plate, "metadata", key=key, value=value)
    ET.SubElement(
        plate, "nozzle", id="0", extruder_id="1",
        nozzle_diameter="0.4", volume_type="Standard",
    )
    slice_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    audit_ns = {
        "Path": Path, "re": re, "zipfile": zipfile, "json": json,
        "ET": ET, "hashlib": hashlib,
        "A1_MINI_PRINTER_NAME": "Bambu Lab A1 mini",
        "A1_MINI_PRINTER_PRESET": "Bambu Lab A1 mini 0.4 nozzle",
        "A1_MINI_PROCESS_PRESET": "0.20mm Standard @BBL A1M",
        "A1_MINI_MODEL_ID": "N1",
        "A1_MINI_NOZZLE_C": 255,
        "A_RETRACT_MM": 0.400,
    }
    exec(compile(NEW_A1_AUDIT, "<a1-audit-test>", "exec"), audit_ns)
    with tempfile.TemporaryDirectory(prefix="fc3d_v198_a1_integration_") as td:
        package = Path(td) / "a1.gcode.3mf"
        with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("Metadata/plate_1.gcode", gb)
            z.writestr("Metadata/plate_1.gcode.md5", (hashlib.md5(gb).hexdigest() + "\n").encode("ascii"))
            z.writestr("Metadata/project_settings.config", json.dumps(project).encode("utf-8"))
            z.writestr("Metadata/slice_info.config", slice_bytes)
        report = audit_ns["audit_a1mini_orca_package"](package)
        if report.get("final_nozzle_c") != 255 or report.get("condition_xy_e_moves") != 2:
            raise RuntimeError(f"{SCRIPT_VERSION}: A1 integration regression report wrong: {report}")


def _run_runtime_module_regression_test() -> None:
    """Regression for the Python 3.14 dataclasses/sys.modules crash from the prior successor."""
    probe_source = """from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class RuntimeProbe:
    value: int = 7
"""
    module_name = "__fc3d_alr_v198_dataclass_probe__"
    mod = _registered_exec(probe_source, module_name, "<v198-dataclass-probe>")
    try:
        obj = mod.RuntimeProbe()
        if obj.value != 7 or sys.modules.get(module_name) is not mod:
            raise RuntimeError(f"{SCRIPT_VERSION}: dataclass runtime registration regression failed")
    finally:
        sys.modules.pop(module_name, None)


def _install_runtime_guards(runtime) -> None:
    """Add fail-closed checks around inherited audits without changing geometry."""
    inherited = runtime.__dict__.get("audit_final_mirror_wave_paths")
    if callable(inherited):
        def v198_geometry_guard(*args, **kwargs):
            report = inherited(*args, **kwargs)
            piece = runtime.__dict__.get("CURRENT_PIECE")
            piece_name = getattr(piece, "name", None)
            if piece_name == "1-2":
                got = report.get("a_pairs") if isinstance(report, dict) else None
                if got != 251:
                    raise RuntimeError(
                        f"V1.98 GEOMETRY GUARD: piece 1-2 A-pair count {got!r} != 251"
                    )
            return report
        runtime.__dict__["audit_final_mirror_wave_paths"] = v198_geometry_guard


def _run_geometry_guard_regression_test() -> None:
    """Prove the guard passes 251 and rejects drift for piece 1-2."""
    class Piece:
        name = "1-2"
    good = types.SimpleNamespace(
        CURRENT_PIECE=Piece(),
        audit_final_mirror_wave_paths=lambda *a, **k: {"a_pairs": 251},
    )
    _install_runtime_guards(good)
    if good.audit_final_mirror_wave_paths().get("a_pairs") != 251:
        raise RuntimeError(f"{SCRIPT_VERSION}: geometry guard good-path regression failed")

    bad = types.SimpleNamespace(
        CURRENT_PIECE=Piece(),
        audit_final_mirror_wave_paths=lambda *a, **k: {"a_pairs": 250},
    )
    _install_runtime_guards(bad)
    try:
        bad.audit_final_mirror_wave_paths()
    except RuntimeError as exc:
        if "!= 251" not in str(exc):
            raise
    else:
        raise RuntimeError(f"{SCRIPT_VERSION}: geometry guard accepted 250 A pairs")



def _run_reference_metadata_template_regression_test() -> None:
    import base64, zlib, json
    # Extract the production helper constants from its source rather than carrying
    # a second independent set of expected template bytes.
    if "working Orca 2.5.0 A1 Mini PETG cube" not in NEW_REFERENCE_METADATA_AUDIT:
        raise RuntimeError(f"{SCRIPT_VERSION}: reference metadata audit source missing provenance")
    # Production contract literals must be present in both patch and audit source.
    for token in (
        '"ensure_vertical_shell_thickness": "ensure_all"',
        '"raft_first_layer_expansion": "2"',
        '"filament_settings_id": ["Generic PETG @BBL A1M"]',
        '"filament_map": ["1"]',
        '"physical_extruder_map": ["0"]',
        '"extruder_ams_count": ["1#0|4#0", ""]',
        '<metadata name="OrcaSlicer">2.5.0-dev</metadata>',
    ):
        if token not in NEW_REFERENCE_METADATA_NORMALIZER and token not in NEW_REFERENCE_METADATA_AUDIT:
            raise RuntimeError(f"{SCRIPT_VERSION}: native reference contract token missing: {token}")

def _execute_upgraded_wrapper() -> None:
    base = _base_wrapper_path()
    base_source = base.read_text(encoding="utf-8")
    transformed = _upgrade_source(base_source)
    _run_regression_tests(base_source, transformed)
    _run_a1_config_and_ordering_regression_test()
    _run_runtime_module_regression_test()
    _run_geometry_guard_regression_test()
    _run_reference_metadata_template_regression_test()

    module_name = "__fc3d_alr_v198_runtime__"
    runtime = _registered_exec(
        transformed,
        module_name,
        str(Path(__file__).resolve()),
    )
    try:
        if runtime.__dict__.get("SCRIPT_VERSION") != SCRIPT_VERSION:
            raise RuntimeError(
                f"{SCRIPT_VERSION}: transformed module version is "
                f"{runtime.__dict__.get('SCRIPT_VERSION')!r}"
            )
        main = runtime.__dict__.get("main")
        if not callable(main):
            raise RuntimeError(f"{SCRIPT_VERSION}: transformed base has no callable main()")
        _install_runtime_guards(runtime)
        main()
    finally:
        sys.modules.pop(module_name, None)



if __name__ == "__main__":
    _execute_upgraded_wrapper()
