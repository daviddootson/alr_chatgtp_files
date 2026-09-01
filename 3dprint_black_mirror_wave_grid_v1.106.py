#!/usr/bin/env python3
"""
FC3D v1.106: A-only dual-arc bonding/profile test-card wrapper.

Builds on the established Orca-capable base/label/tower plumbing and mirror field.
This experiment removes B completely and exposes the dual-A arcs as the optical
surface while testing six progressively less-squashed bonding bands.

The current active implementation supports all 25 positions in the nominal 5x5
100-inch screen grid.  The coupon keeps the previous height but halves its width
to an 8:9 aspect ratio and remains centred inside the selected full tile. Grid
convention is column-row, with 1-1 at bottom-left.

Each card has three 0.28-mm solid black base layers. The optical construction
is A-only: each local pair uses a nominal 0.08-mm inner arc followed immediately
by its nominal 0.14-mm outer/main arc. Their lateral separation continues to be
derived from the local projector->viewer mirror tilt. Six equal radial packs test
progressively higher nozzle clearances from strong squash to nominal clearance.
Built specifically for canonical 3dprintv1.179.py and PETG BLACK slot 9/right head.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import types
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Sequence, Tuple

import numpy as np
from PIL import Image

SCRIPT_VERSION = "3dprint_black_mirror_wave_grid_v1.106"
EXPECTED_DP_VERSION = "3dprintv1.179"
DEFAULT_SLICER_TARGET = "orca"
ORCA_PRODUCER_VERSION = "2.5.0-dev"
PANEL_COUNT = 1

PANEL_WIDTH_X_MM = 110.69009321481777  # v1.106 8:9 coupon; exact master crop is set below
PANEL_Y_OFFSET_MM = 0.0
PANEL_COUNT = 1

LAYER_H_MM = 0.10
PHYSICAL_LAYER_COUNT = 1245
DIRECT_OPTICAL_LAYER_COUNT = PHYSICAL_LAYER_COUNT - 1
PANEL_HEIGHT_Z_MM = PHYSICAL_LAYER_COUNT * LAYER_H_MM

ROAD_WIDTH_MM = 0.40
OUTGOING_FLOW_MULT = 1.00
RETURN_FLOW_MULT = 1.00
REAR_LAND_FLOW_MULT = 1.00
RETURN_ANGLE_DEG = 75.0
DEFAULT_E_PER_MM = 0.01567
CALIBRATED_E_PER_MM = DEFAULT_E_PER_MM
FIRST_MODEL_LAYER_SPEED_MM_S = 50.0
FIRST_MODEL_LAYER_FEED_MM_MIN = int(round(FIRST_MODEL_LAYER_SPEED_MM_S * 60.0))
FIRST_MODEL_LAYER_FLOW_MULT = 1.00
MODEL_G29_BASELINE_MM = -0.020
SOURCE_TEXTURED_PEI_BASELINE_MM = -0.020

# Known-good native Bambu Studio cube process, measured from emitted G-code.
REFERENCE_FIRST_WALL_FEED_MM_MIN = 3000.0      # 50.000 mm/s
REFERENCE_FIRST_FILL_FEED_MM_MIN = 6300.0      # 105.000 mm/s
REFERENCE_LATER_WALL_FEED_MM_MIN = 7564.994    # 126.083 mm/s, flow-limited
REFERENCE_LATER_FILL_FEED_MM_MIN = 7543.943    # 125.732 mm/s, flow-limited
REFERENCE_FIRST_ACCEL_MM_S2 = 500
REFERENCE_LATER_WALL_ACCEL_MM_S2 = 5000
REFERENCE_LATER_FILL_ACCEL_MM_S2 = 8000
REFERENCE_NOZZLE_C = 255
REFERENCE_BED_C = 70
MIN_MODEL_PART_FAN_PWM = 128  # 50.2% part cooling throughout model

# Optical/backbone geometry. The 0.50-mm bottom peak sets the useful optical
# facet size. The deepest (top-screen) tip is kept one half-road from the front
# physical edge. The rear-anchor plane is then placed behind it, and the first
# backbone road remains exactly one 0.40-mm road-width centre-to-centre behind
# that anchor so the beads touch/fuse in the same way as adjacent lines.
BOTTOM_TIP_DEPTH_MM = 0.500
MIN_TOP_REAR_LAND_MM = 0.200
FRONT_TIP_MIN_CENTRE_Y_MM = ROAD_WIDTH_MM / 2.0
BACKBONE_REAR_MARGIN_FROM_ANCHOR_MM = 1.850  # preserve v1.40 rear extent
BACKBONE_DEPTH_Y_MM = BACKBONE_REAR_MARGIN_FROM_ANCHOR_MM
BACKBONE_OVERLAP_MM = 0.0  # legacy report field; anchor itself is the interface

# Viewer-aware full-screen geometry assumptions used to calculate the default
# bottom/top representative surface normals.
FULL_SCREEN_HEIGHT_MM = 1245.0
PROJECTOR_DISTANCE_MM = 24.0 * 25.4
PROJECTOR_BELOW_SCREEN_MM = 18.0 * 25.4
VIEWER_DISTANCE_MM = 3000.0
VIEWER_EYELINE_Z_MM = FULL_SCREEN_HEIGHT_MM / 3.0

# Positive facet tilt magnitude from the nominal screen plane. For a screen
# point at height z, the surface normal/facet tilt is the half-angle bisector
# between the incoming projector ray and outgoing viewer ray.
BOTTOM_ANGLE_DEFAULT_DEG = 0.5 * math.degrees(
    math.atan2(PROJECTOR_BELOW_SCREEN_MM + 0.0, PROJECTOR_DISTANCE_MM)
    - math.atan2(VIEWER_EYELINE_Z_MM - 0.0, VIEWER_DISTANCE_MM)
)
MIDDLE_SCREEN_Z_MM = FULL_SCREEN_HEIGHT_MM / 2.0
MIDDLE_ANGLE_DEFAULT_DEG = 0.5 * math.degrees(
    math.atan2(PROJECTOR_BELOW_SCREEN_MM + MIDDLE_SCREEN_Z_MM, PROJECTOR_DISTANCE_MM)
    - math.atan2(VIEWER_EYELINE_Z_MM - MIDDLE_SCREEN_Z_MM, VIEWER_DISTANCE_MM)
)
TOP_ANGLE_DEFAULT_DEG = 0.5 * math.degrees(
    math.atan2(PROJECTOR_BELOW_SCREEN_MM + FULL_SCREEN_HEIGHT_MM, PROJECTOR_DISTANCE_MM)
    - math.atan2(VIEWER_EYELINE_Z_MM - FULL_SCREEN_HEIGHT_MM, VIEWER_DISTANCE_MM)
)

# Preserve one optical-facet X run across all three representative angles.
# Set the overall pitch from the worst-case top return plus a deliberately
# small 0.20-mm top rear land.
OPTICAL_FACET_RUN_X_MM = (
    BOTTOM_TIP_DEPTH_MM / math.tan(math.radians(BOTTOM_ANGLE_DEFAULT_DEG))
)
TOP_TIP_DEPTH_MM = OPTICAL_FACET_RUN_X_MM * math.tan(math.radians(TOP_ANGLE_DEFAULT_DEG))
TOP_RETURN_RUN_X_MM = TOP_TIP_DEPTH_MM / math.tan(math.radians(RETURN_ANGLE_DEG))
DESIGN_CONSTANT_TOOTH_PITCH_MM = (
    OPTICAL_FACET_RUN_X_MM + TOP_RETURN_RUN_X_MM + MIN_TOP_REAR_LAND_MM
)
CONSTANT_TOOTH_PITCH_MM = DESIGN_CONSTANT_TOOTH_PITCH_MM

# Shift the anchor/rear plane rearward only as much as required by the deeper
# top feature. The top tip centre remains at half a road width from the front.
OPTICAL_END_CENTRE_Y_MM = FRONT_TIP_MIN_CENTRE_Y_MM + TOP_TIP_DEPTH_MM
OPTICAL_REGION_DEPTH_Y_MM = OPTICAL_END_CENTRE_Y_MM
TOTAL_DEPTH_Y_MM = OPTICAL_END_CENTRE_Y_MM + BACKBONE_REAR_MARGIN_FROM_ANCHOR_MM

TOTAL_X_MM = PANEL_WIDTH_X_MM
TOTAL_LAYOUT_DEPTH_Y_MM = (PANEL_COUNT - 1) * PANEL_Y_OFFSET_MM + TOTAL_DEPTH_Y_MM
RP_PITCH_MM = ROAD_WIDTH_MM
STACK_W = int(round(TOTAL_X_MM / RP_PITCH_MM))
STACK_H = int(math.ceil(TOTAL_LAYOUT_DEPTH_Y_MM / RP_PITCH_MM))

BLACK_SLOT_ONE_BASED = 9
BLACK_RAW_TOOL = 8
BLACK_NAME = "BLACK"
BLACK_HEX = "#161616"
BLACK_ASSIGNMENT = "PETG:BLACK"
CYAN_LOGICAL_MATERIAL = "C"
CYAN_ASSIGNMENT = "PETG:C"

LOGICAL_MATERIAL = "W"  # logical W is deliberately remapped to physical PETG BLACK
PROTECTED_UNDERLYING_OPTIONS = {
    "--card", "--image", "--direct-layer-images", "--direct-layout",
    "--output", "--rp-pitch-mm", "--print-width-mm", "--endpoint-trim-mm",
    "--close-gaps-mm", "--directional-block-mm", "--edge-aa",
    "--skip-absent-layer-materials", "--tool-map-json",
    "--filament-assignment-json",
}


def reject_protected_passthrough(args: Sequence[str]) -> None:
    for token in args:
        opt = token.split("=", 1)[0]
        if opt in PROTECTED_UNDERLYING_OPTIONS:
            raise RuntimeError(
                f"{opt} is controlled by {SCRIPT_VERSION} and cannot be "
                "overridden through passthrough arguments."
            )


def _patch_emitter_source_for_v1106(source_text: str) -> str:
    # Wrapper-local v1.179 patch: mixed-material physical base and label-only tower lifecycle.
    base_old = '''        if physical == 0:
            output_material_order = ["W"]
            active=["W"]
            material_order=["W"]
            present_materials=["W"]
            carryover_hit=False
            tower_slot_count=1
            tower_slot_order=["W"]
            filler_slots=0
            if args.material_order != "canonical" or ppspv57_draw_mode != "fixed":
                g.append("; MATERIAL_ORDER_OVERRIDE_IGNORED_PPV64_BASE_W_ONLY requested=" + str(args.material_order) + " draw_mode=" + str(ppspv57_draw_mode))
            g.append("; MATERIAL_PRINT_ORDER_BASE_W_ONLY_FULL_WIDTH_TOWER W")
'''
    base_new = '''        if physical == 0:
            output_material_order = get_runtime_material_order()
            active = list(output_material_order)
            present_materials = [
                m for m in output_material_order
                if m in segs and len(segs[m]) > 0
            ]
            material_order = choose_material_print_order(
                segs,
                mode="fixed",
                base_order=output_material_order,
                previous_final=previous_layer_final_material,
                skip_absent=True,
            )
            if not material_order:
                raise RuntimeError("FC3D_V1106_BASE_MULTI_MATERIAL base has no present material")
            carryover_hit = False
            tower_slot_count = len(material_order)
            tower_slot_order = list(material_order)
            filler_slots = 0
            g.append("; FC3D_V1106_BASE_MULTI_MATERIAL present=" + ",".join(present_materials) + " order=" + ",".join(material_order))
'''
    tower_old = '''            else:
                current_xy=append_tower(
                    g, mat, active, z, lh, current_xy, span_index, tower_bbox,
                    layer_orientation=layer_orient, first_use=first_use_for_tower,
                    tower_slot_index=(visible_tower_slot_index if (job_demand_canonical_tower or ppspv57_dynamic_tower or paired_tower_mode) else None),
                    tower_slot_count=(tower_slot_count if (job_demand_canonical_tower or ppspv57_dynamic_tower or paired_tower_mode) else None),
                    tower_slot_role=(direct_pass_role if paired_tower_mode else "actual"),
                    tower_road_count=(3 if paired_tower_mode else None),
                    tower_slot_material=(mat if job_demand_canonical_tower and physical > 0 else None),
                ); tower_was_printed=True
'''
    tower_new = '''            else:
                if physical <= 1 or activation_needed:
                    current_xy=append_tower(
                        g, mat, active, z, lh, current_xy, span_index, tower_bbox,
                        layer_orientation=layer_orient, first_use=first_use_for_tower,
                        tower_slot_index=(visible_tower_slot_index if (job_demand_canonical_tower or ppspv57_dynamic_tower or paired_tower_mode) else None),
                        tower_slot_count=(tower_slot_count if (job_demand_canonical_tower or ppspv57_dynamic_tower or paired_tower_mode) else None),
                        tower_slot_role=(direct_pass_role if paired_tower_mode else "actual"),
                        tower_road_count=(3 if paired_tower_mode else None),
                        tower_slot_material=(mat if job_demand_canonical_tower and physical > 0 else None),
                    ); tower_was_printed=True
                else:
                    g.append(f"; FC3D_V1106_TOWER_DROPPED_AFTER_LABEL physical={physical} material={mat}")
'''
    filler_old = '''            seen_tools_for_tower_prime.add(current_tool)

            if job_demand_canonical_tower and physical > 0 and not scheduler_action:
'''
    filler_new = '''            seen_tools_for_tower_prime.add(current_tool)

            if job_demand_canonical_tower and physical > 0 and not scheduler_action and tower_was_printed and len(material_order) > 1:
'''
    for label, old, new in (
        ("base multi-material", base_old, base_new),
        ("tower lifecycle", tower_old, tower_new),
        ("tower filler lifecycle", filler_old, filler_new),
    ):
        count = source_text.count(old)
        if count != 1:
            raise RuntimeError(f"v1.106 fail closed: expected exactly one canonical v1.179 {label} patch target, found {count}")
        source_text = source_text.replace(old, new, 1)
    return source_text


def import_3dprint(source: Path):
    source = Path(source)
    if not source.exists():
        raise FileNotFoundError(
            f"Cannot find {source}. Put this wrapper beside "
            f"{EXPECTED_DP_VERSION}.py or pass --source with its full path."
        )

    source_text = source.read_text(encoding="utf-8")
    source_text = _patch_emitter_source_for_v1106(source_text)
    module_name = "fc3d_black_mirror_wave_v1106"
    mod = types.ModuleType(module_name)
    mod.__file__ = str(source)
    mod.__package__ = None
    sys.modules[module_name] = mod
    exec(compile(source_text, str(source), "exec"), mod.__dict__)

    version = str(getattr(mod, "PP_VERSION", getattr(mod, "SCRIPT_VERSION", "")))
    if version != EXPECTED_DP_VERSION:
        raise RuntimeError(
            f"Fail closed: wrapper expects {EXPECTED_DP_VERSION}, "
            f"but {source.name} reports {version!r}."
        )
    return mod


def _blank_segments(material_order: Sequence[str]) -> Dict[str, list]:
    out = {str(m): [] for m in material_order}
    out.setdefault(LOGICAL_MATERIAL, [])
    return out


def _panel_bounds(panel_index: int, x_origin: float) -> Tuple[float, float]:
    """All three cards share the same X span; they are separated in printer Y."""
    if panel_index not in range(PANEL_COUNT):
        raise ValueError(panel_index)
    x0 = float(x_origin)
    return x0, x0 + PANEL_WIDTH_X_MM


def _panel_y_origin(panel_index: int, y_origin: float) -> float:
    """Cards are stacked front-to-rear at 0, 20 and 40 mm in printer Y."""
    if panel_index not in range(PANEL_COUNT):
        raise ValueError(panel_index)
    return float(y_origin) + panel_index * PANEL_Y_OFFSET_MM


def optical_geometry_for_angle(angle_deg: float) -> dict:
    """Constant-pitch asymmetric louver geometry for the requested optical angle."""
    a = math.radians(float(angle_deg))
    s = math.sin(a)
    t = math.tan(a)
    if s <= 0.0 or t <= 0.0:
        raise ValueError(f"invalid optical angle {angle_deg}")

    # Preserve the viewer-corrected optical facet X run from the new
    # 0.50-mm bottom representative geometry. Set overall feature frequency
    # by shortening only the rear land while keeping the optical facet and the
    # 75-degree return law unchanged.
    run_dx = OPTICAL_FACET_RUN_X_MM
    dy = run_dx * t
    tooth_pitch = CONSTANT_TOOTH_PITCH_MM
    return_run_dx = dy / math.tan(math.radians(RETURN_ANGLE_DEG))
    rear_land_x = tooth_pitch - run_dx - return_run_dx
    if rear_land_x <= 0.0:
        raise ValueError(
            f"angle {angle_deg} leaves no rear land at {RETURN_ANGLE_DEG:.1f} deg return: "
            f"pitch={tooth_pitch:.4f} optical_run={run_dx:.4f} return_run={return_run_dx:.4f}"
        )

    y_rear = OPTICAL_END_CENTRE_Y_MM
    y_front = y_rear - dy
    if y_front < ROAD_WIDTH_MM / 2.0 - 1e-9:
        raise ValueError(
            f"angle {angle_deg} requires tip centre Y={y_front:.4f} mm, "
            "which exceeds the available front envelope"
        )

    return {
        "angle_deg": float(angle_deg),
        "facet_run_x_mm": run_dx,
        "facet_rise_y_mm": dy,
        "tip_depth_mm": dy,
        "front_tip_centre_y_mm": y_front,
        "rear_anchor_centre_y_mm": y_rear,
        "segment_length_mm": math.hypot(run_dx, dy),
        "return_angle_deg": RETURN_ANGLE_DEG,
        "return_run_x_mm": return_run_dx,
        "return_length_mm": math.hypot(return_run_dx, dy),
        "rear_land_x_mm": rear_land_x,
        "front_pitch_x_mm": tooth_pitch,
        "front_edge_gap_x_mm": max(0.0, tooth_pitch - ROAD_WIDTH_MM),
        "hook_dx_mm": 0.0,
        "hook_dy_mm": 0.0,
        "hook_length_mm": 0.0,
        "centreline_sep_perp_mm": 0.0,
        "occupied_perp_mm": ROAD_WIDTH_MM,
        "true_perp_pitch_mm": tooth_pitch,
    }

def optical_front_pitch_for_angle(angle_deg: float) -> float:
    return optical_geometry_for_angle(angle_deg)["front_pitch_x_mm"]


def _optical_segments_for_panel(
    panel_index: int,
    angle_deg: float,
    x_origin: float,
    y_origin: float,
) -> list:
    """
    Return one panel's continuous asymmetric louver source segments. Each tooth:
      rear anchor -> optical front tip -> 75-deg return -> rear land -> next anchor.
    """
    if not (1.0 <= float(angle_deg) <= 80.0):
        raise ValueError(f"optical angle must be 1..80 deg, got {angle_deg}")

    geom = optical_geometry_for_angle(angle_deg)
    tooth_pitch_x = geom["front_pitch_x_mm"]
    run_dx = geom["facet_run_x_mm"]
    return_dx = geom["return_run_x_mm"]

    panel_y0 = _panel_y_origin(panel_index, y_origin)
    y_front = panel_y0 + float(geom["front_tip_centre_y_mm"])
    y_rear = panel_y0 + float(geom["rear_anchor_centre_y_mm"])

    panel_x0, panel_x1 = _panel_bounds(panel_index, x_origin)
    half = ROAD_WIDTH_MM / 2.0
    first_anchor_x = panel_x0 + half
    last_anchor_x = panel_x1 - half - tooth_pitch_x

    roads = []
    anchor_x = first_anchor_x
    while anchor_x <= last_anchor_x + 1e-9:
        tip_x = anchor_x + run_dx
        return_foot_x = tip_x + return_dx
        next_anchor_x = anchor_x + tooth_pitch_x
        roads.append((anchor_x, y_rear, tip_x, y_front, OUTGOING_FLOW_MULT))
        roads.append((tip_x, y_front, return_foot_x, y_rear, RETURN_FLOW_MULT))
        roads.append((return_foot_x, y_rear, next_anchor_x, y_rear, REAR_LAND_FLOW_MULT))
        anchor_x = next_anchor_x

    return roads

def _emitter_optical_segments_for_panel(
    panel_index: int,
    angle_deg: float,
    x_origin: float,
    y_origin: float,
) -> list:
    """Segments intentionally handed to 3dprintv1.179.

    Exact horizontal rear lands are withheld because v1.179 diverts them into
    its axis-aligned raster planner and reorders them away from the diagonal
    optical/return pair. The final-G-code continuity pass restores each exact
    horizontal land in its intended source position.
    """
    intended = _optical_segments_for_panel(
        panel_index, angle_deg, x_origin, y_origin
    )
    if len(intended) % 3 != 0:
        raise RuntimeError(
            f"EMITTER LOUVER CONTRACT panel {panel_index}: intended count "
            f"{len(intended)} is not divisible by 3"
        )
    return [seg for i, seg in enumerate(intended) if (i % 3) != 2]

def _centres_for_filled_interval(lo: float, hi: float, nominal_spacing: float) -> list:
    half = ROAD_WIDTH_MM / 2.0
    a = float(lo) + half
    b = float(hi) - half
    if b < a:
        return [(float(lo) + float(hi)) * 0.5]
    span = b - a
    if span <= 1e-9:
        return [a]
    intervals = max(1, int(math.ceil(span / nominal_spacing)))
    step = span / intervals
    return [a + i * step for i in range(intervals + 1)]


def _backbone_segments_for_panel(
    panel_index: int,
    logical_layer: int,
    x_origin: float,
    y_origin: float,
) -> list:
    x0, x1 = _panel_bounds(panel_index, x_origin)
    half = ROAD_WIDTH_MM / 2.0

    # Rear connector centreline is at optical depth + overlap.
    # In v1.20 that is 2.15 mm relative Y, while the first backbone centreline
    # was 2.20 mm: only 0.05 mm apart, so the nozzle ran essentially through
    # the fresh rear connector and could drag the louver off the bed.
    #
    # Start the solid-backbone envelope behind the rear connector bead.
    # _centres_for_filled_interval() adds another half-road, giving a first
    # backbone centreline exactly one 0.40-mm road width behind the rear
    # connector centreline.
    panel_y0 = _panel_y_origin(panel_index, y_origin)
    rear_connector_centre_y = panel_y0 + OPTICAL_END_CENTRE_Y_MM
    y0 = rear_connector_centre_y + half
    y1 = panel_y0 + TOTAL_DEPTH_Y_MM

    # v1.43 simplification: every backbone layer runs in printer X.
    # The previous alternating Y layers created hundreds of very short
    # perpendicular roads per panel. X-only preserves the filled rear-plane
    # envelope while eliminating those start/stop-heavy micro-lines.
    roads = []
    for y in _centres_for_filled_interval(y0, y1, ROAD_WIDTH_MM):
        roads.append((x0 + half, y, x1 - half, y, 1.0))
    return roads


def make_layer_segments(
    logical_layer: int,
    bottom_angle_deg: float,
    middle_angle_deg: float,
    top_angle_deg: float,
    x_origin: float,
    y_origin: float,
    material_order: Sequence[str],
) -> Dict[str, list]:
    out = _blank_segments(material_order)

    optical = []
    for panel_index, angle_deg in enumerate((bottom_angle_deg, middle_angle_deg, top_angle_deg)):
        optical += _emitter_optical_segments_for_panel(
            panel_index, angle_deg, x_origin, y_origin
        )

    backbone = []
    for panel_index in range(PANEL_COUNT):
        backbone += _backbone_segments_for_panel(panel_index, logical_layer, x_origin, y_origin)

    # v1.26 sawtooth: always print the solid rear backbone first, then attach
    # the continuous optical sawtooth path to it.
    out[LOGICAL_MATERIAL] = backbone + optical
    return out


def _v1106_hotend_for_material(material, raw_tool, w_hotend_index):
    # H2C compatibility path: logical W is mapped to the physical BLACK spool
    # in the colour/right head. v1.106 itself is single-material.
    if str(material) == LOGICAL_MATERIAL:
        return 0
    return 1 - int(w_hotend_index)


def _make_v1106_job_material_tower_audit(original_audit):
    def audit(gcode_lines, expected_active_materials, tool_map):
        rows = [str(x) for x in gcode_lines]
        layer_re = re.compile(r";\s*DIRECT_LAYER\s+V4\s+physical=(\d+)")
        current = None
        actual_slots = {li: [] for li in range(PHYSICAL_LAYER_COUNT)}
        tower_present = {li: False for li in range(PHYSICAL_LAYER_COUNT)}
        dropped = {li: False for li in range(PHYSICAL_LAYER_COUNT)}
        for line in rows:
            m = layer_re.search(line)
            if m:
                current = int(m.group(1))
                continue
            if current is None:
                continue
            if "WIPE_TOWER_START" in line:
                tower_present[current] = True
            if "FC3D_V1106_TOWER_DROPPED_AFTER_LABEL" in line:
                dropped[current] = True
            if line.strip().startswith("; FC3D_TOWER_SLOT "):
                mm = re.search(r"canonical_slot=([WFRYGCB])\s+slot=(\d+)/(\d+)\s+role=([^\s]+)", line)
                if mm:
                    actual_slots[current].append((mm.group(1), int(mm.group(2)), int(mm.group(3)), mm.group(4)))
        if [x[0] for x in actual_slots.get(0, [])] != [LOGICAL_MATERIAL]:
            raise RuntimeError(f"v1.106 dynamic tower audit: base slots {actual_slots.get(0)} != W only")
        if [x[0] for x in actual_slots.get(1, [])] != [LOGICAL_MATERIAL]:
            raise RuntimeError(f"v1.106 dynamic tower audit: second-layer slots {actual_slots.get(1)} != W only")
        for li in range(2, PHYSICAL_LAYER_COUNT):
            if actual_slots.get(li):
                raise RuntimeError(f"v1.106 dynamic tower audit: tower slots remain on layer {li}: {actual_slots[li]}")
            if not dropped.get(li):
                raise RuntimeError(f"v1.106 dynamic tower audit: missing tower-drop marker on layer {li}")
        if not tower_present.get(0) or not tower_present.get(1) or any(tower_present.get(li) for li in range(2, PHYSICAL_LAYER_COUNT)):
            raise RuntimeError(f"v1.106 dynamic tower audit: tower presence is {tower_present}")

        # Preserve v1.179's excluded-material/lifecycle audit by giving only its
        # fixed-topology tower checker a synthetic canonical view. Actual tower
        # topology has already been checked above against the v1.106 contract.
        canonical = [m for m in ("W", "F", "R", "Y", "G", "C", "B") if m in set(expected_active_materials)]
        synthetic = []
        for line in rows:
            if line.strip().startswith("; FC3D_TOWER_SLOT "):
                continue
            synthetic.append(line)
            m = layer_re.search(line)
            if m and int(m.group(1)) > 0:
                for idx, mat in enumerate(canonical, start=1):
                    role = "actual" if idx == 1 else "filler_previous"
                    synthetic.append(
                        f"; FC3D_TOWER_SLOT material={canonical[0]} canonical_slot={mat} slot={idx}/{len(canonical)} role={role}"
                    )
        report = original_audit(synthetic, expected_active_materials, tool_map)
        report = dict(report)
        report["v1106_dynamic_tower"] = {
            "actual_slots": {str(k): v for k, v in actual_slots.items()},
            "tower_present": {str(k): bool(v) for k, v in tower_present.items()},
            "dropped": {str(k): bool(v) for k, v in dropped.items()},
        }
        return report
    return audit


def install_patches(dp, bottom_angle_deg: float, middle_angle_deg: float, top_angle_deg: float):
    if abs(float(dp.MIX_H_MM) - 0.10) > 1e-9:
        raise RuntimeError(
            f"Fail closed: imported MIX_H_MM={dp.MIX_H_MM}; expected 0.10 mm."
        )
    if abs(float(dp.BASE_H_MM) - 0.20) > 1e-9:
        raise RuntimeError(
            f"Fail closed: imported BASE_H_MM={dp.BASE_H_MM}; expected 0.20 mm."
        )

    # Register the user's physical black spool with v1.179's installed-filament
    # resolver before asking it to map logical W -> PETG:BLACK.
    # v1.2 omitted this registration, causing:
    #   "Invalid filament assignment for W: no installed PETG BLACK assignment"
    if not hasattr(dp, "PHYSICAL_FILAMENT_COLOURS"):
        raise RuntimeError("3dprint source lacks PHYSICAL_FILAMENT_COLOURS.")
    if not hasattr(dp, "INSTALLED_FILAMENT_TOOL_MAP"):
        raise RuntimeError("3dprint source lacks INSTALLED_FILAMENT_TOOL_MAP.")

    dp.PHYSICAL_FILAMENT_COLOURS[BLACK_NAME] = BLACK_HEX
    dp.INSTALLED_FILAMENT_TOOL_MAP.setdefault("petg", {})[BLACK_NAME] = BLACK_RAW_TOOL

    dp.BASE_H_MM = FIRST_LAYER_H_MM
    dp.MIX_H_MM = LAYER_H_MM

    orig_e_for_len = dp.e_for_len
    orig_m62014_audit = dp.audit_m62014_staging_clearance
    orig_v150_tower_pressure_audit = dp.audit_v150_active_tower_pressure_contract
    orig_job_material_tower_audit = dp.audit_job_material_and_tower_contract
    orig_hotend_for_material = dp.h2c_native_hotend_for_material

    def normal_pair_e_for_len(length, layer_h, line_w=None, material=None):
        lh = float(layer_h)
        lw = ROAD_WIDTH_MM if line_w is None else float(line_w)
        if abs(lh - LAYER_H_MM) <= 1e-9 and abs(lw - ROAD_WIDTH_MM) <= 1e-6:
            return max(0.0, float(length) * CALIBRATED_E_PER_MM)
        if line_w is None:
            return orig_e_for_len(length, layer_h, material=material)
        return orig_e_for_len(length, layer_h, line_w=line_w, material=material)

    dp.e_for_len = normal_pair_e_for_len

    def v1106_right_head_material_selector(material, raw_tool, w_hotend_index):
        if str(material) == LOGICAL_MATERIAL:
            return _v1106_hotend_for_material(material, raw_tool, w_hotend_index)
        return orig_hotend_for_material(material, raw_tool, w_hotend_index)

    dp.h2c_native_hotend_for_material = v1106_right_head_material_selector

    def normal_pair_orientation(logical_layer):
        # v1.43: fixed-X raster/backbone convention on every physical layer.
        return "X"

    dp.orientation = normal_pair_orientation

    def normal_pair_build_direct_layer_stack(
        layer_paths, lookup=None, direct_layout="4x2"
    ):
        layers = DIRECT_OPTICAL_LAYER_COUNT
        h = STACK_H
        w = STACK_W

        stack = np.full((h, w, layers), LOGICAL_MATERIAL, dtype="<U1")
        # v1.106 is deliberately single-material black throughout. Rear marking
        # is created by texture omissions in the first base raster, not colour.
        dose = np.ones((h, w, layers), dtype=np.float32)

        dp.PRECOMPUTED_DOSE_GRID = dose
        dp.DIRECT_OPTICAL_LAYER_COUNT = layers
        dp.PRINTABLE_RP_MASK = np.ones((h, w), dtype=bool)
        dp.DIRECT_FILTER_STACK_GRID = None
        for name in (
            "DIRECT_FILTER_DOSE_GRID",
            "DIRECT_CARRIER_HEIGHT_GRID",
            "DIRECT_ZOFFSET_HEIGHT_PROFILE_GRID",
            "DIRECT_ATOMIC_PARTITION_GRID",
        ):
            if hasattr(dp, name):
                setattr(dp, name, None)

        preview = np.full((h, w, 3), 22.0, dtype=np.float32)
        source_img = Image.new("RGB", (w, h), (22, 22, 22))
        return stack, preview, source_img

    dp.build_direct_layer_stack = normal_pair_build_direct_layer_stack

    def normal_pair_compile_layer(
        img,
        logical_layer,
        x_origin,
        y_origin,
        stack_grid=None,
        dose_grid=None,
        carrier_height_grid=None,
        zoffset_height_profile_grid=None,
        atomic_partition_grid=None,
        road_orientation=None,
        perpendicular_phase_shift_mm=0.0,
        material_road_geometry=None,
        bounded_valleys_only=False,
    ):
        return make_layer_segments(
            int(logical_layer),
            bottom_angle_deg,
            middle_angle_deg,
            top_angle_deg,
            float(x_origin),
            float(y_origin),
            getattr(dp, "MATERIAL_ORDER", ("W", "F", "R", "Y", "G", "C", "B")),
        )

    dp.compile_layer = normal_pair_compile_layer

    def single_tool_m62014_audit(lines, tower_bbox, printable_bbox, card_bbox, mode):
        rows = [str(x) for x in lines]
        full_swap_markers = [
            s for s in rows if "FC3D_PPSPV43_FULL_H2C_SWAP_START" in s
        ]
        staging_markers = [
            s for s in rows
            if "M620.14 " in s and "FC3D_PPSPV43 machine prime location" in s
        ]

        if full_swap_markers:
            return orig_m62014_audit(lines, tower_bbox, printable_bbox, card_bbox, mode)

        if staging_markers:
            raise RuntimeError(
                "Single-material normal-pair job contains FC3D toolchange staging "
                "despite zero full-H2C swap markers."
            )

        return {
            "result": "PASS_SINGLE_TOOL_NO_STAGING",
            "mode": "single-tool-no-swap",
            "points": 0,
            "minimum_tower_clearance_mm": "not-applicable",
            "minimum_card_clearance_mm": "not-applicable",
            "full_h2c_swap_markers": 0,
        }

    dp.audit_m62014_staging_clearance = single_tool_m62014_audit

    # v1.179's v1.180 tower-pressure audit is written for jobs that actually
    # emit the active-layer tower prewipe/exit blocks. This wrapper is now a
    # genuine single-material job and emits none of those blocks, so the
    # original audit's unconditional "must find at least one prewipe marker"
    # check is not applicable. Keep it fail-closed: only bypass when BOTH
    # v1.180 marker families are absent. If either family is present, run the
    # stock v1.179 audit unchanged.
    def single_material_v150_tower_pressure_audit(lines):
        rows = [str(x).strip() for x in lines]
        pre = [
            x for x in rows
            if "FC3D_V150_TOWER_PRESSURE_STATE state=RETRACTED "
               "reason=prewipe_complete_reprime_deferred" in x
        ]
        exits = [
            x for x in rows
            if x.startswith("; WIPE_START FC3D_PPSPV47_POST_TOWER_SAFE_LIFTED")
        ]
        if pre or exits:
            return orig_v150_tower_pressure_audit(lines)
        return {
            "result": "PASS_SINGLE_MATERIAL_NO_ACTIVE_TOWER_PRESSURE_BLOCKS",
            "deferred_prewipe_reprime_blocks": 0,
            "immediate_retract_exit_blocks": 0,
            "canonical_exit_retract_noops": 0,
        }

    dp.audit_v150_active_tower_pressure_contract = (
        single_material_v150_tower_pressure_audit
    )
    dp.audit_job_material_and_tower_contract = _make_v1106_job_material_tower_audit(
        orig_job_material_tower_audit
    )

    return {
        "layer_height_mm": LAYER_H_MM,
        "physical_layers": PHYSICAL_LAYER_COUNT,
        "direct_layers": DIRECT_OPTICAL_LAYER_COUNT,
        "panel_height_z_mm": PANEL_HEIGHT_Z_MM,
        "calibrated_e_per_mm": CALIBRATED_E_PER_MM,
        "bottom_angle_deg": float(bottom_angle_deg),
        "middle_angle_deg": float(middle_angle_deg),
        "top_angle_deg": float(top_angle_deg),
        "logical_material": LOGICAL_MATERIAL,
        "physical_material": "PETG BLACK",
        "slot_one_based": BLACK_SLOT_ONE_BASED,
        "raw_tool": BLACK_RAW_TOOL,
        "studio_colour": BLACK_HEX,
    }


def _replace_zip_members(path: Path, replacements: Dict[str, bytes]) -> None:
    path = Path(path)
    replacements = dict(replacements)

    # Bambu packages carry an MD5 sidecar for plate_1.gcode.  Every FC3D
    # postprocessor that changes the executable stream must keep it in sync.
    gcode_name = "Metadata/plate_1.gcode"
    md5_name = "Metadata/plate_1.gcode.md5"
    if gcode_name in replacements:
        replacements[md5_name] = (
            hashlib.md5(replacements[gcode_name]).hexdigest() + "\n"
        ).encode("ascii")

    tmp = path.with_suffix(path.suffix + ".tmp")
    with zipfile.ZipFile(path, "r") as zin, zipfile.ZipFile(
        tmp, "w", compression=zipfile.ZIP_DEFLATED
    ) as zout:
        seen = set()
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename in replacements:
                data = replacements[info.filename]
                seen.add(info.filename)
            zout.writestr(info, data)
        missing = set(replacements) - seen
        if missing:
            raise RuntimeError(
                f"Cannot patch package; missing members {sorted(missing)}"
            )
    os.replace(tmp, path)


def _find_gcode_producer_line(lines: Sequence[str]) -> int:
    for i, line in enumerate(lines[:32]):
        if line.startswith("; BambuStudio ") or line.startswith("; generated by OrcaSlicer "):
            return i
    raise RuntimeError("V1.90 SLICER TARGET: no recognised slicer producer line in G-code header")


def patch_v1106_orca_nozzle_requirement_metadata(output: Path, target: str = DEFAULT_SLICER_TARGET) -> dict:
    """Normalise the imported-previous-3MF nozzle requirement used by Orca's send dialog.

    Orca's current H2C send check derives the required nozzle flow from the
    loaded project_config ``nozzle_volume_type`` at the logical extruder index
    associated with each used filament.  Our generated job is deliberately
    confined to the physical right/colour H2C head and its 0.4-mm High Flow
    nozzle, but a previous-3MF import can retain the canonical H2C
    ``Standard,High Flow`` logical pair and resolve the active material through
    the Standard entry.  That presents the job to the rack checker as
    "Standard 0.4mm" even though slice_info/nozzle_sequence correctly target
    the right High Flow head.

    For Orca output only, make the *job requirement* unambiguous: both logical
    entries advertise High Flow 0.4 mm.  This does not change physical tool
    selection, filament maps, motion or extrusion; those remain audited as
    right-head-only by the existing metadata contract.  Studio output is left
    untouched.
    """
    output = Path(output)
    target = str(target).strip().lower()
    if target not in {"orca", "studio"}:
        raise RuntimeError(f"V1.90 ORCA NOZZLE METADATA: unsupported target {target!r}")
    if target == "studio":
        return {"target": "studio", "patched": False, "reason": "Studio metadata retained"}

    project_name = "Metadata/project_settings.config"
    gcode_name = "Metadata/plate_1.gcode"
    with zipfile.ZipFile(output, "r") as z:
        for name in (project_name, gcode_name):
            if name not in z.namelist():
                raise RuntimeError(f"V1.90 ORCA NOZZLE METADATA: missing {name}")
        project = json.loads(z.read(project_name).decode("utf-8"))
        gcode = z.read(gcode_name).decode("utf-8", errors="strict")

    # Fail closed on the H2C 0.4-mm two-logical-nozzle structure we expect.
    nozzle_diameter = project.get("nozzle_diameter")
    if not isinstance(nozzle_diameter, list) or len(nozzle_diameter) != 2:
        raise RuntimeError(
            f"V1.90 ORCA NOZZLE METADATA: expected two nozzle_diameter entries, got {nozzle_diameter!r}"
        )
    if any(abs(float(v) - 0.4) > 1e-9 for v in nozzle_diameter):
        raise RuntimeError(
            f"V1.90 ORCA NOZZLE METADATA: expected 0.4/0.4 nozzle diameters, got {nozzle_diameter!r}"
        )

    project["nozzle_volume_type"] = ["High Flow", "High Flow"]
    project["default_nozzle_volume_type"] = ["High Flow", "High Flow"]

    def replace_cfg_line(text: str, key: str, value: str) -> str:
        pat = re.compile(rf"^; {re.escape(key)} = .*?$", re.M)
        matches = list(pat.finditer(text))
        if len(matches) != 1:
            raise RuntimeError(
                f"V1.90 ORCA NOZZLE METADATA: expected one G-code config line for {key}, found {len(matches)}"
            )
        return pat.sub(f"; {key} = {value}", text, count=1)

    gcode = replace_cfg_line(gcode, "nozzle_volume_type", "High Flow,High Flow")
    gcode = replace_cfg_line(gcode, "default_nozzle_volume_type", "High Flow,High Flow")

    _replace_zip_members(
        output,
        {
            project_name: json.dumps(project, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
            gcode_name: gcode.encode("utf-8"),
        },
    )
    return audit_v1106_orca_nozzle_requirement_metadata(output, target)


def audit_v1106_orca_nozzle_requirement_metadata(output: Path, target: str = DEFAULT_SLICER_TARGET) -> dict:
    output = Path(output)
    target = str(target).strip().lower()
    if target == "studio":
        return {"target": "studio", "patched": False}
    if target != "orca":
        raise RuntimeError(f"V1.90 ORCA NOZZLE METADATA AUDIT: unsupported target {target!r}")

    with zipfile.ZipFile(output, "r") as z:
        project = json.loads(z.read("Metadata/project_settings.config").decode("utf-8"))
        gcode_bytes = z.read("Metadata/plate_1.gcode")
        sidecar = z.read("Metadata/plate_1.gcode.md5").decode("ascii").strip().lower()
        root = ET.fromstring(z.read("Metadata/slice_info.config"))
        seq = json.loads(z.read("Metadata/filament_sequence.json").decode("utf-8"))

    flow = project.get("nozzle_volume_type")
    default_flow = project.get("default_nozzle_volume_type")
    if flow != ["High Flow", "High Flow"] or default_flow != ["High Flow", "High Flow"]:
        raise RuntimeError(
            f"V1.90 ORCA NOZZLE METADATA AUDIT: project flow {flow!r}, default {default_flow!r}"
        )
    gcode = gcode_bytes.decode("utf-8", errors="strict")
    if "; nozzle_volume_type = High Flow,High Flow" not in gcode:
        raise RuntimeError("V1.90 ORCA NOZZLE METADATA AUDIT: G-code nozzle_volume_type is not High Flow/High Flow")
    if "; default_nozzle_volume_type = High Flow,High Flow" not in gcode:
        raise RuntimeError("V1.90 ORCA NOZZLE METADATA AUDIT: G-code default_nozzle_volume_type is not High Flow/High Flow")
    actual_md5 = hashlib.md5(gcode_bytes).hexdigest()
    if sidecar != actual_md5:
        raise RuntimeError(f"V1.90 ORCA NOZZLE METADATA AUDIT: MD5 {sidecar} != {actual_md5}")

    # Keep the already-proven physical right-head contract intact.
    plate_node = root.find("plate")
    if plate_node is None:
        raise RuntimeError("V1.90 ORCA NOZZLE METADATA AUDIT: missing slice plate")
    meta = {n.attrib.get("key"): n.attrib.get("value") for n in plate_node.findall("metadata")}
    maps = str(meta.get("filament_maps", "")).split()
    if len(maps) < 15 or maps[8] != "2" or maps[14] != "2":
        raise RuntimeError(f"V1.90 ORCA NOZZLE METADATA AUDIT: active filament maps are not right-head group 2: {maps!r}")
    nozzles = [n.attrib for n in plate_node.findall("nozzle")]
    if nozzles != [{"id": "1", "extruder_id": "2", "nozzle_diameter": "0.4", "volume_type": "High Flow"}]:
        raise RuntimeError(f"V1.90 ORCA NOZZLE METADATA AUDIT: slice nozzle record {nozzles!r}")
    nozzle_sequence = list(seq.get("plate_1", {}).get("nozzle_sequence") or [])
    if not nozzle_sequence or any(v != 1 for v in nozzle_sequence):
        raise RuntimeError(f"V1.90 ORCA NOZZLE METADATA AUDIT: nozzle_sequence {nozzle_sequence!r}")

    return {
        "target": "orca",
        "patched": True,
        "job_nozzle_requirement": ["High Flow 0.4mm", "High Flow 0.4mm"],
        "active_physical_head": "right/colour",
        "slice_nozzle": nozzles[0],
        "nozzle_sequence": nozzle_sequence,
        "md5": actual_md5,
    }


def apply_slicer_target_metadata(output: Path, target: str = DEFAULT_SLICER_TARGET) -> dict:
    """Make the packaged finished G-code importable by the selected slicer.

    Orca's standalone/previous-3MF G-code gate recognises its native producer
    line.  The successful prior Orca diagnostic proved that changing only that
    comment plus the plate_1.gcode MD5 is sufficient; all executable G-code
    and all H2C project/plate metadata remain untouched.

    Studio mode deliberately leaves the canonical BambuStudio producer line
    unchanged.
    """
    output = Path(output)
    target = str(target).strip().lower()
    if target not in {"orca", "studio"}:
        raise RuntimeError(f"V1.90 SLICER TARGET: unsupported target {target!r}")

    name = "Metadata/plate_1.gcode"
    with zipfile.ZipFile(output, "r") as z:
        gcode = z.read(name).decode("utf-8", errors="strict")

    lines = gcode.splitlines()
    producer_idx = _find_gcode_producer_line(lines)
    before = lines[producer_idx]

    if target == "orca":
        stamp = datetime.now().strftime("%Y-%m-%d at %H:%M:%S")
        lines[producer_idx] = f"; generated by OrcaSlicer {ORCA_PRODUCER_VERSION} on {stamp}"
        new_gcode = ("\n".join(lines) + "\n").encode("utf-8")
        _replace_zip_members(output, {name: new_gcode})
    else:
        if not before.startswith("; BambuStudio "):
            raise RuntimeError(
                "V1.90 SLICER TARGET: Studio target expected canonical BambuStudio producer line; "
                f"found {before!r}"
            )

    return audit_slicer_target_metadata(output, target)


def audit_slicer_target_metadata(output: Path, target: str = DEFAULT_SLICER_TARGET) -> dict:
    output = Path(output)
    target = str(target).strip().lower()
    gcode_name = "Metadata/plate_1.gcode"
    md5_name = "Metadata/plate_1.gcode.md5"
    with zipfile.ZipFile(output, "r") as z:
        gcode_bytes = z.read(gcode_name)
        sidecar = z.read(md5_name).decode("ascii").strip().lower()
    lines = gcode_bytes.decode("utf-8", errors="strict").splitlines()
    producer = lines[_find_gcode_producer_line(lines)]
    actual_md5 = hashlib.md5(gcode_bytes).hexdigest()
    if sidecar != actual_md5:
        raise RuntimeError(f"V1.90 SLICER TARGET AUDIT: MD5 {sidecar} != {actual_md5}")
    if target == "orca":
        prefix = f"; generated by OrcaSlicer {ORCA_PRODUCER_VERSION} on "
        if not producer.startswith(prefix):
            raise RuntimeError(f"V1.90 SLICER TARGET AUDIT: Orca producer line {producer!r}")
    elif target == "studio":
        if not producer.startswith("; BambuStudio "):
            raise RuntimeError(f"V1.90 SLICER TARGET AUDIT: Studio producer line {producer!r}")
    else:
        raise RuntimeError(f"V1.90 SLICER TARGET AUDIT: unsupported target {target!r}")
    return {"target": target, "producer": producer, "gcode_md5": actual_md5}



def enforce_safe_finish_tail(output: Path) -> dict:
    """
    Remove v1.179's unsafe hard-coded absolute ``G1 Z5 F1200`` immediately
    after V4_MODEL_END.

    v1.179 appends that move before the retained native H2C finish tail.  Model
    emission is in G90 at this point, so on any print taller than 5 mm it raises
    the bed back toward the nozzle while the head is still over the final model
    XY.  The native H2C tail already provides its own height-aware clearance
    motion, so the safest wrapper correction is to delete only this stray move.

    Fail closed unless the exact v1.179 sequence is found once and, after
    removal, every Z move before the unconditional pre-hotend-off G150.3 head
    park is either an absolute target at/above the final model Z or a
    non-negative relative Z move.
    """
    output = Path(output)
    gcode_name = "Metadata/plate_1.gcode"
    with zipfile.ZipFile(output, "r") as z:
        gcode = z.read(gcode_name).decode("utf-8", errors="replace")

    lines = gcode.splitlines()
    model_ends = [i for i, l in enumerate(lines) if l.strip() == "; V4_MODEL_END"]
    if len(model_ends) != 1:
        raise RuntimeError(
            f"SAFE FINISH TAIL: expected exactly one V4_MODEL_END, found {len(model_ends)}"
        )
    model_end = model_ends[0]

    layer_re = re.compile(
        r";\s*DIRECT_LAYER\s+V4\s+physical=(\d+).*?z=([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)"
    )
    layer_marks = []
    for i, line in enumerate(lines[: model_end + 1]):
        m = layer_re.search(line)
        if m:
            layer_marks.append((i, int(m.group(1)), float(m.group(2))))
    if not layer_marks:
        raise RuntimeError("SAFE FINISH TAIL: no DIRECT_LAYER markers before model end")
    final_model_z = float(layer_marks[-1][2])

    finish_marker = next(
        (i for i in range(model_end + 1, len(lines))
         if "FC3D_PPV64_REFERENCE_FINISH_TAIL_START" in lines[i]),
        None,
    )
    if finish_marker is None:
        raise RuntimeError("SAFE FINISH TAIL: retained reference finish-tail marker missing")

    unsafe = [
        i for i in range(model_end + 1, finish_marker)
        if re.match(r"^\s*G1\s+Z5(?:\.0+)?\s+F1200(?:\.0+)?\s*$", lines[i], re.I)
    ]
    if len(unsafe) != 1:
        raise RuntimeError(
            "SAFE FINISH TAIL: expected exactly one v1.179 hard-coded "
            f"G1 Z5 F1200 before reference finish tail, found {len(unsafe)}"
        )

    # Prove the bad move is actually absolute in the emitted stream.
    mode = "G90"
    for line in lines[: unsafe[0]]:
        s = line.strip()
        if re.match(r"^G90(?:\s|$)", s):
            mode = "G90"
        elif re.match(r"^G91(?:\s|$)", s):
            mode = "G91"
    if mode != "G90":
        raise RuntimeError(
            f"SAFE FINISH TAIL: expected unsafe Z5 to be in G90, found {mode}"
        )

    bad_line_no = unsafe[0] + 1
    lines[unsafe[0]] = (
        "; FC3D_V138_REMOVED_UNSAFE_ABSOLUTE_FINISH_Z5 "
        f"original_line={bad_line_no} final_model_z={final_model_z:.3f}"
    )

    def audit_pre_park(rows):
        me = next(i for i, l in enumerate(rows) if l.strip() == "; V4_MODEL_END")
        hot = next(
            (i for i in range(me + 1, len(rows))
             if re.match(r"^\s*M104\s+S0\s+T0\b", rows[i], re.I)),
            None,
        )
        if hot is None:
            raise RuntimeError("SAFE FINISH TAIL: right-hotend-off command missing")
        parks = [i for i in range(me + 1, hot) if rows[i].strip() == "G150.3"]
        if not parks:
            raise RuntimeError("SAFE FINISH TAIL: unconditional pre-hotend-off G150.3 park missing")
        park = parks[-1]

        modal = "G90"
        for line in rows[: me + 1]:
            s = line.strip()
            if re.match(r"^G90(?:\s|$)", s):
                modal = "G90"
            elif re.match(r"^G91(?:\s|$)", s):
                modal = "G91"

        z_moves = []
        violations = []
        for i in range(me + 1, park):
            s = rows[i].strip()
            if re.match(r"^G90(?:\s|$)", s):
                modal = "G90"
                continue
            if re.match(r"^G91(?:\s|$)", s):
                modal = "G91"
                continue
            if not (s.startswith("G0") or s.startswith("G1")):
                continue
            zm = re.search(r"\bZ([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", s)
            if not zm:
                continue
            zval = float(zm.group(1))
            z_moves.append((i + 1, modal, zval, s))
            if modal == "G90" and zval < final_model_z - 1e-6:
                violations.append((i + 1, modal, zval, s))
            elif modal == "G91" and zval < -1e-9:
                violations.append((i + 1, modal, zval, s))

        if violations:
            raise RuntimeError(
                "SAFE FINISH TAIL: post-model/pre-park Z motion can raise bed "
                f"toward the nozzle below final model Z={final_model_z:.3f}: {violations[:5]}"
            )
        return park + 1, z_moves

    park_line, pre_park_z_moves = audit_pre_park(lines)
    new_gcode = "\n".join(lines) + "\n"
    _replace_zip_members(output, {gcode_name: new_gcode.encode("utf-8")})

    return {
        "final_model_z_mm": final_model_z,
        "removed_unsafe_absolute_z5": True,
        "removed_original_line": bad_line_no,
        "mode_at_removed_move": "G90",
        "pre_park_z_moves": [x[3] for x in pre_park_z_moves],
        "unconditional_head_park_line": park_line,
        "pre_park_bed_raise_toward_nozzle": False,
    }



def _mirror_wave_peak_z_mm():
    return max(NOMINAL_TOP_Z_MM, BASE_TOP_Z_MM + A_MAIN_NOMINAL_HEIGHT_MM + WAVESET_TOTAL_PEAK_MM)



def enforce_mirror_wave_finish_clearance(output: Path) -> dict:
    """Raise the retained H2C finish clearances above the real non-planar B crest."""
    output=Path(output); name="Metadata/plate_1.gcode"
    with zipfile.ZipFile(output,"r") as z:
        lines=z.read(name).decode("utf-8",errors="replace").splitlines()
    model_end=next((i for i,l in enumerate(lines) if l.strip()=="; V4_MODEL_END"),None)
    finish_start=next((i for i,l in enumerate(lines) if "FC3D_PPV64_REFERENCE_FINISH_TAIL_START" in l),None)
    if model_end is None or finish_start is None or finish_start <= model_end:
        raise RuntimeError("MIRROR FINISH CLEARANCE: model/finish markers missing or out of order")
    layer_re=re.compile(r";\s*DIRECT_LAYER\s+V4\s+physical=(\d+).*?z=([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    layer_marks=[(int(m.group(1)),float(m.group(2))) for l in lines[:model_end] if (m:=layer_re.search(l))]
    if not layer_marks:
        raise RuntimeError("MIRROR FINISH CLEARANCE: no nominal layer markers")
    nominal_top=layer_marks[-1][1]
    moves=[]
    zline_re=re.compile(r"^(\s*G1\s+Z)([-+]?\d*\.?\d+)(\s+F900\s*;\s*lower z a little.*)$",re.I)
    for i in range(finish_start+1,min(len(lines),finish_start+120)):
        m=zline_re.match(lines[i])
        if m:
            moves.append((i,m,float(m.group(2))))
    if len(moves)<2:
        raise RuntimeError(f"MIRROR FINISH CLEARANCE: expected two retained clearance Z moves, found {len(moves)}")
    old1=moves[0][2]; old2=moves[1][2]
    if abs(old1-(nominal_top+0.40))>0.002 or abs(old2-(nominal_top+10.0))>0.002:
        raise RuntimeError(f"MIRROR FINISH CLEARANCE: unexpected native targets {old1:.3f},{old2:.3f} for nominal {nominal_top:.3f}")
    peak=_mirror_wave_peak_z_mm(); new1=peak+0.40; new2=peak+10.0
    for (i,m,_old),newz,tag in zip(moves[:2],(new1,new2),("PRE_PARK","POST_PARK")):
        lines[i]=f"{m.group(1)}{newz:.3f}{m.group(3)} ; FC3D_V1106_MIRROR_{tag}_CLEARANCE peak_z={peak:.3f}"
    _replace_zip_members(output,{name:("\n".join(lines)+"\n").encode("utf-8")})
    return {"nominal_top_z_mm":nominal_top,"physical_peak_z_mm":peak,
            "native_pre_park_z_mm":old1,"patched_pre_park_z_mm":new1,
            "native_post_park_z_mm":old2,"patched_post_park_z_mm":new2}


def audit_mirror_wave_finish_clearance(output: Path) -> dict:
    output=Path(output)
    with zipfile.ZipFile(output,"r") as z:
        lines=z.read("Metadata/plate_1.gcode").decode("utf-8",errors="replace").splitlines()
    peak=_mirror_wave_peak_z_mm(); want1=peak+0.40; want2=peak+10.0
    vals=[]
    for l in lines:
        if "FC3D_V1106_MIRROR_PRE_PARK_CLEARANCE" in l or "FC3D_V1106_MIRROR_POST_PARK_CLEARANCE" in l:
            m=re.search(r"\bZ([-+]?\d*\.?\d+)",l)
            if m: vals.append(float(m.group(1)))
    if len(vals)!=2 or abs(vals[0]-want1)>0.0011 or abs(vals[1]-want2)>0.0011:
        raise RuntimeError(f"MIRROR FINISH CLEARANCE AUDIT: got {vals}, expected {[want1,want2]}")
    # The optical patch itself must also finish above every B crest before V4_MODEL_END.
    safe=[]
    for l in lines:
        if "FC3D_V1106_OPTICAL_SAFE_END_Z" in l:
            m=re.search(r"\bZ([-+]?\d*\.?\d+)",l)
            if m: safe.append(float(m.group(1)))
    want_safe=peak+B_TRAVEL_CLEARANCE_MM
    if safe!=[round(want_safe,3)]:
        raise RuntimeError(f"MIRROR FINISH CLEARANCE AUDIT: optical safe-end {safe} != {[round(want_safe,3)]}")
    return {"physical_peak_z_mm":peak,"optical_safe_end_z_mm":safe[0],
            "pre_park_clear_z_mm":vals[0],"post_park_clear_z_mm":vals[1]}


def audit_safe_finish_tail(output: Path) -> dict:
    """Final package audit for the v1.43 post-model Z safety contract."""
    output = Path(output)
    gcode_name = "Metadata/plate_1.gcode"
    with zipfile.ZipFile(output, "r") as z:
        gcode = z.read(gcode_name).decode("utf-8", errors="replace")
    lines = gcode.splitlines()
    model_end = next((i for i,l in enumerate(lines) if l.strip() == "; V4_MODEL_END"), None)
    if model_end is None:
        raise RuntimeError("SAFE FINISH FINAL AUDIT: V4_MODEL_END missing")
    if not any("FC3D_V138_REMOVED_UNSAFE_ABSOLUTE_FINISH_Z5" in l for l in lines[model_end:]):
        raise RuntimeError("SAFE FINISH FINAL AUDIT: v1.43 removal marker missing")
    if any(re.match(r"^\s*G1\s+Z5(?:\.0+)?\s+F1200(?:\.0+)?\s*$", l, re.I)
           for l in lines[model_end + 1:]):
        raise RuntimeError("SAFE FINISH FINAL AUDIT: unsafe post-model G1 Z5 F1200 remains")

    layer_re = re.compile(r";\s*DIRECT_LAYER\s+V4\s+physical=(\d+).*?z=([-+]?\d*\.?\d+)")
    marks = [layer_re.search(l) for l in lines[:model_end+1]]
    marks = [m for m in marks if m]
    final_z = float(marks[-1].group(2))
    hot = next(i for i in range(model_end+1,len(lines))
               if re.match(r"^\s*M104\s+S0\s+T0\b", lines[i], re.I))
    parks = [i for i in range(model_end+1,hot) if lines[i].strip()=="G150.3"]
    if not parks:
        raise RuntimeError("SAFE FINISH FINAL AUDIT: pre-hotend-off G150.3 park missing")
    park = parks[-1]
    mode="G90"
    for l in lines[:model_end+1]:
        s=l.strip()
        if re.match(r"^G90(?:\s|$)",s): mode="G90"
        elif re.match(r"^G91(?:\s|$)",s): mode="G91"
    pre=[]; bad=[]
    for i in range(model_end+1,park):
        s=lines[i].strip()
        if re.match(r"^G90(?:\s|$)",s): mode="G90"; continue
        if re.match(r"^G91(?:\s|$)",s): mode="G91"; continue
        if not (s.startswith("G0") or s.startswith("G1")): continue
        m=re.search(r"\bZ([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)",s)
        if not m: continue
        v=float(m.group(1)); pre.append((i+1,mode,v,s))
        if (mode=="G90" and v < final_z-1e-6) or (mode=="G91" and v < -1e-9):
            bad.append((i+1,mode,v,s))
    if bad:
        raise RuntimeError(f"SAFE FINISH FINAL AUDIT: unsafe pre-park Z moves {bad[:5]}")
    return {
        "final_model_z_mm": final_z,
        "unsafe_absolute_z5_remaining": 0,
        "pre_park_z_moves": [x[3] for x in pre],
        "pre_park_z_safety": "PASS",
        "head_park_line": park+1,
    }


def audit_reference_cube_native_plate_process(output: Path) -> dict:
    """
    Validate the native plate/temperature part of the known-good cube process.

    The known-good Studio cube uses:
      - nominal Z0.100 first layer
      - Textured PEI G29.1 Z-0.02
      - PETG nozzle 255 C
      - bed 70 C

    v1.24 deliberately adds NO extra Z squish.
    """
    output = Path(output)
    gcode_name = "Metadata/plate_1.gcode"
    with zipfile.ZipFile(output, "r") as z:
        gcode = z.read(gcode_name).decode("utf-8", errors="replace")

    executable = [
        line.strip() for line in gcode.splitlines()
        if line.strip() and not line.lstrip().startswith(";")
    ]

    g29_native = [
        line for line in executable
        if re.match(r"^G29\.1\s+Z-0\.0?2(?:0*)?(?:\s|$)", line)
    ]
    g29_other_negative = [
        line for line in executable
        if re.match(r"^G29\.1\s+Z-", line) and line not in g29_native
    ]

    if len(g29_native) != 1:
        raise RuntimeError(
            "REFERENCE CUBE PROCESS: expected exactly one executable "
            f"G29.1 Z-0.02, found {len(g29_native)}"
        )
    if g29_other_negative:
        raise RuntimeError(
            "REFERENCE CUBE PROCESS: unexpected additional negative G29.1 "
            f"commands: {g29_other_negative[:5]}"
        )

    # The source/emitter already owns the normal PETG temperature sequence.
    # Require the known-good target values to appear executably.
    nozzle_ok = any(
        re.match(r"^M10[49]\b.*\bS255(?:\.0+)?(?:\s|$)", line)
        for line in executable
    )
    bed_ok = any(
        re.match(r"^M1(?:40|90)\b.*\bS70(?:\.0+)?(?:\s|$)", line)
        or re.match(r"^M1(?:40|90)\b.*\bD70(?:\.0+)?(?:\s|$)", line)
        for line in executable
    )
    if not nozzle_ok:
        raise RuntimeError("REFERENCE CUBE PROCESS: executable 255 C nozzle target not found")
    if not bed_ok:
        raise RuntimeError("REFERENCE CUBE PROCESS: executable 70 C bed target not found")

    return {
        "textured_pei_g29_mm": -0.02,
        "extra_wrapper_squish_mm": 0.0,
        "nozzle_c": REFERENCE_NOZZLE_C,
        "bed_c": REFERENCE_BED_C,
    }


def apply_model_g29_squish(output: Path) -> dict:
    """
    Increase plate squish while preserving every nominal model Z step.

    v1.179's Textured PEI baseline for the 0.4-mm nozzle is:
        G29.1 Z-0.020

    For this sparse design-following first layer we deliberately translate the
    ENTIRE model down by another 0.050 mm:
        G29.1 Z-0.070

    The same -0.070 baseline remains active for all physical layers, so nominal
    Z positions stay on the 0.100-mm physical layer grid. We do NOT
    restore -0.020 above layer 0.

    Only the executable textured-plate baseline command is changed. The startup
    G29.1 Z0 clear remains untouched.
    """
    output = Path(output)
    gcode_name = "Metadata/plate_1.gcode"

    with zipfile.ZipFile(output, "r") as z:
        if gcode_name not in z.namelist():
            raise RuntimeError(f"Generated package lacks {gcode_name}")
        gcode = z.read(gcode_name).decode("utf-8", errors="replace")

    lines = gcode.splitlines()
    source_cmd = f"G29.1 Z{SOURCE_TEXTURED_PEI_BASELINE_MM:.2f}"
    target_cmd = f"G29.1 Z{MODEL_G29_BASELINE_MM:.2f}"

    matched = 0
    out_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(source_cmd):
            # Keep any explanatory trailing comment.
            suffix = stripped[len(source_cmd):]
            indent = line[:len(line) - len(line.lstrip())]
            line = indent + target_cmd + suffix
            matched += 1
        out_lines.append(line)

    if matched != 1:
        raise RuntimeError(
            "MODEL G29 SQUISH AUDIT: expected exactly one executable "
            f"{source_cmd} baseline, found {matched}"
        )

    # Keep generated summary comments truthful as well.
    out_lines = [
        line.replace("inherited_G29.1=-0.02000", "inherited_G29.1=-0.06000")
            .replace("inherited_baseline=-0.02000", "inherited_baseline=-0.06000")
        for line in out_lines
    ]

    # Final fail-closed audit.
    active_target = [
        line for line in out_lines
        if line.strip().startswith(target_cmd)
    ]
    active_old = [
        line for line in out_lines
        if line.strip().startswith(source_cmd)
    ]
    clear_cmds = [
        line for line in out_lines
        if line.strip().startswith("G29.1 Z0")
    ]
    if len(active_target) != 1 or active_old:
        raise RuntimeError(
            "MODEL G29 SQUISH FINAL AUDIT failed: "
            f"target={len(active_target)} old={len(active_old)}"
        )
    if not clear_cmds:
        raise RuntimeError(
            "MODEL G29 SQUISH FINAL AUDIT: startup G29.1 Z0 clear not found"
        )

    new_gcode = "\n".join(out_lines) + "\n"
    _replace_zip_members(output, {gcode_name: new_gcode.encode("utf-8")})

    return {
        "source_textured_pei_baseline_mm": SOURCE_TEXTURED_PEI_BASELINE_MM,
        "final_model_g29_baseline_mm": MODEL_G29_BASELINE_MM,
        "extra_downward_translation_mm": (
            SOURCE_TEXTURED_PEI_BASELINE_MM - MODEL_G29_BASELINE_MM
        ),
        "nominal_layer_height_mm": LAYER_H_MM,
        "nominal_z_sequence_changed": False,
        "baseline_retained_for_all_layers": True,
        "patched_executable_commands": matched,
    }


def apply_continuous_optical_paths(
    output: Path,
    bottom_angle_deg: float,
    middle_angle_deg: float,
    top_angle_deg: float,
) -> dict:
    """Restore exact rear lands and make one live louver path per panel.

    v1.179 receives only the diagonal optical facet and 75-degree return for
    each tooth. Its passthrough emitter preserves those diagonals in source
    order. This pass removes their isolated retract/travel/reprime intervals
    and inserts the exact horizontal rear land after every return.
    """
    output = Path(output)
    gcode_name = "Metadata/plate_1.gcode"
    with zipfile.ZipFile(output, "r") as z:
        gcode = z.read(gcode_name).decode("utf-8", errors="replace")

    lines = gcode.splitlines()
    layer_re = re.compile(r";\s*DIRECT_LAYER\s+V4\s+physical=(\d+)")
    x_re = re.compile(r"\sX([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    y_re = re.compile(r"\sY([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    e_re = re.compile(r"\sE([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")

    expected = []
    angles = (bottom_angle_deg, middle_angle_deg, top_angle_deg)
    for panel_idx, ang in enumerate(angles):
        geom = optical_geometry_for_angle(ang)
        intended = _optical_segments_for_panel(panel_idx, ang, 0.0, 0.0)
        emitted = _emitter_optical_segments_for_panel(panel_idx, ang, 0.0, 0.0)
        if len(intended) % 3 != 0:
            raise RuntimeError(
                f"CONTINUITY CONTRACT panel {panel_idx}: intended count "
                f"{len(intended)} is not divisible by 3"
            )
        teeth = len(intended) // 3
        if len(emitted) != 2 * teeth:
            raise RuntimeError(
                f"CONTINUITY CONTRACT panel {panel_idx}: emitted count "
                f"{len(emitted)} != 2*{teeth}"
            )
        expected.append({
            "panel": panel_idx,
            "teeth": teeth,
            "emitted_count": len(emitted),
            "final_count": len(intended),
            "optical_run": float(geom["facet_run_x_mm"]),
            "return_run": float(geom["return_run_x_mm"]),
            "dy": float(geom["facet_rise_y_mm"]),
            "land_run": float(geom["rear_land_x_mm"]),
        })

    vec_tol = 0.035
    chain_tol = 0.035
    layer_starts = [i for i, line in enumerate(lines) if layer_re.search(line)]
    if not layer_starts:
        raise RuntimeError("CONTINUITY AUDIT: no DIRECT_LAYER markers found")
    layer_starts.append(len(lines))
    rebuilt = lines[:layer_starts[0]]

    total_removed_retracts = 0
    total_removed_reprimes = 0
    total_removed_dry_xy = 0
    total_synth_lands = [0] * PANEL_COUNT
    total_joins = [0] * PANEL_COUNT
    matched_counts = [0] * PANEL_COUNT

    def account_removed(interval):
        nonlocal total_removed_retracts, total_removed_reprimes, total_removed_dry_xy
        for q in interval:
            qs = q.strip()
            if re.match(r"^G1\s+E-0\.4(?:0+)?\b", qs):
                total_removed_retracts += 1
            elif re.match(r"^G1\s+E0\.4(?:0+)?\b", qs):
                total_removed_reprimes += 1
            elif ((qs.startswith("G0") or qs.startswith("G1"))
                  and (x_re.search(q) or y_re.search(q))):
                total_removed_dry_xy += 1

    for li in range(len(layer_starts) - 1):
        block = lines[layer_starts[li]:layer_starts[li + 1]]
        in_model = False
        current_xy = None
        records = []

        for i, line in enumerate(block):
            s = line.strip()
            if s.startswith("; FEATURE:"):
                in_model = "DIRECT_DETERMINISTIC_ROADS_" in s
                current_xy = None
                continue
            if not in_model or not (s.startswith("G0") or s.startswith("G1")):
                continue
            xm, ym = x_re.search(line), y_re.search(line)
            if not (xm or ym):
                continue
            old_xy = current_xy
            nx = float(xm.group(1)) if xm else (old_xy[0] if old_xy else None)
            ny = float(ym.group(1)) if ym else (old_xy[1] if old_xy else None)
            if nx is None or ny is None:
                continue
            new_xy = (nx, ny)
            if s.startswith("G1") and old_xy is not None:
                em = e_re.search(line)
                if em and float(em.group(1)) > 0.0:
                    dx, dy = nx - old_xy[0], ny - old_xy[1]
                    hits = []
                    for ps in expected:
                        if (abs(abs(dx) - ps["optical_run"]) <= vec_tol
                                and abs(abs(dy) - ps["dy"]) <= vec_tol):
                            hits.append((ps["panel"], "optical"))
                        if (abs(abs(dx) - ps["return_run"]) <= vec_tol
                                and abs(abs(dy) - ps["dy"]) <= vec_tol):
                            hits.append((ps["panel"], "return"))
                    if len(hits) > 1:
                        raise RuntimeError(
                            f"CONTINUITY AUDIT layer {li}: ambiguous diagonal "
                            f"dx={dx:.4f} dy={dy:.4f} hits={hits}"
                        )
                    if len(hits) == 1:
                        p, kind = hits[0]
                        records.append({
                            "idx": i,
                            "panel": p,
                            "kind": kind,
                            "start": old_xy,
                            "end": new_xy,
                        })
            current_xy = new_xy

        by_panel = {p: [] for p in range(PANEL_COUNT)}
        for record in records:
            by_panel[record["panel"]].append(record)

        for ps in expected:
            p = ps["panel"]
            recs = by_panel[p]
            if len(recs) != ps["emitted_count"]:
                raise RuntimeError(
                    f"CONTINUITY AUDIT layer {li} panel {p}: matched "
                    f"{len(recs)} diagonals, expected {ps['emitted_count']}"
                )
            matched_counts[p] += len(recs)
            for j, record in enumerate(recs):
                want = "optical" if j % 2 == 0 else "return"
                if record["kind"] != want:
                    raise RuntimeError(
                        f"CONTINUITY AUDIT layer {li} panel {p}: diagonal cycle "
                        f"{j} is {record['kind']}, expected {want}"
                    )
            for tooth in range(ps["teeth"]):
                optical = recs[2 * tooth]
                ret = recs[2 * tooth + 1]
                gap = math.hypot(
                    optical["end"][0] - ret["start"][0],
                    optical["end"][1] - ret["start"][1],
                )
                if gap > chain_tol:
                    raise RuntimeError(
                        f"CONTINUITY AUDIT layer {li} panel {p} tooth {tooth}: "
                        f"optical->return gap={gap:.4f} mm"
                    )
                land_end = (ret["end"][0] + ps["land_run"], ret["end"][1])
                if tooth + 1 < ps["teeth"]:
                    nxt = recs[2 * (tooth + 1)]
                    gap = math.hypot(
                        land_end[0] - nxt["start"][0],
                        land_end[1] - nxt["start"][1],
                    )
                    if gap > chain_tol:
                        raise RuntimeError(
                            f"CONTINUITY AUDIT layer {li} panel {p} tooth {tooth}: "
                            f"land->next optical gap={gap:.4f} mm"
                        )

        actions = {}
        starts = {}
        finals = {}
        for ps in expected:
            p = ps["panel"]
            recs = by_panel[p]
            starts[recs[0]["idx"]] = p
            for tooth in range(ps["teeth"]):
                optical = recs[2 * tooth]
                ret = recs[2 * tooth + 1]
                actions[optical["idx"]] = {
                    "target": ret["idx"], "panel": p, "land_end": None,
                }
                land_end = (ret["end"][0] + ps["land_run"], ret["end"][1])
                if tooth + 1 < ps["teeth"]:
                    nxt = recs[2 * (tooth + 1)]
                    actions[ret["idx"]] = {
                        "target": nxt["idx"], "panel": p, "land_end": land_end,
                    }
                else:
                    finals[ret["idx"]] = {"panel": p, "land_end": land_end}

        out = []
        i = 0
        while i < len(block):
            if i in starts:
                out.append(
                    f"; FC3D_V140_LOUVER_PANEL_START layer={li} panel={starts[i]}"
                )
            out.append(block[i])

            if i in actions:
                info = actions[i]
                p = info["panel"]
                if info["land_end"] is not None:
                    lx, ly = info["land_end"]
                    land_e = (expected[p]["land_run"] * CALIBRATED_E_PER_MM
                              * REAR_LAND_FLOW_MULT)
                    out.append(
                        f"G1 X{lx:.3f} Y{ly:.3f} E{land_e:.5f} "
                        f"; FC3D_V140_SYNTH_REAR_LAND panel={p}"
                    )
                    total_synth_lands[p] += 1
                    total_joins[p] += 1
                target = info["target"]
                account_removed(block[i + 1:target])
                total_joins[p] += 1
                i = target
                continue

            if i in finals:
                info = finals[i]
                p = info["panel"]
                lx, ly = info["land_end"]
                land_e = (expected[p]["land_run"] * CALIBRATED_E_PER_MM
                          * REAR_LAND_FLOW_MULT)
                out.append(
                    f"G1 X{lx:.3f} Y{ly:.3f} E{land_e:.5f} "
                    f"; FC3D_V140_SYNTH_REAR_LAND panel={p} final=1"
                )
                out.append(
                    f"; FC3D_V140_LOUVER_PANEL_END layer={li} panel={p}"
                )
                total_synth_lands[p] += 1
                total_joins[p] += 1
            i += 1

        rebuilt.extend(out)

    new_gcode = "\n".join(rebuilt) + "\n"
    _replace_zip_members(output, {gcode_name: new_gcode.encode("utf-8")})
    return {
        "geometry": "asymmetric_louver_75deg_return_synthesized_rear_land",
        "return_angle_deg": RETURN_ANGLE_DEG,
        "selection_basis": (
            "emitted optical/return diagonal geometry; exact horizontal rear "
            "lands withheld from v1.179 and synthesized in final source order"
        ),
        "source_land_emission_by_v1106": False,
        "emitted_segments_per_layer_panel0": expected[0]["emitted_count"],
        "emitted_segments_per_layer_panel1": expected[1]["emitted_count"],
        "emitted_segments_per_layer_panel2": expected[2]["emitted_count"],
        "final_segments_per_layer_panel0": expected[0]["final_count"],
        "final_segments_per_layer_panel1": expected[1]["final_count"],
        "final_segments_per_layer_panel2": expected[2]["final_count"],
        "matched_emitted_segments_all_layers_panel0": matched_counts[0],
        "matched_emitted_segments_all_layers_panel1": matched_counts[1],
        "matched_emitted_segments_all_layers_panel2": matched_counts[2],
        "synthetic_rear_lands_panel0": total_synth_lands[0],
        "synthetic_rear_lands_panel1": total_synth_lands[1],
        "synthetic_rear_lands_panel2": total_synth_lands[2],
        "panel0_inter_segment_joins": total_joins[0],
        "panel1_inter_segment_joins": total_joins[1],
        "panel2_inter_segment_joins": total_joins[2],
        "retracts_removed_inside_optical_paths": total_removed_retracts,
        "reprimes_removed_inside_optical_paths": total_removed_reprimes,
        "dry_xy_moves_removed_inside_optical_paths": total_removed_dry_xy,
        "cross_panel_joining": False,
    }

def apply_first_model_layer_flow(output: Path) -> dict:
    """
    Increase extrusion on physical model layer 0 only.

    Robustness rule for v1.18:
      - identify physical layer 0 from DIRECT_LAYER V4 physical=0
      - stop when DIRECT_LAYER V4 physical=1 begins
      - do NOT depend on FEATURE comments being present

    Only positive-E XY model moves inside physical layer 0 are multiplied.
    E-only reprime/retract moves and every later physical layer are untouched.
    """
    output = Path(output)
    gcode_name = "Metadata/plate_1.gcode"

    with zipfile.ZipFile(output, "r") as z:
        if gcode_name not in z.namelist():
            raise RuntimeError(f"Generated package lacks {gcode_name}")
        gcode = z.read(gcode_name).decode("utf-8", errors="replace")

    lines = gcode.splitlines()
    out = []
    current_physical = None
    changed = 0
    layer0_xy_e_seen = 0

    layer_re = re.compile(r";\s*DIRECT_LAYER\s+V4\s+physical=(\d+)")
    e_re = re.compile(r"(\sE)([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")

    for line in lines:
        m = layer_re.search(line)
        if m:
            current_physical = int(m.group(1))

        s = line.strip()
        if current_physical == 0 and s.startswith("G1"):
            has_xy = (" X" in (" " + s)) or (" Y" in (" " + s))
            em = e_re.search(line)
            if has_xy and em and float(em.group(2)) > 0.0:
                old_e = float(em.group(2))
                new_e = old_e * FIRST_MODEL_LAYER_FLOW_MULT
                line = line[:em.start(2)] + f"{new_e:.5f}" + line[em.end(2):]
                changed += 1
                layer0_xy_e_seen += 1

        out.append(line)

    if changed == 0:
        raise RuntimeError(
            "FIRST-LAYER FLOW AUDIT: no positive-E XY moves found inside "
            "DIRECT_LAYER physical=0"
        )

    # Verify later layers were not touched by counting only; transformation is
    # guarded strictly by current_physical == 0.
    new_gcode = "\n".join(out) + "\n"
    _replace_zip_members(output, {gcode_name: new_gcode.encode("utf-8")})

    return {
        "first_model_layer_flow_multiplier": FIRST_MODEL_LAYER_FLOW_MULT,
        "changed_positive_e_xy_moves": changed,
        "layer0_positive_e_xy_moves_seen": layer0_xy_e_seen,
        "selection_basis": "DIRECT_LAYER physical=0 scope",
        "later_layers_unchanged": True,
    }


def apply_studio_first_layer_speed(output: Path) -> dict:
    """
    Set positive-E XY model moves on physical layer 0 to 20 mm/s.

    v1.18 uses DIRECT_LAYER physical=0 scope instead of relying on FEATURE
    comments. E-only pressure moves, dry travels, startup, and later layers are
    untouched.
    """
    output = Path(output)
    gcode_name = "Metadata/plate_1.gcode"

    with zipfile.ZipFile(output, "r") as z:
        if gcode_name not in z.namelist():
            raise RuntimeError(f"Generated package lacks {gcode_name}")
        gcode = z.read(gcode_name).decode("utf-8", errors="replace")

    lines = gcode.splitlines()
    out_lines = []
    current_physical = None
    rewritten_draw_moves = 0

    layer_re = re.compile(r";\s*DIRECT_LAYER\s+V4\s+physical=(\d+)")

    for line in lines:
        m = layer_re.search(line)
        if m:
            current_physical = int(m.group(1))

        s = line.strip()
        if current_physical == 0 and s.startswith("G1"):
            has_xy = (" X" in (" " + s)) or (" Y" in (" " + s))
            m_e = re.search(r"\bE(-?\d+(?:\.\d+)?)\b", line)
            if has_xy and m_e and float(m_e.group(1)) > 0:
                if re.search(r"\bF\d+(?:\.\d+)?\b", line):
                    line = re.sub(
                        r"\bF\d+(?:\.\d+)?\b",
                        f"F{FIRST_MODEL_LAYER_FEED_MM_MIN}",
                        line,
                        count=1,
                    )
                else:
                    line = line.rstrip() + f" F{FIRST_MODEL_LAYER_FEED_MM_MIN}"
                rewritten_draw_moves += 1

        out_lines.append(line)

    if rewritten_draw_moves == 0:
        raise RuntimeError(
            "FIRST-LAYER SPEED AUDIT: no positive-E XY moves found inside "
            "DIRECT_LAYER physical=0"
        )

    # Final audit: every positive-E XY move in layer 0 must explicitly carry F1200.
    current_physical = None
    audited = 0
    for line in out_lines:
        m = layer_re.search(line)
        if m:
            current_physical = int(m.group(1))
        if current_physical != 0:
            continue
        s = line.strip()
        if not s.startswith("G1"):
            continue
        has_xy = (" X" in (" " + s)) or (" Y" in (" " + s))
        m_e = re.search(r"\bE(-?\d+(?:\.\d+)?)\b", line)
        if has_xy and m_e and float(m_e.group(1)) > 0:
            audited += 1
            if not re.search(rf"\bF{FIRST_MODEL_LAYER_FEED_MM_MIN}\b", line):
                raise RuntimeError(
                    "FIRST-LAYER SPEED FINAL AUDIT: positive-E XY move without "
                    f"F{FIRST_MODEL_LAYER_FEED_MM_MIN}: {line}"
                )

    new_gcode = "\n".join(out_lines) + "\n"
    _replace_zip_members(output, {gcode_name: new_gcode.encode("utf-8")})

    return {
        "first_model_layer_speed_mm_s": FIRST_MODEL_LAYER_SPEED_MM_S,
        "first_model_layer_feed_mm_min": FIRST_MODEL_LAYER_FEED_MM_MIN,
        "rewritten_draw_moves": rewritten_draw_moves,
        "audited_layer0_positive_e_xy_moves": audited,
        "selection_basis": "DIRECT_LAYER physical=0 scope",
        "later_layers_unchanged": True,
    }


def apply_dynamic_tower_policy(output: Path) -> dict:
    """Remove every known v1.179 tower operation for this one-material A1 job.

    v1.179 has more than one tower representation.  In addition to the usual
    ``WIPE_TOWER_START/END DIRECT_SOLID_V4`` block, same-layer scheduler work can
    emit ``DIRECT_SOLID_V156_SECONDARY`` blocks and an undelimited primary
    structural fill beginning at ``FC3D_TOWER_PRIMARY_STRUCTURAL_FILL`` and
    ending only when ``FC3D_TOWER_LAYER_COMPLETE_V129`` is emitted.

    Never scrub an in-owner ``FC3D_TOWER_SLOT`` marker by itself: it can own real
    extrusion. Remove all four v1.179 ownership forms first. Only after those
    owners are gone may an exact standalone slot-comment line be scrubbed without
    consuming neighbouring motion; then fail closed if any tower marker survives.  After deleting a tower, neutralise only the stale XY
    seed on the first canonical checked hop by converting that XYZ hop to Z-only.
    """
    output = Path(output)
    gcode_name = "Metadata/plate_1.gcode"
    with zipfile.ZipFile(output, "r") as z:
        if gcode_name not in z.namelist():
            raise RuntimeError(f"DYNAMIC TOWER POLICY: generated package lacks {gcode_name}")
        gcode = z.read(gcode_name).decode("utf-8", errors="replace")

    m_active = re.search(
        r";\s*FC3D_V169_JOB_ACTIVE_MATERIALS\s+([A-Z]+(?:[ \t,]+[A-Z]+)*)",
        gcode,
    )
    if not m_active:
        raise RuntimeError("DYNAMIC TOWER POLICY: active-material marker not found")
    active_materials = [
        x for x in re.split(r"[ \t,]+", m_active.group(1).strip())
        if x and x.lower() != "none"
    ]
    if not active_materials:
        raise RuntimeError("DYNAMIC TOWER POLICY: parsed zero active materials")

    lines = gcode.splitlines()
    tower_start_re = re.compile(
        r"^;\s*WIPE_TOWER_START\s+(DIRECT_SOLID_[A-Za-z0-9_]+)(?:\s|$)"
    )
    tower_end_re = re.compile(
        r"^;\s*WIPE_TOWER_END\s+(DIRECT_SOLID_[A-Za-z0-9_]+)(?:\s|$)"
    )
    post_start = "; WIPE_START FC3D_PPSPV47_POST_TOWER_SAFE_LIFTED"
    post_end = "; WIPE_END FC3D_PPSPV47_POST_TOWER_SAFE_LIFTED"
    exit_safe = "; FC3D_PPSPV47_TOWER_EXIT_ALREADY_LIFTED_NEXT_TRAVEL_SAFE"
    scheduler_primary = "; FC3D_TOWER_PRIMARY_STRUCTURAL_FILL"
    scheduler_complete = "; FC3D_TOWER_LAYER_COMPLETE_V129"
    hop_marker = "FC3D_PPSPV62_STUDIO_SAFE_VERTICAL_CHECKED_HOP"
    model_end = "; V4_MODEL_END"

    # Validate every explicit tower delimiter before changing anything.  The ID
    # must match, not merely the number of starts and ends.
    open_tower_id = None
    starts_before = 0
    ends_before = 0
    tower_id_counts = {}
    for line_no, line in enumerate(lines, start=1):
        s = line.strip()
        ms = tower_start_re.match(s)
        me = tower_end_re.match(s)
        if ms:
            if open_tower_id is not None:
                raise RuntimeError(
                    f"DYNAMIC TOWER POLICY: nested tower START at line {line_no}: "
                    f"open={open_tower_id} new={ms.group(1)}"
                )
            open_tower_id = ms.group(1)
            starts_before += 1
            tower_id_counts[open_tower_id] = tower_id_counts.get(open_tower_id, 0) + 1
            continue
        if me:
            ends_before += 1
            if open_tower_id is None:
                raise RuntimeError(
                    f"DYNAMIC TOWER POLICY: tower END without START at line {line_no}: {me.group(1)}"
                )
            if me.group(1) != open_tower_id:
                raise RuntimeError(
                    f"DYNAMIC TOWER POLICY: mismatched tower END at line {line_no}: "
                    f"open={open_tower_id} end={me.group(1)}"
                )
            open_tower_id = None
    if open_tower_id is not None:
        raise RuntimeError(
            f"DYNAMIC TOWER POLICY: unterminated tower block before patch: {open_tower_id}"
        )
    if starts_before != ends_before:
        raise RuntimeError(
            "DYNAMIC TOWER POLICY: mismatched tower delimiter counts before patch: "
            f"{starts_before} START / {ends_before} END"
        )

    post_starts_before = sum(1 for line in lines if line.strip().startswith(post_start))
    post_ends_before = sum(1 for line in lines if line.strip().startswith(post_end))
    if post_starts_before != post_ends_before:
        raise RuntimeError(
            "DYNAMIC TOWER POLICY: mismatched optional post-tower wipe delimiters before patch: "
            f"{post_starts_before} START / {post_ends_before} END"
        )

    if len(active_materials) >= 2:
        return {
            "policy": "multi_material_tower_unchanged",
            "active_materials": active_materials,
            "active_material_count": len(active_materials),
            "tower_removed": False,
            "original_tower_blocks": starts_before,
            "original_tower_block_ids": dict(sorted(tower_id_counts.items())),
            "original_post_tower_wipes": post_starts_before,
            "removed_tower_blocks": 0,
            "removed_scheduler_primary_fill_groups": 0,
            "removed_scheduler_primary_fill_markers": 0,
            "removed_scheduler_completion_markers": 0,
            "removed_post_tower_wipes": 0,
            "sanitized_tower_exit_hops": 0,
            "tower_exits_without_following_hop": 0,
            "removed_tower_lines": 0,
        }

    out = []
    in_tower_id = None
    in_post = False
    in_scheduler_completion = False
    pending_exit = False
    need_hop_motion = False
    removed_blocks = 0
    removed_post = 0
    removed_lines = 0
    removed_scheduler_groups = 0
    removed_scheduler_primary_markers = 0
    removed_scheduler_completion_markers = 0
    sanitized_hops = 0
    exits_without_hop = 0

    motion_re = re.compile(r"^\s*G[01]\b", re.I)
    x_re = re.compile(r"\bX[-+]?\d")
    y_re = re.compile(r"\bY[-+]?\d")
    z_value_re = re.compile(r"\bZ([-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?)")
    f_value_re = re.compile(r"\bF([-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?)")

    for line_no, line in enumerate(lines, start=1):
        s = line.strip()
        ms = tower_start_re.match(s)
        me = tower_end_re.match(s)

        # Scheduler completion primary fills are not explicitly delimited by
        # WIPE_TOWER markers.  Once the first primary-fill marker appears, the
        # remainder of complete_same_layer_scheduler_tower() belongs to tower
        # completion until its authoritative LAYER_COMPLETE marker.
        if in_scheduler_completion:
            removed_lines += 1
            if s.startswith(scheduler_primary):
                removed_scheduler_primary_markers += 1
            if ms:
                removed_blocks += 1
            if s.startswith(scheduler_complete):
                removed_scheduler_completion_markers += 1
                in_scheduler_completion = False
                pending_exit = True
                continue
            if (
                s.startswith("; CHANGE_LAYER")
                or s.startswith("; FEATURE:")
                or s.startswith(model_end)
            ):
                raise RuntimeError(
                    "DYNAMIC TOWER POLICY: scheduler primary fill reached model/layer boundary "
                    f"without {scheduler_complete!r}; line {line_no}: {line!r}"
                )
            continue

        if in_tower_id is not None:
            removed_lines += 1
            if ms:
                raise RuntimeError(f"DYNAMIC TOWER POLICY: nested tower START at line {line_no}")
            if me:
                if me.group(1) != in_tower_id:
                    raise RuntimeError(
                        f"DYNAMIC TOWER POLICY: mismatched tower END at line {line_no}: "
                        f"open={in_tower_id} end={me.group(1)}"
                    )
                in_tower_id = None
                pending_exit = True
            continue

        if in_post:
            removed_lines += 1
            if s.startswith(post_start):
                raise RuntimeError(f"DYNAMIC TOWER POLICY: nested post-tower WIPE_START at line {line_no}")
            if s.startswith(post_end):
                in_post = False
            continue

        # Generic ownership for every explicitly delimited DIRECT_SOLID tower
        # family (V4, V4_FILLER, V156_SECONDARY, and future named variants).
        if ms:
            in_tower_id = ms.group(1)
            removed_blocks += 1
            removed_lines += 1
            continue
        if me:
            raise RuntimeError(f"DYNAMIC TOWER POLICY: tower END without START at line {line_no}")

        # Undelimited scheduler primary completion.  Do not scrub its slot line
        # alone: the following G-code is real tower extrusion and is removed as
        # one owned completion group through FC3D_TOWER_LAYER_COMPLETE_V129.
        if s.startswith(scheduler_primary):
            in_scheduler_completion = True
            removed_scheduler_groups += 1
            removed_scheduler_primary_markers += 1
            removed_lines += 1
            continue

        # If all primary slots were already used, scheduler completion may consist
        # only of delimited secondary blocks followed by this marker.  Remove the
        # marker, but open no new exit episode unless tower geometry was removed.
        if s.startswith(scheduler_complete):
            removed_scheduler_completion_markers += 1
            removed_lines += 1
            continue

        # POST_TOWER_SAFE_LIFTED is optional: only a tool-change exit emits it.
        if s.startswith(post_start):
            if not pending_exit:
                raise RuntimeError(
                    f"DYNAMIC TOWER POLICY: orphan post-tower WIPE_START at line {line_no}"
                )
            in_post = True
            removed_post += 1
            removed_lines += 1
            continue
        if s.startswith(post_end):
            raise RuntimeError(f"DYNAMIC TOWER POLICY: post-tower WIPE_END without START at line {line_no}")

        # This marker describes the deleted tool-change post-wipe state.
        if pending_exit and s.startswith(exit_safe):
            removed_lines += 1
            continue

        # The first canonical checked hop after a deleted tower owns the stale
        # tower XY seed.  Keep its marker and rewrite exactly its first XYZ move.
        if pending_exit and hop_marker in s:
            pending_exit = False
            need_hop_motion = True
            out.append(line)
            continue

        if need_hop_motion and motion_re.match(s) and (
            x_re.search(s) or y_re.search(s) or z_value_re.search(s)
        ):
            mz = z_value_re.search(s)
            if mz is None or not (x_re.search(s) or y_re.search(s)):
                raise RuntimeError(
                    "DYNAMIC TOWER POLICY: expected first checked-hop motion to carry stale XY and Z; "
                    f"line {line_no}: {line!r}"
                )
            mf = f_value_re.search(s)
            feed = f" F{mf.group(1)}" if mf else ""
            out.append(
                f"G1 Z{mz.group(1)}{feed} ; FC3D_V1106_TOWER_EXIT_HOP_SANITIZED_Z_ONLY"
            )
            sanitized_hops += 1
            need_hop_motion = False
            continue

        # Feed-only/E-only commands and Z-only lifts are safe after tower deletion.
        # A move carrying X or Y before the checked-hop marker is not safe because
        # the generated planner may still be using the now-deleted tower XY state.
        if pending_exit and motion_re.match(s) and (x_re.search(s) or y_re.search(s)):
            raise RuntimeError(
                "DYNAMIC TOWER POLICY: XY motion after removed tower before checked-hop marker; "
                f"line {line_no}: {line!r}"
            )

        if pending_exit and s.startswith(model_end):
            exits_without_hop += 1
            pending_exit = False

        out.append(line)

    if in_tower_id is not None:
        raise RuntimeError(f"DYNAMIC TOWER POLICY: unterminated tower block at EOF: {in_tower_id}")
    if in_scheduler_completion:
        raise RuntimeError(
            "DYNAMIC TOWER POLICY: unterminated scheduler primary-fill completion at EOF"
        )
    if in_post:
        raise RuntimeError("DYNAMIC TOWER POLICY: unterminated optional post-tower wipe at EOF")
    if need_hop_motion:
        raise RuntimeError("DYNAMIC TOWER POLICY: checked-hop marker had no following motion before EOF")
    if pending_exit:
        raise RuntimeError("DYNAMIC TOWER POLICY: removed tower exit remained unresolved at EOF")
    if removed_blocks != starts_before or removed_post != post_starts_before:
        raise RuntimeError(
            "DYNAMIC TOWER POLICY: removal counts mismatch: "
            f"tower {removed_blocks}/{starts_before}, optional_post {removed_post}/{post_starts_before}"
        )

    # v1.106: all real v1.179 FC3D_TOWER_SLOT emission owners have now been
    # removed above.  Any exact slot marker that remains is therefore standalone
    # commentary (the predecessor policy also scrubbed this form).  Remove the
    # comment only; never consume neighbouring motion.
    standalone_slot_re = re.compile(r"^\s*;\s*FC3D_TOWER_SLOT(?:\s|$)")
    standalone_slot_comments = [line for line in out if standalone_slot_re.match(line)]
    if standalone_slot_comments:
        out = [line for line in out if not standalone_slot_re.match(line)]
        removed_lines += len(standalone_slot_comments)

    new_gcode = "\n".join(out) + "\n"
    tower_tokens = (
        "WIPE_TOWER_START DIRECT_SOLID_",
        "WIPE_TOWER_END DIRECT_SOLID_",
        "FEATURE: DIRECT_SOLID_PRIME_TOWER",
        "DIRECT_SOLID_PRIME_TOWER_V57",
        "PRIME_TOWER_PPV64_CONTINUOUS_STUDIO_X",
        "PRIME_TOWER_V169_CANONICAL_FILLER",
        "FC3D_TOWER_PRIMARY_STRUCTURAL_FILL",
        "FC3D_TOWER_SECONDARY_GAPS_V156",
        "FC3D_TOWER_LAYER_COMPLETE_V129",
        "FC3D_TOWER_FILL_NO_SWAP",
        "FC3D_PPV64_SOLID_WHITE_TOWER_BASE",
        "WIPE_START FC3D_PPSPV47_POST_TOWER_SAFE_LIFTED",
        "WIPE_END FC3D_PPSPV47_POST_TOWER_SAFE_LIFTED",
        "FC3D_PPSPV47_TOWER_EXIT_ALREADY_LIFTED_NEXT_TRAVEL_SAFE",
        "FC3D_V150_TOWER_PRESSURE_STATE",
        "reason=TOWER_TRAVEL",
        "PPSPV53 tower XY",
    )
    leaked = [tok for tok in tower_tokens if tok in new_gcode]
    residual_slot_markers = [
        line for line in out if standalone_slot_re.match(line)
    ]
    if residual_slot_markers:
        raise RuntimeError(
            "DYNAMIC TOWER POLICY: exact FC3D_TOWER_SLOT marker survived standalone scrub: "
            f"{residual_slot_markers[:5]}"
        )
    if leaked:
        leak_context = [
            (i + 1, line) for i, line in enumerate(out)
            if any(tok in line for tok in leaked)
        ]
        raise RuntimeError(
            "DYNAMIC TOWER POLICY: tower lifecycle content survived removal: "
            f"{leaked}; first_lines={leak_context[:8]}"
        )

    if new_gcode != gcode:
        _replace_zip_members(output, {gcode_name: new_gcode.encode("utf-8")})

    return {
        "policy": "single_material_remove_all_known_tower_owners_and_sanitize_checked_exit_hop",
        "active_materials": active_materials,
        "active_material_count": len(active_materials),
        "tower_removed": bool(removed_blocks or removed_scheduler_groups),
        "original_tower_blocks": starts_before,
        "original_tower_block_ids": dict(sorted(tower_id_counts.items())),
        "original_post_tower_wipes": post_starts_before,
        "removed_tower_blocks": removed_blocks,
        "removed_scheduler_primary_fill_groups": removed_scheduler_groups,
        "removed_scheduler_primary_fill_markers": removed_scheduler_primary_markers,
        "removed_scheduler_completion_markers": removed_scheduler_completion_markers,
        "removed_standalone_slot_comments": len(standalone_slot_comments),
        "removed_post_tower_wipes": removed_post,
        "sanitized_tower_exit_hops": sanitized_hops,
        "tower_exits_without_following_hop": exits_without_hop,
        "removed_tower_lines": removed_lines,
        "tower_markers_after": 0,
    }



def patch_v1106_two_colour_right_head_metadata(output: Path) -> dict:
    output = Path(output)
    seq_name = "Metadata/filament_sequence.json"
    plate_name = "Metadata/plate_1.json"
    slice_name = "Metadata/slice_info.config"
    with zipfile.ZipFile(output, "r") as z:
        seq = json.loads(z.read(seq_name).decode("utf-8"))
        plate = json.loads(z.read(plate_name).decode("utf-8"))
        slice_bytes = z.read(slice_name)

    sp = seq.setdefault("plate_1", {})
    sequence = list(sp.get("sequence") or [])
    if not sequence or any(v not in (BLACK_SLOT_ONE_BASED, 15) for v in sequence):
        raise RuntimeError(f"V1.90 METADATA: unexpected emitted sequence {sequence!r}")
    if BLACK_SLOT_ONE_BASED not in sequence or 15 not in sequence:
        raise RuntimeError(f"V1.90 METADATA: sequence must include black and cyan: {sequence!r}")
    sp["nozzle_sequence"] = [1] * len(sequence)
    assignment_len = max(17, len(sp.get("optimal_assignment") or []))
    assignment = [0] * assignment_len
    assignment[BLACK_SLOT_ONE_BASED - 1] = 1
    assignment[15 - 1] = 1
    sp["optimal_assignment"] = assignment
    sp["fc3d_v1106_head_rule"] = "PETG BLACK slot9 and PETG C slot15 both use physical right/colour head"

    plate["filament_colors"] = [BLACK_HEX, "#76D9F4"]
    plate["filament_ids"] = [BLACK_RAW_TOOL, 14]
    plate["first_extruder"] = BLACK_RAW_TOOL
    plate["nozzle_diameter"] = ROAD_WIDTH_MM
    for obj in plate.get("bbox_objects", []) or []:
        if isinstance(obj, dict):
            obj["layer_height"] = LAYER_H_MM

    root = ET.fromstring(slice_bytes)
    plate_node = root.find("plate")
    if plate_node is None:
        raise RuntimeError("V1.90 METADATA: missing slice <plate>")
    metadata_nodes = {n.attrib.get("key"): n for n in plate_node.findall("metadata") if n.attrib.get("key")}
    maps = ["1"] * 16
    maps[BLACK_SLOT_ONE_BASED - 1] = "2"
    maps[15 - 1] = "2"
    if "filament_maps" in metadata_nodes:
        metadata_nodes["filament_maps"].set("value", " ".join(maps))
    else:
        ET.SubElement(plate_node, "metadata", key="filament_maps", value=" ".join(maps))

    existing = {n.attrib.get("id"): dict(n.attrib) for n in plate_node.findall("filament")}
    for node in list(plate_node.findall("filament")):
        plate_node.remove(node)
    for slot, colour in ((BLACK_SLOT_ONE_BASED, BLACK_HEX), (15, "#76D9F4")):
        prev = existing.get(str(slot), {})
        ET.SubElement(
            plate_node,
            "filament",
            id=str(slot),
            tray_info_idx=prev.get("tray_info_idx", "GFG99"),
            type="PETG",
            color=colour,
            used_m=prev.get("used_m", "0"),
            used_g=prev.get("used_g", "0"),
            group_id="1",
            nozzle_diameter=f"{ROAD_WIDTH_MM:.2f}",
            volume_type="High Flow",
            used_for_object="true",
            used_for_support="false",
            total_load_time=prev.get("total_load_time", "15.00"),
            total_unload_time=prev.get("total_unload_time", "0.00"),
        )

    for node in list(plate_node.findall("nozzle")):
        plate_node.remove(node)
    ET.SubElement(
        plate_node, "nozzle", id="1", extruder_id="2",
        nozzle_diameter="0.4", volume_type="High Flow",
    )

    layer_lists = plate_node.find("layer_filament_lists")
    if layer_lists is not None:
        for node in list(layer_lists):
            layer_lists.remove(node)
        ET.SubElement(layer_lists, "layer_filament_list", filament_list=f"{BLACK_RAW_TOOL} 14", layer_ranges="0 0")
        ET.SubElement(layer_lists, "layer_filament_list", filament_list=str(BLACK_RAW_TOOL), layer_ranges=f"1 {PHYSICAL_LAYER_COUNT - 1}")

    _replace_zip_members(
        output,
        {
            seq_name: json.dumps(seq, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
            plate_name: json.dumps(plate, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
            slice_name: ET.tostring(root, encoding="utf-8", xml_declaration=True),
        },
    )
    return audit_v1106_two_colour_right_head_metadata(output)


def audit_v1106_two_colour_right_head_metadata(output: Path) -> dict:
    output = Path(output)
    with zipfile.ZipFile(output, "r") as z:
        seq = json.loads(z.read("Metadata/filament_sequence.json").decode("utf-8"))
        plate = json.loads(z.read("Metadata/plate_1.json").decode("utf-8"))
        root = ET.fromstring(z.read("Metadata/slice_info.config"))
        gcode = z.read("Metadata/plate_1.gcode").decode("utf-8", errors="replace")
    sp = seq.get("plate_1", {})
    sequence = list(sp.get("sequence") or [])
    nozzle_sequence = list(sp.get("nozzle_sequence") or [])
    if not sequence or any(v not in (BLACK_SLOT_ONE_BASED, 15) for v in sequence):
        raise RuntimeError(f"V1.90 METADATA AUDIT: sequence {sequence!r}")
    if nozzle_sequence != [1] * len(sequence):
        raise RuntimeError(f"V1.90 METADATA AUDIT: nozzle_sequence {nozzle_sequence!r}")
    if plate.get("filament_ids") != [BLACK_RAW_TOOL, 14] or plate.get("first_extruder") != BLACK_RAW_TOOL:
        raise RuntimeError(f"V1.90 METADATA AUDIT: plate ids/first {plate.get('filament_ids')!r}/{plate.get('first_extruder')!r}")
    plate_node = root.find("plate")
    if plate_node is None:
        raise RuntimeError("V1.90 METADATA AUDIT: missing plate")
    meta = {n.attrib.get("key"): n.attrib.get("value") for n in plate_node.findall("metadata")}
    maps = str(meta.get("filament_maps", "")).split()
    if len(maps) < 15 or maps[8] != "2" or maps[14] != "2":
        raise RuntimeError(f"V1.90 METADATA AUDIT: right-head filament maps wrong: {maps!r}")
    filaments = {n.attrib.get("id"): n.attrib for n in plate_node.findall("filament")}
    if set(filaments) != {"9", "15"} or any(filaments[k].get("group_id") != "1" for k in filaments):
        raise RuntimeError(f"V1.90 METADATA AUDIT: filament records {filaments!r}")
    nozzles = plate_node.findall("nozzle")
    if len(nozzles) != 1 or nozzles[0].attrib.get("id") != "1" or nozzles[0].attrib.get("extruder_id") != "2":
        raise RuntimeError(f"V1.90 METADATA AUDIT: nozzle records {[n.attrib for n in nozzles]!r}")
    layer_lists_node = plate_node.find("layer_filament_lists")
    layer_lists = [n.attrib for n in list(layer_lists_node)] if layer_lists_node is not None else []
    expected_lists = [
        {"filament_list": f"{BLACK_RAW_TOOL} 14", "layer_ranges": "0 0"},
        {"filament_list": str(BLACK_RAW_TOOL), "layer_ranges": f"1 {PHYSICAL_LAYER_COUNT - 1}"},
    ]
    if layer_lists != expected_lists:
        raise RuntimeError(f"V1.90 METADATA AUDIT: layer lists {layer_lists!r}")

    swap_starts = [line for line in gcode.splitlines() if "FC3D_PPSPV43_FULL_H2C_SWAP_START" in line]
    if len(swap_starts) != 2:
        raise RuntimeError(f"V1.90 METADATA AUDIT: expected two swaps, got {len(swap_starts)}")
    for line in swap_starts:
        if "current_hotend=0" not in line or "target_hotend=0" not in line or "side_change=0" not in line:
            raise RuntimeError(f"V1.90 METADATA AUDIT: swap not confined to right head: {line}")
    blocks = gcode.split("; ===== FC3D_PPSPV43_FULL_H2C_SWAP_START")
    for block in blocks[1:]:
        block = block.split("; ===== FC3D_PPSPV43_FULL_H2C_SWAP_END", 1)[0]
        if re.search(r"^M104\s+T1\b", block, re.M):
            raise RuntimeError("V1.90 METADATA AUDIT: left hotend T1 command found inside label material swap")
    return {
        "sequence": sequence,
        "nozzle_sequence": nozzle_sequence,
        "filament_ids": plate.get("filament_ids"),
        "first_extruder": plate.get("first_extruder"),
        "right_head_slots": [BLACK_SLOT_ONE_BASED, 15],
        "swap_count": len(swap_starts),
        "layer_filament_lists": layer_lists,
    }


def patch_right_head_metadata(output: Path) -> dict:
    output = Path(output)
    seq_name = "Metadata/filament_sequence.json"
    plate_name = "Metadata/plate_1.json"
    slice_name = "Metadata/slice_info.config"

    with zipfile.ZipFile(output, "r") as z:
        for n in (seq_name, plate_name, slice_name):
            if n not in z.namelist():
                raise RuntimeError(f"Generated package lacks required metadata member {n}")
        seq = json.loads(z.read(seq_name).decode("utf-8"))
        plate = json.loads(z.read(plate_name).decode("utf-8"))
        slice_bytes = z.read(slice_name)

    sp = seq.setdefault("plate_1", {})
    existing_assignment = sp.get("optimal_assignment")
    assignment_len = (
        len(existing_assignment)
        if isinstance(existing_assignment, list) and existing_assignment
        else 16
    )
    sp["sequence"] = [BLACK_SLOT_ONE_BASED]
    sp["nozzle_sequence"] = [1]
    sp["optimal_assignment"] = [0] * assignment_len

    plate["filament_colors"] = [BLACK_HEX]
    plate["filament_ids"] = [BLACK_RAW_TOOL]
    plate["first_extruder"] = BLACK_RAW_TOOL
    plate["nozzle_diameter"] = ROAD_WIDTH_MM
    for obj in plate.get("bbox_objects", []) or []:
        if isinstance(obj, dict):
            obj["layer_height"] = LAYER_H_MM

    root = ET.fromstring(slice_bytes)
    plate_node = root.find("plate")
    if plate_node is None:
        raise RuntimeError("slice_info.config has no <plate> node")

    metadata_nodes = {
        n.attrib.get("key"): n
        for n in plate_node.findall("metadata")
        if n.attrib.get("key")
    }
    filament_maps = ["1"] * 16
    filament_maps[BLACK_SLOT_ONE_BASED - 1] = "2"
    if "filament_maps" in metadata_nodes:
        metadata_nodes["filament_maps"].set("value", " ".join(filament_maps))
    else:
        ET.SubElement(plate_node, "metadata", key="filament_maps", value=" ".join(filament_maps))

    for node in list(plate_node.findall("filament")):
        plate_node.remove(node)
    ET.SubElement(
        plate_node,
        "filament",
        id=str(BLACK_SLOT_ONE_BASED),
        tray_info_idx="GFG99",
        type="PETG",
        color=BLACK_HEX,
        used_m="0",
        used_g="0",
        group_id="1",
        nozzle_diameter=f"{ROAD_WIDTH_MM:.2f}",
        volume_type="High Flow",
        used_for_object="true",
        used_for_support="false",
        total_load_time="15.00",
        total_unload_time="0.00",
    )

    for node in list(plate_node.findall("nozzle")):
        plate_node.remove(node)
    ET.SubElement(
        plate_node, "nozzle", id="1", extruder_id="2",
        nozzle_diameter="0.4", volume_type="High Flow",
    )

    layer_lists = plate_node.find("layer_filament_lists")
    if layer_lists is not None:
        for node in list(layer_lists):
            layer_lists.remove(node)
        ET.SubElement(
            layer_lists,
            "layer_filament_list",
            filament_list=str(BLACK_RAW_TOOL),
            layer_ranges=f"0 {PHYSICAL_LAYER_COUNT - 1}",
        )

    slice_out = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    _replace_zip_members(
        output,
        {
            seq_name: json.dumps(seq, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
            plate_name: json.dumps(plate, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
            slice_name: slice_out,
        },
    )

    return audit_right_head_metadata(output)


def audit_right_head_metadata(output: Path) -> dict:
    output = Path(output)
    with zipfile.ZipFile(output, "r") as z:
        seq = json.loads(z.read("Metadata/filament_sequence.json").decode("utf-8"))
        plate = json.loads(z.read("Metadata/plate_1.json").decode("utf-8"))
        root = ET.fromstring(z.read("Metadata/slice_info.config"))
        gcode = z.read("Metadata/plate_1.gcode").decode("utf-8", errors="replace")

    sp = seq.get("plate_1", {})
    if sp.get("sequence") != [BLACK_SLOT_ONE_BASED]:
        raise RuntimeError(f"RIGHT-HEAD AUDIT: sequence={sp.get('sequence')!r}")
    if sp.get("nozzle_sequence") != [1]:
        raise RuntimeError(f"RIGHT-HEAD AUDIT: nozzle_sequence={sp.get('nozzle_sequence')!r}")
    if plate.get("filament_ids") != [BLACK_RAW_TOOL]:
        raise RuntimeError(f"RIGHT-HEAD AUDIT: filament_ids={plate.get('filament_ids')!r}")
    if plate.get("first_extruder") != BLACK_RAW_TOOL:
        raise RuntimeError(f"RIGHT-HEAD AUDIT: first_extruder={plate.get('first_extruder')!r}")

    plate_node = root.find("plate")
    if plate_node is None:
        raise RuntimeError("RIGHT-HEAD AUDIT: missing slice <plate>")

    meta = {n.attrib.get("key"): n.attrib.get("value") for n in plate_node.findall("metadata")}
    maps = str(meta.get("filament_maps", "")).split()
    if len(maps) < BLACK_SLOT_ONE_BASED or maps[BLACK_SLOT_ONE_BASED - 1] != "2":
        raise RuntimeError(f"RIGHT-HEAD AUDIT: slot-9 filament_maps is not 2: {maps!r}")

    filaments = plate_node.findall("filament")
    if len(filaments) != 1 or filaments[0].attrib.get("id") != "9":
        raise RuntimeError("RIGHT-HEAD AUDIT: slice_info does not contain exactly filament id=9")
    if filaments[0].attrib.get("group_id") != "1":
        raise RuntimeError("RIGHT-HEAD AUDIT: slot-9 group_id is not 1")

    nozzles = plate_node.findall("nozzle")
    if len(nozzles) != 1:
        raise RuntimeError("RIGHT-HEAD AUDIT: expected exactly one nozzle record")
    if nozzles[0].attrib.get("id") != "1" or nozzles[0].attrib.get("extruder_id") != "2":
        raise RuntimeError(f"RIGHT-HEAD AUDIT: wrong nozzle record {nozzles[0].attrib!r}")

    raw_tool8_refs = 0
    for line in gcode.splitlines():
        if re.search(r"\bI8\b", line) or re.search(r"\bT8\b", line) or re.search(r"\bS8A\b", line):
            raw_tool8_refs += 1
    if raw_tool8_refs == 0:
        raise RuntimeError("RIGHT-HEAD AUDIT: executable G-code contains no raw-tool-8 reference")

    if "FC3D_PPSPV43_FULL_H2C_SWAP_START" in gcode:
        raise RuntimeError("RIGHT-HEAD AUDIT: unexpected full H2C swap remains in single-material job")
    if "FC3D_V169_JOB_ACTIVE_MATERIALS W B" in gcode:
        raise RuntimeError("RIGHT-HEAD AUDIT: job still reports active W,B instead of single-material W")

    return {
        "sequence": sp["sequence"],
        "nozzle_sequence": sp["nozzle_sequence"],
        "filament_ids": plate["filament_ids"],
        "first_extruder": plate["first_extruder"],
        "slice_filament_maps_slot9": maps[8],
        "slice_nozzle_id": nozzles[0].attrib.get("id"),
        "slice_extruder_id": nozzles[0].attrib.get("extruder_id"),
        "raw_tool8_reference_lines": raw_tool8_refs,
    }


def geometry_report(bottom_angle_deg: float, middle_angle_deg: float, top_angle_deg: float) -> dict:
    report = {
        "script": SCRIPT_VERSION,
        "panel_width_x_mm": PANEL_WIDTH_X_MM,
        "panel_height_z_mm": PANEL_HEIGHT_Z_MM,
        "panel_depth_y_mm": TOTAL_DEPTH_Y_MM,
        "panel_y_offset_mm": PANEL_Y_OFFSET_MM,
        "overall_layout_depth_y_mm": TOTAL_LAYOUT_DEPTH_Y_MM,
        "overall_x_span_mm": TOTAL_X_MM,
        "physical_layer_height_mm": LAYER_H_MM,
        "physical_layers": PHYSICAL_LAYER_COUNT,
        "direct_layers_above_base": DIRECT_OPTICAL_LAYER_COUNT,
        "road_width_mm": ROAD_WIDTH_MM,
        "optical_region_depth_y_mm": OPTICAL_REGION_DEPTH_Y_MM,
        "bottom_tip_depth_mm": BOTTOM_TIP_DEPTH_MM,
        "constant_tooth_pitch_mm": CONSTANT_TOOTH_PITCH_MM,
        "backbone_depth_y_mm": BACKBONE_DEPTH_Y_MM,
        "optical_backbone_overlap_mm": BACKBONE_OVERLAP_MM,
        "calibrated_e_per_mm": CALIBRATED_E_PER_MM,
        "panels": [],
    }

    for idx, (name, ang) in enumerate((
        ("FRONT_bottom_of_100in_screen_viewer_corrected", float(bottom_angle_deg)),
        ("MIDDLE_middle_of_100in_screen_viewer_corrected", float(middle_angle_deg)),
        ("REAR_top_of_100in_screen_viewer_corrected", float(top_angle_deg)),
    )):
        segs = _optical_segments_for_panel(idx, ang, 0.0, 0.0)
        if not segs:
            raise RuntimeError(f"{name}: no optical roads generated")
        s = segs[0]
        length = math.hypot(s[2] - s[0], s[3] - s[1])
        x_shift = abs(s[2] - s[0])
        front_pitch = optical_front_pitch_for_angle(ang)
        report["panels"].append({
            "name": name,
            "panel_y_offset_mm": idx * PANEL_Y_OFFSET_MM,
            "angle_deg_in_xy": ang,
            "optical_roads_per_cross_section": len(segs),
            "road_path_length_mm": length,
            "rearward_x_shift_mm": x_shift,
            "tooth_pitch_x_mm": front_pitch,
            "reflective_facet_run_x_mm": optical_geometry_for_angle(ang)["facet_run_x_mm"],
            "reflective_facet_depth_y_mm": optical_geometry_for_angle(ang)["facet_rise_y_mm"],
            "front_tip_centre_y_mm": optical_geometry_for_angle(ang)["front_tip_centre_y_mm"],
            "segments_per_cross_section": len(segs),
            "teeth_per_cross_section": len(segs) // 3,
            "return_angle_deg": optical_geometry_for_angle(ang)["return_angle_deg"],
            "return_run_x_mm": optical_geometry_for_angle(ang)["return_run_x_mm"],
            "rear_land_x_mm": optical_geometry_for_angle(ang)["rear_land_x_mm"],
        })
    return report



def audit_louver_backbone_clearance(
    bottom_angle_deg: float,
    middle_angle_deg: float,
    top_angle_deg: float,
) -> dict:
    """Validate optical facet -> 75-deg return -> rear-land topology and backbone interface."""
    report={"panels":[]}
    for panel_idx,angle in enumerate((bottom_angle_deg,middle_angle_deg,top_angle_deg)):
        segs=_optical_segments_for_panel(panel_idx,angle,0.0,0.0)
        if len(segs)%3 != 0:
            raise RuntimeError(f"LOUVER INTERFACE AUDIT panel {panel_idx}: segment count {len(segs)} not divisible by 3")
        n=len(segs)//3
        if n<=0: raise RuntimeError(f"LOUVER INTERFACE AUDIT panel {panel_idx}: no teeth")
        g=optical_geometry_for_angle(angle)
        panel_y0=_panel_y_origin(panel_idx,0.0)
        y_rear=panel_y0+g["rear_anchor_centre_y_mm"]
        y_front=panel_y0+g["front_tip_centre_y_mm"]
        prev=None
        for j in range(n):
            opt,ret,land=segs[3*j:3*j+3]
            if abs(opt[1]-y_rear)>1e-9 or abs(opt[3]-y_front)>1e-9:
                raise RuntimeError(f"LOUVER INTERFACE AUDIT panel {panel_idx} tooth {j}: optical Y envelope")
            if abs(ret[1]-y_front)>1e-9 or abs(ret[3]-y_rear)>1e-9:
                raise RuntimeError(f"LOUVER INTERFACE AUDIT panel {panel_idx} tooth {j}: return Y envelope")
            if abs(land[1]-y_rear)>1e-9 or abs(land[3]-y_rear)>1e-9:
                raise RuntimeError(f"LOUVER INTERFACE AUDIT panel {panel_idx} tooth {j}: land not on rear plane")
            if abs((opt[2]-opt[0])-g["facet_run_x_mm"])>1e-9:
                raise RuntimeError(f"LOUVER INTERFACE AUDIT panel {panel_idx} tooth {j}: optical run mismatch")
            ret_angle=math.degrees(math.atan2(abs(ret[3]-ret[1]),abs(ret[2]-ret[0])))
            if abs(ret_angle-RETURN_ANGLE_DEG)>1e-8:
                raise RuntimeError(f"LOUVER INTERFACE AUDIT panel {panel_idx} tooth {j}: return angle {ret_angle}")
            if abs((land[2]-land[0])-g["rear_land_x_mm"])>1e-9:
                raise RuntimeError(f"LOUVER INTERFACE AUDIT panel {panel_idx} tooth {j}: land length mismatch")
            if math.hypot(opt[2]-ret[0],opt[3]-ret[1])>1e-9 or math.hypot(ret[2]-land[0],ret[3]-land[1])>1e-9:
                raise RuntimeError(f"LOUVER INTERFACE AUDIT panel {panel_idx} tooth {j}: internal discontinuity")
            if prev is not None and math.hypot(prev[0]-opt[0],prev[1]-opt[1])>1e-9:
                raise RuntimeError(f"LOUVER INTERFACE AUDIT panel {panel_idx} tooth {j}: tooth-to-tooth discontinuity")
            prev=(land[2],land[3])
        bb0=_backbone_segments_for_panel(panel_idx,0,0.0,0.0)
        first_backbone_centre=bb0[0][1]
        backbone_sep=first_backbone_centre-y_rear
        if abs(backbone_sep-ROAD_WIDTH_MM)>1e-9:
            raise RuntimeError(f"LOUVER INTERFACE AUDIT panel {panel_idx}: backbone separation {backbone_sep}")
        report["panels"].append({
            "panel_index":panel_idx,"angle_deg":float(angle),"tooth_count":n,
            "source_segments_per_tooth":3,"facet_run_x_mm":g["facet_run_x_mm"],
            "tip_depth_mm":g["tip_depth_mm"],"return_angle_deg":RETURN_ANGLE_DEG,
            "return_run_x_mm":g["return_run_x_mm"],"rear_land_x_mm":g["rear_land_x_mm"],
            "tooth_pitch_x_mm":g["front_pitch_x_mm"],"panel_y_offset_mm":panel_y0,
            "rear_anchor_y_mm":y_rear,"first_backbone_centre_y_mm":first_backbone_centre,
            "backbone_centre_sep_from_anchor_mm":backbone_sep,
            "backbone_rear_edge_y_mm":panel_y0+TOTAL_DEPTH_Y_MM,
            "layer0_backbone_road_count":len(bb0),
        })
    return report

def dry_validate(dp, bottom_angle_deg: float, middle_angle_deg: float, top_angle_deg: float, patch_report: dict):
    rear_interface = audit_louver_backbone_clearance(bottom_angle_deg, middle_angle_deg, top_angle_deg)
    print("SAWTOOTH/BACKBONE REAR INTERFACE AUDIT: PASS")
    print(json.dumps(rear_interface, indent=2, sort_keys=True))

    # v1.43 contract: backbone orientation never alternates.
    for panel_index in range(PANEL_COUNT):
        parity_counts = []
        for logical_layer in (0, 1):
            roads = _backbone_segments_for_panel(
                panel_index, logical_layer, 0.0, 0.0
            )
            if not roads:
                raise RuntimeError(
                    f"DRY VALIDATION: no backbone roads panel={panel_index} layer={logical_layer}"
                )
            for road in roads:
                if abs(float(road[1]) - float(road[3])) > 1e-9:
                    raise RuntimeError(
                        f"DRY VALIDATION: non-X backbone road panel={panel_index} "
                        f"layer={logical_layer}: {road}"
                    )
            parity_counts.append(len(roads))
        if parity_counts[0] != parity_counts[1]:
            raise RuntimeError(
                f"DRY VALIDATION: backbone road count changed with parity "
                f"panel={panel_index}: {parity_counts}"
            )
    print("X-ONLY BACKBONE AUDIT: PASS")

    layer0_test = make_layer_segments(
        0, bottom_angle_deg, middle_angle_deg, top_angle_deg, 0.0, 0.0, ("W", "F", "R", "Y", "G", "C", "B")
    )[LOGICAL_MATERIAL]
    expected_bb0 = []
    for panel_index in range(PANEL_COUNT):
        expected_bb0 += _backbone_segments_for_panel(panel_index, 0, 0.0, 0.0)
    if layer0_test[:len(expected_bb0)] != expected_bb0:
        raise RuntimeError("DRY VALIDATION: logical layer 0 does not begin with all three backbones")

    emitter_optical = layer0_test[len(expected_bb0):]
    expected_emitter_optical = []
    for panel_index, angle_deg in enumerate(
        (bottom_angle_deg, middle_angle_deg, top_angle_deg)
    ):
        expected_emitter_optical += _emitter_optical_segments_for_panel(
            panel_index, angle_deg, 0.0, 0.0
        )
    if emitter_optical != expected_emitter_optical:
        raise RuntimeError("DRY VALIDATION: emitter optical stream contract mismatch")
    if any(abs(s[1] - s[3]) < 1e-9 for s in emitter_optical):
        raise RuntimeError(
            "DRY VALIDATION: axis-aligned rear land leaked into v1.179 emitter stream"
        )

    # install_patches() has already converted both source layer-height roles to
    # the physical 0.10-mm layer used by this wrapper.  The original v1.179
    # 0.20/0.10 semantics are checked fail-closed inside install_patches()
    # before this conversion.
    if (
        abs(float(getattr(dp, "BASE_H_MM", -1.0)) - LAYER_H_MM) > 1e-9
        or abs(float(getattr(dp, "MIX_H_MM", -1.0)) - LAYER_H_MM) > 1e-9
    ):
        raise RuntimeError(
            "DRY VALIDATION: patched source layer heights are not both 0.10 mm"
        )


def enforce_first_layer_backbone_then_sawtooth(
    output: Path,
    bottom_angle_deg: float,
    middle_angle_deg: float,
    top_angle_deg: float,
) -> dict:
    """Enforce backbone-first execution on physical layer 0 for all test cards."""
    output = Path(output)
    gcode_name = "Metadata/plate_1.gcode"
    with zipfile.ZipFile(output, "r") as z:
        gcode = z.read(gcode_name).decode("utf-8", errors="replace")

    lines = gcode.splitlines()
    layer_re = re.compile(r";\s*DIRECT_LAYER\s+V4\s+physical=(\d+)")
    e_re = re.compile(r"\sE([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")

    layer_starts = [i for i, line in enumerate(lines) if layer_re.search(line)]
    if len(layer_starts) < 2:
        raise RuntimeError("FIRST-LAYER ORDER: physical layer 0/1 boundaries missing")

    s0, s1 = layer_starts[0], layer_starts[1]
    block = lines[s0:s1]
    feature_rel = next((
        i for i, line in enumerate(block)
        if line.strip().startswith("; FEATURE: DIRECT_DETERMINISTIC_ROADS_")
    ), None)
    if feature_rel is None:
        raise RuntimeError("FIRST-LAYER ORDER: model feature marker missing")

    panel_starts = []
    panel_ends = []
    for panel in range(PANEL_COUNT):
        ps = next((i for i, line in enumerate(block)
                   if f"FC3D_V140_LOUVER_PANEL_START layer=0 panel={panel}" in line), None)
        pe = next((i for i, line in enumerate(block)
                   if f"FC3D_V140_LOUVER_PANEL_END layer=0 panel={panel}" in line), None)
        if ps is None or pe is None:
            raise RuntimeError(
                f"FIRST-LAYER ORDER: complete sawtooth markers missing for panel {panel}"
            )
        panel_starts.append(ps)
        panel_ends.append(pe)

    order = [feature_rel]
    for ps, pe in zip(panel_starts, panel_ends):
        order += [ps, pe]
    if order != sorted(order) or len(set(order)) != len(order):
        raise RuntimeError("FIRST-LAYER ORDER: sawtooth marker sequence invalid")

    last_panel_end = panel_ends[-1]
    backbone_start = next((
        i for i in range(last_panel_end + 1, len(block))
        if block[i].strip().startswith("; STUDIO_LOCAL_TILE_MM:")
    ), None)
    if backbone_start is None:
        backbone_start = next((
            i for i in range(feature_rel + 1, panel_starts[0])
            if block[i].strip().startswith("; STUDIO_LOCAL_TILE_MM:")
        ), None)
    if backbone_start is None:
        raise RuntimeError("FIRST-LAYER ORDER: actual backbone STUDIO_LOCAL_TILE_MM block missing")

    backbone_end_candidates = [
        i for i in range(backbone_start, len(block))
        if "retract end of local tile" in block[i]
    ]
    if not backbone_end_candidates:
        raise RuntimeError("FIRST-LAYER ORDER: backbone final retract missing")
    backbone_end = backbone_end_candidates[-1]

    hop_candidates = [
        i for i in range(feature_rel + 1, panel_starts[0])
        if "FC3D_PPSPV62_STUDIO_SAFE_VERTICAL_CHECKED_HOP" in block[i]
        and "reason=SEGMENT_START" in block[i]
    ]
    if not hop_candidates:
        raise RuntimeError(
            "FIRST-LAYER ORDER: emitted sawtooth SEGMENT_START safe-hop marker missing"
        )
    optical_start = hop_candidates[-1]
    if optical_start > feature_rel + 1 and block[optical_start - 1].strip().startswith("M204 "):
        optical_start -= 1

    optical_end = None
    scan_hi = backbone_start if backbone_start > last_panel_end else len(block)
    for i in range(last_panel_end + 1, scan_hi):
        em = e_re.search(block[i])
        if em and float(em.group(1)) < 0.0:
            optical_end = i
            break
    if optical_end is None:
        raise RuntimeError(
            f"FIRST-LAYER ORDER: final panel-{PANEL_COUNT - 1} sawtooth retract missing"
        )

    originally_backbone_first = backbone_end < optical_start
    reordered = False
    if not originally_backbone_first:
        if not (
            feature_rel < optical_start <= panel_starts[0]
            and panel_ends[-1] < optical_end < backbone_start <= backbone_end
        ):
            raise RuntimeError(
                "FIRST-LAYER ORDER: unexpected layer-0 block topology; refusing to reorder"
            )
        header = block[:optical_start]
        optical = block[optical_start:optical_end + 1]
        between = block[optical_end + 1:backbone_start]
        backbone = block[backbone_start:backbone_end + 1]
        tail = block[backbone_end + 1:]
        reordered_block = (
            header
            + ["; FC3D_V131_LAYER0_ORDER backbone_then_sawtooth"]
            + between
            + backbone
            + optical
            + tail
        )
        lines = lines[:s0] + reordered_block + lines[s1:]
        _replace_zip_members(
            output, {gcode_name: ("\n".join(lines) + "\n").encode("utf-8")}
        )
        reordered = True

    with zipfile.ZipFile(output, "r") as z:
        final_gcode = z.read(gcode_name).decode("utf-8", errors="replace")
    flines = final_gcode.splitlines()
    fstarts = [i for i, line in enumerate(flines) if layer_re.search(line)]
    fb = flines[fstarts[0]:fstarts[1]]

    f_feature = next(i for i, line in enumerate(fb)
                     if line.strip().startswith("; FEATURE: DIRECT_DETERMINISTIC_ROADS_"))
    f_backbone_start = next(i for i, line in enumerate(fb)
                            if line.strip().startswith("; STUDIO_LOCAL_TILE_MM:"))
    f_backbone_end = max(i for i, line in enumerate(fb)
                         if "retract end of local tile" in line)
    f_panel_starts = [
        next(i for i, line in enumerate(fb)
             if f"FC3D_V140_LOUVER_PANEL_START layer=0 panel={panel}" in line)
        for panel in range(PANEL_COUNT)
    ]
    f_panel_ends = [
        next(i for i, line in enumerate(fb)
             if f"FC3D_V140_LOUVER_PANEL_END layer=0 panel={panel}" in line)
        for panel in range(PANEL_COUNT)
    ]
    if not (f_feature < f_backbone_start <= f_backbone_end < f_panel_starts[0]):
        raise RuntimeError(
            "FIRST-LAYER ORDER FINAL AUDIT: backbone is not before sawtooth"
        )
    marker_order = []
    for ps, pe in zip(f_panel_starts, f_panel_ends):
        marker_order += [ps, pe]
    if marker_order != sorted(marker_order):
        raise RuntimeError("FIRST-LAYER ORDER FINAL AUDIT: panel marker order invalid")

    def positive_e_xy(line: str) -> bool:
        s = line.strip()
        if not s.startswith("G1"):
            return False
        if " X" not in (" " + s) and " Y" not in (" " + s):
            return False
        em = e_re.search(line)
        return bool(em and float(em.group(1)) > 0.0)

    backbone_draws = [
        i for i in range(f_backbone_start, f_backbone_end + 1)
        if positive_e_xy(fb[i])
    ]
    expected_backbone_draws = sum(
        len(_backbone_segments_for_panel(panel, 0, 0.0, 0.0))
        for panel in range(PANEL_COUNT)
    )
    if len(backbone_draws) != expected_backbone_draws:
        raise RuntimeError(
            "FIRST-LAYER ORDER FINAL AUDIT: expected "
            f"{expected_backbone_draws} backbone positive-E XY moves, "
            f"found {len(backbone_draws)}"
        )

    transition = fb[f_backbone_end + 1:f_panel_starts[0]]
    if any(positive_e_xy(line) for line in transition):
        raise RuntimeError(
            "FIRST-LAYER ORDER FINAL AUDIT: positive-E XY draw in backbone->sawtooth transition"
        )
    hop_rel = next((
        i for i, line in enumerate(transition)
        if "FC3D_PPSPV62_STUDIO_SAFE_VERTICAL_CHECKED_HOP" in line
        and "reason=SEGMENT_START" in line
    ), None)
    if hop_rel is None:
        raise RuntimeError(
            "FIRST-LAYER ORDER FINAL AUDIT: safe lifted transition missing after reorder"
        )

    z_re = re.compile(r"\sZ([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    zvals = [float(m.group(1)) for line in transition if (m := z_re.search(line))]
    if not zvals:
        raise RuntimeError("FIRST-LAYER ORDER FINAL AUDIT: no Z motion in safe transition")
    nominal_z = LAYER_H_MM
    max_z = max(zvals)
    if max_z < nominal_z + 0.39:
        raise RuntimeError(
            f"FIRST-LAYER ORDER FINAL AUDIT: safe lift only {max_z - nominal_z:.3f} mm"
        )
    if not any(abs(z - nominal_z) <= 0.001 for z in zvals):
        raise RuntimeError(
            "FIRST-LAYER ORDER FINAL AUDIT: transition does not lower back to nominal Z"
        )

    reprime_seen = False
    for line in transition:
        em = e_re.search(line)
        stripped = line.strip()
        if (em and float(em.group(1)) > 0.0
                and " X" not in (" " + stripped) and " Y" not in (" " + stripped)):
            reprime_seen = True
    if not reprime_seen:
        raise RuntimeError(
            "FIRST-LAYER ORDER FINAL AUDIT: no E-only reprime before sawtooth"
        )

    return {
        "physical_layer": 0,
        "reordered_final_gcode": reordered,
        "backbone_before_sawtooth": True,
        "panel_count": PANEL_COUNT,
        "backbone_positive_e_xy_moves": len(backbone_draws),
        "backbone_final_retract": True,
        "safe_segment_start_hop_present": True,
        "safe_hop_max_z_mm": max_z,
        "safe_hop_above_nominal_mm": max_z - nominal_z,
        "lowered_to_nominal_before_sawtooth": True,
        "reprime_before_sawtooth": True,
    }

def apply_reference_cube_model_process(output: Path) -> dict:
    """Apply the known-good cube speeds/accelerations to backbone vs sawtooth."""
    output = Path(output)
    gcode_name = "Metadata/plate_1.gcode"
    with zipfile.ZipFile(output, "r") as z:
        gcode = z.read(gcode_name).decode("utf-8", errors="replace")

    lines = gcode.splitlines()
    layer_re = re.compile(r";\s*DIRECT_LAYER\s+V4\s+physical=(\d+)")
    e_re = re.compile(r"\sE([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    f_re = re.compile(r"\bF[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?\b")

    physical = None
    in_model = False
    optical_depth = 0
    counts = {
        "layer0_backbone_moves": 0,
        "layer0_optical_moves": 0,
        "later_backbone_moves": 0,
        "later_optical_moves": 0,
    }
    unclassified = []
    starts = 0
    ends = 0
    out = []

    def rewrite_feed(line: str, feed: float) -> str:
        token = f"F{feed:.3f}".rstrip("0").rstrip(".")
        if f_re.search(line):
            return f_re.sub(token, line, count=1)
        return line.rstrip() + " " + token

    for line_no, line in enumerate(lines, start=1):
        lm = layer_re.search(line)
        if lm:
            if optical_depth != 0:
                raise RuntimeError(
                    f"REFERENCE CUBE MODEL PROCESS: unterminated sawtooth marker before layer {physical} end"
                )
            physical = int(lm.group(1))
            in_model = False
            optical_depth = 0
            out.append(line)
            continue

        s = line.strip()
        if s.startswith("; FEATURE:"):
            in_model = "DIRECT_DETERMINISTIC_ROADS_" in s
            optical_depth = 0
            out.append(line)
            continue

        if in_model and "FC3D_V140_LOUVER_PANEL_START" in s:
            if optical_depth != 0:
                raise RuntimeError("REFERENCE CUBE MODEL PROCESS: nested sawtooth START marker")
            optical_depth = 1
            starts += 1
            out.append(line)
            continue
        if in_model and "FC3D_V140_LOUVER_PANEL_END" in s:
            if optical_depth != 1:
                raise RuntimeError("REFERENCE CUBE MODEL PROCESS: sawtooth END without START")
            optical_depth = 0
            ends += 1
            out.append(line)
            continue

        phase = "optical" if (in_model and optical_depth == 1) else ("backbone" if in_model else None)

        if in_model and s.startswith("M204 "):
            accel = None
            if phase == "backbone":
                accel = REFERENCE_FIRST_ACCEL_MM_S2 if physical == 0 else REFERENCE_LATER_FILL_ACCEL_MM_S2
            elif phase == "optical":
                accel = REFERENCE_FIRST_ACCEL_MM_S2 if physical == 0 else REFERENCE_LATER_WALL_ACCEL_MM_S2
            if accel is not None:
                line = f"M204 S{accel}"
            out.append(line)
            continue

        if in_model and s.startswith("G1"):
            has_xy = bool(re.search(r"\s[XY]", line))
            em = e_re.search(line)
            if has_xy and em and float(em.group(1)) > 0.0:
                if phase == "backbone":
                    feed = REFERENCE_FIRST_FILL_FEED_MM_MIN if physical == 0 else REFERENCE_LATER_FILL_FEED_MM_MIN
                    counts["layer0_backbone_moves" if physical == 0 else "later_backbone_moves"] += 1
                    line = rewrite_feed(line, feed)
                elif phase == "optical":
                    feed = REFERENCE_FIRST_WALL_FEED_MM_MIN if physical == 0 else REFERENCE_LATER_WALL_FEED_MM_MIN
                    counts["layer0_optical_moves" if physical == 0 else "later_optical_moves"] += 1
                    line = rewrite_feed(line, feed)
                else:
                    unclassified.append((line_no, physical, s))
        out.append(line)

    if optical_depth != 0:
        raise RuntimeError("REFERENCE CUBE MODEL PROCESS: final sawtooth marker left open")
    if unclassified:
        raise RuntimeError(
            "REFERENCE CUBE MODEL PROCESS: positive-E model moves were not classified; "
            f"count={len(unclassified)} sample={unclassified[:5]}"
        )
    expected_markers = PHYSICAL_LAYER_COUNT * PANEL_COUNT
    if starts != expected_markers or ends != expected_markers:
        raise RuntimeError(
            f"REFERENCE CUBE MODEL PROCESS: expected {expected_markers} START and END markers, "
            f"got starts={starts} ends={ends}"
        )
    if not all(counts.values()):
        raise RuntimeError(f"REFERENCE CUBE MODEL PROCESS: incomplete model mapping {counts}")

    new_gcode = "\n".join(out) + "\n"
    _replace_zip_members(output, {gcode_name: new_gcode.encode("utf-8")})
    return {
        **counts,
        "sawtooth_panel_start_markers_seen": starts,
        "sawtooth_panel_end_markers_seen": ends,
        "classification_basis": "explicit bracketed sawtooth START/END markers",
        "first_layer_backbone_mm_s": REFERENCE_FIRST_FILL_FEED_MM_MIN / 60.0,
        "first_layer_optical_mm_s": REFERENCE_FIRST_WALL_FEED_MM_MIN / 60.0,
        "later_backbone_mm_s": REFERENCE_LATER_FILL_FEED_MM_MIN / 60.0,
        "later_optical_mm_s": REFERENCE_LATER_WALL_FEED_MM_MIN / 60.0,
        "first_layer_accel_mm_s2": REFERENCE_FIRST_ACCEL_MM_S2,
        "later_backbone_accel_mm_s2": REFERENCE_LATER_FILL_ACCEL_MM_S2,
        "later_optical_accel_mm_s2": REFERENCE_LATER_WALL_ACCEL_MM_S2,
        "layer_height_mm": LAYER_H_MM,
        "road_width_mm": ROAD_WIDTH_MM,
        "nominal_e_per_mm": CALIBRATED_E_PER_MM,
        "first_layer_flow_multiplier": 1.0,
    }


def enforce_minimum_model_part_fan(output: Path) -> dict:
    """Force the normal part-cooling fan to at least 50% during model printing."""
    output = Path(output)
    gcode_name = "Metadata/plate_1.gcode"
    with zipfile.ZipFile(output, "r") as z:
        gcode = z.read(gcode_name).decode("utf-8", errors="replace")

    lines = gcode.splitlines()
    layer_re = re.compile(r";\s*DIRECT_LAYER\s+V4\s+physical=(\d+)")
    bare_m106_re = re.compile(r"^\s*M106(?!\s+P\d+)\s+S([-+]?\d*\.?\d+)(.*)$")

    in_model = False
    layer_assertions = 0
    clamped = 0
    out = []
    for line in lines:
        lm = layer_re.search(line)
        if lm:
            in_model = True
            out.append(line)
            out.append(f"M106 S{MIN_MODEL_PART_FAN_PWM} ; FC3D_V126_MIN_MODEL_PART_FAN physical={int(lm.group(1))}")
            layer_assertions += 1
            continue
        if in_model and line.strip().startswith("; V4_MODEL_END"):
            in_model = False
            out.append(line)
            continue
        if in_model:
            m = bare_m106_re.match(line)
            if m and float(m.group(1)) < MIN_MODEL_PART_FAN_PWM:
                line = f"M106 S{MIN_MODEL_PART_FAN_PWM}{m.group(2)} ; FC3D_V126_CLAMPED_MIN_FAN"
                clamped += 1
        out.append(line)

    new_gcode = "\n".join(out) + "\n"
    _replace_zip_members(output, {gcode_name: new_gcode.encode("utf-8")})
    return {
        "minimum_part_fan_pwm": MIN_MODEL_PART_FAN_PWM,
        "minimum_part_fan_percent": 100.0 * MIN_MODEL_PART_FAN_PWM / 255.0,
        "model_layer_assertions": layer_assertions,
        "existing_low_part_fan_commands_clamped": clamped,
    }



def enforce_active_right_black_nozzle_temperature(output: Path) -> dict:
    """
    Keep the physically active right-head black PETG nozzle at 255 C.

    The v1.179 single-logical-W startup was inherited from a left-head W job.
    After tool T8 (right-head black) is selected and heated, that startup still
    emits `M104 T0 S25 N0 ;Multi extruder pre cooling`, which explicitly cools
    the physical right hotend.  The prime tower previously reheated/activated
    that head before model extrusion; removing the tower exposed the stale
    pre-cool.

    Replace that one post-startup active-head pre-cool with an explicit 255 C
    target and wait before the first DIRECT_LAYER. Fail closed if the exact
    bad command is not present exactly once or if any later T0 target below
    print temperature occurs before model start.
    """
    output = Path(output)
    gcode_name = "Metadata/plate_1.gcode"
    with zipfile.ZipFile(output, "r") as z:
        gcode = z.read(gcode_name).decode("utf-8", errors="replace")

    lines = gcode.splitlines()
    model_i = next((i for i,l in enumerate(lines) if "; DIRECT_LAYER V4 physical=0" in l), None)
    if model_i is None:
        raise RuntimeError("RIGHT-NOZZLE TEMP AUDIT: physical layer 0 marker missing")

    bad_re = re.compile(r"^\s*M104\s+T0\s+S25(?:\.0+)?\s+N0\b.*Multi extruder pre cooling", re.I)
    bad = [i for i,l in enumerate(lines[:model_i]) if bad_re.search(l)]
    if len(bad) != 1:
        raise RuntimeError(
            f"RIGHT-NOZZLE TEMP AUDIT: expected exactly one active T0 S25 pre-cool before model, found {len(bad)}"
        )

    i = bad[0]
    lines[i] = (
        f"M104 T0 S{REFERENCE_NOZZLE_C} N0 "
        "; FC3D_V132_KEEP_ACTIVE_RIGHT_BLACK_AT_PRINT_TEMP"
    )
    lines.insert(
        i + 1,
        f"M109 S{REFERENCE_NOZZLE_C} "
        "; FC3D_V132_WAIT_ACTIVE_RIGHT_BLACK_BEFORE_MODEL",
    )
    model_i += 1

    # Final fail-closed scan from the correction to first model extrusion.
    active_t0_targets = []
    for j,l in enumerate(lines[i:model_i], start=i):
        m = re.match(r"^\s*M104\s+T0\s+S([-+]?\d*\.?\d+)", l, re.I)
        if m:
            active_t0_targets.append((j, float(m.group(1)), l.strip()))
    low = [x for x in active_t0_targets if x[1] < REFERENCE_NOZZLE_C - 1e-9]
    if low:
        raise RuntimeError(
            f"RIGHT-NOZZLE TEMP AUDIT: active T0 is cooled below {REFERENCE_NOZZLE_C} C before model: {low[:5]}"
        )

    wait_lines = [
        (j,l.strip()) for j,l in enumerate(lines[i:model_i], start=i)
        if re.match(rf"^\s*M109\s+S{REFERENCE_NOZZLE_C}(?:\.0+)?\b", l, re.I)
    ]
    if not wait_lines:
        raise RuntimeError(
            f"RIGHT-NOZZLE TEMP AUDIT: no M109 S{REFERENCE_NOZZLE_C} wait after active-head target"
        )

    new_gcode = "\n".join(lines) + "\n"
    _replace_zip_members(output, {gcode_name: new_gcode.encode("utf-8")})
    return {
        "physical_active_head": "right / thermal T0",
        "physical_black_raw_tool": BLACK_RAW_TOOL,
        "replaced_stale_active_head_precool": "M104 T0 S25 N0",
        "enforced_target_c": REFERENCE_NOZZLE_C,
        "wait_for_temperature_before_model": True,
        "active_t0_targets_below_255_after_fix_before_model": 0,
        "model_start_line_index": model_i,
    }

def audit_final_sawtooth_paths(
    output: Path,
    bottom_angle_deg: float,
    middle_angle_deg: float,
    top_angle_deg: float,
) -> dict:
    """Fail closed on final asymmetric-louver geometry and continuous panel paths."""
    output=Path(output); gcode_name="Metadata/plate_1.gcode"
    with zipfile.ZipFile(output,"r") as z:
        lines=z.read(gcode_name).decode("utf-8",errors="replace").splitlines()
    layer_re=re.compile(r";\s*DIRECT_LAYER\s+V4\s+physical=(\d+)")
    x_re=re.compile(r"\sX([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    y_re=re.compile(r"\sY([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    e_re=re.compile(r"\sE([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    expected=[]
    for p,ang in enumerate((bottom_angle_deg,middle_angle_deg,top_angle_deg)):
        g=optical_geometry_for_angle(ang)
        expected.append({
            "panel":p,"count":len(_optical_segments_for_panel(p,ang,0.0,0.0)),
            "vectors":[("optical",g["facet_run_x_mm"],g["facet_rise_y_mm"]),
                       ("return",g["return_run_x_mm"],g["facet_rise_y_mm"]),
                       ("land",g["rear_land_x_mm"],0.0)]})
    starts=[i for i,l in enumerate(lines) if layer_re.search(l)]; starts.append(len(lines))
    total=[0]*PANEL_COUNT; internal_retracts=0; internal_dry=0; markers={"start":0,"end":0}
    tol=0.04
    for li in range(len(starts)-1):
        block=lines[starts[li]:starts[li+1]]; xy=None; active=None
        recs={p:[] for p in range(PANEL_COUNT)}; retracts={p:0 for p in range(PANEL_COUNT)}; dry={p:0 for p in range(PANEL_COUNT)}
        for line in block:
            s=line.strip()
            sm=re.search(r"FC3D_V140_LOUVER_PANEL_START layer=\d+ panel=(\d+)",s)
            emk=re.search(r"FC3D_V140_LOUVER_PANEL_END layer=\d+ panel=(\d+)",s)
            if sm: active=int(sm.group(1)); markers["start"]+=1; continue
            if emk:
                if active!=int(emk.group(1)): raise RuntimeError(f"FINAL LOUVER AUDIT layer {li}: panel end mismatch")
                active=None; markers["end"]+=1; continue
            if not (s.startswith("G0") or s.startswith("G1")): continue
            xm,ym,ee=x_re.search(line),y_re.search(line),e_re.search(line)
            if active is not None and ee and float(ee.group(1))<0: retracts[active]+=1
            if xm or ym:
                old=xy; nx=float(xm.group(1)) if xm else (old[0] if old else None); ny=float(ym.group(1)) if ym else (old[1] if old else None)
                if nx is None or ny is None: continue
                new=(nx,ny)
                if active is not None and old is not None:
                    positive=s.startswith("G1") and ee and float(ee.group(1))>0
                    if not positive and math.hypot(new[0]-old[0],new[1]-old[1])>1e-6: dry[active]+=1
                    if positive: recs[active].append((old,new))
                xy=new
        if active is not None: raise RuntimeError(f"FINAL LOUVER AUDIT layer {li}: unterminated panel bracket")
        for ps in expected:
            p=ps["panel"]; rr=recs[p]
            if len(rr)!=ps["count"]: raise RuntimeError(f"FINAL LOUVER AUDIT layer {li} panel {p}: {len(rr)} segments expected {ps['count']}")
            for j,(a,b) in enumerate(rr):
                kind,ex,ey=ps["vectors"][j%3]; dx=b[0]-a[0]; dy=b[1]-a[1]
                if abs(abs(dx)-ex)>tol or abs(abs(dy)-ey)>tol:
                    raise RuntimeError(f"FINAL LOUVER AUDIT layer {li} panel {p} seg {j} {kind}: dx={dx:.4f} dy={dy:.4f}")
                if j:
                    gap=math.hypot(rr[j-1][1][0]-a[0],rr[j-1][1][1]-a[1])
                    if gap>0.002: raise RuntimeError(f"FINAL LOUVER AUDIT layer {li} panel {p}: continuity gap {gap:.4f}")
            if retracts[p] or dry[p]: raise RuntimeError(f"FINAL LOUVER AUDIT layer {li} panel {p}: internal retracts={retracts[p]} dry={dry[p]}")
            total[p]+=len(rr); internal_retracts+=retracts[p]; internal_dry+=dry[p]
    exp_markers=PHYSICAL_LAYER_COUNT*PANEL_COUNT
    if markers["start"]!=exp_markers or markers["end"]!=exp_markers:
        raise RuntimeError(f"FINAL LOUVER AUDIT: marker counts {markers} expected {exp_markers}")
    return {
        "physical_layers":PHYSICAL_LAYER_COUNT,"return_angle_deg":RETURN_ANGLE_DEG,
        "panel0_segments_per_layer":expected[0]["count"],"panel1_segments_per_layer":expected[1]["count"],
        "panel2_segments_per_layer":expected[2]["count"],"panel0_total_segments":total[0],
        "panel1_total_segments":total[1],"panel2_total_segments":total[2],
        "internal_retracts":internal_retracts,"internal_dry_xy_moves":internal_dry,
        "start_markers":markers["start"],"end_markers":markers["end"],
        "continuous_within_each_panel":True,
    }

def audit_final_panel_xz_geometry(output: Path) -> dict:
    """Fail closed on the three 200-mm cards, their Z stack and Y separation."""
    output = Path(output)
    gcode_name = "Metadata/plate_1.gcode"
    with zipfile.ZipFile(output, "r") as z:
        gcode = z.read(gcode_name).decode("utf-8", errors="replace")

    lines = gcode.splitlines()
    layer_re = re.compile(
        r";\s*DIRECT_LAYER\s+V4\s+physical=(\d+)\s+logical=\d+\s+z=([-+]?\d*\.?\d+)"
    )
    x_re = re.compile(r"\sX([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    y_re = re.compile(r"\sY([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    e_re = re.compile(r"\sE([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")

    layer_z = None
    in_model_feature = False
    model_points = []       # (x, y, z)
    layer_zs = {}
    model_move_records = [] # (line_no, start_xy, end_xy, e, line)
    current_xy = None

    for line_no, line in enumerate(lines, start=1):
        lm = layer_re.search(line)
        if lm:
            physical_layer = int(lm.group(1))
            layer_z = float(lm.group(2))
            layer_zs[physical_layer] = layer_z
            in_model_feature = False
            current_xy = None
            continue

        st = line.strip()
        if st.startswith("; FEATURE:"):
            in_model_feature = "DIRECT_DETERMINISTIC_ROADS_" in st
            current_xy = None
            continue
        if not in_model_feature or not (st.startswith("G0") or st.startswith("G1")):
            continue

        xm, ym, em = x_re.search(line), y_re.search(line), e_re.search(line)
        if not (xm or ym):
            continue
        old_xy = current_xy
        new_x = float(xm.group(1)) if xm else (old_xy[0] if old_xy else None)
        new_y = float(ym.group(1)) if ym else (old_xy[1] if old_xy else None)
        if new_x is None or new_y is None:
            continue
        new_xy = (new_x, new_y)
        if (st.startswith("G1") and em and float(em.group(1)) > 0.0
                and layer_z is not None):
            model_points.append((new_x, new_y, layer_z))
            model_move_records.append((line_no, old_xy, new_xy, float(em.group(1)), st))
        current_xy = new_xy

    if not model_points:
        raise RuntimeError(
            "FINAL XYZ AUDIT: no positive-E moves found inside DIRECT_DETERMINISTIC_ROADS"
        )

    zs = [layer_zs[k] for k in sorted(layer_zs)]
    if len(zs) != PHYSICAL_LAYER_COUNT:
        raise RuntimeError(
            f"FINAL XYZ AUDIT: expected {PHYSICAL_LAYER_COUNT} physical layers, found {len(zs)}"
        )
    expected_zs = [FIRST_LAYER_H_MM + i * LAYER_H_MM for i in range(PHYSICAL_LAYER_COUNT)]
    expected_first_z = expected_zs[0]
    expected_last_z = expected_zs[-1]
    if len(zs) != len(expected_zs) or any(abs(a-b) > 1e-6 for a,b in zip(zs, expected_zs)):
        raise RuntimeError(
            f"FINAL XYZ AUDIT: Z sequence {zs}, expected {expected_zs}"
        )

    # Resolve three Y clusters using the two largest gaps in the model-point Y
    # coordinates. Inter-card gaps are ~17 mm, while all intra-card Y gaps are
    # far smaller, so this is deliberately fail-closed for the 0/20/40 layout.
    unique_y = sorted(set(round(y, 5) for _x, y, _z in model_points))
    if len(unique_y) < PANEL_COUNT:
        raise RuntimeError("FINAL XYZ AUDIT: insufficient Y coordinates for three card clusters")
    gaps = [(unique_y[i + 1] - unique_y[i], i) for i in range(len(unique_y) - 1)]
    split_gaps = sorted(gaps, reverse=True)[:PANEL_COUNT - 1]
    if len(split_gaps) != 2 or min(g for g, _i in split_gaps) < 5.0:
        raise RuntimeError(
            f"FINAL XYZ AUDIT: could not find two deliberate large Y gaps; largest={split_gaps}"
        )
    split_indices = sorted(i for _g, i in split_gaps)
    split_y = [0.5 * (unique_y[i] + unique_y[i + 1]) for i in split_indices]

    clusters = [[] for _ in range(PANEL_COUNT)]
    for point in model_points:
        y = point[1]
        if y < split_y[0]:
            clusters[0].append(point)
        elif y < split_y[1]:
            clusters[1].append(point)
        else:
            clusters[2].append(point)
    if any(not cluster for cluster in clusters):
        raise RuntimeError("FINAL XYZ AUDIT: one or more Y card clusters are empty")

    expected_centreline_w = PANEL_WIDTH_X_MM - ROAD_WIDTH_MM
    width_tol = 0.35
    cluster_stats = []
    for panel, cluster in enumerate(clusters):
        xs = [x for x, _y, _z in cluster]
        ys = [y for _x, y, _z in cluster]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        width = x_max - x_min
        if abs(width - expected_centreline_w) > width_tol:
            raise RuntimeError(
                f"FINAL XYZ AUDIT: panel {panel} X centreline width {width:.3f} mm; "
                f"expected about {expected_centreline_w:.3f} mm"
            )
        cluster_stats.append({
            "panel": panel,
            "x_min": x_min,
            "x_max": x_max,
            "x_width": width,
            "y_min": y_min,
            "y_max": y_max,
        })

    measured_offsets = []
    free_gaps = []
    for panel in range(1, PANEL_COUNT):
        prev = cluster_stats[panel - 1]
        cur = cluster_stats[panel]
        measured = cur["y_max"] - prev["y_max"]
        if abs(measured - PANEL_Y_OFFSET_MM) > 0.05:
            raise RuntimeError(
                f"FINAL XYZ AUDIT: panel {panel-1}->{panel} Y offset {measured:.3f} mm; "
                f"expected {PANEL_Y_OFFSET_MM:.3f} mm"
            )
        free_gap = cur["y_min"] - prev["y_max"]
        if free_gap <= 0.0:
            raise RuntimeError(
                f"FINAL XYZ AUDIT: panel {panel-1}->{panel} clusters overlap in Y "
                f"(gap={free_gap:.3f} mm)"
            )
        measured_offsets.append(measured)
        free_gaps.append(free_gap)

    # No positive-E move may bridge any of the two deliberate inter-card gaps.
    crossings = []
    for rec in model_move_records:
        line_no, start_xy, end_xy, e_val, st = rec
        if start_xy is None:
            continue
        sy, ey = start_xy[1], end_xy[1]
        for boundary in range(PANEL_COUNT - 1):
            low_max = cluster_stats[boundary]["y_max"]
            high_min = cluster_stats[boundary + 1]["y_min"]
            if ((sy <= low_max and ey >= high_min)
                    or (sy >= high_min and ey <= low_max)):
                crossings.append(rec)
                break
    if crossings:
        raise RuntimeError(
            "FINAL XYZ AUDIT: positive-E model moves bridge an inter-card Y gap; "
            f"count={len(crossings)} sample={crossings[:3]}"
        )

    return {
        "panel_count": PANEL_COUNT,
        "nominal_panel_width_x_mm": PANEL_WIDTH_X_MM,
        "nominal_panel_height_z_mm": expected_last_z,
        "physical_layer_count": len(zs),
        "nominal_layer_step_mm": LAYER_H_MM,
        "first_nominal_z_mm": zs[0],
        "last_nominal_z_mm": zs[-1],
        "requested_successive_panel_y_offset_mm": PANEL_Y_OFFSET_MM,
        "measured_successive_panel_y_offsets_mm": measured_offsets,
        "free_model_gaps_y_mm": free_gaps,
        "positive_e_model_gap_crossings": 0,
        "panel_stats": cluster_stats,
        "model_y_splits_mm": split_y,
        "audit_scope": "DIRECT_DETERMINISTIC_ROADS; three Y clusters; G0/G1 XY state tracked",
    }



# ============================================================================
# v1.67 100-inch global radial-fan 5x5-grid half-tile test
# ============================================================================
import csv
from dataclasses import dataclass
from typing import List, Any




@dataclass(frozen=True)
class MasterFan:
    """Global screen geometry used to orient tangent/concentric arc roads."""
    diagonal_in: float = 100.0
    projector_below_screen_mm: float = 225.0
    projector_distance_mm: float = 470.0
    viewer_distance_mm: float = 3000.0
    viewer_eyeline_fraction: float = 1.0 / 3.0

    @property
    def diagonal_mm(self) -> float:
        return self.diagonal_in * 25.4

    @property
    def screen_width_mm(self) -> float:
        return self.diagonal_mm * 16.0 / math.sqrt(16.0**2 + 9.0**2)

    @property
    def screen_height_mm(self) -> float:
        return self.diagonal_mm * 9.0 / math.sqrt(16.0**2 + 9.0**2)

    @property
    def projector_x_mm(self) -> float:
        return self.screen_width_mm / 2.0

    @property
    def projector_z_mm(self) -> float:
        return -self.projector_below_screen_mm

    @property
    def viewer_x_mm(self) -> float:
        return self.screen_width_mm / 2.0

    @property
    def viewer_z_mm(self) -> float:
        return self.screen_height_mm * self.viewer_eyeline_fraction

    def radius_mm(self, x_mm: float, z_mm: float) -> float:
        return math.hypot(float(x_mm) - self.projector_x_mm,
                          float(z_mm) - self.projector_z_mm)


BASE_SCREEN_LAYER_H_MM = 0.10
SCREEN_SAMPLE_HEIGHT_MM = 124.5
SCREEN_SAMPLE_LAYERS = int(round(SCREEN_SAMPLE_HEIGHT_MM / BASE_SCREEN_LAYER_H_MM))
SCREEN_SAMPLE_HEIGHT_MM = SCREEN_SAMPLE_LAYERS * BASE_SCREEN_LAYER_H_MM


@dataclass(frozen=True)
class PieceSpec:
    name: str
    global_x0_mm: float
    global_x1_mm: float
    global_z0_mm: float
    global_z1_mm: float

    @property
    def width_mm(self) -> float:
        return self.global_x1_mm - self.global_x0_mm

    @property
    def height_mm(self) -> float:
        return self.global_z1_mm - self.global_z0_mm

    @classmethod
    def for_name(cls, name: str) -> 'PieceSpec':
        f = MasterFan()
        m = re.fullmatch(r"([1-5])-([1-5])", str(name))
        if not m:
            raise ValueError(name)
        col = int(m.group(1))
        row = int(m.group(2))
        tile_w = f.screen_width_mm / 5.0
        tile_h = f.screen_height_mm / 5.0
        sample_w = f.screen_width_mm / 20.0
        sample_h = SCREEN_SAMPLE_HEIGHT_MM
        # Grid convention: 1-1 is the bottom-left full tile; first index moves
        # left->right, second index bottom->top.  The proof coupon is centered
        # inside that nominal full tile so every 1-1..5-5 selection is
        # consistent and directly comparable.
        tile_x0 = (col - 1) * tile_w
        tile_z0 = (row - 1) * tile_h
        x0 = tile_x0 + (tile_w - sample_w) / 2.0
        z0 = tile_z0 + (tile_h - sample_h) / 2.0
        return cls(name, x0, x0 + sample_w, z0, z0 + sample_h)


# ============================================================================
# v1.106 A-only dual-arc bonding/profile test card
# ============================================================================
SCRIPT_VERSION = "3dprint_black_mirror_wave_grid_v1.106"
EXPECTED_DP_VERSION = "3dprintv1.179"
PANEL_COUNT = 1
FIRST_LAYER_H_MM = 0.20
LAYER_H_MM = 0.10
BASE_LAYER_COUNT = 3
PHYSICAL_LAYER_COUNT = 4
DIRECT_OPTICAL_LAYER_COUNT = 3
BASE_TOP_Z_MM = 0.40
NOMINAL_TOP_Z_MM = 0.50
CARD_THICKNESS_Z_MM = 0.50
TOP_SUPPORT_FILL_VE = 0.25
TOP_SUPPORT_FILL_DEPTH_MM = 0.080
TOP_SUPPORT_FILL_EFFECTIVE_Z_MM = 0.420
TOP_SUPPORT_FILL_G29_DELTA_MM = 0.020
TOP_SUPPORT_FILL_E_PER_MM = 0.0039175
TOP_SUPPORT_FILL_FEED_MM_S = 250.0
ROAD_WIDTH_MM = 0.40
DEFAULT_E_PER_MM = 0.01567 * (LAYER_H_MM / 0.10)
CALIBRATED_E_PER_MM = DEFAULT_E_PER_MM
MASTER_FAN = MasterFan()

def _unit3(v):
    m = math.sqrt(sum(float(q) * float(q) for q in v))
    if m <= 1e-12:
        raise ValueError("zero-length 3D vector")
    return tuple(float(q) / m for q in v)

def _line_angle_deg(angle_deg: float) -> float:
    """Return an unoriented line angle in [-90, 90)."""
    a = float(angle_deg)
    while a >= 90.0:
        a -= 180.0
    while a < -90.0:
        a += 180.0
    return a

def mirror_frame_global(x_mm: float, z_mm: float):
    """Ideal local specular mirror frame for projector -> screen -> viewer.

    Coordinates are global screen X/Z in mm. The third coordinate is physical
    distance out from the screen toward the projector/viewer.  `b_unit` is the
    projected mirror-normal direction followed by B. `a_unit` is its transverse
    contour direction and therefore the preferred mechanical A direction.
    """
    x = float(x_mm); z = float(z_mm)
    p = _unit3((MASTER_FAN.projector_x_mm - x,
                MASTER_FAN.projector_z_mm - z,
                MASTER_FAN.projector_distance_mm))
    v = _unit3((MASTER_FAN.viewer_x_mm - x,
                MASTER_FAN.viewer_z_mm - z,
                MASTER_FAN.viewer_distance_mm))
    n = _unit3(tuple(p[i] + v[i] for i in range(3)))
    xy_mag = math.hypot(n[0], n[1])
    if xy_mag <= 1e-12:
        b = (1.0, 0.0)
    else:
        b = (n[0] / xy_mag, n[1] / xy_mag)
    a = (-b[1], b[0])
    normal_az = math.degrees(math.atan2(b[1], b[0]))
    contour_az = _line_angle_deg(normal_az + 90.0)
    tilt = math.degrees(math.atan2(xy_mag, n[2]))
    # Specular-law regression measure: reflect the incoming propagation vector
    # (-p) about n; it must point at v.
    incoming = tuple(-q for q in p)
    d_dot_n = sum(incoming[i] * n[i] for i in range(3))
    reflected = tuple(incoming[i] - 2.0 * d_dot_n * n[i] for i in range(3))
    reflection_error = math.sqrt(sum((reflected[i] - v[i]) ** 2 for i in range(3)))
    return {
        "point_mm": (x, z),
        "projector_unit": p,
        "viewer_unit": v,
        "normal_unit": n,
        "b_unit": b,
        "b_rise_unit": (-b[0], -b[1]),
        "a_unit": a,
        "normal_azimuth_deg": _line_angle_deg(normal_az),
        "contour_azimuth_deg": contour_az,
        "facet_tilt_deg": tilt,
        "reflection_error": reflection_error,
    }

def _unit_surface_normal_from_tangents(a_unit, dx, dz, dh):
    # Coordinate order is screen-X, screen-Z, physical-height-out-of-screen.
    ax, az = a_unit
    cx = az * dh
    cz = -ax * dh
    ch = ax * dz - az * dx
    nn = _unit3((cx, cz, ch))
    if nn[2] < 0.0:
        nn = tuple(-q for q in nn)
    return nn

def integrate_b_front_global(x_mm: float, z_mm: float, relief_mm: float = 0.32, max_step_mm: float = 0.05):
    """Integrate one useful B front while its local slope tracks the ideal mirror.

    The B front rises while travelling opposite the projected mirror normal. This
    is the sign that makes the resulting surface normal point toward the ideal
    projector/viewer bisector rather than 180 degrees away in azimuth.
    """
    x = float(x_mm); z = float(z_mm); h = 0.0
    relief = float(relief_mm); step_max = float(max_step_mm)
    if relief <= 0.0 or step_max <= 0.0:
        raise ValueError("relief_mm and max_step_mm must be positive")
    pts = [(x, z, h)]
    max_normal_error = 0.0
    xy_run = 0.0
    guard = 0
    while h < relief - 1e-12:
        guard += 1
        if guard > 100000:
            raise RuntimeError("B-front integration guard tripped")
        f0 = mirror_frame_global(x, z)
        d0 = f0["b_rise_unit"]
        tan0 = math.tan(math.radians(f0["facet_tilt_deg"]))
        ds0 = min(step_max, (relief - h) / max(tan0, 1e-12))
        mx = x + 0.5 * d0[0] * ds0
        mz = z + 0.5 * d0[1] * ds0
        fm = mirror_frame_global(mx, mz)
        d = fm["b_rise_unit"]
        tan_tilt = math.tan(math.radians(fm["facet_tilt_deg"]))
        ds = min(step_max, (relief - h) / max(tan_tilt, 1e-12))
        nx = x + d[0] * ds
        nz = z + d[1] * ds
        nh = min(relief, h + tan_tilt * ds)
        actual = _unit_surface_normal_from_tangents(fm["a_unit"], nx - x, nz - z, nh - h)
        ideal = fm["normal_unit"]
        err = math.sqrt(sum((actual[i] - ideal[i]) ** 2 for i in range(3)))
        max_normal_error = max(max_normal_error, err)
        xy_run += math.hypot(nx - x, nz - z)
        x, z, h = nx, nz, nh
        pts.append((x, z, h))
    return {
        "points": pts,
        "xy_run_mm": xy_run,
        "relief_mm": relief,
        "max_normal_error": max_normal_error,
    }

def _advance_b_rise_global(x_mm: float, z_mm: float, distance_mm: float, max_step_mm: float = 0.05):
    x = float(x_mm); z = float(z_mm); rem = float(distance_mm)
    pts = [(x, z)]
    while rem > 1e-12:
        ds = min(float(max_step_mm), rem)
        f0 = mirror_frame_global(x, z)
        d0 = f0["b_rise_unit"]
        mx = x + 0.5 * d0[0] * ds
        mz = z + 0.5 * d0[1] * ds
        fm = mirror_frame_global(mx, mz)
        d = fm["b_rise_unit"]
        x += d[0] * ds
        z += d[1] * ds
        rem -= ds
        pts.append((x, z))
    return (x, z), pts

def build_wave_cell_global(x_mm: float, z_mm: float):
    """One B wave from valley-start to the next valley-start plus its dual-A former."""
    sx, sz = float(x_mm), float(z_mm)
    foot, flat_xy = _advance_b_rise_global(sx, sz, VALLEY_LAND_MM, B_FRONT_MAX_STEP_MM)
    front = integrate_b_front_global(foot[0], foot[1], WAVE_RELIEF_MM, B_FRONT_MAX_STEP_MM)
    crest = front["points"][-1]
    cf = mirror_frame_global(crest[0], crest[1])
    support_offset = ((A_MAIN_HEIGHT_MM - A_INNER_HEIGHT_MM) /
                      math.tan(math.radians(cf["facet_tilt_deg"])))
    inner_xy = (crest[0] + cf["b_unit"][0] * support_offset,
                crest[1] + cf["b_unit"][1] * support_offset)
    rear_run = WAVE_RELIEF_MM / math.tan(math.radians(REAR_RETURN_ANGLE_DEG))
    rear_end, rear_xy = _advance_b_rise_global(crest[0], crest[1], rear_run, B_FRONT_MAX_STEP_MM)
    # Build one continuous B path: flat valley at h=0, ideal front to H, then
    # a deliberately non-optical 67.5-degree return to h=0.
    bpts = [(flat_xy[0][0], flat_xy[0][1], 0.0)]
    for q in flat_xy[1:]:
        bpts.append((q[0], q[1], 0.0))
    for q in front["points"][1:]:
        bpts.append(q)
    rear_total = max(1e-12, sum(math.hypot(rear_xy[i+1][0]-rear_xy[i][0], rear_xy[i+1][1]-rear_xy[i][1]) for i in range(len(rear_xy)-1)))
    accum = 0.0
    prev = rear_xy[0]
    for q in rear_xy[1:]:
        accum += math.hypot(q[0]-prev[0], q[1]-prev[1])
        h = max(0.0, WAVE_RELIEF_MM * (1.0 - accum / rear_total))
        bpts.append((q[0], q[1], h))
        prev = q
    pitch = sum(math.hypot(bpts[i+1][0]-bpts[i][0], bpts[i+1][1]-bpts[i][1]) for i in range(len(bpts)-1))
    return {
        "start": (sx, sz, 0.0),
        "foot": (foot[0], foot[1], 0.0),
        "crest": crest,
        "end": (rear_end[0], rear_end[1], 0.0),
        "b_points": bpts,
        "main_a": {"point": (crest[0], crest[1]), "height_mm": A_MAIN_HEIGHT_MM},
        "inner_a": {"point": inner_xy, "height_mm": A_INNER_HEIGHT_MM, "offset_mm": support_offset},
        "xy_pitch_mm": pitch,
        "front_normal_error": front["max_normal_error"],
    }

def _resample_polyline2(points, max_spacing_mm):
    pts = [(float(x), float(z)) for x, z in points]
    if len(pts) < 2:
        return pts
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.hypot(b[0]-a[0], b[1]-a[1]))
    total = cum[-1]
    if total <= 1e-12:
        return [pts[0]]
    nseg = max(1, int(math.ceil(total / float(max_spacing_mm))))
    targets = [total * i / nseg for i in range(nseg + 1)]
    out = []
    j = 0
    for t in targets:
        while j + 1 < len(cum) and cum[j+1] < t - 1e-12:
            j += 1
        if j + 1 >= len(cum):
            out.append(pts[-1]); continue
        den = max(cum[j+1] - cum[j], 1e-12)
        f = (t - cum[j]) / den
        out.append((pts[j][0] + f*(pts[j+1][0]-pts[j][0]),
                    pts[j][1] + f*(pts[j+1][1]-pts[j][1])))
    return out

def _clip_segment_rect3(a, b, xmin, xmax, zmin, zmax):
    x0,z0,h0 = map(float,a); x1,z1,h1 = map(float,b)
    dx=x1-x0; dz=z1-z0
    t0=0.0; t1=1.0
    for p,q in ((-dx,x0-xmin),(dx,xmax-x0),(-dz,z0-zmin),(dz,zmax-z0)):
        if abs(p) <= 1e-15:
            if q < 0.0: return None
            continue
        r=q/p
        if p < 0.0:
            if r > t1: return None
            t0=max(t0,r)
        else:
            if r < t0: return None
            t1=min(t1,r)
    if t1 < t0: return None
    def at(t):
        return (x0+t*dx,z0+t*dz,h0+t*(h1-h0))
    return at(t0),at(t1)

def _clip_polyline3_to_piece(points, piece, inset_mm=None):
    inset = ROAD_WIDTH_MM/2.0 if inset_mm is None else float(inset_mm)
    xmin=piece.global_x0_mm+inset; xmax=piece.global_x1_mm-inset
    zmin=piece.global_z0_mm+inset; zmax=piece.global_z1_mm-inset
    out=[]; cur=[]
    for a,b in zip(points,points[1:]):
        cl=_clip_segment_rect3(a,b,xmin,xmax,zmin,zmax)
        if cl is None:
            if len(cur)>=2: out.append(cur)
            cur=[]; continue
        c0,c1=cl
        if not cur:
            cur=[c0,c1]
        else:
            if math.dist(cur[-1],c0) <= 1e-6:
                if math.dist(cur[-1],c1)>1e-9: cur.append(c1)
            else:
                if len(cur)>=2: out.append(cur)
                cur=[c0,c1]
    if len(cur)>=2: out.append(cur)
    return out

def _clip_polyline2_to_piece(points, piece, inset_mm=None):
    p3=[(x,z,0.0) for x,z in points]
    return [[(q[0],q[1]) for q in seg] for seg in _clip_polyline3_to_piece(p3,piece,inset_mm)]

def _append_clipped_b_cell_local(store, road_index, cell_points, piece):
    """Clip one B wave cell immediately and merge it into this family's local road."""
    for seg in _clip_polyline3_to_piece(cell_points, piece):
        local = [(q[0]-piece.global_x0_mm, q[1]-piece.global_z0_mm, q[2]) for q in seg]
        if len(local) < 2:
            continue
        paths = store[road_index]
        if paths and math.dist(paths[-1][-1], local[0]) <= 1e-6:
            paths[-1].extend(local[1:])
        else:
            paths.append(local)


def _trace_a_streamline_global(seed_x, seed_z, negative_len_mm, positive_len_mm, step_mm=0.20):
    """Trace the mechanically transverse A direction field through a seed point."""
    def one(sign, length):
        out=[(float(seed_x),float(seed_z))]
        x,z=out[0]; rem=max(0.0,float(length))
        while rem > 1e-12:
            ds=min(float(step_mm),rem)
            f0=mirror_frame_global(x,z)
            d0=(f0["a_unit"][0]*sign,f0["a_unit"][1]*sign)
            mx=x+0.5*d0[0]*ds; mz=z+0.5*d0[1]*ds
            fm=mirror_frame_global(mx,mz)
            d=(fm["a_unit"][0]*sign,fm["a_unit"][1]*sign)
            x+=d[0]*ds; z+=d[1]*ds
            out.append((x,z)); rem-=ds
        return out
    neg=one(-1.0,negative_len_mm)
    pos=one(+1.0,positive_len_mm)
    return list(reversed(neg[1:]))+pos


def generate_mirror_wave_lattice(piece: PieceSpec):
    """Build the full A/B curvilinear lattice before any G-code concerns.

    B roads rise opposite the ideal normal projection. Corresponding crests are
    connected to make the main A curves; the lower inner A curve is derived from
    the same local tilt. Families are re-meshed only at valleys if the edge gap
    exceeds half a nominal road width.

    v1.106 clips B cells and A curves as they are generated instead of retaining
    the complete padded global lattice. This keeps the physical geometry the
    same while avoiding millions of unnecessary Python point objects.
    """
    cx=0.5*(piece.global_x0_mm+piece.global_x1_mm)
    cz=0.5*(piece.global_z0_mm+piece.global_z1_mm)
    cf=mirror_frame_global(cx,cz)
    d0=cf["b_rise_unit"]; a0=cf["a_unit"]
    inset=ROAD_WIDTH_MM/2.0
    corners=[(piece.global_x0_mm+inset,piece.global_z0_mm+inset),
             (piece.global_x0_mm+inset,piece.global_z1_mm-inset),
             (piece.global_x1_mm-inset,piece.global_z0_mm+inset),
             (piece.global_x1_mm-inset,piece.global_z1_mm-inset)]
    su=[]
    for x,z in corners:
        dx=x-cx; dz=z-cz
        su.append((dx*d0[0]+dz*d0[1], dx*a0[0]+dz*a0[1]))
    smin=min(v[0] for v in su); smax=max(v[0] for v in su)
    umin=min(v[1] for v in su)-5.0; umax=max(v[1] for v in su)+5.0
    start_s=smin-1.0
    # Seed B on a true A streamline, not a straight line at the centre angle.
    # That removes the several-degree transverse drift that otherwise accumulates
    # when corresponding B crest indices are joined across the coupon.
    seed=(cx+d0[0]*start_s, cz+d0[1]*start_s)
    seed_curve=_trace_a_streamline_global(
        seed[0],seed[1],abs(umin)+5.0,abs(umax)+5.0,A_TRACE_STEP_MM)
    nodes=_resample_polyline2(seed_curve,B_ROAD_CENTER_PITCH_MM)
    initial_road_count=len(nodes)

    family_id=0
    family_local_paths=[[ ] for _ in nodes]
    families=[]
    main_curves=[]; inner_curves=[]
    clipped_main=[]; clipped_inner=[]; clipped_b=[]
    max_front_err=0.0; max_a_err=0.0; max_edge_observed=0.0
    reset_count=0; wave_count=0

    def finish_family(wave_idx, needs_reset, trigger_edge_gap):
        nonlocal clipped_b
        local_count=0
        for ri,parts in enumerate(family_local_paths):
            for path in parts:
                if len(path) >= 2:
                    clipped_b.append({"family":family_id,"road":ri,"points":path})
                    local_count += 1
        families.append({
            "id":family_id,
            "wave_end":wave_idx,
            "road_count":len(family_local_paths),
            "reset":bool(needs_reset),
            "trigger_edge_gap_mm":float(trigger_edge_gap),
            "local_path_count":local_count,
        })

    for wave_idx in range(1000):
        cells=[build_wave_cell_global(p[0],p[1]) for p in nodes]
        wave_count += 1
        crest_nodes=[(c["crest"][0],c["crest"][1]) for c in cells]
        inner_nodes=[c["inner_a"]["point"] for c in cells]
        main_rec={"wave":wave_idx,"family":family_id,"points":crest_nodes}
        inner_rec={"wave":wave_idx,"family":family_id,"points":inner_nodes}
        main_curves.append(main_rec); inner_curves.append(inner_rec)

        # Clip A immediately; only the coupon-local portion is retained for output.
        for seg in _clip_polyline2_to_piece(crest_nodes,piece):
            clipped_main.append({"wave":wave_idx,"family":family_id,"points":[
                (q[0]-piece.global_x0_mm,q[1]-piece.global_z0_mm) for q in seg]})
        for seg in _clip_polyline2_to_piece(inner_nodes,piece):
            clipped_inner.append({"wave":wave_idx,"family":family_id,"points":[
                (q[0]-piece.global_x0_mm,q[1]-piece.global_z0_mm) for q in seg]})

        max_front_err=max(max_front_err,max(c["front_normal_error"] for c in cells))
        for j in range(len(crest_nodes)-1):
            aa=crest_nodes[j]; bb=crest_nodes[j+1]
            tx=bb[0]-aa[0]; tz=bb[1]-aa[1]; tm=math.hypot(tx,tz)
            if tm>1e-12:
                mf=mirror_frame_global(0.5*(aa[0]+bb[0]),0.5*(aa[1]+bb[1]))
                max_a_err=max(max_a_err,abs((tx*mf["b_unit"][0]+tz*mf["b_unit"][1])/tm))

        new_nodes=[]
        for j,c in enumerate(cells):
            _append_clipped_b_cell_local(family_local_paths,j,c["b_points"],piece)
            new_nodes.append((c["end"][0],c["end"][1]))

        centres=[math.hypot(new_nodes[j+1][0]-new_nodes[j][0],new_nodes[j+1][1]-new_nodes[j][1]) for j in range(len(new_nodes)-1)]
        max_edge=max([max(0.0,q-ROAD_WIDTH_MM) for q in centres] or [0.0])
        max_edge_observed=max(max_edge_observed,min(max_edge,FAMILY_RESET_EDGE_GAP_MM))
        progress=[(p[0]-cx)*d0[0]+(p[1]-cz)*d0[1] for p in new_nodes]
        done=min(progress) > smax + 1.0
        needs_reset=(max_edge > FAMILY_RESET_EDGE_GAP_MM + 1e-12) and not done
        if done or needs_reset:
            finish_family(wave_idx, needs_reset, max_edge)
            if done:
                nodes=new_nodes
                break
            reset_count += 1
            family_id += 1
            nodes=_resample_polyline2(new_nodes,B_ROAD_CENTER_PITCH_MM)
            family_local_paths=[[] for _ in nodes]
        else:
            nodes=new_nodes
    else:
        raise RuntimeError(f"{piece.name}: mirror-wave lattice exceeded 1000 waves")

    return {
        "piece":piece.name,
        "initial_road_count":initial_road_count,
        "wave_count":wave_count,
        "family_reset_count":reset_count,
        "families":families,
        "main_a_curves":main_curves,
        "inner_a_curves":inner_curves,
        "b_paths_local":clipped_b,
        "main_a_local":clipped_main,
        "inner_a_local":clipped_inner,
        "clipped_b_path_count":len(clipped_b),
        "clipped_main_a_count":len(clipped_main),
        "clipped_inner_a_count":len(clipped_inner),
        "max_edge_gap_before_reset_mm":max_edge_observed,
        "max_a_transverse_error":max_a_err,
        "max_front_normal_error":max_front_err,
    }


def get_mirror_wave_lattice(piece: PieceSpec):
    key=(piece.name, round(piece.global_x0_mm,9), round(piece.global_z0_mm,9))
    rec=_MIRROR_LATTICE_CACHE.get(key)
    if rec is None:
        rec=generate_mirror_wave_lattice(piece)
        _MIRROR_LATTICE_CACHE[key]=rec
    return rec


def _a_pair_pack_map(piece: PieceSpec, lat):
    """Map each A pair to one of six equal radial-distance packs.

    Pack 0 is the pair closest to the projector in screen-plane radial distance;
    pack 5 is furthest away.  Main and inner paths from the same wave/family use
    the same pack, so the bonding shift translates the pair without changing its
    mirror-derived lateral relationship.
    """
    main_by_key = {(r["wave"], r["family"]): r for r in lat["main_a_local"]}
    radii = {}
    for key, rec in main_by_key.items():
        pts = rec["points"]
        if not pts:
            continue
        vals = [math.hypot((piece.global_x0_mm + p[0]) - MASTER_FAN.projector_x_mm,
                           (piece.global_z0_mm + p[1]) - MASTER_FAN.projector_z_mm)
                for p in pts]
        radii[key] = sum(vals) / len(vals)
    if not radii:
        raise RuntimeError(f"{piece.name}: no A pairs available for bonding packs")
    rmin=min(radii.values()); rmax=max(radii.values())
    span=max(rmax-rmin, 1e-12)
    out={}
    for key,r in radii.items():
        idx=min(A_BOND_PACK_COUNT-1, int(((r-rmin)/span)*A_BOND_PACK_COUNT))
        out[key]=idx
    return out, rmin, rmax



def _explicit_mirror_wave_layer_gcode(piece: PieceSpec, x_origin: float, y_origin: float):
    """Emit v1.106 full-arc serpentine wave sets at constant logical G1 Z.

    Physical wave height is carried by G29.1 so Bambu/Orca retain one optical
    logical layer.  Successive complete arcs are connected at alternating ends;
    every positive-E move uses actual 3D path length and F3000 (50 mm/s).
    """
    geo=get_true_normal_wave_sets(piece)
    xo=float(x_origin); yo=float(y_origin)
    logical_z=WAVESET_COMMAND_Z_MM
    travel_z=max(NOMINAL_TOP_Z_MM,logical_z+WAVESET_TOTAL_PEAK_MM)+B_TRAVEL_CLEARANCE_MM
    rows=[f"; FC3D_V1106_WAVESETS_START sets={geo['set_count']} cells={geo['cell_count']} roads={len(geo['roads'])} order={WAVESET_BUILD_ORDER}"]
    baseline=-0.020
    # The inherited A1 textured-plate baseline is audited independently; these
    # offsets are relative to that baseline and never manufacture a logical layer.
    def g29_for_height(h): return baseline+float(h)
    for s in geo["sets"]:
        roadrecs=s["roads"]
        if not roadrecs: continue
        oriented=[]; prev_end=None
        for ri,rec in enumerate(roadrecs):
            pts=[(xo+(x-piece.global_x0_mm),yo+(z-piece.global_z0_mm),float(rec["height_mm"])) for x,z in rec["points_clip"]]
            if len(pts)<2: continue
            if prev_end is not None:
                d0=math.hypot(pts[0][0]-prev_end[0],pts[0][1]-prev_end[1]); d1=math.hypot(pts[-1][0]-prev_end[0],pts[-1][1]-prev_end[1])
                if d1<d0: pts=list(reversed(pts))
            elif ri%2: pts=list(reversed(pts))
            oriented.append((rec,pts)); prev_end=pts[-1]
        if not oriented: continue
        first=oriented[0][1][0]
        rows.append(f"; FC3D_V1106_WAVESET_START set={s['set_index']} roads={len(oriented)} end_reason={s['end_reason']}")
        rows.append(f"G0 Z{travel_z:.3f} F900 ; FC3D_V1106_WAVESET_TRAVEL_Z set={s['set_index']}")
        rows.append(f"G29.1 Z{g29_for_height(first[2]):.3f} ; FC3D_V1106_WAVE_G29_SET set={s['set_index']} role={oriented[0][0]['role']} h={first[2]:.3f}")
        rows.append(f"G0 X{first[0]:.3f} Y{first[1]:.3f} F18000 ; FC3D_V1106_WAVESET_MOVE set={s['set_index']}")
        rows.append(f"G0 Z{logical_z:.3f} F900 ; FC3D_V1106_WAVE_LOGICAL_Z set={s['set_index']}")
        rows.append(f"G1 E{A_REPRIME_MM:.3f} F1800 ; FC3D_V1106_WAVESET_REPRIME set={s['set_index']}")
        prev=first
        dry_endpoint=None
        for oi,(rec,pts) in enumerate(oriented):
            target_h=pts[0][2]
            if abs(prev[2]-target_h)>1e-9 or math.hypot(prev[0]-pts[0][0],prev[1]-pts[0][1])>1e-9:
                rows.append(f"G29.1 Z{g29_for_height(target_h):.3f} ; FC3D_V1106_WAVE_G29_PROFILE set={s['set_index']} cell={rec['cell_index']} role={rec['role']} h={target_h:.3f}")
                q=pts[0]; length=_waveset_length3(prev,q); e=length*A_MAIN_E_PER_MM
                if length>1e-9:
                    rows.append(f"G1 X{q[0]:.3f} Y{q[1]:.3f} Z{logical_z:.3f} E{e:.5f} F{WAVESET_PRINT_FEED_MM_S*60:.0f} ; FC3D_V1106_WAVE_CONNECT set={s['set_index']} cell={rec['cell_index']} role={rec['role']} L3={length:.6f}")
                prev=q
            is_last=(oi==len(oriented)-1)
            remain=None
            if is_last:
                arc_total=sum(_waveset_length3(a,b) for a,b in zip(pts,pts[1:]))
                remain=max(0.0,arc_total-A_ENDPOINT_DRY_TAIL_MM)
                dry_endpoint=pts[-1]
            for j,q in enumerate(pts[1:]):
                length=_waveset_length3(prev,q)
                use=length if remain is None else min(length,remain)
                if use<=1e-12: break
                if use<length-1e-12:
                    t=use/length
                    q=(prev[0]+(q[0]-prev[0])*t,prev[1]+(q[1]-prev[1])*t,prev[2]+(q[2]-prev[2])*t)
                e=use*A_MAIN_E_PER_MM
                rows.append(f"G1 X{q[0]:.3f} Y{q[1]:.3f} Z{logical_z:.3f} E{e:.5f} F{WAVESET_PRINT_FEED_MM_S*60:.0f} ; FC3D_V1106_WAVE_ARC set={s['set_index']} cell={rec['cell_index']} role={rec['role']} seg={j} L3={use:.6f}")
                prev=q
                if remain is not None:
                    remain-=use
                    if remain<=1e-12: break
        rows.append(f"G1 E-{A_RETRACT_MM:.3f} F1800 ; FC3D_V1106_WAVESET_RETRACT set={s['set_index']}")
        if dry_endpoint is not None and _waveset_length3(prev,dry_endpoint)>1e-9:
            dry_len=_waveset_length3(prev,dry_endpoint)
            rows.append(f"G1 X{dry_endpoint[0]:.3f} Y{dry_endpoint[1]:.3f} Z{logical_z:.3f} F15000 ; FC3D_V1106_WAVESET_DRY_TAIL set={s['set_index']} len={dry_len:.6f}")
            prev=dry_endpoint
        rows.append(f"G0 Z{travel_z:.3f} F900 ; FC3D_V1106_WAVESET_SAFE_LIFT set={s['set_index']}")
        rows.append(f"G29.1 Z{baseline:.3f} ; FC3D_V1106_WAVE_G29_RESTORE set={s['set_index']}")
        rows.append(f"; FC3D_V1106_WAVESET_END set={s['set_index']}")
    rows.append(f"G0 Z{travel_z:.3f} F900 ; FC3D_V1106_OPTICAL_SAFE_END_Z")
    rows.append("; FC3D_V1106_WAVESETS_END B_EMITTED=0 INNER_EMITTED=0")
    return rows



CURRENT_PIECE = None
RUNTIME_ORIGIN = None
PANEL_WIDTH_X_MM = MASTER_FAN.screen_width_mm / 20.0
PANEL_HEIGHT_Y_MM = SCREEN_SAMPLE_HEIGHT_MM
TOTAL_X_MM = PANEL_WIDTH_X_MM
TOTAL_LAYOUT_DEPTH_Y_MM = PANEL_HEIGHT_Y_MM
RP_PITCH_MM = ROAD_WIDTH_MM
STACK_W = int(math.ceil(PANEL_WIDTH_X_MM / RP_PITCH_MM))
STACK_H = int(math.ceil(PANEL_HEIGHT_Y_MM / RP_PITCH_MM))
ARC_RADIAL_PITCH_MM = 0.40
ARC_SEGMENT_MAX_LEN_MM = 0.60
BASE_LAYER_INDEX = 0
ARC_LAYER_INDEX = BASE_LAYER_COUNT

# v1.106 A-only dual-arc bonding/profile geometry
# B geometry is retained internally only as a construction scaffold for locating
# the mirror-derived A pairs. No B extrusion is emitted in this experiment.
B_ENABLED = False
WAVE_RELIEF_MM = 0.32
VALLEY_LAND_MM = 0.10
REAR_RETURN_ANGLE_DEG = 67.5
A_INNER_NOMINAL_HEIGHT_MM = 0.08
A_MAIN_NOMINAL_HEIGHT_MM = 0.14
# Six equal radial packs. Pack 0 is closest to the projector and receives the
# greatest squash. Pack 5 is furthest out and uses nominal 0.08/0.14 clearance.
A_BOND_PACK_COUNT = 1
A_BOND_Z_SHIFTS_MM = (0.000,)
# Extrusion is tied to nominal feature height, not to the bonding-clearance test.
A_REFERENCE_E_PER_MM_0P10 = 0.01567
A_INNER_E_PER_MM = A_REFERENCE_E_PER_MM_0P10 * (A_INNER_NOMINAL_HEIGHT_MM / 0.10)
A_MAIN_E_PER_MM = A_REFERENCE_E_PER_MM_0P10 * (A_MAIN_NOMINAL_HEIGHT_MM / 0.10)
# Legacy names used by mirror-pair placement. Height difference expresses the
# Z component; local XY separation remains derived from the local mirror tilt.
A_INNER_HEIGHT_MM = A_INNER_NOMINAL_HEIGHT_MM
A_MAIN_HEIGHT_MM = A_MAIN_NOMINAL_HEIGHT_MM
A_MAIN_FLOW_MULT = A_MAIN_E_PER_MM / CALIBRATED_E_PER_MM
A_INNER_FLOW_MULT = A_INNER_E_PER_MM / CALIBRATED_E_PER_MM
B_FRONT_MAX_STEP_MM = 0.50
A_TRACE_STEP_MM = 0.20
B_ROAD_CENTER_PITCH_MM = ROAD_WIDTH_MM
FAMILY_RESET_EDGE_GAP_MM = ROAD_WIDTH_MM / 2.0
A_PRINT_FEED_MM_S = 250.0
A_REPRIME_MM = 0.795
A_RETRACT_MM = 0.800
A_ENDPOINT_DRY_TAIL_MM = 0.160
B_PRINT_FEED_MM_S = 20.0
B_TRAVEL_CLEARANCE_MM = 0.20
_MIRROR_LATTICE_CACHE = {}


def set_runtime_e_per_mm(value: float):
    global CALIBRATED_E_PER_MM
    value = float(value)
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError("e-per-mm must be a finite positive value")
    CALIBRATED_E_PER_MM = value
    return value


def _current_piece() -> PieceSpec:
    if CURRENT_PIECE is None:
        raise RuntimeError("piece not selected")
    return CURRENT_PIECE


def _coord_key(a, b):
    return tuple(round(float(v), 4) for v in (*a, *b))


def _base_roads_x(x_origin: float, y_origin: float):
    x0 = float(x_origin)
    x1 = x0 + PANEL_WIDTH_X_MM
    half = ROAD_WIDTH_MM / 2.0
    ys = _centres_for_filled_interval(0.0, PANEL_HEIGHT_Y_MM, ROAD_WIDTH_MM)
    return [(x0 + half, float(y_origin) + y, x1 - half, float(y_origin) + y, 1.0) for y in ys]


def _base_roads_y(x_origin: float, y_origin: float):
    y0 = float(y_origin)
    y1 = y0 + PANEL_HEIGHT_Y_MM
    half = ROAD_WIDTH_MM / 2.0
    xs = _centres_for_filled_interval(0.0, PANEL_WIDTH_X_MM, ROAD_WIDTH_MM)
    return [(float(x_origin) + x, y0 + half, float(x_origin) + x, y1 - half, 1.0) for x in xs]


def _base_roads_for_layer(logical_layer: int, x_origin: float, y_origin: float):
    li = int(logical_layer)
    if not 0 <= li < BASE_LAYER_COUNT:
        raise ValueError(li)
    # Mechanical interlock: every structural layer swaps raster direction.
    return _base_roads_x(x_origin, y_origin) if li % 2 == 0 else _base_roads_y(x_origin, y_origin)


LABEL_PIXEL_MM = 3.0
LABEL_TEXT_Y0_MM = 8.0
VERSION_TEXT_Y0_MM = 36.0
ARROW_SHAFT_Y0_MM = 62.0
ARROW_SHAFT_Y1_MM = 88.0
ARROW_HEAD_Y0_MM = 84.0
ARROW_HEAD_Y1_MM = 116.0
ARROW_SHAFT_HALF_W_MM = 4.5
ARROW_HEAD_HALF_W_BASE_MM = 17.0
REAR_VERSION_TEXT = "106"
LABEL_GLYPHS = {
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("01110", "00110", "00110", "00110", "00110", "00110", "11111"),
    "2": ("11110", "00001", "00001", "11110", "10000", "10000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("10010", "10010", "10010", "11111", "00010", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01111", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "11110"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
}


def _merge_intervals(intervals):
    clean = sorted((float(a), float(b)) for a, b in intervals if float(b) > float(a) + 1e-9)
    if not clean:
        return []
    out = [list(clean[0])]
    for a, b in clean[1:]:
        if a <= out[-1][1] + 1e-9:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def _text_intervals_back_view(piece: PieceSpec, text: str, y_local_mm: float, y0_mm: float):
    scale = LABEL_PIXEL_MM
    row = int(math.floor((float(y_local_mm) - float(y0_mm)) / scale))
    if not 0 <= row < 7:
        return []
    total_cols = sum(len(LABEL_GLYPHS[c][0]) for c in text) + max(0, len(text) - 1)
    total_w = total_cols * scale
    cursor = 0.5 * (piece.width_mm - total_w)
    intervals = []
    for ci, ch in enumerate(text):
        glyph = LABEL_GLYPHS[ch]
        for col, bit in enumerate(glyph[row]):
            if bit == "1":
                intervals.append((cursor + col * scale, cursor + (col + 1) * scale))
        cursor += len(glyph[0]) * scale
        if ci != len(text) - 1:
            cursor += scale
    return _merge_intervals(intervals)


def _arrow_intervals_back_view(piece: PieceSpec, y_local_mm: float):
    y = float(y_local_mm)
    cx = piece.width_mm / 2.0
    intervals = []
    if ARROW_SHAFT_Y0_MM <= y <= ARROW_SHAFT_Y1_MM:
        intervals.append((cx - ARROW_SHAFT_HALF_W_MM, cx + ARROW_SHAFT_HALF_W_MM))
    if ARROW_HEAD_Y0_MM <= y <= ARROW_HEAD_Y1_MM:
        frac = max(0.0, min(1.0, (ARROW_HEAD_Y1_MM - y) / (ARROW_HEAD_Y1_MM - ARROW_HEAD_Y0_MM)))
        half_w = ARROW_HEAD_HALF_W_BASE_MM * frac
        if half_w > 1e-9:
            intervals.append((cx - half_w, cx + half_w))
    return _merge_intervals(intervals)


def _arrow_intervals_back_view_vertical_flip(piece: PieceSpec, y_local_mm: float):
    """Flip only the arrow vertically inside its original rear-face bounding box."""
    y_flipped=(ARROW_SHAFT_Y0_MM+ARROW_HEAD_Y1_MM)-float(y_local_mm)
    return _arrow_intervals_back_view(piece,y_flipped)


def label_intervals_printer_x(piece: PieceSpec, y_local_mm: float):
    # v1.102 physically proved the raw text/number orientation. Preserve every
    # text stroke and its placement exactly; flip ONLY the arrow vertically.
    return _merge_intervals(
        _text_intervals_back_view(piece,piece.name,y_local_mm,LABEL_TEXT_Y0_MM)
        + _text_intervals_back_view(piece,REAR_VERSION_TEXT,y_local_mm,VERSION_TEXT_Y0_MM)
        + _arrow_intervals_back_view_vertical_flip(piece,y_local_mm)
    )



def _subtract_intervals(x0: float, x1: float, omitted_intervals):
    x0, x1 = sorted((float(x0), float(x1)))
    omitted=[]
    for a,b in omitted_intervals:
        a=max(x0,float(a)); b=min(x1,float(b))
        if b>a+1e-9: omitted.append((a,b))
    omitted=_merge_intervals(omitted)
    keep=[]; cursor=x0
    for a,b in omitted:
        if a>cursor+1e-9: keep.append((cursor,a))
        cursor=max(cursor,b)
    if cursor<x1-1e-9: keep.append((cursor,x1))
    return keep


def _base_segments_by_material_for_layer(logical_layer: int, x_origin: float, y_origin: float, material_order):
    """Single-colour base; first-layer rear markings are texture omissions.

    On every other X-raster road that crosses the back-view ID/arrow mask, the
    black segment under that mask is omitted.  The next structural layer is the
    perpendicular Y raster, so these shallow first-layer texture gaps are
    crossed and supported rather than becoming through-holes.
    """
    out = _blank_segments(material_order)
    li = int(logical_layer)
    if li != 0:
        out[LOGICAL_MATERIAL] = _base_roads_for_layer(li, x_origin, y_origin)
        return out
    piece=_current_piece()
    half=ROAD_WIDTH_MM/2.0
    local_x0=half; local_x1=piece.width_mm-half
    textured_rows=0; omitted_len=0.0
    for row_idx,seg in enumerate(_base_roads_x(x_origin,y_origin)):
        y_local=seg[1]-float(y_origin)
        mask=label_intervals_printer_x(piece,y_local)
        # Alternate base roads only where the marking exists.  The intervening
        # roads remain intact, producing a texture rather than an open cutout.
        if mask and row_idx % 2 == 0:
            keep=_subtract_intervals(local_x0,local_x1,mask)
            for a,b in keep:
                out[LOGICAL_MATERIAL].append((float(x_origin)+a,seg[1],float(x_origin)+b,seg[3],1.0))
            omitted_len += sum(max(0.0,b-a) for a,b in mask)
            textured_rows += 1
        else:
            out[LOGICAL_MATERIAL].append(seg)
    if textured_rows <= 0 or omitted_len < 50.0:
        raise RuntimeError(f"v1.106: black-only rear texture mask too small/missing for {piece.name}: rows={textured_rows} omitted={omitted_len:.1f}")
    return out

def _placeholder_segment(x_origin: float, y_origin: float):
    return (float(x_origin) + 0.20, float(y_origin) + 0.20,
            float(x_origin) + 0.60, float(y_origin) + 0.60, 1.0)


def make_layer_segments(logical_layer, bottom_angle_deg, middle_angle_deg, top_angle_deg,
                        x_origin, y_origin, material_order):
    global RUNTIME_ORIGIN
    here = (float(x_origin), float(y_origin))
    if RUNTIME_ORIGIN is None:
        RUNTIME_ORIGIN = here
    elif math.hypot(RUNTIME_ORIGIN[0] - here[0], RUNTIME_ORIGIN[1] - here[1]) > 1e-9:
        raise RuntimeError(f"RUNTIME ORIGIN changed {RUNTIME_ORIGIN!r}->{here!r}")
    out = _blank_segments(material_order)
    li = int(logical_layer)
    if 0 <= li < BASE_LAYER_COUNT:
        split = _base_segments_by_material_for_layer(li, x_origin, y_origin, material_order)
        for material, segments in split.items():
            out.setdefault(material, []).extend(segments)
    elif li == ARC_LAYER_INDEX:
        out[LOGICAL_MATERIAL] = [_placeholder_segment(x_origin, y_origin)]
    else:
        raise RuntimeError(f"unexpected logical_layer {logical_layer}; expected 0..{ARC_LAYER_INDEX}")
    return out


def _inside_box(x: float, z: float, x0: float, x1: float, z0: float, z1: float, eps: float = 1e-7) -> bool:
    return (x0 - eps <= x <= x1 + eps) and (z0 - eps <= z <= z1 + eps)


def _radius_range_for_piece(piece: PieceSpec):
    x0, x1 = piece.global_x0_mm, piece.global_x1_mm
    z0, z1 = piece.global_z0_mm, piece.global_z1_mm
    cx, cz = MASTER_FAN.projector_x_mm, MASTER_FAN.projector_z_mm
    nearest_x = min(max(cx, x0), x1)
    nearest_z = min(max(cz, z0), z1)
    min_r = math.hypot(nearest_x - cx, nearest_z - cz)
    max_r = max(MASTER_FAN.radius_mm(x, z) for x in (x0, x1) for z in (z0, z1))
    return min_r, max_r


def _circle_box_arc_intervals(radius_mm: float, piece: PieceSpec):
    cx = MASTER_FAN.projector_x_mm
    cz = MASTER_FAN.projector_z_mm
    x0, x1 = piece.global_x0_mm, piece.global_x1_mm
    z0, z1 = piece.global_z0_mm, piece.global_z1_mm
    r = float(radius_mm)
    eps = 1e-8
    angles = []

    def add_angle(x, z):
        if _inside_box(x, z, x0, x1, z0, z1, eps=1e-6):
            angles.append(math.atan2(z - cz, x - cx))

    for x in (x0, x1):
        dx = x - cx
        rem = r * r - dx * dx
        if rem >= -eps:
            rem = max(0.0, rem)
            root = math.sqrt(rem)
            add_angle(x, cz - root)
            add_angle(x, cz + root)

    for z in (z0, z1):
        dz = z - cz
        rem = r * r - dz * dz
        if rem >= -eps:
            rem = max(0.0, rem)
            root = math.sqrt(rem)
            add_angle(cx - root, z)
            add_angle(cx + root, z)

    if len(angles) < 2:
        return []

    uniq = []
    for a in sorted(angles):
        if not uniq or abs(a - uniq[-1]) > 1e-8:
            uniq.append(a)
    intervals = []
    for a, b in zip(uniq, uniq[1:]):
        if b - a <= 1e-9:
            continue
        mid = 0.5 * (a + b)
        mx = cx + r * math.cos(mid)
        mz = cz + r * math.sin(mid)
        if _inside_box(mx, mz, x0, x1, z0, z1):
            intervals.append((a, b))
    return intervals


def _sample_arc_interval(radius_mm: float, theta0: float, theta1: float, piece: PieceSpec):
    cx = MASTER_FAN.projector_x_mm
    cz = MASTER_FAN.projector_z_mm
    arc_len = abs(theta1 - theta0) * radius_mm
    steps = max(1, int(math.ceil(arc_len / ARC_SEGMENT_MAX_LEN_MM)))
    pts = []
    for i in range(steps + 1):
        t = theta0 + (theta1 - theta0) * (i / steps)
        gx = cx + radius_mm * math.cos(t)
        gz = cz + radius_mm * math.sin(t)
        lx = gx - piece.global_x0_mm
        ly = gz - piece.global_z0_mm
        lx = min(max(lx, 0.0), piece.width_mm)
        ly = min(max(ly, 0.0), piece.height_mm)
        pts.append((lx, ly))
    out = [pts[0]]
    for p in pts[1:]:
        if math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 1e-6:
            out.append(p)
    return out


def _arc_paths_local(piece: PieceSpec):
    r_min, r_max = _radius_range_for_piece(piece)
    base = MASTER_FAN.projector_below_screen_mm
    k0 = int(math.floor((r_min - base) / ARC_RADIAL_PITCH_MM)) - 2
    k1 = int(math.ceil((r_max - base) / ARC_RADIAL_PITCH_MM)) + 2
    paths = []
    for k in range(k0, k1 + 1):
        r = base + k * ARC_RADIAL_PITCH_MM
        if r <= 0.0:
            continue
        for theta0, theta1 in _circle_box_arc_intervals(r, piece):
            pts = _sample_arc_interval(r, theta0, theta1, piece)
            if len(pts) >= 2:
                length = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))
                paths.append({
                    "radius_mm": r,
                    "theta0_rad": theta0,
                    "theta1_rad": theta1,
                    "points": pts,
                    "length_mm": length,
                })
    paths.sort(key=lambda p: p["radius_mm"])
    for i, p in enumerate(paths):
        if i % 2 == 1:
            p["points"] = list(reversed(p["points"]))
            p["theta0_rad"], p["theta1_rad"] = p["theta1_rad"], p["theta0_rad"]
    if not paths:
        raise RuntimeError(f"{piece.name}: no concentric arc paths generated")
    return paths


def _arc_paths_absolute(piece: PieceSpec, x_origin: float, y_origin: float):
    out = []
    for rec in _arc_paths_local(piece):
        pts = [(float(x_origin) + x, float(y_origin) + y) for x, y in rec["points"]]
        out.append({**rec, "points": pts})
    return out


def write_arc_summary_csv(path):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    piece = _current_piece()
    fields = [
        "path_index", "radius_mm", "segments", "approx_length_mm",
        "start_local_x_mm", "start_local_y_mm", "end_local_x_mm", "end_local_y_mm"
    ]
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for idx, rec in enumerate(_arc_paths_local(piece)):
            pts = rec["points"]
            w.writerow({
                "path_index": idx,
                "radius_mm": f"{rec['radius_mm']:.8f}",
                "segments": len(pts) - 1,
                "approx_length_mm": f"{rec['length_mm']:.8f}",
                "start_local_x_mm": f"{pts[0][0]:.8f}",
                "start_local_y_mm": f"{pts[0][1]:.8f}",
                "end_local_x_mm": f"{pts[-1][0]:.8f}",
                "end_local_y_mm": f"{pts[-1][1]:.8f}",
            })
    return p


def write_layer_summary_csv(path):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    piece = _current_piece()
    paths = _arc_paths_local(piece)
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["physical_layer", "role", "layer_height_mm", "road_width_mm", "path_count", "piece_width_mm", "piece_height_mm"])
        w.writeheader()
        for li in range(BASE_LAYER_COUNT):
            orientation = "X" if li % 2 == 0 else "Y"
            w.writerow({"physical_layer": li, "role": f"base_{orientation}", "layer_height_mm": f"{(FIRST_LAYER_H_MM if li == 0 else LAYER_H_MM):.5f}", "road_width_mm": f"{ROAD_WIDTH_MM:.5f}", "path_count": len(_base_roads_for_layer(li, 0.0, 0.0)), "piece_width_mm": f"{piece.width_mm:.8f}", "piece_height_mm": f"{piece.height_mm:.8f}"})
        w.writerow({"physical_layer": ARC_LAYER_INDEX, "role": "optical_arcs", "layer_height_mm": f"{(FIRST_LAYER_H_MM if li == 0 else LAYER_H_MM):.5f}", "road_width_mm": f"{ROAD_WIDTH_MM:.5f}", "path_count": len(paths), "piece_width_mm": f"{piece.width_mm:.8f}", "piece_height_mm": f"{piece.height_mm:.8f}"})
    return p



def write_mirror_summary_csv(path):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    rep=waveset_report(_current_piece())
    fields=["piece","set_count","cell_count","road_count","peak_mm","optical_rise_mm","hidden_rise_mm","pitch_min_mm","pitch_mean_mm","pitch_max_mm","front_normal_error_max","hidden_projector_clearance_min_mm","wave_feed_mm_s","top_fill_ve"]
    with p.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerow({"piece":_current_piece().name,"set_count":rep["set_count"],"cell_count":rep["cell_count"],"road_count":rep["road_count"],"peak_mm":rep["peak_mm"],"optical_rise_mm":rep["optical_rise_mm"],"hidden_rise_mm":rep["hidden_rise_mm"],"pitch_min_mm":rep["pitch_mm"]["min"],"pitch_mean_mm":rep["pitch_mm"]["mean"],"pitch_max_mm":rep["pitch_mm"]["max"],"front_normal_error_max":rep["front_normal_error_max"],"hidden_projector_clearance_min_mm":rep["hidden_projector_clearance_min_mm"],"wave_feed_mm_s":rep["print_feed_mm_s"],"top_fill_ve":TOP_SUPPORT_FILL_VE})




def write_mirror_layer_summary_csv(path):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    piece=_current_piece(); lat=get_mirror_wave_lattice(piece)
    fields=["physical_layer","role","nominal_z_mm","road_width_mm","path_count","piece_width_mm","piece_height_mm","physical_peak_z_mm"]
    with p.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for li in range(BASE_LAYER_COUNT):
            orientation="X" if li%2==0 else "Y"
            w.writerow({"physical_layer":li,"role":f"base_{orientation}","nominal_z_mm":f"{(FIRST_LAYER_H_MM + li*LAYER_H_MM):.5f}",
                        "road_width_mm":f"{ROAD_WIDTH_MM:.5f}","path_count":len(_base_roads_for_layer(li,0.0,0.0)),
                        "piece_width_mm":f"{piece.width_mm:.8f}","piece_height_mm":f"{piece.height_mm:.8f}","physical_peak_z_mm":""})
        w.writerow({"physical_layer":ARC_LAYER_INDEX,"role":"A_only_true_normal_wave_sets",
                    "nominal_z_mm":f"{NOMINAL_TOP_Z_MM:.5f}","road_width_mm":f"{ROAD_WIDTH_MM:.5f}",
                    "path_count":len(lat["main_a_local"]),
                    "piece_width_mm":f"{piece.width_mm:.8f}","piece_height_mm":f"{piece.height_mm:.8f}",
                    "physical_peak_z_mm":f"{_mirror_wave_peak_z_mm():.5f}"})
    return p


def _explicit_arc_layer_gcode(x_origin: float, y_origin: float):
    piece = _current_piece()
    rows = []
    for idx, rec in enumerate(_arc_paths_absolute(piece, x_origin, y_origin)):
        pts = rec["points"]
        rows.append(f"; FC3D_V1106_ARC_START layer={ARC_LAYER_INDEX} path={idx} radius_mm={rec['radius_mm']:.6f}")
        rows.append(f"G0 X{pts[0][0]:.3f} Y{pts[0][1]:.3f} ; FC3D_V1106_ARC_MOVE_TO_START")
        for j, (a, b) in enumerate(zip(pts, pts[1:])):
            e = math.hypot(b[0] - a[0], b[1] - a[1]) * CALIBRATED_E_PER_MM
            rows.append(f"G1 X{b[0]:.3f} Y{b[1]:.3f} E{e:.5f} ; FC3D_V1106_ARC_SEG path={idx} seg={j}")
        rows.append(f"; FC3D_V1106_ARC_END layer={ARC_LAYER_INDEX} path={idx}")
    return rows


def apply_mirror_wave_paths(output, *unused):
    """Replace the optical placeholder with the real dual-A + XYZ-B construction."""
    if RUNTIME_ORIGIN is None:
        raise RuntimeError("MIRROR WAVE PATCH: runtime origin missing")
    output=Path(output); name="Metadata/plate_1.gcode"
    with zipfile.ZipFile(output,"r") as z:
        lines=z.read(name).decode("utf-8",errors="replace").splitlines()
    xo,yo=RUNTIME_ORIGIN
    ph=_placeholder_segment(xo,yo); pkey=_coord_key((ph[0],ph[1]),(ph[2],ph[3]))
    layer_re=re.compile(r";\s*DIRECT_LAYER\s+V4\s+physical=(\d+)")
    x_re=re.compile(r"\sX([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    y_re=re.compile(r"\sY([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    e_re=re.compile(r"\sE([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    starts=[i for i,l in enumerate(lines) if layer_re.search(l)]
    if len(starts)!=PHYSICAL_LAYER_COUNT:
        raise RuntimeError(f"MIRROR WAVE PATCH: DIRECT_LAYER count {len(starts)} != {PHYSICAL_LAYER_COUNT}")
    starts.append(len(lines)); rebuilt=lines[:starts[0]]
    counts={"inner_segments":0,"main_segments":0,"b_segments":0,"b_paths":0,"families":0}
    for li in range(PHYSICAL_LAYER_COUNT):
        block=lines[starts[li]:starts[li+1]]
        if li!=ARC_LAYER_INDEX:
            rebuilt.extend(block); continue
        in_model=False; xy=None; found=[]
        for i,line in enumerate(block):
            st=line.strip()
            if st.startswith("; FEATURE:"):
                in_model="DIRECT_DETERMINISTIC_ROADS_" in st; xy=None; continue
            if not in_model or not (st.startswith("G0") or st.startswith("G1")): continue
            xm,ym=x_re.search(line),y_re.search(line)
            if not (xm or ym): continue
            old=xy
            nx=float(xm.group(1)) if xm else (old[0] if old else None)
            ny=float(ym.group(1)) if ym else (old[1] if old else None)
            if nx is None or ny is None: continue
            newxy=(nx,ny); em=e_re.search(line)
            if old is not None and st.startswith("G1") and em and float(em.group(1))>0 and _coord_key(old,newxy)==pkey:
                found.append(i)
            xy=newxy
        if len(found)!=1:
            raise RuntimeError(f"MIRROR WAVE PATCH layer {li}: placeholder matches={found!r}")
        a=found[0]
        layer_rows=_explicit_mirror_wave_layer_gcode(_current_piece(),xo,yo)
        replacement=[f"; FC3D_V1106_MIRROR_WAVE_START layer={li} piece={_current_piece().name}"]+layer_rows+[f"; FC3D_V1106_MIRROR_WAVE_END layer={li} piece={_current_piece().name}"]
        counts["inner_segments"]=0
        counts["main_segments"]=sum("FC3D_V1106_A_ROAD_SEG" in r for r in layer_rows)
        counts["b_segments"]=sum("FC3D_V1106_B_SEG" in r for r in layer_rows)
        counts["b_paths"]=sum("FC3D_V1106_B_PATH_START" in r for r in layer_rows)
        counts["families"]=sum("FC3D_V1106_B_FAMILY_START" in r for r in layer_rows)
        entry_prefix=list(block[:a])
        eonly=[]
        for j in range(0,a):
            st=entry_prefix[j].strip()
            if re.match(r"^G1\b",st) and re.search(r"\bE[-+]?\d",st) and not re.search(r"\b[XYZ][-+]?\d",st):
                em=e_re.search(st)
                if em:
                    eonly.append((j,float(em.group(1)),st))
        # The support-ending -0.400 belongs to the preceding physical-layer block,
        # not this DIRECT_LAYER block. Prove locally that the inherited +0.400
        # placeholder is the only E-only state change before the replaced road;
        # the whole-G-code post-audit proves the cross-boundary predecessor.
        if len(eonly)!=1 or abs(eonly[0][1]-0.400)>1e-9:
            raise RuntimeError(f"MIRROR WAVE PATCH layer {li}: expected exactly one inherited +0.400 E-only placeholder prime before A replacement, got {eonly}")
        prime_i=eonly[0][0]
        entry_prefix[prime_i]="G1 E-0.400 F1800 ; FC3D_V1106_A_ENTRY_EXTRA_RETRACT base_minus_0.400_to_a1_minus_0.800"
        rebuilt.extend(entry_prefix); rebuilt.extend(replacement); rebuilt.extend(block[a+1:])
    _replace_zip_members(output,{name:("\n".join(rebuilt)+"\n").encode("utf-8")})
    return {"piece":_current_piece().name,**counts}



def audit_final_mirror_wave_paths(output,*unused):
    output=Path(output)
    with zipfile.ZipFile(output,"r") as z:
        lines=z.read("Metadata/plate_1.gcode").decode("utf-8",errors="replace").splitlines()
    txt="\n".join(lines)
    geo=get_true_normal_wave_sets(_current_piece())
    if txt.count("FC3D_V1106_WAVESETS_START")!=1 or txt.count("FC3D_V1106_WAVESETS_END")!=1:
        raise RuntimeError("FINAL V1.106 AUDIT: wave-set boundaries missing")
    starts=re.findall(r"FC3D_V1106_WAVESET_START set=(\d+)",txt)
    if len(starts)!=geo["set_count"]: raise RuntimeError(f"FINAL V1.106 AUDIT: set count {len(starts)} != {geo['set_count']}")
    if [int(x) for x in starts] != list(range(1,len(starts)+1)): raise RuntimeError("FINAL V1.106 AUDIT: set order invalid")
    dry=[l for l in lines if "FC3D_V1106_WAVESET_DRY_TAIL" in l]
    if len(dry)!=geo["set_count"]: raise RuntimeError(f"FINAL V1.106 AUDIT: dry-tail count {len(dry)} != {geo['set_count']}")
    for l in dry:
        m=re.search(r"len=([-+0-9.]+)",l)
        if not m or abs(float(m.group(1))-A_ENDPOINT_DRY_TAIL_MM)>0.0015: raise RuntimeError(f"FINAL V1.106 AUDIT: dry-tail length {l}")
    if any(tag in txt for tag in ("FC3D_V1106_A_INNER_","FC3D_V1106_A_MAIN_","FC3D_V1106_B_SEG")):
        raise RuntimeError("FINAL V1.106 AUDIT: obsolete paired/B geometry leaked")
    wave_lines=[l for l in lines if "FC3D_V1106_WAVE_ARC" in l or "FC3D_V1106_WAVE_CONNECT" in l]
    if not wave_lines: raise RuntimeError("FINAL V1.106 AUDIT: no wave extrusion")
    zvals=[]; epm=[]
    for l in wave_lines:
        m=re.search(r"\bZ([-+0-9.]+)",l); e=re.search(r"\bE([-+0-9.]+)",l); lm=re.search(r"L3=([-+0-9.]+)",l)
        if not(m and e and lm): raise RuntimeError(f"FINAL V1.106 AUDIT: malformed wave line {l}")
        zvals.append(float(m.group(1))); L=float(lm.group(1)); E=float(e.group(1));
        if L>1e-9: epm.append(E/L)
        if f"F{WAVESET_PRINT_FEED_MM_S*60:.0f}" not in l: raise RuntimeError(f"FINAL V1.106 AUDIT: wrong wave feed {l}")
    if max(zvals)-min(zvals)>1e-9 or abs(zvals[0]-WAVESET_COMMAND_Z_MM)>1e-6:
        raise RuntimeError(f"FINAL V1.106 AUDIT: logical G1 Z varied {min(zvals)}..{max(zvals)}")
    total_l=0.0; total_e=0.0; rounded_zero=[]
    for l in wave_lines:
        em=re.search(r"\bE([-+0-9.]+)",l); lm=re.search(r"L3=([-+0-9.]+)",l)
        L=float(lm.group(1)); E=float(em.group(1)); total_l+=L; total_e+=E
        if E==0.0: rounded_zero.append(L)
    aggregate_e_per_mm=total_e/max(total_l,1e-12)
    if abs(aggregate_e_per_mm-A_MAIN_E_PER_MM)>2e-6:
        raise RuntimeError(f"FINAL V1.106 AUDIT: aggregate 3D E/mm {aggregate_e_per_mm:.9f} != {A_MAIN_E_PER_MM:.9f}")
    if rounded_zero and max(rounded_zero)>0.001:
        raise RuntimeError(f"FINAL V1.106 AUDIT: rounded-zero extrusion on nontrivial 3D segment {max(rounded_zero):.6f} mm")
    rep=waveset_report(_current_piece())
    if rep["front_normal_error_max"]>0.01: raise RuntimeError(f"FINAL V1.106 AUDIT: front-normal error {rep['front_normal_error_max']}")
    if rep["hidden_projector_clearance_min_mm"]<WAVESET_HIDDEN_PROJECTOR_MARGIN_MM-1e-9:
        raise RuntimeError(f"FINAL V1.106 AUDIT: hidden surface visible {rep}")
    return {"wave_sets":rep["set_count"],"wave_cells":rep["cell_count"],"wave_roads":rep["road_count"],
            "wave_feed_mm_s":WAVESET_PRINT_FEED_MM_S,"logical_z_constant":True,"logical_z_mm":WAVESET_COMMAND_Z_MM,
            "e_per_3d_mm_aggregate":aggregate_e_per_mm,"rounded_zero_max_length_mm":max(rounded_zero) if rounded_zero else 0.0,"wave_set_report":rep,
            "rear_label_transform":"text_none_arrow_vertical_flip"}




def apply_concentric_arc_paths(output, *unused):
    if RUNTIME_ORIGIN is None:
        raise RuntimeError("ARC PATCH: runtime origin missing")
    output = Path(output)
    name = "Metadata/plate_1.gcode"
    with zipfile.ZipFile(output, "r") as z:
        lines = z.read(name).decode("utf-8", errors="replace").splitlines()
    xo, yo = RUNTIME_ORIGIN
    ph = _placeholder_segment(xo, yo)
    pkey = _coord_key((ph[0], ph[1]), (ph[2], ph[3]))
    layer_re = re.compile(r";\s*DIRECT_LAYER\s+V4\s+physical=(\d+)")
    x_re = re.compile(r"\sX([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    y_re = re.compile(r"\sY([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    e_re = re.compile(r"\sE([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    starts = [i for i, l in enumerate(lines) if layer_re.search(l)]
    if len(starts) != PHYSICAL_LAYER_COUNT:
        raise RuntimeError(f"ARC PATCH: DIRECT_LAYER count {len(starts)} != {PHYSICAL_LAYER_COUNT}")
    starts.append(len(lines))
    rebuilt = lines[:starts[0]]
    path_count = 0
    segment_count = 0
    for li in range(PHYSICAL_LAYER_COUNT):
        block = lines[starts[li]:starts[li + 1]]
        if li != ARC_LAYER_INDEX:
            rebuilt.extend(block)
            continue
        in_model = False
        xy = None
        found = []
        for i, line in enumerate(block):
            st = line.strip()
            if st.startswith("; FEATURE:"):
                in_model = "DIRECT_DETERMINISTIC_ROADS_" in st
                xy = None
                continue
            if not in_model or not (st.startswith("G0") or st.startswith("G1")):
                continue
            xm, ym = x_re.search(line), y_re.search(line)
            if not (xm or ym):
                continue
            old = xy
            nx = float(xm.group(1)) if xm else (old[0] if old else None)
            ny = float(ym.group(1)) if ym else (old[1] if old else None)
            if nx is None or ny is None:
                continue
            new = (nx, ny)
            em = e_re.search(line)
            if old is not None and st.startswith("G1") and em and float(em.group(1)) > 0 and _coord_key(old, new) == pkey:
                found.append(i)
            xy = new
        if len(found) != 1:
            raise RuntimeError(f"ARC PATCH layer {li}: placeholder matches={found!r}")
        a = found[0]
        replacement = [f"; FC3D_V1106_OPTICAL_ARCS_START layer={li} piece={_current_piece().name}"]
        layer_rows = _explicit_arc_layer_gcode(xo, yo)
        replacement.extend(layer_rows)
        replacement.append(f"; FC3D_V1106_OPTICAL_ARCS_END layer={li} piece={_current_piece().name}")
        path_count = sum(1 for row in layer_rows if row.startswith("; FC3D_V1106_ARC_START"))
        segment_count = sum(1 for row in layer_rows if "FC3D_V1106_ARC_SEG" in row)
        rebuilt.extend(block[:a])
        rebuilt.extend(replacement)
        rebuilt.extend(block[a + 1:])
    _replace_zip_members(output, {name: ("\n".join(rebuilt) + "\n").encode("utf-8")})
    return {"piece": _current_piece().name, "path_count": path_count, "segment_count": segment_count, "radial_pitch_mm": ARC_RADIAL_PITCH_MM, "segment_max_len_mm": ARC_SEGMENT_MAX_LEN_MM}


def audit_final_base_interlock(output):
    output = Path(output)
    with zipfile.ZipFile(output, "r") as z:
        lines = z.read("Metadata/plate_1.gcode").decode("utf-8", errors="replace").splitlines()
    layer_re = re.compile(r";\s*DIRECT_LAYER\s+V4\s+physical=(\d+)")
    x_re = re.compile(r"\sX([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    y_re = re.compile(r"\sY([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    e_re = re.compile(r"\sE([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    starts = [i for i, l in enumerate(lines) if layer_re.search(l)]
    if len(starts) != PHYSICAL_LAYER_COUNT:
        raise RuntimeError(f"BASE INTERLOCK AUDIT: DIRECT_LAYER count {len(starts)} != {PHYSICAL_LAYER_COUNT}")
    starts.append(len(lines))
    orientations = []
    draw_counts = []
    for li in range(BASE_LAYER_COUNT):
        block = lines[starts[li]:starts[li + 1]]
        xy = None
        xdraw = ydraw = draws = 0
        for line in block:
            st = line.strip()
            if not (st.startswith("G0") or st.startswith("G1")):
                continue
            xm, ym, em = x_re.search(line), y_re.search(line), e_re.search(line)
            if not (xm or ym):
                continue
            old = xy
            nx = float(xm.group(1)) if xm else (old[0] if old else None)
            ny = float(ym.group(1)) if ym else (old[1] if old else None)
            if nx is None or ny is None:
                continue
            new = (nx, ny)
            if old is not None and st.startswith("G1") and em and float(em.group(1)) > 0:
                dx = abs(new[0] - old[0])
                dy = abs(new[1] - old[1])
                if max(dx, dy) >= 10.0:  # structural raster roads; ignore tiny priming/tower moves
                    draws += 1
                    if dx > dy * 5.0:
                        xdraw += 1
                    elif dy > dx * 5.0:
                        ydraw += 1
            xy = new
        if draws < 100:
            raise RuntimeError(f"BASE INTERLOCK AUDIT layer {li}: too few structural draws {draws}")
        orientation = "X" if xdraw > ydraw else "Y"
        orientations.append(orientation)
        draw_counts.append({"layer": li, "X": xdraw, "Y": ydraw, "total": draws})
    expected_orientations = ["X" if i % 2 == 0 else "Y" for i in range(BASE_LAYER_COUNT)]
    if orientations != expected_orientations:
        raise RuntimeError(f"BASE INTERLOCK AUDIT: expected {expected_orientations}, got {orientations}; {draw_counts}")
    return {"orientations": orientations, "draw_counts": draw_counts}


def audit_final_arc_paths(output, *unused):
    output = Path(output)
    with zipfile.ZipFile(output, "r") as z:
        lines = z.read("Metadata/plate_1.gcode").decode("utf-8", errors="replace").splitlines()
    layer_re = re.compile(r";\s*DIRECT_LAYER\s+V4\s+physical=(\d+)")
    x_re = re.compile(r"\sX([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    y_re = re.compile(r"\sY([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    e_re = re.compile(r"\sE([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    starts = [i for i, l in enumerate(lines) if layer_re.search(l)]
    if len(starts) != PHYSICAL_LAYER_COUNT:
        raise RuntimeError(f"FINAL ARC AUDIT: DIRECT_LAYER count {len(starts)} != {PHYSICAL_LAYER_COUNT}")
    starts.append(len(lines))
    block = lines[starts[ARC_LAYER_INDEX]:starts[ARC_LAYER_INDEX + 1]]
    sidx = next((i for i, l in enumerate(block) if "FC3D_V1106_OPTICAL_ARCS_START" in l), None)
    eidx = next((i for i, l in enumerate(block) if "FC3D_V1106_OPTICAL_ARCS_END" in l), None)
    if sidx is None or eidx is None or not sidx < eidx:
        raise RuntimeError("FINAL ARC AUDIT: optical-arc layer markers missing")
    expected = _arc_paths_absolute(_current_piece(), *RUNTIME_ORIGIN)
    active_path = -1
    pts = []
    seen = []
    path_markers = 0
    segment_total = 0
    for line in block[sidx + 1:eidx]:
        st = line.strip()
        if st.startswith("; FC3D_V1106_ARC_START"):
            if active_path != -1:
                raise RuntimeError("FINAL ARC AUDIT: nested arc start")
            m = re.search(r"path=(\d+)", st)
            active_path = int(m.group(1))
            pts = []
            path_markers += 1
            continue
        if st.startswith("; FC3D_V1106_ARC_END"):
            if active_path == -1:
                raise RuntimeError("FINAL ARC AUDIT: arc end without start")
            seen.append((active_path, pts))
            active_path = -1
            pts = []
            continue
        if active_path == -1:
            continue
        xm, ym, em = x_re.search(line), y_re.search(line), e_re.search(line)
        if xm and ym:
            pts.append((float(xm.group(1)), float(ym.group(1)), None if em is None else float(em.group(1)), line))
            if em and float(em.group(1)) > 0:
                segment_total += 1
    if active_path != -1:
        raise RuntimeError("FINAL ARC AUDIT: unterminated arc")
    if len(seen) != len(expected):
        raise RuntimeError(f"FINAL ARC AUDIT: path count {len(seen)} != {len(expected)}")
    tol = 0.004
    expected_segment_total = 0
    for idx, (seen_idx, seen_rows) in enumerate(seen):
        if seen_idx != idx:
            raise RuntimeError(f"FINAL ARC AUDIT: path order mismatch {seen_idx} != {idx}")
        exp_pts = expected[idx]["points"]
        g1_rows = [row for row in seen_rows if row[2] is not None and row[2] > 0.0]
        if len(g1_rows) != len(exp_pts) - 1:
            raise RuntimeError(f"FINAL ARC AUDIT path {idx}: segments {len(g1_rows)} != {len(exp_pts) - 1}")
        expected_segment_total += len(exp_pts) - 1
        for j, ((x, y, e, line), a, b) in enumerate(zip(g1_rows, exp_pts, exp_pts[1:])):
            if math.hypot(x - b[0], y - b[1]) > tol:
                raise RuntimeError(f"FINAL ARC AUDIT path {idx} seg {j}: coordinate mismatch")
            want_e = math.hypot(b[0] - a[0], b[1] - a[1]) * CALIBRATED_E_PER_MM
            if abs(e - want_e) > 0.00012:
                raise RuntimeError(f"FINAL ARC AUDIT path {idx} seg {j}: E mismatch")
    return {"path_count": len(expected), "segment_count": expected_segment_total, "arc_start_markers": path_markers}


def audit_final_black_texture_and_single_material(output):
    """Audit the v1.106 black-only rear texture and single-material lifecycle."""
    output=Path(output)
    with zipfile.ZipFile(output,"r") as z:
        lines=z.read("Metadata/plate_1.gcode").decode("utf-8",errors="replace").splitlines()
    layer_re=re.compile(r";\s*DIRECT_LAYER\s+V4\s+physical=(\d+)")
    starts=[i for i,l in enumerate(lines) if layer_re.search(l)]
    if len(starts)!=PHYSICAL_LAYER_COUNT:
        raise RuntimeError(f"BLACK TEXTURE AUDIT: layer count {len(starts)} != {PHYSICAL_LAYER_COUNT}")
    starts.append(len(lines))
    features=[]
    for li in range(PHYSICAL_LAYER_COUNT):
        block=lines[starts[li]:starts[li+1]]
        mats=sorted({m.group(1) for line in block if (m:=re.search(r"FEATURE: DIRECT_DETERMINISTIC_ROADS_([WFRYGCB])",line))})
        features.append(mats)
    used={m for mats in features for m in mats}
    if used != {LOGICAL_MATERIAL}:
        raise RuntimeError(f"BLACK TEXTURE AUDIT: expected W-only model material, got {sorted(used)} from {features}")
    if any("FC3D_PPSPV43_FULL_H2C_SWAP_START" in l for l in lines):
        raise RuntimeError("BLACK TEXTURE AUDIT: unexpected material-swap block in black-only job")
    if any("FEATURE: DIRECT_SOLID_PRIME_TOWER_V57" in l for l in lines):
        raise RuntimeError("BLACK TEXTURE AUDIT: prime tower remains in single-material job")
    return {
        "layer_materials":features,
        "single_material":LOGICAL_MATERIAL,
        "rear_texture":f"{_current_piece().name} + {REAR_VERSION_TEXT} + UP arrow by first-layer black-road omissions",
        "prime_tower_present":False,
        "material_swaps_present":False,
    }

def audit_final_panel_xy_geometry(output):
    piece=_current_piece(); lat=get_mirror_wave_lattice(piece)
    return {
        "piece":piece.name,"panel_width_x_mm":piece.width_mm,"panel_height_y_mm":piece.height_mm,
        "nominal_layer_top_z_mm":NOMINAL_TOP_Z_MM,
        "physical_peak_z_mm":_mirror_wave_peak_z_mm(),"physical_layers":PHYSICAL_LAYER_COUNT,
        "base_interlock":["X" if i % 2 == 0 else "Y" for i in range(BASE_LAYER_COUNT)],"road_width_mm":ROAD_WIDTH_MM,
        "global_x_range_mm":[piece.global_x0_mm,piece.global_x1_mm],
        "global_z_range_mm":[piece.global_z0_mm,piece.global_z1_mm],
        "wave_relief_mm":WAVE_RELIEF_MM,"a_main_height_mm":A_MAIN_HEIGHT_MM,"a_inner_enabled":False,
        "initial_b_road_count":lat["initial_road_count"],"wave_count":lat["wave_count"],
        "family_count":len(lat["families"]),"family_reset_count":lat["family_reset_count"],
    }


def _tangent_error_ratio(a, b, piece: PieceSpec):
    gx = piece.global_x0_mm + 0.5 * (a[0] + b[0])
    gz = piece.global_z0_mm + 0.5 * (a[1] + b[1])
    tx = b[0] - a[0]
    ty = b[1] - a[1]
    rx = gx - MASTER_FAN.projector_x_mm
    rz = gz - MASTER_FAN.projector_z_mm
    tmag = math.hypot(tx, ty)
    rmag = math.hypot(rx, rz)
    if tmag <= 1e-9 or rmag <= 1e-9:
        return 0.0
    return abs(tx * rx + ty * rz) / (tmag * rmag)


def write_audit_json(path, report):
    p = Path(path)
    p.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return p



def dry_validate_v1106(dp):
    piece=_current_piece()
    if abs(float(getattr(dp,"BASE_H_MM",-1))-FIRST_LAYER_H_MM)>1e-9 or abs(float(getattr(dp,"MIX_H_MM",-1))-LAYER_H_MM)>1e-9:
        raise RuntimeError("v1.106: canonical 0.20/0.10 layer-height patch mismatch")
    base_layers=[_base_roads_for_layer(li,0.0,0.0) for li in range(BASE_LAYER_COUNT)]
    base_orient=[]
    for li,base in enumerate(base_layers):
        dx=sum(abs(seg[2]-seg[0]) for seg in base); dy=sum(abs(seg[3]-seg[1]) for seg in base); base_orient.append("X" if dx>dy else "Y")
    if base_orient != ["X","Y","X"]: raise RuntimeError(f"v1.106: base interlock {base_orient}")
    geo=get_true_normal_wave_sets(piece); rep=waveset_report(piece)
    if geo["cell_count"]<2 or len(geo["roads"])<5: raise RuntimeError(f"v1.106: insufficient wave geometry {rep}")
    if rep["front_normal_error_max"]>0.01: raise RuntimeError(f"v1.106: front normal error {rep['front_normal_error_max']}")
    if rep["hidden_projector_clearance_min_mm"]<WAVESET_HIDDEN_PROJECTOR_MARGIN_MM-1e-9: raise RuntimeError(f"v1.106: hidden top visible {rep}")
    print("DRY V1.106 VALIDATION: PASS")
    print(f"  piece                         : {piece.name}")
    print(f"  base interlock                : {'/'.join(base_orient)}")
    print(f"  wave sets / cells / roads     : {rep['set_count']} / {rep['cell_count']} / {rep['road_count']}")
    print(f"  wave peak / optical rise      : {WAVESET_TOTAL_PEAK_MM:.3f} / {WAVESET_OPTICAL_RISE_MM:.3f} mm")
    print(f"  pitch min/mean/max            : {rep['pitch_mm']['min']:.4f} / {rep['pitch_mm']['mean']:.4f} / {rep['pitch_mm']['max']:.4f} mm")
    print(f"  front normal max error        : {rep['front_normal_error_max']:.6g}")
    print(f"  hidden projector clearance    : {rep['hidden_projector_clearance_min_mm']:.4f} mm")
    print(f"  wave extrusion feed           : {WAVESET_PRINT_FEED_MM_S:.1f} mm/s")
    print(f"  top valley filler             : {TOP_SUPPORT_FILL_VE*100:.0f}% at effective Z{TOP_SUPPORT_FILL_EFFECTIVE_Z_MM:.3f}")




A1_MINI_NOZZLE_C = 255
A1_MINI_BED_C = 70
A1_MINI_MODEL_ID = "N1"
A1_MINI_PRINTER_NAME = "Bambu Lab A1 mini"
A1_MINI_PRINTER_PRESET = "Bambu Lab A1 mini 0.4 nozzle"
A1_MINI_PROCESS_PRESET = "0.20mm Standard @BBL A1M"


def _a1mini_start_gcode() -> str:
    """Reduced A1 Mini single-material start derived from Orca A1 Mini ordering.

    Keep the nozzle below PETG print temperature during cleaning/probing, enable
    the ABL mesh before G29, commit the completed probe, then block at 255 C and
    condition the already-loaded black PETG in the unused front bed margin.
    Conditioning exits retracted by the active A-road retract for the canonical model contract.
    """
    return "\n".join([
        "; FC3D_V1106_A1MINI_START",
        "; machine: A1 mini / single 0.4 mm nozzle / black PETG",
        "M1002 gcode_claim_action : 2",
        "M17",
        "G90",
        "M83",
        "M220 S100",
        "M221 S100",
        "M104 S170",
        f"M140 S{A1_MINI_BED_C}",
        "G28",

        "; FC3D_V1106_A1MINI_NOZZLE_WIPE_START",
        "M1002 gcode_claim_action : 14",
        "M104 S170",
        "M106 S255",
        "M211 S",
        "M211 X0 Y0 Z0",
        "M83",
        "G1 E-1.000 F500",
        "M109 S170",
        "M104 S140",
        "G1 Z5.000 F3000",
        "G1 X25.000 Y175.000 F30000",
        "G1 Z0.200 F30000",
        "G1 Y185.000 F30000",
        "G91",
        "G1 X-30.000 F30000",
        "G1 Y-2.000",
        "G1 X27.000",
        "G1 Y1.500",
        "G1 X-28.000",
        "G1 Y-2.000",
        "G1 X30.000",
        "G1 Y1.500",
        "G1 X-30.000",
        "G90",
        "M83",
        "G1 Z5.000 F3000",
        "M211 R",
        "M106 S0",
        "; FC3D_V1106_A1MINI_NOZZLE_WIPE_END",

        "; A1 native thermal/ABL ordering",
        "M104 S0",
        f"M190 S{A1_MINI_BED_C}",
        "M109 S140",
        "G1 Z5.000 F3000",
        "G29.2 S1",
        "G1 X10.000 Y10.000 F20000",
        "M1002 gcode_claim_action : 1",
        "G29 A1 X20 Y20 I140 J140",
        "M400",
        "M500",
        "G29.1 Z-0.02 ; Textured PEI",

        "; FC3D_V1106_A1MINI_CONDITION_START",
        "G90",
        "M83",
        "G0 X10.000 Y5.000 Z2.000 F12000",
        f"M104 S{A1_MINI_NOZZLE_C}",
        f"M109 S{A1_MINI_NOZZLE_C}",
        "G92 E0",
        "G0 Z0.300 F900",
        "G1 X20.000 Y5.000 E1.000 F1200 ; recover wipe retract while moving",
        "G1 X50.000 Y5.000 E1.200 F1200 ; short single-material conditioning line",
        f"G1 E-{A_RETRACT_MM:.3f} F1800 ; leave canonical model retracted",
        "G0 Z2.000 F900",
        "; FC3D_V1106_A1MINI_CONDITION_END state=RETRACTED",
        "M106 S0",
        "M1002 gcode_claim_action : 0",
        "; FC3D_V1106_A1MINI_START_END",
    ])



def _a1mini_end_gcode(final_z: float) -> str:
    # Relative lift can never command beyond the A1 Mini's 180-mm Z envelope.
    clearance = max(0.0, 180.0 - float(final_z) - 0.20)
    lift = min(5.0, clearance)
    rows = [
        "; FC3D_V1106_A1MINI_END",
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
        "; FC3D_V1106_A1MINI_END_DONE",
        "; EXECUTABLE_BLOCK_END",
    ]
    return "\n".join(rows)



def _strip_prime_tower_blocks(lines):
    """Audit-only at the A1 conversion boundary.

    All tower deletion belongs to apply_dynamic_tower_policy().  Any surviving
    explicit, scheduler, filler or post-tower lifecycle marker is fatal here.
    """
    rows = list(lines)
    forbidden = (
        "WIPE_TOWER_START DIRECT_SOLID_",
        "WIPE_TOWER_END DIRECT_SOLID_",
        "FEATURE: DIRECT_SOLID_PRIME_TOWER",
        "DIRECT_SOLID_PRIME_TOWER_V57",
        "PRIME_TOWER_PPV64_CONTINUOUS_STUDIO_X",
        "PRIME_TOWER_V169_CANONICAL_FILLER",
        "FC3D_TOWER_PRIMARY_STRUCTURAL_FILL",
        "FC3D_TOWER_SECONDARY_GAPS_V156",
        "FC3D_TOWER_LAYER_COMPLETE_V129",
        "FC3D_TOWER_FILL_NO_SWAP",
        "FC3D_PPV64_SOLID_WHITE_TOWER_BASE",
        "WIPE_START FC3D_PPSPV47_POST_TOWER_SAFE_LIFTED",
        "WIPE_END FC3D_PPSPV47_POST_TOWER_SAFE_LIFTED",
        "FC3D_PPSPV47_TOWER_EXIT_ALREADY_LIFTED_NEXT_TRAVEL_SAFE",
        "FC3D_V150_TOWER_PRESSURE_STATE",
        "reason=TOWER_TRAVEL",
        "PPSPV53 tower XY",
    )
    slot_re = re.compile(r"^\s*;\s*FC3D_TOWER_SLOT(?:\s|$)")
    hits = [
        (i + 1, line) for i, line in enumerate(rows)
        if any(tok in line for tok in forbidden) or slot_re.match(line)
    ]
    if hits:
        raise RuntimeError(
            "V1.101 A1 MINI: tower lifecycle incomplete before package conversion; "
            f"first surviving lines={hits[:8]}"
        )
    return rows, 0



def _replace_config_comment(gcode: str, key: str, value: str) -> str:
    pat = re.compile(rf"^; {re.escape(key)} = .*?$", re.M)
    replacement = f"; {key} = {value}"
    if pat.search(gcode):
        # Callable replacement is deliberate: re.sub replacement strings parse
        # backslash escapes, which would turn literal \\n config separators into
        # physical newlines and leak startup markers into the header namespace.
        return pat.sub(lambda _m: replacement, gcode, count=1)
    end = gcode.find("; CONFIG_BLOCK_END")
    if end < 0:
        raise RuntimeError("V1.101 A1 MINI: CONFIG_BLOCK_END missing")
    return gcode[:end] + replacement + "\n" + gcode[end:]



def convert_package_to_a1mini_orca(output: Path) -> dict:
    """Convert the canonical H2C package shell to an A1 Mini single-nozzle job.

    The FC3D model section is retained; H2C startup/end/tool lifecycle is replaced,
    the model is centred at 90/90 by the generation command, prime tower is removed,
    and printer/package metadata is normalised to the current Orca A1 Mini profile.
    """
    output=Path(output)
    gname="Metadata/plate_1.gcode"; pname="Metadata/project_settings.config"
    sname="Metadata/slice_info.config"; platejson="Metadata/plate_1.json"
    with zipfile.ZipFile(output,"r") as z:
        names=set(z.namelist())
        for n in (gname,pname,sname,platejson):
            if n not in names: raise RuntimeError(f"V1.91 A1 MINI: missing {n}")
        g=z.read(gname).decode("utf-8",errors="strict")
        project=json.loads(z.read(pname).decode("utf-8"))
        slice_root=ET.fromstring(z.read(sname))
        plate=json.loads(z.read(platejson).decode("utf-8"))

    lines=g.splitlines()
    first_layer=next((i for i,l in enumerate(lines) if l.strip()=="; CHANGE_LAYER"),None)
    model_end=next((i for i,l in enumerate(lines) if l.strip()=="; V4_MODEL_END"),None)
    if first_layer is None or model_end is None or first_layer>=model_end:
        raise RuntimeError("V1.91 A1 MINI: cannot isolate canonical model block")
    model_lines, removed_tower=_strip_prime_tower_blocks(lines[first_layer:model_end+1])
    model_text="\n".join(model_lines)
    forbidden=("FC3D_PPSPV43_FULL_H2C_SWAP_START","M640.8","G151 ","M481 ")
    if any(x in model_text for x in forbidden):
        raise RuntimeError("V1.91 A1 MINI: H2C/Vortek lifecycle leaked into model block")

    # Determine actual model peak before constructing a bounded finish lift.
    zs=[float(m.group(1)) for l in model_lines if (m:=re.search(r"\bZ(-?\d+(?:\.\d+)?)",l))]
    final_z=max(zs) if zs else PHYSICAL_LAYER_COUNT*LAYER_H_MM
    header=lines[:]
    exec_i=next((i for i,l in enumerate(lines) if l.strip()=="; EXECUTABLE_BLOCK_START"),None)
    if exec_i is None: raise RuntimeError("V1.91 A1 MINI: executable block marker missing")
    header=lines[:exec_i+1]
    new_g="\n".join(header)+"\n"+_a1mini_start_gcode()+"\n"+model_text+"\n"+_a1mini_end_gcode(final_z)+"\n"

    # G-code config metadata: current Orca A1 Mini machine contract.
    cfg={
      "printer_model": A1_MINI_PRINTER_NAME,
      "printer_settings_id": A1_MINI_PRINTER_PRESET,
      "print_settings_id": A1_MINI_PROCESS_PRESET,
      "print_compatible_printers": f'"{A1_MINI_PRINTER_PRESET}"',
      "printer_structure": "i3",
      "printable_area": "0x0,180x0,180x180,0x180",
      "printable_height": "180",
      "nozzle_diameter": "0.4",
      "nozzle_type": "stainless_steel",
      "nozzle_volume": "92",
      "nozzle_volume_type": "Standard",
      "default_nozzle_volume_type": "Standard",
      "enable_prime_tower": "0",
      "prime_tower_enable_framework": "0",
      "wipe_tower_no_sparse_layers": "0",
      "curr_bed_type": "Textured PEI Plate",
      "machine_start_gcode": _a1mini_start_gcode().replace("\\","\\\\").replace("\n","\\n"),
      "machine_end_gcode": _a1mini_end_gcode(final_z).replace("\\","\\\\").replace("\n","\\n"),
    }
    for k,v in cfg.items(): new_g=_replace_config_comment(new_g,k,v)
    new_g=_replace_config_comment(new_g,"enable_prime_tower","0")

    # Project settings. Keep filament chemistry/calibration arrays inherited from
    # v1.179, but collapse all machine/nozzle identity to the A1 Mini single nozzle.
    project.update({
      "printer_model":A1_MINI_PRINTER_NAME,
      "printer_settings_id":A1_MINI_PRINTER_PRESET,
      "print_settings_id":A1_MINI_PROCESS_PRESET,
      "print_compatible_printers":[A1_MINI_PRINTER_PRESET],
      "printer_structure":"i3",
      "printable_area":["0x0","180x0","180x180","0x180"],
      "printable_height":"180",
      "nozzle_diameter":["0.4"],
      "nozzle_type":["stainless_steel"],
      "nozzle_volume":["92"],
      "nozzle_volume_type":["Standard"],
      "default_nozzle_volume_type":["Standard"],
      "printer_extruder_id":["1"], "print_extruder_id":["1"],
      "printer_extruder_variant":["Direct Drive Standard"],
      "print_extruder_variant":["Direct Drive Standard"],
      "enable_prime_tower":"0", "prime_tower_enable_framework":"0",
      "curr_bed_type":"Textured PEI Plate",
      "machine_start_gcode":_a1mini_start_gcode()+"\n",
      "machine_end_gcode":_a1mini_end_gcode(final_z)+"\n",
    })

    # Slice metadata: one standard-flow 0.4-mm nozzle and one black PETG filament.
    plate_node=slice_root.find("plate")
    if plate_node is None: raise RuntimeError("V1.91 A1 MINI: missing slice plate")
    for n in list(plate_node):
        if n.tag in ("filament","nozzle","layer_filament_lists"):
            plate_node.remove(n)
    meta={n.attrib.get("key"):n for n in plate_node.findall("metadata")}
    def sm(k,v):
        if k in meta: meta[k].set("value",str(v))
        else: ET.SubElement(plate_node,"metadata",{"key":k,"value":str(v)})
    sm("extruder_type","0"); sm("nozzle_volume_type","0"); sm("printer_model_id",A1_MINI_MODEL_ID)
    sm("nozzle_diameters","0.4"); sm("enable_filament_dynamic_map","false")
    sm("has_filament_switcher","false"); sm("filament_maps","1"); sm("limit_filament_maps","0")
    sm("fc3d_active_raw_tools","0"); sm("fc3d_active_filament_one_based","1")
    lfl=ET.SubElement(plate_node,"layer_filament_lists")
    ET.SubElement(lfl,"layer_filament_list",{"filament_list":"0","layer_ranges":f"0 {PHYSICAL_LAYER_COUNT-1}"})
    ET.SubElement(plate_node,"filament",{
       "id":"1","tray_info_idx":"GFG99","type":"PETG","color":"#161616",
       "used_m":"0.00","used_g":"0.00","group_id":"0","nozzle_diameter":"0.40",
       "volume_type":"Standard","used_for_object":"true","used_for_support":"false",
       "total_load_time":"0.00","total_unload_time":"0.00"})
    ET.SubElement(plate_node,"nozzle",{"id":"0","extruder_id":"1","nozzle_diameter":"0.4","volume_type":"Standard"})
    slice_bytes=ET.tostring(slice_root,encoding="utf-8",xml_declaration=True)

    plate["filament_ids"]=[0]; plate["first_extruder"]=0; plate["bed_type"]="Textured PEI Plate"
    # Remove any physical tower geometry metadata if present.
    for k in list(plate):
        if "wipe_tower" in k.lower() or "prime_tower" in k.lower():
            if isinstance(plate[k],bool): plate[k]=False
            elif isinstance(plate[k],(int,float)): plate[k]=0

    _replace_zip_members(output,{
      gname:new_g.encode("utf-8"),
      pname:json.dumps(project,separators=(",",":"),ensure_ascii=False).encode("utf-8"),
      sname:slice_bytes,
      platejson:json.dumps(plate,separators=(",",":"),ensure_ascii=False).encode("utf-8"),
    })
    return audit_a1mini_orca_package(output,removed_tower)


def audit_a1mini_orca_package(output: Path, removed_tower_blocks: int = 0) -> dict:
    output = Path(output)
    with zipfile.ZipFile(output, "r") as z:
        gbytes = z.read("Metadata/plate_1.gcode")
        g = gbytes.decode("utf-8")
        project = json.loads(z.read("Metadata/project_settings.config").decode("utf-8"))
        root = ET.fromstring(z.read("Metadata/slice_info.config"))
        md5 = z.read("Metadata/plate_1.gcode.md5").decode("ascii").strip().lower()

    expected_project = {
        "printer_model": A1_MINI_PRINTER_NAME,
        "printer_settings_id": A1_MINI_PRINTER_PRESET,
        "print_settings_id": A1_MINI_PROCESS_PRESET,
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
    for key, expected in expected_project.items():
        if project.get(key) != expected:
            raise RuntimeError(
                f"V1.101 A1 MINI AUDIT: project {key}={project.get(key)!r}, expected {expected!r}"
            )

    lines = g.splitlines()
    exec_starts = [i for i, line in enumerate(lines) if line.strip() == "; EXECUTABLE_BLOCK_START"]
    exec_ends = [i for i, line in enumerate(lines) if line.strip() == "; EXECUTABLE_BLOCK_END"]
    if len(exec_starts) != 1 or len(exec_ends) != 1 or exec_starts[0] >= exec_ends[0]:
        raise RuntimeError(
            "V1.101 A1 MINI AUDIT: executable block boundary invalid: "
            f"starts={exec_starts} ends={exec_ends}"
        )
    exec_start_i = exec_starts[0]
    exec_end_i = exec_ends[0]
    executable_lines = lines[exec_start_i + 1:exec_end_i]
    executable = "\n".join(executable_lines)
    forbidden = (
        "machine: H2C",
        "Vortek",
        "FC3D_PPSPV43_FULL_H2C_SWAP_START",
        "M640.8",
        "G151 ",
        "M481 ",
        "FEATURE: DIRECT_SOLID_PRIME_TOWER",
        "WIPE_TOWER_START DIRECT_SOLID_",
        "WIPE_TOWER_END DIRECT_SOLID_",
        "WIPE_TOWER_END DIRECT_SOLID_V4",
        "PRIME_TOWER_PPV64_CONTINUOUS_STUDIO_X",
        "FC3D_TOWER_PRIMARY_STRUCTURAL_FILL",
        "FC3D_TOWER_SECONDARY_GAPS_V156",
        "FC3D_TOWER_LAYER_COMPLETE_V129",
        "WIPE_START FC3D_PPSPV47_POST_TOWER_SAFE_LIFTED",
        "WIPE_END FC3D_PPSPV47_POST_TOWER_SAFE_LIFTED",
        "FC3D_PPSPV47_TOWER_EXIT_ALREADY_LIFTED_NEXT_TRAVEL_SAFE",
        "FC3D_V150_TOWER_PRESSURE_STATE",
        "reason=TOWER_TRAVEL",
        "PPSPV53 tower XY",
    )
    leaked = [x for x in forbidden if x in executable]
    exact_slot_lines = [
        line for line in executable.splitlines()
        if re.match(r"^\s*;\s*FC3D_TOWER_SLOT(?:\s|$)", line)
    ]
    if exact_slot_lines:
        leaked.append("FC3D_TOWER_SLOT_MARKER")
    if leaked:
        raise RuntimeError(
            f"V1.101 A1 MINI AUDIT: forbidden H2C/tower executable content {leaked}; "
            f"slot_lines={exact_slot_lines[:5]}"
        )

    for required in (
        "; FC3D_V1106_A1MINI_START",
        "; FC3D_V1106_A1MINI_NOZZLE_WIPE_START",
        "; FC3D_V1106_A1MINI_NOZZLE_WIPE_END",
        "; FC3D_V1106_A1MINI_CONDITION_START",
        "; FC3D_V1106_A1MINI_CONDITION_END state=RETRACTED",
        "; FC3D_V1106_A1MINI_END",
    ):
        if required not in executable:
            raise RuntimeError(f"V1.101 A1 MINI AUDIT: required executable marker missing: {required}")
    for required in (
        "; enable_prime_tower = 0",
        "; prime_tower_enable_framework = 0",
    ):
        if required not in g:
            raise RuntimeError(f"V1.101 A1 MINI AUDIT: required config missing: {required}")

    # A1 Mini is single-nozzle: reject H2C-style thermal-head targeting.
    thermal_head_leaks = [
        line for line in executable.splitlines()
        if re.match(r"^\s*M10[49]\b", line, re.I) and re.search(r"\bT[01]\b", line, re.I)
    ]
    if thermal_head_leaks:
        raise RuntimeError(
            "V1.101 A1 MINI AUDIT: T0/T1 thermal-head command leaked into A1 job: "
            f"{thermal_head_leaks[:6]}"
        )

    exec_range = range(exec_start_i + 1, exec_end_i)
    try:
        start_i = next(i for i in exec_range if lines[i].strip() == "; FC3D_V1106_A1MINI_START")
        wipe_start_i = next(i for i in range(start_i + 1, exec_end_i) if lines[i].strip() == "; FC3D_V1106_A1MINI_NOZZLE_WIPE_START")
        wipe_end_i = next(i for i in range(wipe_start_i + 1, exec_end_i) if lines[i].strip() == "; FC3D_V1106_A1MINI_NOZZLE_WIPE_END")
        g29_i = next(i for i in range(wipe_end_i + 1, exec_end_i) if re.match(r"^\s*G29\s+A1\b", lines[i]))
        cond_start_i = next(i for i in range(g29_i + 1, exec_end_i) if lines[i].strip() == "; FC3D_V1106_A1MINI_CONDITION_START")
        cond_end_i = next(i for i in range(cond_start_i + 1, exec_end_i) if lines[i].strip() == "; FC3D_V1106_A1MINI_CONDITION_END state=RETRACTED")
        first_layer_i = next(i for i in range(cond_end_i + 1, exec_end_i) if lines[i].strip() == "; CHANGE_LAYER")
        a1_end_i = next(i for i in range(first_layer_i + 1, exec_end_i) if lines[i].strip() == "; FC3D_V1106_A1MINI_END")
    except StopIteration as exc:
        raise RuntimeError("V1.101 A1 MINI AUDIT: executable startup/model ordering marker missing") from exc

    if not (start_i < wipe_start_i < wipe_end_i < g29_i < cond_start_i < cond_end_i < first_layer_i < a1_end_i < exec_end_i):
        raise RuntimeError(
            "V1.101 A1 MINI AUDIT: startup ordering invalid: "
            f"start={start_i}, wipe={wipe_start_i}:{wipe_end_i}, G29={g29_i}, "
            f"condition={cond_start_i}:{cond_end_i}, model={first_layer_i}, "
            f"end={a1_end_i}, exec={exec_start_i}:{exec_end_i}"
        )

    # Real brush use from the current A1 Mini profile: rear brush reaches Y185.
    wipe_block = lines[wipe_start_i:wipe_end_i + 1]
    if not any(re.search(r"\bY185(?:\.0+)?\b", line) for line in wipe_block):
        raise RuntimeError("V1.101 A1 MINI AUDIT: physical A1 brush wipe does not reach Y185")
    wipe_170_waits = [
        line for line in wipe_block
        if re.match(r"^\s*M109\b", line, re.I)
        and re.search(r"\bS170(?:\.0+)?(?:\s|$)", line, re.I)
    ]
    if len(wipe_170_waits) != 1:
        raise RuntimeError(
            f"V1.101 A1 MINI AUDIT: expected exactly one blocking M109 S170 in wipe, got {wipe_170_waits}"
        )

    def nozzle_target(line):
        if not re.match(r"^\s*M10[49]\b", line, re.I):
            return None
        m = re.search(r"\bS(-?\d+(?:\.\d+)?)\b", line, re.I)
        return float(m.group(1)) if m else None

    # ABL must be after a blocking 140-C wait, explicitly enabled, and before
    # the final 255-C wait. The current A1 Mini sequence synchronizes/saves the
    # completed probe before applying the Textured-PEI trim.
    pre_g29 = lines[start_i:g29_i]
    if not any(line.strip() == "G29.2 S1" for line in pre_g29):
        raise RuntimeError("V1.101 A1 MINI AUDIT: G29.2 S1 missing before ABL")
    waits_140 = [i for i, line in enumerate(pre_g29, start_i) if re.match(r"^\s*M109\b", line, re.I) and abs((nozzle_target(line) or -999) - 140.0) < 1e-6]
    if not waits_140:
        raise RuntimeError("V1.101 A1 MINI AUDIT: no blocking M109 S140 before ABL")

    post_g29_before_model = lines[g29_i + 1:first_layer_i]
    if not any(line.strip() == "M400" for line in post_g29_before_model):
        raise RuntimeError("V1.101 A1 MINI AUDIT: M400 missing after ABL")
    if not any(line.strip() == "M500" for line in post_g29_before_model):
        raise RuntimeError("V1.101 A1 MINI AUDIT: M500 missing after ABL")

    final_waits = [
        i for i in range(g29_i + 1, first_layer_i)
        if re.match(r"^\s*M109\b", lines[i], re.I)
        and abs((nozzle_target(lines[i]) or -999) - float(A1_MINI_NOZZLE_C)) < 1e-6
    ]
    if not final_waits:
        raise RuntimeError(f"V1.101 A1 MINI AUDIT: no blocking M109 S{A1_MINI_NOZZLE_C} after ABL")
    final_heat_i = final_waits[-1]

    lowered_after_final = []
    for i in range(final_heat_i + 1, first_layer_i):
        target = nozzle_target(lines[i])
        if target is not None and target < float(A1_MINI_NOZZLE_C) - 1e-6:
            lowered_after_final.append((i + 1, lines[i]))
    if lowered_after_final:
        raise RuntimeError(
            "V1.101 A1 MINI AUDIT: nozzle target lowered after final print-temperature wait: "
            f"{lowered_after_final[:6]}"
        )

    condition_block = lines[cond_start_i:cond_end_i + 1]
    positive_xy_e = []
    for line in condition_block:
        if not re.match(r"^\s*G[01]\b", line):
            continue
        if not (re.search(r"\bX-?\d", line) or re.search(r"\bY-?\d", line)):
            continue
        me = re.search(r"\bE(-?\d+(?:\.\d+)?)\b", line)
        if me and float(me.group(1)) > 0:
            positive_xy_e.append(line)
    if len(positive_xy_e) != 2:
        raise RuntimeError(
            "V1.101 A1 MINI AUDIT: expected exactly two positive-E XY conditioning moves, "
            f"got {positive_xy_e}"
        )
    # The conditioning line is deliberately confined to the unused front strip.
    # The model/card begins much farther back on this coupon; fail closed rather
    # than allowing a future edit to drag the purge line through the card.
    for line in positive_xy_e:
        mx = re.search(r"\bX(-?\d+(?:\.\d+)?)\b", line)
        my = re.search(r"\bY(-?\d+(?:\.\d+)?)\b", line)
        if mx is None or my is None:
            raise RuntimeError(
                "V1.101 A1 MINI AUDIT: conditioning extrusion must carry explicit X and Y: "
                f"{line}"
            )
        x = float(mx.group(1)); y = float(my.group(1))
        if not (0.0 <= x <= 180.0 and 0.0 <= y <= 10.0):
            raise RuntimeError(
                "V1.101 A1 MINI AUDIT: conditioning extrusion escaped safe front strip "
                f"X=0..180 Y=0..10: {line}"
            )
    e_only_changes = [
        line for line in condition_block
        if re.match(r"^\s*G1\b", line)
        and re.search(r"\bE[-+]?\d", line)
        and not re.search(r"\b[XYZ][-+]?\d", line)
    ]
    expected_condition_retract = f"E-{A_RETRACT_MM:.3f}"
    if not e_only_changes or expected_condition_retract not in e_only_changes[-1]:
        raise RuntimeError(
            f"V1.101 A1 MINI AUDIT: final conditioning E-only state change is not {expected_condition_retract}: "
            f"{e_only_changes[-3:]}"
        )

    p = root.find("plate")
    if p is None:
        raise RuntimeError("V1.101 A1 MINI AUDIT: slice_info has no plate")
    meta = {n.attrib.get("key"): n.attrib.get("value") for n in p.findall("metadata")}
    if meta.get("printer_model_id") != A1_MINI_MODEL_ID or meta.get("nozzle_diameters") != "0.4":
        raise RuntimeError(f"V1.101 A1 MINI AUDIT: slice machine metadata {meta}")
    if meta.get("has_filament_switcher") != "false":
        raise RuntimeError(f"V1.101 A1 MINI AUDIT: has_filament_switcher={meta.get('has_filament_switcher')!r}")
    nozzles = [n.attrib for n in p.findall("nozzle")]
    expected_nozzles = [{"id": "0", "extruder_id": "1", "nozzle_diameter": "0.4", "volume_type": "Standard"}]
    if nozzles != expected_nozzles:
        raise RuntimeError(f"V1.101 A1 MINI AUDIT: nozzle record {nozzles}")

    actual_md5 = hashlib.md5(gbytes).hexdigest()
    if actual_md5 != md5:
        raise RuntimeError(
            f"V1.101 A1 MINI AUDIT: gcode MD5 mismatch package={md5} actual={actual_md5}"
        )

    model = g.split("; CHANGE_LAYER", 1)[-1].split("; V4_MODEL_END", 1)[0]
    model_motion = "\n".join(
        line for line in model.splitlines()
        if re.match(r"^\s*G[01]\b", line, re.I)
    )
    xs = [float(m.group(1)) for m in re.finditer(r"\bX(-?\d+(?:\.\d+)?)", model_motion)]
    ys = [float(m.group(1)) for m in re.finditer(r"\bY(-?\d+(?:\.\d+)?)", model_motion)]
    if not xs or not ys or min(xs) < 0 or max(xs) > 180 or min(ys) < 0 or max(ys) > 180:
        raise RuntimeError(
            "V1.101 A1 MINI AUDIT: model outside bed "
            f"X={min(xs) if xs else None}..{max(xs) if xs else None} "
            f"Y={min(ys) if ys else None}..{max(ys) if ys else None}"
        )

    return {
        "printer": A1_MINI_PRINTER_PRESET,
        "model_id": A1_MINI_MODEL_ID,
        "envelope_mm": [180, 180, 180],
        "nozzle": "0.4 mm Standard stainless",
        "prime_tower_present": False,
        "removed_tower_blocks_at_converter": removed_tower_blocks,
        "model_xy_mm": [min(xs), max(xs), min(ys), max(ys)],
        "probe_nozzle_c": 140,
        "final_nozzle_c": A1_MINI_NOZZLE_C,
        "condition_xy_e_moves": len(positive_xy_e),
        "condition_exit_retract_mm": A_RETRACT_MM,
        "sanitized_tower_exit_hops": g.count("FC3D_V1106_TOWER_EXIT_HOP_SANITIZED_Z_ONLY"),
        "md5": md5,
    }



# ============================================================================
# v1.106 true-normal continuous wave-set geometry
# ============================================================================
WAVESET_BUILD_ORDER = "outer_to_inner"
WAVESET_RESET_ONLY_AFTER_COMPLETE_ARC = True
WAVESET_TOTAL_PEAK_MM = 0.300
WAVESET_HIDDEN_RISE_MM = 0.050
WAVESET_OPTICAL_RISE_MM = WAVESET_TOTAL_PEAK_MM - WAVESET_HIDDEN_RISE_MM
WAVESET_BASE_LEAD_MM = 0.100
WAVESET_HIDDEN_RUN_MM = 0.400
WAVESET_RETURN_ANGLE_DEG = 45.0
WAVESET_RETURN_RUN_MM = WAVESET_TOTAL_PEAK_MM / math.tan(math.radians(WAVESET_RETURN_ANGLE_DEG))
WAVESET_PRINT_FEED_MM_S = 50.0
WAVESET_RESET_CENTER_SPACING_MM = 0.600
WAVESET_MIN_CENTER_SPACING_MM = 0.400
WAVESET_PITCH_TOL_MM = 0.002
WAVESET_HIDDEN_PROJECTOR_MARGIN_MM = 0.010
WAVESET_COMMAND_Z_MM = BASE_TOP_Z_MM + A_MAIN_NOMINAL_HEIGHT_MM
WAVESET_PROFILE_MODEL = "full_arc_serpentine_exact_front_hidden_top"
_WAVESET_CACHE = {}


def _waveset_length3(a,b):
    return math.sqrt((b[0]-a[0])**2+(b[1]-a[1])**2+(b[2]-a[2])**2)


def _waveset_advance_point_inward(x,z,distance_mm,max_step_mm=0.05):
    x=float(x); z=float(z); rem=max(0.0,float(distance_mm))
    while rem>1e-12:
        ds=min(float(max_step_mm),rem)
        f0=mirror_frame_global(x,z); d0=f0["b_unit"]
        mx=x+0.5*d0[0]*ds; mz=z+0.5*d0[1]*ds
        fm=mirror_frame_global(mx,mz); d=fm["b_unit"]
        x+=d[0]*ds; z+=d[1]*ds; rem-=ds
    return (x,z)


def _waveset_advance_curve_inward(curve,distance_mm):
    return [_waveset_advance_point_inward(x,z,distance_mm) for x,z in curve]


def _waveset_front_point(x,z,rise_mm):
    rec=integrate_b_front_global(float(x),float(z),float(rise_mm),0.05)
    q=rec["points"][-1]
    return (q[0],q[1]),rec["max_normal_error"]


def _waveset_front_curve(foot_curve):
    out=[]; errs=[]
    for x,z in foot_curve:
        q,e=_waveset_front_point(x,z,WAVESET_OPTICAL_RISE_MM)
        out.append(q); errs.append(e)
    return out,(max(errs) if errs else 0.0)


def _waveset_curve_tangent(curve,j):
    a=curve[max(0,j-1)]; b=curve[min(len(curve)-1,j+1)]
    dx=b[0]-a[0]; dz=b[1]-a[1]; m=math.hypot(dx,dz)
    if m<=1e-12: return (1.0,0.0)
    return (dx/m,dz/m)


def _waveset_surface_normal(tangent,cross):
    tx,tz=tangent; dx,dz,dh=cross
    # tangent=(tx,tz,0); cross=(dx,dz,dh)
    n=(tz*dh,-tx*dh,tx*dz-tz*dx)
    m=math.sqrt(sum(q*q for q in n))
    if m<=1e-12: return (0.0,0.0,1.0)
    n=tuple(q/m for q in n)
    if n[2]<0: n=tuple(-q for q in n)
    return n


def _waveset_front_normal_error(foot,crest,piece):
    vals=[]
    n=min(len(foot),len(crest))
    for j in range(n):
        x,z=foot[j]; qx,qz=crest[j]
        if not (piece.global_x0_mm-ROAD_WIDTH_MM <= x <= piece.global_x1_mm+ROAD_WIDTH_MM and piece.global_z0_mm-ROAD_WIDTH_MM <= z <= piece.global_z1_mm+ROAD_WIDTH_MM):
            continue
        t=_waveset_curve_tangent(foot,j)
        actual=_waveset_surface_normal(t,(qx-x,qz-z,WAVESET_OPTICAL_RISE_MM))
        mx=0.5*(x+qx); mz=0.5*(z+qz); ideal=mirror_frame_global(mx,mz)["normal_unit"]
        vals.append(math.sqrt(sum((actual[k]-ideal[k])**2 for k in range(3))))
    return max(vals) if vals else 0.0


def _waveset_hidden_surface_clearance(crest,hidden,piece):
    """Return projector-ray clearance over the shallow hidden top at its inward end.

    The crest is intentionally visible.  The hidden segment must immediately fall
    below the projector visibility ray as it runs inward; endpoint clearance is a
    stable conservative proxy because both are monotone over this short segment.
    """
    vals=[]; slopes=[]
    n=min(len(crest),len(hidden))
    for j in range(n):
        x,z=crest[j]; hx,hz=hidden[j]
        if not (piece.global_x0_mm-ROAD_WIDTH_MM <= x <= piece.global_x1_mm+ROAD_WIDTH_MM and piece.global_z0_mm-ROAD_WIDTH_MM <= z <= piece.global_z1_mm+ROAD_WIDTH_MM):
            continue
        f=mirror_frame_global(x,z); b=f["b_unit"]; p=f["projector_unit"]
        du=(hx-x)*b[0]+(hz-z)*b[1]
        pdu=p[0]*b[0]+p[1]*b[1]
        if du<=1e-9 or pdu<=1e-9: continue
        ray_rise=p[2]*(du/pdu)
        vals.append(ray_rise-WAVESET_HIDDEN_RISE_MM)
        slopes.append(p[2]/pdu - WAVESET_HIDDEN_RISE_MM/du)
    if not vals: return {"endpoint_clearance_min_mm":float("inf"),"slope_margin_min":float("inf"),"samples":0}
    return {"endpoint_clearance_min_mm":min(vals),"slope_margin_min":min(slopes),"samples":len(vals)}


def _waveset_clip_curve(curve,piece):
    segs=_clip_polyline2_to_piece(curve,piece)
    if len(segs)>1:
        raise RuntimeError(f"v1.106 wave curve split into {len(segs)} clipped segments")
    return segs[0] if segs else []


def _waveset_outer_reference_curve(piece):
    lat=get_mirror_wave_lattice(piece)
    candidates=[]
    for rec in lat["main_a_curves"]:
        clips=_clip_polyline2_to_piece(rec["points"],piece)
        if not clips: continue
        pts=clips[0]
        rr=[math.hypot(x-MASTER_FAN.projector_x_mm,z-MASTER_FAN.projector_z_mm) for x,z in pts]
        candidates.append((sum(rr)/len(rr),rec))
    if not candidates: raise RuntimeError(f"{piece.name}: no v1.101 outer reference arc")
    full=[(float(x),float(z)) for x,z in max(candidates,key=lambda q:q[0])[1]["points"]]
    halo=12.0
    idx=[i for i,(x,z) in enumerate(full) if piece.global_x0_mm-halo<=x<=piece.global_x1_mm+halo and piece.global_z0_mm-halo<=z<=piece.global_z1_mm+halo]
    if not idx: raise RuntimeError(f"{piece.name}: outer reference has no halo samples")
    a=max(0,min(idx)-2); b=min(len(full),max(idx)+3)
    work=full[a:b]
    return _resample_polyline2(work,1.0)


def _waveset_curve_spacing(a,b,piece):
    vals=[]
    for p,q in zip(a,b):
        x,z=p
        if piece.global_x0_mm-ROAD_WIDTH_MM <= x <= piece.global_x1_mm+ROAD_WIDTH_MM and piece.global_z0_mm-ROAD_WIDTH_MM <= z <= piece.global_z1_mm+ROAD_WIDTH_MM:
            vals.append(math.hypot(q[0]-p[0],q[1]-p[1]))
    if not vals: return None
    return {"min":min(vals),"mean":sum(vals)/len(vals),"max":max(vals),"samples":len(vals)}


def generate_true_normal_wave_sets(piece: PieceSpec):
    key=(piece.name,WAVESET_TOTAL_PEAK_MM,WAVESET_HIDDEN_RISE_MM,WAVESET_BASE_LEAD_MM,WAVESET_HIDDEN_RUN_MM,WAVESET_RETURN_ANGLE_DEG)
    if key in _WAVESET_CACHE: return _WAVESET_CACHE[key]
    current=[(float(x),float(z)) for x,z in _waveset_outer_reference_curve(piece)]
    sets=[]; all_roads=[]; cells=[]; set_idx=1; cell_idx=0
    set_roads=[]; set_cells=[]
    max_cells=800
    while cell_idx<max_cells:
        # Stop only after the entire profile no longer intersects the coupon.
        if not _waveset_clip_curve(current,piece):
            probe=_waveset_advance_curve_inward(current,WAVESET_RESET_CENTER_SPACING_MM)
            if not _waveset_clip_curve(probe,piece): break
        cell_idx+=1
        foot=_waveset_advance_curve_inward(current,WAVESET_BASE_LEAD_MM)
        crest,front_integrator_err=_waveset_front_curve(foot)
        hidden=_waveset_advance_curve_inward(crest,WAVESET_HIDDEN_RUN_MM)
        end=_waveset_advance_curve_inward(hidden,WAVESET_RETURN_RUN_MM)
        spacing=_waveset_curve_spacing(current,end,piece)
        if spacing is None:
            current=end; continue
        front_err=max(front_integrator_err,_waveset_front_normal_error(foot,crest,piece))
        hidden_clear=_waveset_hidden_surface_clearance(crest,hidden,piece)
        if hidden_clear["samples"] and hidden_clear["endpoint_clearance_min_mm"] < WAVESET_HIDDEN_PROJECTOR_MARGIN_MM-1e-9:
            raise RuntimeError(f"v1.106 hidden top visible to projector: {hidden_clear}")
        roads=[
            ("VALLEY",current,0.0),
            ("FOOT",foot,0.0),
            ("OPTICAL_CREST",crest,WAVESET_OPTICAL_RISE_MM),
            ("HIDDEN_TOP",hidden,WAVESET_TOTAL_PEAK_MM),
            ("RETURN_VALLEY",end,0.0),
        ]
        # First cell owns its starting valley; later cells share the previous end.
        add=roads if not set_roads else roads[1:]
        for role,curve,h in add:
            clip=_waveset_clip_curve(curve,piece)
            if clip:
                rec={"set_index":set_idx,"cell_index":cell_idx,"role":role,"height_mm":h,
                     "points_global":curve,"points_clip":clip}
                set_roads.append(rec); all_roads.append(rec)
        crec={"set_index":set_idx,"cell_index":cell_idx,"pitch":spacing,"front_normal_error":front_err,
              "hidden_clearance":hidden_clear}
        set_cells.append(crec); cells.append(crec)
        current=end
        # Complete the current full-arc cell, then reset only if zero gap is reached.
        if spacing["min"] <= WAVESET_MIN_CENTER_SPACING_MM + WAVESET_PITCH_TOL_MM:
            sets.append({"set_index":set_idx,"roads":set_roads,"cells":set_cells,"end_reason":"zero_gap"})
            current=_waveset_advance_curve_inward(current,WAVESET_RESET_CENTER_SPACING_MM)
            set_idx+=1; set_roads=[]; set_cells=[]
    if set_roads or set_cells:
        sets.append({"set_index":set_idx,"roads":set_roads,"cells":set_cells,"end_reason":"coupon_boundary"})
    if not all_roads or not cells: raise RuntimeError(f"{piece.name}: v1.106 generated no wave-set geometry")
    pitches=[c["pitch"]["mean"] for c in cells]
    front_errors=[c["front_normal_error"] for c in cells]
    hidden_clear=[c["hidden_clearance"]["endpoint_clearance_min_mm"] for c in cells if c["hidden_clearance"]["samples"]]
    out={"sets":sets,"roads":all_roads,"cells":cells,"set_count":len(sets),"cell_count":len(cells),
         "pitch_min_mm":min(pitches),"pitch_mean_mm":sum(pitches)/len(pitches),"pitch_max_mm":max(pitches),
         "front_normal_error_max":max(front_errors),
         "hidden_projector_clearance_min_mm":min(hidden_clear) if hidden_clear else float("inf")}
    _WAVESET_CACHE[key]=out
    return out


def get_true_normal_wave_sets(piece: PieceSpec):
    return generate_true_normal_wave_sets(piece)


def waveset_report(piece: PieceSpec):
    w=get_true_normal_wave_sets(piece)
    return {"build_order":WAVESET_BUILD_ORDER,"profile_model":WAVESET_PROFILE_MODEL,
            "set_count":w["set_count"],"cell_count":w["cell_count"],"road_count":len(w["roads"]),
            "peak_mm":WAVESET_TOTAL_PEAK_MM,"optical_rise_mm":WAVESET_OPTICAL_RISE_MM,
            "hidden_rise_mm":WAVESET_HIDDEN_RISE_MM,"print_feed_mm_s":WAVESET_PRINT_FEED_MM_S,
            "pitch_mm":{"min":w["pitch_min_mm"],"mean":w["pitch_mean_mm"],"max":w["pitch_max_mm"]},
            "front_normal_error_max":w["front_normal_error_max"],
            "hidden_projector_clearance_min_mm":w["hidden_projector_clearance_min_mm"],
            "reset_center_spacing_mm":WAVESET_RESET_CENTER_SPACING_MM,"minimum_center_spacing_mm":WAVESET_MIN_CENTER_SPACING_MM,
            "sets":[{"set_index":s["set_index"],"cell_count":len(s["cells"]),"road_count":len(s["roads"]),"end_reason":s["end_reason"],
                     "pitch_start_mm":s["cells"][0]["pitch"]["mean"] if s["cells"] else None,
                     "pitch_end_mm":s["cells"][-1]["pitch"]["mean"] if s["cells"] else None} for s in w["sets"]]}


def _waveset_midpoint_radius(curve,piece):
    pc=(0.5*(piece.global_x0_mm+piece.global_x1_mm),0.5*(piece.global_z0_mm+piece.global_z1_mm))
    p=min(curve,key=lambda q:math.hypot(q[0]-pc[0],q[1]-pc[1]))
    return math.hypot(p[0]-MASTER_FAN.projector_x_mm,p[1]-MASTER_FAN.projector_z_mm),p


def v105_v106_wave_set_comparison_report(piece: PieceSpec):
    ref=get_shadow_clear_single_road_lattice(piece)
    new=get_true_normal_wave_sets(piece)
    refrows=[]
    for r in ref["main_a_local"]:
        pts=[(piece.global_x0_mm+x,piece.global_z0_mm+z) for x,z in r["points"]]
        rr,p=_waveset_midpoint_radius(pts,piece); refrows.append((rr,r["arc_index"],p))
    rows=[]
    for rec in new["roads"]:
        if rec["role"]!="OPTICAL_CREST": continue
        rr,p=_waveset_midpoint_radius(rec["points_global"],piece)
        nr=min(refrows,key=lambda q:abs(q[0]-rr)) if refrows else (float("nan"),None,(float("nan"),float("nan")))
        rows.append({"set_index":rec["set_index"],"cell_index":rec["cell_index"],"new_mid_radius_mm":rr,
                     "nearest_v105_arc":nr[1],"v105_mid_radius_mm":nr[0],"radial_delta_mm":rr-nr[0],
                     "new_mid_x_mm":p[0],"new_mid_z_mm":p[1],"v105_mid_x_mm":nr[2][0],"v105_mid_z_mm":nr[2][1]})
    return {"v105_arc_count":len(refrows),"v106_wave_cell_count":new["cell_count"],"v106_optical_crest_count":len(rows),"rows":rows}


def write_v105_v106_wave_set_comparison_csv(path):
    rep=v105_v106_wave_set_comparison_report(_current_piece()); rows=rep["rows"]
    fields=["set_index","cell_index","new_mid_radius_mm","nearest_v105_arc","v105_mid_radius_mm","radial_delta_mm","new_mid_x_mm","new_mid_z_mm","v105_mid_x_mm","v105_mid_z_mm"]
    with Path(path).open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    return rep



ARC_PLACEMENT_ORDER = "inner_to_outer"
ARC_SHADOW_MODEL = "single_0p14_full_ellipse_previous_peak"
ARC_PROFILE_WIDTH_MM = 0.40
ARC_SHADOW_CLEARANCE_MARGIN_MM = 0.010
ARC_MIN_CENTER_SPACING_MM = 0.400
ARC_SPACING_NUMERICAL_MARGIN_MM = 0.005
ARC_PLACEMENT_TOL_MM = 0.0005
_SHADOW_CLEAR_LATTICE_CACHE = {}


def _polyline_length2(points):
    return sum(math.hypot(b[0]-a[0], b[1]-a[1]) for a,b in zip(points,points[1:]))


def _single_bead_critical_point(center_x_mm: float, center_z_mm: float) -> dict:
    """Critical exposed point on the nominal single 0.14-mm bead.

    Cross-section is a full ellipse of nominal width 0.40 mm and height 0.14 mm,
    resting on the support plane.  The selected point is on the projector-facing
    (+B/inward) side and has the local projector/viewer bisecting normal.  The
    frame is iterated at the displaced surface point so the reported location is
    self-consistent to well below printer resolution.
    """
    cx=float(center_x_mm); cz=float(center_z_mm)
    a=ARC_PROFILE_WIDTH_MM*0.5
    b=A_MAIN_NOMINAL_HEIGHT_MM*0.5
    sx=sz=0.0; h=A_MAIN_NOMINAL_HEIGHT_MM
    frame=None; s=0.0
    for _ in range(5):
        frame=mirror_frame_global(cx+sx, cz+sz)
        nb=math.hypot(frame["normal_unit"][0], frame["normal_unit"][1])
        nh=frame["normal_unit"][2]
        den=math.sqrt((a*nb)**2 + (b*nh)**2)
        if den <= 1e-12:
            raise RuntimeError("V1.105 SHADOW: degenerate bead critical-point normal")
        s=(a*a*nb)/den
        h=b + (b*b*nh)/den
        sx=frame["b_unit"][0]*s
        sz=frame["b_unit"][1]*s
    x=cx+sx; z=cz+sz
    # Use the actual surface height for the projector ray rather than treating
    # the critical point as if it were on the backplate plane.
    pv=(MASTER_FAN.projector_x_mm-x,
        MASTER_FAN.projector_z_mm-z,
        MASTER_FAN.projector_distance_mm-h)
    pm=math.sqrt(sum(q*q for q in pv))
    p=tuple(q/pm for q in pv)
    return {
        "center_mm":(cx,cz), "point_mm":(x,z), "height_mm":h,
        "inward_offset_mm":s, "projector_unit":p,
        "facet_tilt_deg":frame["facet_tilt_deg"],
        "normal_unit":frame["normal_unit"], "b_unit":frame["b_unit"],
    }


def _curve_tangent2(points, idx):
    j=int(idx)
    a=points[max(0,j-1)]; b=points[min(len(points)-1,j+1)]
    dx=b[0]-a[0]; dz=b[1]-a[1]
    m=math.hypot(dx,dz)
    if m <= 1e-12:
        raise RuntimeError("V1.105 SHADOW: degenerate previous-arc tangent")
    return (dx/m,dz/m)


def _projector_clearance_over_previous_peak(current_center, previous_peak_center, previous_tangent) -> dict:
    """Ray clearance above the immediately inward arc's peak line.

    The incoming projector ray from the current arc's critical optical point is
    intersected in screen X/Z with the local tangent line through the previous
    arc's centre/peak.  Clearance is ray physical height at that crossing minus
    the previous bead peak height (0.14 mm above support).
    """
    crit=_single_bead_critical_point(current_center[0],current_center[1])
    cx,cz=crit["point_mm"]; ch=crit["height_mm"]
    rx,rz,rh=crit["projector_unit"]
    px,pz=map(float,previous_peak_center)
    tx,tz=map(float,previous_tangent)
    det=rx*(-tz)-rz*(-tx)
    if abs(det) <= 1e-12:
        raise RuntimeError("V1.105 SHADOW: projector ray parallel to previous arc")
    dx=px-cx; dz=pz-cz
    ray_t=(dx*(-tz)-dz*(-tx))/det
    if ray_t <= 0.0:
        return {"clearance_mm":float("-inf"),"ray_t_mm":ray_t,"critical":crit}
    ray_h=ch+rh*ray_t
    return {
        "clearance_mm":ray_h-A_MAIN_NOMINAL_HEIGHT_MM,
        "ray_height_at_previous_peak_mm":ray_h,
        "ray_t_mm":ray_t,
        "critical":crit,
    }


def _shadow_reference_setup(piece: PieceSpec):
    """Freeze the inward reference to v1.101's first physical main arc."""
    base=get_mirror_wave_lattice(piece)
    if not base["main_a_local"]:
        raise RuntimeError(f"{piece.name}: v1.101 reference has no main arcs")
    first_local=base["main_a_local"][0]
    wave=first_local["wave"]; family=first_local["family"]
    candidates=[r for r in base["main_a_curves"] if r["wave"]==wave and r["family"]==family]
    if len(candidates)!=1:
        raise RuntimeError(f"{piece.name}: cannot resolve v1.101 inward reference wave={wave} family={family}")
    pts=[(float(x),float(z)) for x,z in candidates[0]["points"]]
    pc=(0.5*(piece.global_x0_mm+piece.global_x1_mm),0.5*(piece.global_z0_mm+piece.global_z1_mm))
    seed_i=min(range(len(pts)),key=lambda i:math.hypot(pts[i][0]-pc[0],pts[i][1]-pc[1]))
    seed=pts[seed_i]
    neg=_polyline_length2(pts[:seed_i+1]); pos=_polyline_length2(pts[seed_i:])
    if neg < 20.0 or pos < 20.0:
        raise RuntimeError(f"{piece.name}: inadequate A reference trace lengths {neg:.3f}/{pos:.3f}")
    return {"base":base,"wave":wave,"family":family,"seed_index":seed_i,"seed":seed,"negative_len_mm":neg,"positive_len_mm":pos}


def _shadow_trace_from_seed(seed, setup):
    return _trace_a_streamline_global(seed[0],seed[1],setup["negative_len_mm"],setup["positive_len_mm"],A_TRACE_STEP_MM)


def _shadow_indices_in_piece(points, piece, stride=1):
    # Include a small halo so the boundary portion is not accidentally the
    # limiting un-audited part of a clipped road.
    halo=ROAD_WIDTH_MM
    out=[i for i,p in enumerate(points)
         if i % int(stride)==0
         and piece.global_x0_mm-halo <= p[0] <= piece.global_x1_mm+halo
         and piece.global_z0_mm-halo <= p[1] <= piece.global_z1_mm+halo]
    return out


def _shadow_pair_metrics(current, previous, piece, stride=1):
    if len(current)!=len(previous):
        raise RuntimeError("V1.105 SHADOW: corresponding A traces differ in sample count")
    idxs=_shadow_indices_in_piece(current,piece,stride)
    if not idxs:
        return None
    clear=[]; spacing=[]; crit_h=[]; crit_off=[]; tilts=[]
    for j in idxs:
        tan=_curve_tangent2(previous,j)
        rec=_projector_clearance_over_previous_peak(current[j],previous[j],tan)
        clear.append(rec["clearance_mm"])
        spacing.append(math.hypot(current[j][0]-previous[j][0],current[j][1]-previous[j][1]))
        crit=rec["critical"]
        crit_h.append(crit["height_mm"]); crit_off.append(crit["inward_offset_mm"]); tilts.append(crit["facet_tilt_deg"])
    return {
        "sample_count":len(idxs),
        "clearance_min_mm":min(clear),"clearance_mean_mm":sum(clear)/len(clear),"clearance_max_mm":max(clear),
        "center_spacing_min_mm":min(spacing),"center_spacing_mean_mm":sum(spacing)/len(spacing),"center_spacing_max_mm":max(spacing),
        "critical_height_min_mm":min(crit_h),"critical_height_mean_mm":sum(crit_h)/len(crit_h),"critical_height_max_mm":max(crit_h),
        "critical_inward_offset_min_mm":min(crit_off),"critical_inward_offset_mean_mm":sum(crit_off)/len(crit_off),"critical_inward_offset_max_mm":max(crit_off),
        "target_tilt_min_deg":min(tilts),"target_tilt_mean_deg":sum(tilts)/len(tilts),"target_tilt_max_deg":max(tilts),
    }


def generate_shadow_clear_single_road_lattice(piece: PieceSpec):
    """Place single 0.14-mm arcs inner->outer using projector shadow clearance.

    Arc 1 is anchored to v1.101's first physical main arc. Each later seed is
    advanced outward along the true B-rise field. A true A streamline is traced
    through that seed. The minimum accepted pitch satisfies both the critical
    point projector-clearance margin and nominal 0.40-mm bead non-overlap.
    """
    setup=_shadow_reference_setup(piece)
    seed=setup["seed"]
    previous=_shadow_trace_from_seed(seed,setup)
    first_clip=_clip_polyline2_to_piece(previous,piece)
    if len(first_clip)!=1:
        raise RuntimeError(f"{piece.name}: v1.106 inward anchor clipped segments={len(first_clip)} expected 1")
    roads=[{"arc_index":1,"points":[(q[0]-piece.global_x0_mm,q[1]-piece.global_z0_mm) for q in first_clip[0]],
            "seed_global":seed,"seed_pitch_mm":None,"constraint":"anchor","metrics":None}]
    full_curves=[previous]; seeds=[seed]
    arc_records=[]
    max_arcs=1000
    for arc_idx in range(2,max_arcs+1):
        # Nominal road-width lower bound plus a 1-micron numerical cushion. The
        # shadow solver is still active and can increase this if illumination
        # requires a larger pitch anywhere along the new arc.
        lo=ARC_MIN_CENTER_SPACING_MM + ARC_SPACING_NUMERICAL_MARGIN_MM
        def candidate(distance):
            new_seed,_=_advance_b_rise_global(seed[0],seed[1],distance,B_FRONT_MAX_STEP_MM)
            curve=_shadow_trace_from_seed(new_seed,setup)
            metrics=_shadow_pair_metrics(curve,previous,piece,stride=1)
            return new_seed,curve,metrics
        new_seed,curve,metrics=candidate(lo)
        clipped=_clip_polyline2_to_piece(curve,piece)
        if not clipped:
            break
        if metrics is None:
            raise RuntimeError(f"{piece.name}: arc {arc_idx} has clipped geometry but no shadow samples")
        def passes(m):
            return (m["clearance_min_mm"] >= ARC_SHADOW_CLEARANCE_MARGIN_MM-1e-9
                    and m["center_spacing_min_mm"] >= ARC_MIN_CENTER_SPACING_MM-1e-9)
        distance=lo
        constraint="road_width"
        if not passes(metrics):
            constraint="projector_shadow" if metrics["clearance_min_mm"] < ARC_SHADOW_CLEARANCE_MARGIN_MM else "road_width_numeric"
            high=max(lo+0.05,lo*1.10)
            while True:
                hs,hc,hm=candidate(high)
                if hm is not None and passes(hm): break
                high*=1.15
                if high>5.0: raise RuntimeError(f"{piece.name}: arc {arc_idx} cannot satisfy clearance/non-overlap within 5 mm")
            low=lo
            for _ in range(20):
                mid=0.5*(low+high); ms,mc,mm=candidate(mid)
                if mm is not None and passes(mm): high=mid
                else: low=mid
            distance=high; new_seed,curve,metrics=candidate(distance)
            if not passes(metrics):
                raise RuntimeError(f"{piece.name}: arc {arc_idx} full-resolution solver failed at {distance:.6f} mm")
        clipped=_clip_polyline2_to_piece(curve,piece)
        if len(clipped)!=1:
            raise RuntimeError(f"{piece.name}: arc {arc_idx} clipped into {len(clipped)} segments; expected one")
        roads.append({"arc_index":arc_idx,"points":[(q[0]-piece.global_x0_mm,q[1]-piece.global_z0_mm) for q in clipped[0]],
                      "seed_global":new_seed,"seed_pitch_mm":distance,"constraint":constraint,"metrics":metrics})
        arc_records.append({"arc_index":arc_idx,"seed_pitch_mm":distance,"constraint":constraint,**metrics})
        seeds.append(new_seed); full_curves.append(curve)
        seed=new_seed; previous=curve
    else:
        raise RuntimeError(f"{piece.name}: v1.106 shadow lattice exceeded {max_arcs} arcs")
    if len(roads)<2:
        raise RuntimeError(f"{piece.name}: v1.106 generated too few arcs: {len(roads)}")
    return {
        "piece":piece.name,"placement_order":ARC_PLACEMENT_ORDER,"shadow_model":ARC_SHADOW_MODEL,
        "v101_reference_arc_count":len(set((r["wave"],r["family"]) for r in setup["base"]["main_a_local"])),
        "main_a_local":roads,"arc_records":arc_records,"seeds_global":seeds,"full_curves_global":full_curves,
        "inward_anchor_wave":setup["wave"],"inward_anchor_family":setup["family"],"reference_seed_index":setup["seed_index"],
        "negative_trace_len_mm":setup["negative_len_mm"],"positive_trace_len_mm":setup["positive_len_mm"],
    }


def get_shadow_clear_single_road_lattice(piece: PieceSpec):
    key=(piece.name,round(piece.global_x0_mm,9),round(piece.global_z0_mm,9))
    rec=_SHADOW_CLEAR_LATTICE_CACHE.get(key)
    if rec is None:
        rec=generate_shadow_clear_single_road_lattice(piece)
        _SHADOW_CLEAR_LATTICE_CACHE[key]=rec
    return rec


def shadow_clearance_report(piece: PieceSpec) -> dict:
    lat=get_shadow_clear_single_road_lattice(piece)
    recs=lat["arc_records"]
    pitches=[r["seed_pitch_mm"] for r in recs]
    clear=[r["clearance_min_mm"] for r in recs]
    spaces=[r["center_spacing_min_mm"] for r in recs]
    constraints={k:sum(1 for r in recs if r["constraint"]==k) for k in ("road_width","projector_shadow")}
    if not pitches or min(clear)<ARC_SHADOW_CLEARANCE_MARGIN_MM-1e-8 or min(spaces)<ARC_MIN_CENTER_SPACING_MM-1e-8:
        raise RuntimeError(f"{piece.name}: v1.106 shadow report failed pitch/clearance contract")
    return {
        "result":"PASS","model":ARC_SHADOW_MODEL,"placement_order":ARC_PLACEMENT_ORDER,
        "arc_count":len(lat["main_a_local"]),"v101_arc_count":lat["v101_reference_arc_count"],
        "arc_count_change":len(lat["main_a_local"])-lat["v101_reference_arc_count"],
        "pitch_mm":{"min":min(pitches),"mean":sum(pitches)/len(pitches),"max":max(pitches)},
        "projector_clearance_mm":{"min":min(clear),"mean":sum(clear)/len(clear),"max":max(clear)},
        "center_spacing_min_mm":min(spaces),"required_clearance_margin_mm":ARC_SHADOW_CLEARANCE_MARGIN_MM,
        "minimum_nominal_center_spacing_mm":ARC_MIN_CENTER_SPACING_MM,"constraint_counts":constraints,
    }


def _v101_reference_arc_positions(piece: PieceSpec):
    base=get_mirror_wave_lattice(piece)
    setup=_shadow_reference_setup(piece); idx=setup["seed_index"]
    full={(r["wave"],r["family"]):r for r in base["main_a_curves"]}
    rows=[]; cumulative=0.0; prev=None
    for ordinal,loc in enumerate(base["main_a_local"],start=1):
        rec=full[(loc["wave"],loc["family"])]
        p=tuple(map(float,rec["points"][idx]))
        pitch=None if prev is None else math.hypot(p[0]-prev[0],p[1]-prev[1])
        if pitch is not None: cumulative+=pitch
        rows.append({"ordinal":ordinal,"wave":loc["wave"],"family":loc["family"],"point":p,"pitch_mm":pitch,"cumulative_mm":cumulative})
        prev=p
    return rows


def v101_arc_position_comparison_report(piece: PieceSpec) -> dict:
    old=_v101_reference_arc_positions(piece)
    new=get_shadow_clear_single_road_lattice(piece)
    seeds=new["seeds_global"]
    new_rows=[]; new_cum=0.0; prev=None
    for i,p in enumerate(seeds,start=1):
        pitch=None if prev is None else math.hypot(p[0]-prev[0],p[1]-prev[1])
        if pitch is not None: new_cum+=pitch
        o=old[i-1] if i<=len(old) else None
        old_cum=o["cumulative_mm"] if o else None
        nearest=min(old,key=lambda r:abs(r["cumulative_mm"]-new_cum))
        arc_rec=new["main_a_local"][i-1]
        m=arc_rec.get("metrics") or {}
        new_rows.append({
            "arc_index":i,"v101_wave":o["wave"] if o else None,"v101_family":o["family"] if o else None,
            "v101_ref_x_mm":o["point"][0] if o else None,"v101_ref_z_mm":o["point"][1] if o else None,
            "v105_ref_x_mm":p[0],"v105_ref_z_mm":p[1],
            "v101_pitch_prev_mm":o["pitch_mm"] if o else None,"v105_pitch_prev_mm":pitch,
            "pitch_change_mm":(pitch-o["pitch_mm"]) if o and pitch is not None and o["pitch_mm"] is not None else None,
            "v101_cumulative_mm":old_cum,"v105_cumulative_mm":new_cum,
            "cumulative_shift_vs_ordinal_v101_mm":(new_cum-old_cum) if old_cum is not None else None,
            "nearest_v101_arc_index":nearest["ordinal"],"nearest_v101_cumulative_mm":nearest["cumulative_mm"],
            "projector_clearance_min_mm":m.get("clearance_min_mm"),"center_spacing_min_mm":m.get("center_spacing_min_mm"),
            "critical_height_mean_mm":m.get("critical_height_mean_mm"),"critical_inward_offset_mean_mm":m.get("critical_inward_offset_mean_mm"),
            "controlling_constraint":arc_rec.get("constraint"),
        })
        prev=p
    old_p=[r["pitch_mm"] for r in old if r["pitch_mm"] is not None]
    new_p=[r["v105_pitch_prev_mm"] for r in new_rows if r["v105_pitch_prev_mm"] is not None]
    shared=[r for r in new_rows if r["pitch_change_mm"] is not None]
    return {
        "result":"PASS","v101_arc_count":len(old),"v105_arc_count":len(new_rows),"arc_count_change":len(new_rows)-len(old),
        "v101_pitch_mm":{"min":min(old_p),"mean":sum(old_p)/len(old_p),"max":max(old_p)},
        "v105_pitch_mm":{"min":min(new_p),"mean":sum(new_p)/len(new_p),"max":max(new_p)},
        "shared_ordinal_pitch_change_mm":{"min":min(r["pitch_change_mm"] for r in shared),"mean":sum(r["pitch_change_mm"] for r in shared)/len(shared),"max":max(r["pitch_change_mm"] for r in shared)},
        "outermost_v105_cumulative_mm":new_rows[-1]["v105_cumulative_mm"],"outermost_v101_cumulative_mm":old[-1]["cumulative_mm"],
        "rows":new_rows,
    }


def write_v101_arc_position_comparison_csv(path):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    report=v101_arc_position_comparison_report(_current_piece())
    rows=report["rows"]
    fields=list(rows[0].keys())
    with p.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    return p

def apply_top_support_valley_fill(output: Path) -> dict:
    """Fill every top-support X-raster valley with a 40% FC3D-height-compensated road.

    The filler remains owned by physical support layer 2 / nominal G1 Z0.400.
    Physical height adjustment is represented only with G29.1: the default FC3D
    40% depth is 0.068 mm below the next 0.10-mm nominal plane, hence the filler
    effective level is Z0.432 and the trim shift from the inherited plate baseline
    is +0.032 mm. No CHANGE_LAYER or DIRECT_LAYER marker is added.
    """
    output = Path(output)
    gname = "Metadata/plate_1.gcode"
    with zipfile.ZipFile(output, "r") as z:
        lines = z.read(gname).decode("utf-8", errors="strict").splitlines()

    layer_re = re.compile(r";\s*DIRECT_LAYER\s+V4\s+physical=(\d+)")
    layer_starts = [(i, int(m.group(1))) for i, l in enumerate(lines) if (m := layer_re.search(l))]
    if [p for _, p in layer_starts] != list(range(PHYSICAL_LAYER_COUNT)):
        raise RuntimeError(f"V1.101 TOP FILL: physical layer sequence invalid: {layer_starts}")
    top_physical = BASE_LAYER_COUNT - 1
    top_start = next(i for i, p in layer_starts if p == top_physical)
    optical_start = next(i for i, p in layer_starts if p == ARC_LAYER_INDEX)
    if not top_start < optical_start:
        raise RuntimeError("V1.101 TOP FILL: top support/optical ordering invalid")

    change_i = next((i for i in range(top_start, optical_start) if lines[i].strip() == "; CHANGE_LAYER"), None)
    if change_i is None:
        raise RuntimeError("V1.101 TOP FILL: change-layer boundary after top support missing")
    support_block = lines[top_start:change_i]
    if any("FC3D_V1106_TOP_VALLEY_FILL_" in l for l in support_block):
        raise RuntimeError("V1.101 TOP FILL: filler already present")

    marker_re = re.compile(r"FC3D_RASTER_SCANLINE_DIRECTION\s+mode=serpentine\s+reverse=(\d+)\s+fixed=([-+0-9.]+)")
    fixed = []
    for l in support_block:
        m = marker_re.search(l)
        if m:
            fixed.append(float(m.group(2)))
    if len(fixed) < 3 or any(fixed[i + 1] <= fixed[i] for i in range(len(fixed) - 1)):
        raise RuntimeError(f"V1.101 TOP FILL: invalid X-raster centres count/order: {len(fixed)}")
    diffs = [fixed[i + 1] - fixed[i] for i in range(len(fixed) - 1)]
    if min(diffs) < 0.395 or max(diffs) > 0.405:
        raise RuntimeError(f"V1.101 TOP FILL: top support pitch outside 0.4-mm contract: {min(diffs):.6f}..{max(diffs):.6f}")

    # Derive the support X span from positive-E raster draws, not geometry constants.
    draw_x = []
    motion_re = re.compile(r"^\s*G1\b")
    x_re = re.compile(r"\bX([-+0-9.]+)")
    e_re = re.compile(r"\bE([-+0-9.]+)")
    for l in support_block:
        if not motion_re.match(l):
            continue
        xm, em = x_re.search(l), e_re.search(l)
        if xm and em and float(em.group(1)) > 0:
            draw_x.append(float(xm.group(1)))
    if len(draw_x) < len(fixed):
        raise RuntimeError(f"V1.101 TOP FILL: insufficient top-support positive-E draws {len(draw_x)} for {len(fixed)} roads")
    x_lo, x_hi = min(draw_x), max(draw_x)
    if x_hi - x_lo < 100.0:
        raise RuntimeError(f"V1.101 TOP FILL: derived X span too short {x_lo:.3f}..{x_hi:.3f}")

    # Existing raster must finish retracted before this post-pass.
    tail_e = []
    for i in range(change_i - 1, top_start - 1, -1):
        st = lines[i].strip()
        if re.match(r"^G1\b", st) and not re.search(r"\b[XYZ][-+]?\d", st):
            em = e_re.search(st)
            if em:
                tail_e.append(float(em.group(1)))
                break
    if tail_e != [-0.4]:
        raise RuntimeError(f"V1.101 TOP FILL: top support does not end at canonical -0.400 retract: {tail_e}")

    # Recover inherited absolute G29.1 baseline active through model printing.
    g29_re = re.compile(r"^\s*G29\.1\s+Z([-+0-9.]+)")
    baselines = []
    for l in lines[:top_start]:
        m = g29_re.match(l)
        if m:
            baselines.append(float(m.group(1)))
    if not baselines:
        raise RuntimeError("V1.101 TOP FILL: inherited G29.1 baseline missing")
    baseline = baselines[-1]
    trim_target = baseline + TOP_SUPPORT_FILL_G29_DELTA_MM

    # Actual midpoints are authoritative valley centres. Emit high-Y to low-Y so
    # the first filler begins beside the final ordinary raster endpoint.
    centres = [(fixed[i] + fixed[i + 1]) * 0.5 for i in range(len(fixed) - 1)]
    centres_desc = list(reversed(centres))
    road_len = x_hi - x_lo
    e_road = road_len * TOP_SUPPORT_FILL_E_PER_MM
    fill = [
        "; FC3D_V1106_TOP_VALLEY_FILL_START no_new_logical_layer=1",
        f"; FC3D_V1106_TOP_VALLEY_FILL_RULE ve={TOP_SUPPORT_FILL_VE:.3f} depth={TOP_SUPPORT_FILL_DEPTH_MM:.3f} effective_z={TOP_SUPPORT_FILL_EFFECTIVE_Z_MM:.3f} commanded_z={BASE_TOP_Z_MM:.3f}",
        f"; FC3D_V1106_TOP_VALLEY_FILL_RASTER source_roads={len(fixed)} filler_roads={len(centres_desc)} pitch_min={min(diffs):.6f} pitch_max={max(diffs):.6f}",
        "M400",
        f"G29.1 Z{trim_target:.5f} ; FC3D_V1106_TOP_VALLEY_FILL_G29_SET baseline={baseline:.5f} delta={TOP_SUPPORT_FILL_G29_DELTA_MM:.5f}",
        "M400",
        "G90",
        "M83",
        "M204 S8000",
        f"G1 F{TOP_SUPPORT_FILL_FEED_MM_S * 60.0:.0f}",
    ]
    current_low = True
    for idx, y in enumerate(centres_desc):
        x0, x1 = (x_lo, x_hi) if current_low else (x_hi, x_lo)
        fill += [
            f"; FC3D_V1106_TOP_VALLEY_FILL_ROAD_START index={idx + 1}/{len(centres_desc)} y={y:.5f}",
            f"G1 X{x0:.3f} Y{y:.5f} F{TOP_SUPPORT_FILL_FEED_MM_S * 60.0:.0f} ; FC3D_V1106_TOP_VALLEY_FILL_MOVE",
            "G1 E0.38000 F1800 ; FC3D_V1106_TOP_VALLEY_FILL_PREPRIME",
            "G1 E0.02000 F1800 ; FC3D_V1106_TOP_VALLEY_FILL_FINAL_PRIME",
            f"G1 X{x1:.3f} Y{y:.5f} E{e_road:.5f} F{TOP_SUPPORT_FILL_FEED_MM_S * 60.0:.0f} ; FC3D_V1106_TOP_VALLEY_FILL_DRAW",
            "G1 E-0.40000 F1800 ; FC3D_V1106_TOP_VALLEY_FILL_RETRACT",
            f"; FC3D_V1106_TOP_VALLEY_FILL_ROAD_END index={idx + 1}/{len(centres_desc)}",
        ]
        current_low = not current_low
    fill.append("; FC3D_V1106_TOP_VALLEY_FILL_END state=RETRACTED trim=ACTIVE")

    # Restore plate baseline only after the existing next-layer safe lift.
    lift_i = None
    down_i = None
    z_re = re.compile(r"\bZ([-+0-9.]+)")
    for i in range(change_i + 1, optical_start):
        if re.match(r"^\s*G1\b", lines[i]):
            zm = z_re.search(lines[i])
            if zm and float(zm.group(1)) > NOMINAL_TOP_Z_MM + 0.2:
                lift_i = i
                break
    if lift_i is None:
        raise RuntimeError("V1.101 TOP FILL: next-layer safe lift missing for G29 restore")
    for i in range(lift_i + 1, optical_start):
        if re.match(r"^\s*G1\b", lines[i]):
            zm = z_re.search(lines[i])
            if zm and abs(float(zm.group(1)) - NOMINAL_TOP_Z_MM) < 1e-6:
                down_i = i
                break
    if down_i is None:
        raise RuntimeError("V1.101 TOP FILL: nominal optical descent missing after safe lift")

    out = lines[:change_i] + fill + lines[change_i:lift_i + 1] + [
        "M400",
        f"G29.1 Z{baseline:.5f} ; FC3D_V1106_TOP_VALLEY_FILL_G29_RESTORE after_safe_lift=1",
        "M400",
    ] + lines[lift_i + 1:]
    new_g = "\n".join(out) + "\n"
    _replace_zip_members(output, {gname: new_g.encode("utf-8")})
    return {
        "result": "PASS",
        "top_support_physical_layer": top_physical,
        "source_support_roads": len(fixed),
        "filler_roads": len(centres_desc),
        "ve": TOP_SUPPORT_FILL_VE,
        "depth_mm": TOP_SUPPORT_FILL_DEPTH_MM,
        "effective_z_mm": TOP_SUPPORT_FILL_EFFECTIVE_Z_MM,
        "commanded_g1_z_mm": BASE_TOP_Z_MM,
        "g29_baseline": baseline,
        "g29_target": trim_target,
        "g29_delta_mm": TOP_SUPPORT_FILL_G29_DELTA_MM,
        "e_per_mm": TOP_SUPPORT_FILL_E_PER_MM,
        "road_e": e_road,
        "x_span_mm": [x_lo, x_hi],
        "pitch_mm": [min(diffs), max(diffs)],
        "no_new_logical_layer": True,
    }

def audit_top_support_valley_fill(output: Path) -> dict:
    """Independent fail-closed audit of the v1.106 top-support filler."""
    output = Path(output)
    with zipfile.ZipFile(output, "r") as z:
        gbytes = z.read("Metadata/plate_1.gcode")
        lines = gbytes.decode("utf-8", errors="strict").splitlines()
        md5 = z.read("Metadata/plate_1.gcode.md5").decode("ascii").strip().lower()
    if hashlib.md5(gbytes).hexdigest() != md5:
        raise RuntimeError("V1.101 TOP FILL AUDIT: G-code MD5 mismatch")
    starts = [i for i, l in enumerate(lines) if re.search(r";\s*DIRECT_LAYER\s+V4\s+physical=", l)]
    if len(starts) != PHYSICAL_LAYER_COUNT:
        raise RuntimeError(f"V1.101 TOP FILL AUDIT: logical layer count changed: {len(starts)}")
    text = "\n".join(lines)
    if text.count("FC3D_V1106_TOP_VALLEY_FILL_START") != 1 or text.count("FC3D_V1106_TOP_VALLEY_FILL_END") != 1:
        raise RuntimeError("V1.101 TOP FILL AUDIT: fill boundary markers missing/duplicated")
    draws = [l for l in lines if "FC3D_V1106_TOP_VALLEY_FILL_DRAW" in l]
    starts_r = [l for l in lines if "FC3D_V1106_TOP_VALLEY_FILL_ROAD_START" in l]
    retracts = [l for l in lines if "FC3D_V1106_TOP_VALLEY_FILL_RETRACT" in l]
    pre = [l for l in lines if "FC3D_V1106_TOP_VALLEY_FILL_PREPRIME" in l]
    fin = [l for l in lines if "FC3D_V1106_TOP_VALLEY_FILL_FINAL_PRIME" in l]
    if not draws or not (len(draws) == len(starts_r) == len(retracts) == len(pre) == len(fin)):
        raise RuntimeError(
            f"V1.101 TOP FILL AUDIT: pressure/draw counts inconsistent draw={len(draws)} "
            f"start={len(starts_r)} retract={len(retracts)} pre={len(pre)} final={len(fin)}"
        )
    e_re = re.compile(r"\bE([-+0-9.]+)")
    f_re = re.compile(r"\bF([-+0-9.]+)")
    x_re = re.compile(r"\bX([-+0-9.]+)")
    y_re = re.compile(r"\bY([-+0-9.]+)")
    epm = []
    for i, l in enumerate(lines):
        if "FC3D_V1106_TOP_VALLEY_FILL_DRAW" not in l:
            continue
        xm, ym, em, fm = x_re.search(l), y_re.search(l), e_re.search(l), f_re.search(l)
        if not (xm and ym and em and fm):
            raise RuntimeError(f"V1.101 TOP FILL AUDIT: malformed draw {l}")
        if abs(float(fm.group(1)) - TOP_SUPPORT_FILL_FEED_MM_S * 60.0) > 1e-6:
            raise RuntimeError(f"V1.101 TOP FILL AUDIT: wrong draw feed {l}")
        j = i - 1
        while j >= 0 and "FC3D_V1106_TOP_VALLEY_FILL_MOVE" not in lines[j]:
            j -= 1
        if j < 0:
            raise RuntimeError("V1.101 TOP FILL AUDIT: draw lacks preceding move")
        x0 = float(x_re.search(lines[j]).group(1))
        y0 = float(y_re.search(lines[j]).group(1))
        x1 = float(xm.group(1))
        y1 = float(ym.group(1))
        e = float(em.group(1))
        dist = math.hypot(x1 - x0, y1 - y0)
        epm.append(e / dist)
    if max(abs(v - TOP_SUPPORT_FILL_E_PER_MM) for v in epm) > 2e-6:
        raise RuntimeError(f"V1.101 TOP FILL AUDIT: E/mm mismatch range {min(epm):.8f}..{max(epm):.8f}")
    set_lines = [l for l in lines if "FC3D_V1106_TOP_VALLEY_FILL_G29_SET" in l]
    restore_lines = [l for l in lines if "FC3D_V1106_TOP_VALLEY_FILL_G29_RESTORE" in l]
    if len(set_lines) != 1 or len(restore_lines) != 1:
        raise RuntimeError("V1.101 TOP FILL AUDIT: G29 set/restore count invalid")
    g29_re = re.compile(r"G29\.1\s+Z([-+0-9.]+)")
    target = float(g29_re.search(set_lines[0]).group(1))
    restored = float(g29_re.search(restore_lines[0]).group(1))
    if abs((target - restored) - TOP_SUPPORT_FILL_G29_DELTA_MM) > 1e-6:
        raise RuntimeError(
            f"V1.101 TOP FILL AUDIT: G29 delta {target - restored:.5f} != {TOP_SUPPORT_FILL_G29_DELTA_MM:.5f}"
        )
    restore_i = lines.index(restore_lines[0])
    prior_z = []
    z_re = re.compile(r"\bZ([-+0-9.]+)")
    for l in lines[max(0, restore_i - 8):restore_i]:
        if re.match(r"^\s*G1\b", l) and (m := z_re.search(l)):
            prior_z.append(float(m.group(1)))
    if not prior_z or max(prior_z) <= NOMINAL_TOP_Z_MM + 0.2:
        raise RuntimeError(f"V1.101 TOP FILL AUDIT: G29 restore not performed after safe lift: {prior_z}")
    start_i = next(i for i, l in enumerate(lines) if "FC3D_V1106_TOP_VALLEY_FILL_START" in l)
    end_i = next(i for i, l in enumerate(lines) if "FC3D_V1106_TOP_VALLEY_FILL_END" in l)
    if any("CHANGE_LAYER" in l or "DIRECT_LAYER" in l for l in lines[start_i:end_i + 1]):
        raise RuntimeError("V1.101 TOP FILL AUDIT: filler manufactured a logical layer")
    return {
        "result": "PASS",
        "filler_roads": len(draws),
        "e_per_mm_min": min(epm),
        "e_per_mm_max": max(epm),
        "g29_delta_mm": target - restored,
        "effective_z_mm": TOP_SUPPORT_FILL_EFFECTIVE_Z_MM,
        "no_new_logical_layer": True,
    }

def normalize_a1mini_orca_reference_metadata(output: Path) -> dict:
    """Normalize non-executable metadata to the working Orca A1 Mini reference.

    The embedded templates are copied byte-for-byte from the user's Orca 2.5.0
    cube that successfully printed through Bambu Connect.  Only metadata/config
    is replaced here.  The already-audited executable A1 startup/model/end block
    is not reconstructed or resliced.
    """
    import base64, zlib
    output = Path(output)
    gname = "Metadata/plate_1.gcode"
    pname = "Metadata/project_settings.config"
    sname = "Metadata/slice_info.config"
    plate_name = "Metadata/plate_1.json"
    seq_name = "Metadata/filament_sequence.json"
    model_settings_name = "Metadata/model_settings.config"
    model_name = "3D/3dmodel.model"
    required = (gname, pname, sname, plate_name, seq_name, model_settings_name, model_name)
    with zipfile.ZipFile(output, "r") as z:
        missing = [n for n in required if n not in z.namelist()]
        if missing:
            raise RuntimeError(f"V1.101 ORCA REFERENCE METADATA: missing members {missing}")
        old_g = z.read(gname).decode("utf-8", errors="strict")
        old_project = json.loads(z.read(pname).decode("utf-8"))
        slice_root = ET.fromstring(z.read(sname))
        plate = json.loads(z.read(plate_name).decode("utf-8"))
        model_settings_root = ET.fromstring(z.read(model_settings_name))
        model_text = z.read(model_name).decode("utf-8", errors="strict")

    native_project = json.loads(zlib.decompress(base64.b64decode('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')).decode("utf-8"))
    native_config = zlib.decompress(base64.b64decode('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')).decode("utf-8")

    # Keep only truthful FC3D process-display values that are useful in Orca's
    # preview UI.  Machine, filament, AMS and enum values come from the native
    # A1 Mini reference instead of the inherited H2C template.
    preserve_project_keys = (
        "layer_height", "initial_layer_print_height", "initial_layer_line_width",
        "line_width", "outer_wall_line_width", "inner_wall_line_width",
        "sparse_infill_line_width", "top_surface_line_width", "support_line_width",
        "print_sequence", "spiral_mode",
    )
    preserved_project = {k: old_project[k] for k in preserve_project_keys if k in old_project}
    project = dict(native_project)
    project.update(preserved_project)
    project.update({
        "printer_model": A1_MINI_PRINTER_NAME,
        "printer_settings_id": A1_MINI_PRINTER_PRESET,
        "print_settings_id": A1_MINI_PROCESS_PRESET,
        "print_compatible_printers": [A1_MINI_PRINTER_PRESET],
        "printer_structure": "i3",
        "printable_area": ["0x0", "180x0", "180x180", "0x180"],
        "printable_height": "180",
        "nozzle_diameter": ["0.4"],
        "nozzle_type": ["stainless_steel"],
        "nozzle_volume": ["92"],
        "nozzle_volume_type": ["Standard"],
        "default_nozzle_volume_type": ["Standard"],
        "printer_extruder_id": ["1"],
        "print_extruder_id": ["1"],
        "printer_extruder_variant": ["Direct Drive Standard"],
        "print_extruder_variant": ["Direct Drive Standard"],
        "filament_settings_id": ["Generic PETG @BBL A1M"],
        "filament_type": ["PETG"],
        "filament_colour": ["#000000"],
        "filament_multi_colour": ["#000000"],
        "filament_ids": ["GFG99"],
        "filament_map": ["1"],
        "filament_map_2": ["1"],
        "filament_nozzle_map": ["0"],
        "physical_extruder_map": ["0"],
        "extruder_ams_count": ["1#0|4#0", ""],
        "enable_prime_tower": "0",
        "prime_tower_enable_framework": "0",
        "curr_bed_type": "Textured PEI Plate",
        "ensure_vertical_shell_thickness": "ensure_all",
        "raft_first_layer_expansion": "2",
        "prime_tower_brim_width": "3",
        "machine_start_gcode": _a1mini_start_gcode() + "\n",
        "machine_end_gcode": _a1mini_end_gcode(_mirror_wave_peak_z_mm()) + "\n",
    })
    # Native Orca does not carry this legacy negative sentinel.  Its presence
    # caused Orca 2.5.0's invalid-range toast in the previous output.
    project.pop("prime_tower_lift_height", None)

    # Replace the complete CONFIG_BLOCK with the known-working A1/Orca block.
    a = old_g.find("; CONFIG_BLOCK_START")
    b0 = old_g.find("; CONFIG_BLOCK_END")
    if a < 0 or b0 < 0 or b0 <= a:
        raise RuntimeError("V1.101 ORCA REFERENCE METADATA: CONFIG_BLOCK boundaries missing")
    b = b0 + len("; CONFIG_BLOCK_END")
    new_g = old_g[:a] + native_config + old_g[b:]

    # Preserve a small set of truthful FC3D process-display values from the old
    # config while keeping all machine/filament topology native A1 Mini.
    preserve_config_keys = preserve_project_keys
    for key in preserve_config_keys:
        m = re.search(rf"^; {re.escape(key)} = (.*)$", old_g, re.M)
        if m:
            new_g = _replace_config_comment(new_g, key, m.group(1))
    for key, value in {
        "enable_prime_tower": "0",
        "prime_tower_enable_framework": "0",
        "curr_bed_type": "Textured PEI Plate",
        "ensure_vertical_shell_thickness": "ensure_all",
        "raft_first_layer_expansion": "2",
        "prime_tower_brim_width": "3",
        "machine_start_gcode": _a1mini_start_gcode().replace("\n", "\\n"),
        "machine_end_gcode": _a1mini_end_gcode(_mirror_wave_peak_z_mm()).replace("\n", "\\n"),
    }.items():
        new_g = _replace_config_comment(new_g, key, value)

    # Header filament identity also becomes one logical A1 external-spool PETG.
    header_patch = {
        "filament": "1",
        "filament_density": "1.27",
        "filament_diameter": "1.75",
    }
    for key, value in header_patch.items():
        pat = re.compile(rf"^; {re.escape(key)}:\s*.*$", re.M)
        if len(pat.findall(new_g)) != 1:
            raise RuntimeError(f"V1.101 ORCA REFERENCE METADATA: expected one header {key} line")
        new_g = pat.sub(lambda _m, k=key, v=value: f"; {k}: {v}", new_g, count=1)

    # Orca/Bambu config values that select one PETG on the external spool.
    config_contract = {
        "default_filament_profile": '"Bambu PLA Basic @BBL A1M"',
        "filament_settings_id": '"Generic PETG @BBL A1M"',
        "filament_colour": "#000000",
        "filament_type": "PETG",
        "filament_ids": "GFG99",
        "filament_map": "1",
        "filament_map_2": "0",
        "filament_nozzle_map": "0",
        "filament_extruder_variant": '"Direct Drive Standard"',
        "filament_max_volumetric_speed": "8",
        "filament_flow_ratio": "0.95",
        "extruder_ams_count": "1#0|4#0;",
        "physical_extruder_map": "0",
        "single_extruder_multi_material": "1",
        "printer_extruder_id": "1",
        "print_extruder_id": "1",
        "printer_extruder_variant": '"Direct Drive Standard"',
        "print_extruder_variant": '"Direct Drive Standard"',
        "extruder_max_nozzle_count": "1",
        "extruder_nozzle_stats": "Standard#1",
        "extruder_variant_list": '"Direct Drive Standard"',
        "extruder_type": "Direct Drive",
        "extruder_offset": "0x0",
        "extruder_colour": "#000000",
        "extruder_printable_area": "",
        "extruder_printable_height": "0",
    }
    for key, value in config_contract.items():
        new_g = _replace_config_comment(new_g, key, value)

    # Slice-info header: reproduce Orca's own package identity convention.
    header = slice_root.find("header")
    if header is None:
        header = ET.Element("header")
        slice_root.insert(0, header)
    header_items = {n.attrib.get("key"): n for n in header.findall("header_item")}
    for key, value in (
        ("X-BBL-Client-Type", "slicer"),
        ("X-BBL-Client-Version", "02.08.01.55"),
        ("OrcaSlicer-Version", "2.5.0-dev"),
    ):
        node = header_items.get(key)
        if node is None:
            node = ET.SubElement(header, "header_item", key=key, value=value)
        else:
            node.set("value", value)

    plate_node = slice_root.find("plate")
    if plate_node is None:
        raise RuntimeError("V1.101 ORCA REFERENCE METADATA: slice_info has no plate")
    meta_nodes = {n.attrib.get("key"): n for n in plate_node.findall("metadata") if n.attrib.get("key")}
    for key, value in (
        ("printer_model_id", "N1"),
        ("nozzle_diameters", "0.4"),
        ("nozzle_volume_type", "0"),
        ("has_filament_switcher", "false"),
        ("filament_maps", "1"),
        ("limit_filament_maps", "0"),
    ):
        node = meta_nodes.get(key)
        if node is None:
            ET.SubElement(plate_node, "metadata", key=key, value=value)
        else:
            node.set("value", value)
    old_fil = plate_node.find("filament")
    used_m = old_fil.attrib.get("used_m", "0.00") if old_fil is not None else "0.00"
    used_g = old_fil.attrib.get("used_g", "0.00") if old_fil is not None else "0.00"
    for node in list(plate_node.findall("filament")):
        plate_node.remove(node)
    ET.SubElement(plate_node, "filament", {
        "id": "1", "tray_info_idx": "GFG99", "type": "PETG", "color": "#000000",
        "used_m": used_m, "used_g": used_g, "group_id": "0",
        "nozzle_diameter": "0.40", "volume_type": "Standard",
        "used_for_object": "true", "used_for_support": "false",
    })
    for node in list(plate_node.findall("nozzle")):
        plate_node.remove(node)
    ET.SubElement(plate_node, "nozzle", {
        "id": "0", "extruder_id": "1", "nozzle_diameter": "0.4", "volume_type": "Standard",
    })
    layer_lists = plate_node.find("layer_filament_lists")
    if layer_lists is not None:
        existing_ranges = [n.attrib.get("layer_ranges") for n in list(layer_lists) if n.attrib.get("layer_ranges")]
        for node in list(layer_lists):
            layer_lists.remove(node)
        layer_ranges = existing_ranges[0] if existing_ranges else f"0 {PHYSICAL_LAYER_COUNT - 1}"
        ET.SubElement(layer_lists, "layer_filament_list", filament_list="0", layer_ranges=layer_ranges)

    # plate_1.json follows the exact native A1 Mini representation.
    plate["bed_type"] = "textured_plate"
    plate["filament_colors"] = ["#000000"]
    plate["filament_ids"] = [0]
    plate["first_extruder"] = 0
    plate["nozzle_diameter"] = 0.4000000059604645

    # External-spool/no-AMS filament sequence from the successful cube.
    seq = {"plate_1": {"nozzle_sequence": [0], "optimal_assignment": [0], "sequence": [1]}}

    # model_settings.config must agree with the same single logical filament.
    ms_plate = model_settings_root.find("plate")
    if ms_plate is None:
        raise RuntimeError("V1.101 ORCA REFERENCE METADATA: model_settings has no plate")
    ms_meta = {n.attrib.get("key"): n for n in ms_plate.findall("metadata") if n.attrib.get("key")}
    for key, value in (("filament_maps", "1"), ("filament_volume_maps", "0")):
        node = ms_meta.get(key)
        if node is None:
            ET.SubElement(ms_plate, "metadata", key=key, value=value)
        else:
            node.set("value", value)
    if "fc3d_active_filament_one_based" in ms_meta:
        ms_meta["fc3d_active_filament_one_based"].set("value", "1")

    # Native Orca 2.5.0 retains a BambuStudio Application metadata item and adds
    # its own OrcaSlicer item.  Reproduce that convention exactly; do not invent
    # a non-native Application value.
    app_pat = re.compile(r'<metadata name="Application">.*?</metadata>')
    if len(app_pat.findall(model_text)) != 1:
        raise RuntimeError("V1.101 ORCA REFERENCE METADATA: 3D model Application metadata missing/ambiguous")
    model_text = app_pat.sub('<metadata name="Application">BambuStudio-02.08.01.55</metadata>', model_text, count=1)
    orca_pat = re.compile(r'<metadata name="OrcaSlicer">.*?</metadata>')
    if orca_pat.search(model_text):
        model_text = orca_pat.sub('<metadata name="OrcaSlicer">2.5.0-dev</metadata>', model_text, count=1)
    else:
        app_line = '<metadata name="Application">BambuStudio-02.08.01.55</metadata>'
        model_text = model_text.replace(app_line, app_line + '\n <metadata name="OrcaSlicer">2.5.0-dev</metadata>', 1)

    replacements = {
        gname: new_g.encode("utf-8"),
        pname: json.dumps(project, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
        sname: ET.tostring(slice_root, encoding="utf-8", xml_declaration=True),
        plate_name: json.dumps(plate, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
        seq_name: json.dumps(seq, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
        model_settings_name: ET.tostring(model_settings_root, encoding="utf-8", xml_declaration=True),
        model_name: model_text.encode("utf-8"),
    }
    _replace_zip_members(output, replacements)
    return audit_a1mini_orca_reference_metadata(output)

def audit_a1mini_orca_reference_metadata(output: Path) -> dict:
    """Fail-closed audit against the successfully printed Orca A1 Mini reference."""
    output = Path(output)
    with zipfile.ZipFile(output, "r") as z:
        project = json.loads(z.read("Metadata/project_settings.config").decode("utf-8"))
        gbytes = z.read("Metadata/plate_1.gcode")
        g = gbytes.decode("utf-8", errors="strict")
        slice_root = ET.fromstring(z.read("Metadata/slice_info.config"))
        plate = json.loads(z.read("Metadata/plate_1.json").decode("utf-8"))
        seq = json.loads(z.read("Metadata/filament_sequence.json").decode("utf-8"))
        model_settings = ET.fromstring(z.read("Metadata/model_settings.config"))
        model_text = z.read("3D/3dmodel.model").decode("utf-8", errors="strict")
        md5 = z.read("Metadata/plate_1.gcode.md5").decode("ascii").strip().lower()

    expected_project = {
        "printer_model": "Bambu Lab A1 mini",
        "printer_settings_id": "Bambu Lab A1 mini 0.4 nozzle",
        "print_settings_id": "0.20mm Standard @BBL A1M",
        "printer_structure": "i3",
        "nozzle_diameter": ["0.4"],
        "nozzle_type": ["stainless_steel"],
        "nozzle_volume": ["92"],
        "nozzle_volume_type": ["Standard"],
        "default_nozzle_volume_type": ["Standard"],
        "filament_settings_id": ["Generic PETG @BBL A1M"],
        "filament_type": ["PETG"],
        "filament_colour": ["#000000"],
        "filament_ids": ["GFG99"],
        "filament_map": ["1"],
        "filament_map_2": ["1"],
        "filament_nozzle_map": ["0"],
        "physical_extruder_map": ["0"],
        "extruder_ams_count": ["1#0|4#0", ""],
        "ensure_vertical_shell_thickness": "ensure_all",
        "raft_first_layer_expansion": "2",
        "prime_tower_brim_width": "3",
        "enable_prime_tower": "0",
        "prime_tower_enable_framework": "0",
        "curr_bed_type": "Textured PEI Plate",
    }
    wrong = {k: (project.get(k), v) for k, v in expected_project.items() if project.get(k) != v}
    if wrong:
        raise RuntimeError(f"V1.101 ORCA REFERENCE AUDIT: project mismatch {wrong}")
    if "prime_tower_lift_height" in project:
        raise RuntimeError("V1.101 ORCA REFERENCE AUDIT: legacy negative prime_tower_lift_height survived")
    if "H2C" in json.dumps(project, ensure_ascii=False):
        raise RuntimeError("V1.101 ORCA REFERENCE AUDIT: H2C project metadata survived")

    config_expect = {
        "ensure_vertical_shell_thickness": "ensure_all",
        "raft_first_layer_expansion": "2",
        "prime_tower_brim_width": "3",
        "filament_settings_id": '"Generic PETG @BBL A1M"',
        "filament_type": "PETG",
        "filament_colour": "#000000",
        "filament_ids": "GFG99",
        "filament_map": "1",
        "filament_map_2": "0",
        "filament_nozzle_map": "0",
        "extruder_ams_count": "1#0|4#0;",
        "physical_extruder_map": "0",
        "enable_prime_tower": "0",
        "prime_tower_enable_framework": "0",
    }
    cfg_a = g.find("; CONFIG_BLOCK_START")
    cfg_b = g.find("; CONFIG_BLOCK_END")
    if cfg_a < 0 or cfg_b <= cfg_a:
        raise RuntimeError("V1.101 ORCA REFERENCE AUDIT: CONFIG_BLOCK missing")
    cfg_text = g[cfg_a:cfg_b]
    if "H2C" in cfg_text:
        raise RuntimeError("V1.101 ORCA REFERENCE AUDIT: H2C G-code config metadata survived")
    for key, expected in config_expect.items():
        m = re.search(rf"^; {re.escape(key)} = (.*)$", cfg_text, re.M)
        if not m or m.group(1) != expected:
            raise RuntimeError(
                f"V1.101 ORCA REFERENCE AUDIT: G-code config {key}={m.group(1) if m else None!r}, expected {expected!r}"
            )
    if re.search(r"^; raft_first_layer_expansion = -", cfg_text, re.M):
        raise RuntimeError("V1.101 ORCA REFERENCE AUDIT: invalid negative raft_first_layer_expansion survived")
    for key, expected in (("filament", "1"), ("filament_density", "1.27"), ("filament_diameter", "1.75")):
        m = re.search(rf"^; {re.escape(key)}:\s*(.*)$", g, re.M)
        if not m or m.group(1).strip() != expected:
            raise RuntimeError(f"V1.101 ORCA REFERENCE AUDIT: header {key}={m.group(1) if m else None!r}")

    header = slice_root.find("header")
    h = {n.attrib.get("key"): n.attrib.get("value") for n in header.findall("header_item")} if header is not None else {}
    if h.get("X-BBL-Client-Version") != "02.08.01.55" or h.get("OrcaSlicer-Version") != "2.5.0-dev":
        raise RuntimeError(f"V1.101 ORCA REFERENCE AUDIT: slice header {h}")
    p = slice_root.find("plate")
    if p is None:
        raise RuntimeError("V1.101 ORCA REFERENCE AUDIT: slice plate missing")
    meta = {n.attrib.get("key"): n.attrib.get("value") for n in p.findall("metadata")}
    if meta.get("printer_model_id") != "N1" or meta.get("nozzle_diameters") != "0.4" or meta.get("has_filament_switcher") != "false" or meta.get("filament_maps") != "1":
        raise RuntimeError(f"V1.101 ORCA REFERENCE AUDIT: slice metadata {meta}")
    fil = [n.attrib for n in p.findall("filament")]
    if len(fil) != 1 or fil[0].get("id") != "1" or fil[0].get("type") != "PETG" or fil[0].get("color") != "#000000" or fil[0].get("group_id") != "0":
        raise RuntimeError(f"V1.101 ORCA REFERENCE AUDIT: slice filament {fil}")
    nozzles = [n.attrib for n in p.findall("nozzle")]
    if nozzles != [{"id": "0", "extruder_id": "1", "nozzle_diameter": "0.4", "volume_type": "Standard"}]:
        raise RuntimeError(f"V1.101 ORCA REFERENCE AUDIT: slice nozzle {nozzles}")
    if seq != {"plate_1": {"nozzle_sequence": [0], "optimal_assignment": [0], "sequence": [1]}}:
        raise RuntimeError(f"V1.101 ORCA REFERENCE AUDIT: filament sequence {seq}")
    if plate.get("bed_type") != "textured_plate" or plate.get("filament_colors") != ["#000000"] or plate.get("filament_ids") != [0] or plate.get("first_extruder") != 0:
        raise RuntimeError(f"V1.101 ORCA REFERENCE AUDIT: plate JSON mapping {plate.get('bed_type')!r}/{plate.get('filament_colors')!r}/{plate.get('filament_ids')!r}/{plate.get('first_extruder')!r}")
    ms_plate = model_settings.find("plate")
    ms = {n.attrib.get("key"): n.attrib.get("value") for n in ms_plate.findall("metadata")} if ms_plate is not None else {}
    if ms.get("filament_maps") != "1" or ms.get("filament_volume_maps") != "0":
        raise RuntimeError(f"V1.101 ORCA REFERENCE AUDIT: model_settings filament maps {ms}")
    if '<metadata name="Application">BambuStudio-02.08.01.55</metadata>' not in model_text or '<metadata name="OrcaSlicer">2.5.0-dev</metadata>' not in model_text:
        raise RuntimeError("V1.101 ORCA REFERENCE AUDIT: native Orca 3MF identity metadata missing")
    actual_md5 = hashlib.md5(gbytes).hexdigest()
    if actual_md5 != md5:
        raise RuntimeError(f"V1.101 ORCA REFERENCE AUDIT: MD5 {md5} != {actual_md5}")
    return {
        "reference": "working Orca 2.5.0 A1 Mini PETG cube",
        "printer": "Bambu Lab A1 mini 0.4 nozzle",
        "filament": "Generic PETG / black / external spool",
        "ams": False,
        "filament_sequence": [1],
        "nozzle_sequence": [0],
        "ensure_vertical_shell_thickness": "ensure_all",
        "raft_first_layer_expansion": 2,
        "orca_3mf_metadata": "2.5.0-dev",
        "gcode_md5": actual_md5,
    }

def main():
    ap = argparse.ArgumentParser(description="FC3D v1.106 A-only six-pack bonding test with per-arc pressure reset and black-only rear texture", allow_abbrev=False)
    ap.add_argument("--source", type=Path, default=Path("3dprintv1.179.py"))
    ap.add_argument("--piece", choices=tuple(f"{c}-{r}" for c in range(1, 6) for r in range(1, 6)), required=True)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--dry-validate", action="store_true")
    ap.add_argument("--slicer-target", "--slicer", choices=("orca", "studio"), default=DEFAULT_SLICER_TARGET, help="Output package compatibility target (default: orca for the ALR project).")
    ap.add_argument("--printer-target", choices=("a1mini",), default="a1mini", help="Physical printer target; v1.106 emits an A1 Mini 0.4-mm Orca-compatible package.")
    ap.add_argument("--e-per-mm", type=float, default=DEFAULT_E_PER_MM, help=f"Calibrated E/mm for {LAYER_H_MM:.2f}-mm layers and {ROAD_WIDTH_MM:.2f}-mm roads (default {DEFAULT_E_PER_MM:.6f}).")
    known, passthrough = ap.parse_known_args()
    reject_protected_passthrough(passthrough)
    global CURRENT_PIECE, RUNTIME_ORIGIN
    set_runtime_e_per_mm(known.e_per_mm)
    CURRENT_PIECE = PieceSpec.for_name(known.piece)
    RUNTIME_ORIGIN = None
    if known.output is None:
        known.output = Path(f"black_a_only_wave_sets_true_normal_valleyfill25_{known.piece.replace('-', '_')}_v1.106.gcode.3mf")
    dummy = 45.0
    dp = import_3dprint(known.source)
    install_patches(dp, dummy, dummy, dummy)
    mirror_csv = Path(str(known.output) + ".mirror_summary.csv")
    layer_csv = Path(str(known.output) + ".layer_summary.csv")
    write_mirror_summary_csv(mirror_csv)
    write_mirror_layer_summary_csv(layer_csv)
    arc_position_csv = Path(str(known.output) + ".v105_v106_wave_set_comparison.csv")
    write_v105_v106_wave_set_comparison_csv(arc_position_csv)
    print(SCRIPT_VERSION)
    print("  slicer target                 :", known.slicer_target, "(default Orca for ALR)")
    print("  printer target                :", known.printer_target)
    dry_validate_v1106(dp)
    print("  mirror CSV                    :", mirror_csv)
    print("  layer CSV                     :", layer_csv)
    print("  v1.105->v1.106 wave-set CSV    :", arc_position_csv)
    if known.dry_validate:
        return
    with tempfile.TemporaryDirectory(prefix="fc3d_mirror_wave_v1106_") as td:
        placeholder = Path(td) / "placeholder.png"
        Image.new("RGB", (8, 2), (22, 22, 22)).save(placeholder)
        base_args = [
            str(known.source), "--direct-layer-images", ",".join([str(placeholder)] * DIRECT_OPTICAL_LAYER_COUNT), "--direct-layout", "4x2",
            "--center-x", "90.000", "--center-y", "90.000",
            "--output", str(known.output), "--rp-pitch-mm", f"{RP_PITCH_MM:.6f}",
            "--print-width-mm", f"{ROAD_WIDTH_MM:.6f}", "--endpoint-trim-mm", "0",
            "--close-gaps-mm", "0", "--directional-block-mm", "0", "--edge-aa", "off",
            "--skip-absent-layer-materials", "on", "--progress", "on",
            "--filament-assignment-json", json.dumps({LOGICAL_MATERIAL: BLACK_ASSIGNMENT}, separators=(",", ":")),
        ]
        old = sys.argv
        try:
            sys.argv = base_args + list(passthrough)
            dp.main()
        finally:
            sys.argv = old
    reports = {"script": SCRIPT_VERSION, "base_emitter": EXPECTED_DP_VERSION, "piece": CURRENT_PIECE.name, "slicer_target": known.slicer_target, "printer_target": known.printer_target}
    reports["native_plate_process"] = audit_reference_cube_native_plate_process(known.output)
    reports["mirror_wave_paths"] = apply_mirror_wave_paths(known.output)
    reports["top_support_valley_fill"] = apply_top_support_valley_fill(known.output)
    reports["mirror_finish_clearance"] = enforce_mirror_wave_finish_clearance(known.output)
    reports["tower_policy"] = apply_dynamic_tower_policy(known.output)
    reports["fan"] = enforce_minimum_model_part_fan(known.output)
    reports["base_interlock"] = audit_final_base_interlock(known.output)
    reports["black_texture_single_material"] = audit_final_black_texture_and_single_material(known.output)
    reports["final_paths"] = audit_final_mirror_wave_paths(known.output)
    reports["top_support_valley_fill_audit"] = audit_top_support_valley_fill(known.output)
    reports["card_geometry"] = audit_final_panel_xy_geometry(known.output)
    reports["wave_sets"] = waveset_report(CURRENT_PIECE)
    reports["v105_v106_wave_set_comparison"] = {k:v for k,v in v105_v106_wave_set_comparison_report(CURRENT_PIECE).items() if k != "rows"}
    reports["a1mini_package"] = convert_package_to_a1mini_orca(known.output)
    reports["a1mini_reference_metadata"] = normalize_a1mini_orca_reference_metadata(known.output)
    reports["slicer_target_metadata"] = apply_slicer_target_metadata(known.output, known.slicer_target)
    reports["a1mini_final"] = audit_a1mini_orca_package(known.output)
    reports["a1mini_reference_final"] = audit_a1mini_orca_reference_metadata(known.output)
    reports["mirror_design"] = {"screen_diagonal_in":100.0,"screen_width_mm":MASTER_FAN.screen_width_mm,"screen_height_mm":MASTER_FAN.screen_height_mm,"projector_screen_x_mm":MASTER_FAN.projector_x_mm,"projector_screen_z_mm":MASTER_FAN.projector_z_mm,"projector_distance_mm":MASTER_FAN.projector_distance_mm,"viewer_distance_mm":MASTER_FAN.viewer_distance_mm,"viewer_eyeline_fraction":MASTER_FAN.viewer_eyeline_fraction,"piece_global_x_mm":[CURRENT_PIECE.global_x0_mm,CURRENT_PIECE.global_x1_mm],"piece_global_z_mm":[CURRENT_PIECE.global_z0_mm,CURRENT_PIECE.global_z1_mm],"road_width_mm":ROAD_WIDTH_MM,"nominal_layer_height_mm":LAYER_H_MM,"b_enabled":False,"a_inner_enabled":False,"rear_label_transform":"text_none_arrow_vertical_flip","a_main_nominal_height_mm":A_MAIN_NOMINAL_HEIGHT_MM,"wave_peak_mm":WAVESET_TOTAL_PEAK_MM,"wave_feed_mm_s":WAVESET_PRINT_FEED_MM_S,"a_main_e_per_mm":A_MAIN_E_PER_MM,"bond_pack_count":A_BOND_PACK_COUNT,"bond_z_shifts_mm":list(A_BOND_Z_SHIFTS_MM),"single_main_only":False,"true_normal_wave_sets":True,"physical_peak_z_mm":_mirror_wave_peak_z_mm(),"base_interlock":["X" if i % 2 == 0 else "Y" for i in range(BASE_LAYER_COUNT)]}
    aj = Path(str(known.output) + ".audit.json")
    write_audit_json(aj, reports)
    print("\nFINAL AUDIT: PASS")
    for k in ("native_plate_process", "mirror_wave_paths", "top_support_valley_fill", "mirror_finish_clearance", "tower_policy", "fan", "base_interlock", "black_texture_single_material", "final_paths", "top_support_valley_fill_audit", "card_geometry", "a1mini_package", "a1mini_reference_metadata", "slicer_target_metadata", "a1mini_final", "a1mini_reference_final"):
        print(f"  {k}: PASS")
    print("Wrote", known.output)
    print("Wrote", mirror_csv)
    print("Wrote", layer_csv)
    print("Wrote", arc_position_csv)
    print("Wrote", aj)


if __name__ == "__main__":
    main()
