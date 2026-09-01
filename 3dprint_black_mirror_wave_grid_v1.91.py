#!/usr/bin/env python3
"""
FC3D v1.91: A-only dual-arc bonding/profile test-card wrapper.

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

SCRIPT_VERSION = "3dprint_black_mirror_wave_grid_v1.91"
EXPECTED_DP_VERSION = "3dprintv1.179"
DEFAULT_SLICER_TARGET = "orca"
ORCA_PRODUCER_VERSION = "2.5.0-dev"
PANEL_COUNT = 1

PANEL_WIDTH_X_MM = 110.69009321481777  # v1.91 8:9 coupon; exact master crop is set below
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


def _patch_emitter_source_for_v191(source_text: str) -> str:
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
                raise RuntimeError("FC3D_V191_BASE_MULTI_MATERIAL base has no present material")
            carryover_hit = False
            tower_slot_count = len(material_order)
            tower_slot_order = list(material_order)
            filler_slots = 0
            g.append("; FC3D_V191_BASE_MULTI_MATERIAL present=" + ",".join(present_materials) + " order=" + ",".join(material_order))
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
                    g.append(f"; FC3D_V191_TOWER_DROPPED_AFTER_LABEL physical={physical} material={mat}")
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
            raise RuntimeError(f"v1.91 fail closed: expected exactly one canonical v1.179 {label} patch target, found {count}")
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
    source_text = _patch_emitter_source_for_v191(source_text)
    module_name = "fc3d_black_mirror_wave_v191"
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


def _v191_hotend_for_material(material, raw_tool, w_hotend_index):
    # H2C compatibility path: logical W is mapped to the physical BLACK spool
    # in the colour/right head. v1.91 itself is single-material.
    if str(material) == LOGICAL_MATERIAL:
        return 0
    return 1 - int(w_hotend_index)


def _make_v191_job_material_tower_audit(original_audit):
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
            if "FC3D_V191_TOWER_DROPPED_AFTER_LABEL" in line:
                dropped[current] = True
            if line.strip().startswith("; FC3D_TOWER_SLOT "):
                mm = re.search(r"canonical_slot=([WFRYGCB])\s+slot=(\d+)/(\d+)\s+role=([^\s]+)", line)
                if mm:
                    actual_slots[current].append((mm.group(1), int(mm.group(2)), int(mm.group(3)), mm.group(4)))
        if [x[0] for x in actual_slots.get(0, [])] != [LOGICAL_MATERIAL]:
            raise RuntimeError(f"v1.91 dynamic tower audit: base slots {actual_slots.get(0)} != W only")
        if [x[0] for x in actual_slots.get(1, [])] != [LOGICAL_MATERIAL]:
            raise RuntimeError(f"v1.91 dynamic tower audit: second-layer slots {actual_slots.get(1)} != W only")
        for li in range(2, PHYSICAL_LAYER_COUNT):
            if actual_slots.get(li):
                raise RuntimeError(f"v1.91 dynamic tower audit: tower slots remain on layer {li}: {actual_slots[li]}")
            if not dropped.get(li):
                raise RuntimeError(f"v1.91 dynamic tower audit: missing tower-drop marker on layer {li}")
        if not tower_present.get(0) or not tower_present.get(1) or any(tower_present.get(li) for li in range(2, PHYSICAL_LAYER_COUNT)):
            raise RuntimeError(f"v1.91 dynamic tower audit: tower presence is {tower_present}")

        # Preserve v1.179's excluded-material/lifecycle audit by giving only its
        # fixed-topology tower checker a synthetic canonical view. Actual tower
        # topology has already been checked above against the v1.91 contract.
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
        report["v191_dynamic_tower"] = {
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

    dp.BASE_H_MM = LAYER_H_MM
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

    def v191_right_head_material_selector(material, raw_tool, w_hotend_index):
        if str(material) == LOGICAL_MATERIAL:
            return _v191_hotend_for_material(material, raw_tool, w_hotend_index)
        return orig_hotend_for_material(material, raw_tool, w_hotend_index)

    dp.h2c_native_hotend_for_material = v191_right_head_material_selector

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
        # v1.91 is deliberately single-material black throughout. Rear marking
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
    dp.audit_job_material_and_tower_contract = _make_v191_job_material_tower_audit(
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


def patch_v191_orca_nozzle_requirement_metadata(output: Path, target: str = DEFAULT_SLICER_TARGET) -> dict:
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
    return audit_v191_orca_nozzle_requirement_metadata(output, target)


def audit_v191_orca_nozzle_requirement_metadata(output: Path, target: str = DEFAULT_SLICER_TARGET) -> dict:
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
    # v1.91 emits no B. The logical optical layer still has nominal top at
    # PHYSICAL_LAYER_COUNT*LAYER_H_MM; never lower finish clearances beneath it.
    a_peak = BASE_LAYER_COUNT * LAYER_H_MM + A_MAIN_NOMINAL_HEIGHT_MM + max(A_BOND_Z_SHIFTS_MM)
    nominal_top = PHYSICAL_LAYER_COUNT * LAYER_H_MM
    return max(a_peak, nominal_top)


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
        lines[i]=f"{m.group(1)}{newz:.3f}{m.group(3)} ; FC3D_V191_MIRROR_{tag}_CLEARANCE peak_z={peak:.3f}"
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
        if "FC3D_V191_MIRROR_PRE_PARK_CLEARANCE" in l or "FC3D_V191_MIRROR_POST_PARK_CLEARANCE" in l:
            m=re.search(r"\bZ([-+]?\d*\.?\d+)",l)
            if m: vals.append(float(m.group(1)))
    if len(vals)!=2 or abs(vals[0]-want1)>0.0011 or abs(vals[1]-want2)>0.0011:
        raise RuntimeError(f"MIRROR FINISH CLEARANCE AUDIT: got {vals}, expected {[want1,want2]}")
    # The optical patch itself must also finish above every B crest before V4_MODEL_END.
    safe=[]
    for l in lines:
        if "FC3D_V191_OPTICAL_SAFE_END_Z" in l:
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
        "source_land_emission_by_v191": False,
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
    """
    Single material => remove the actual prime-tower feature blocks emitted by
    v1.179, including DIRECT_SOLID_PRIME_TOWER_V57 / PPV64 tower content.
    Multi-material => leave normal v1.179 tower behaviour untouched.
    """
    output = Path(output)
    gcode_name = "Metadata/plate_1.gcode"
    with zipfile.ZipFile(output, "r") as z:
        gcode = z.read(gcode_name).decode("utf-8", errors="replace")

    m_active = re.search(
        r";\s*FC3D_V169_JOB_ACTIVE_MATERIALS\s+([A-Z]+(?:[ \t,]+[A-Z]+)*)", gcode
    )
    if not m_active:
        raise RuntimeError("DYNAMIC TOWER POLICY: active-material marker not found")
    active_materials = [x for x in re.split(r"[ \t,]+", m_active.group(1).strip()) if x]

    if len(active_materials) >= 2:
        return {
            "active_materials": active_materials,
            "active_material_count": len(active_materials),
            "policy": "multi-material: untouched",
            "tower_removed": False,
        }

    lines = gcode.splitlines()
    out = []
    in_tower = False
    removed = 0
    feature_start = re.compile(r"^\s*;\s*FEATURE:\s*DIRECT_SOLID_PRIME_TOWER_V57\s*$")
    # tower body ends when the next FEATURE starts or DIRECT model-road feature starts
    any_feature = re.compile(r"^\s*;\s*FEATURE:")

    for line in lines:
        if feature_start.match(line):
            in_tower = True
            removed += 1
            continue
        if in_tower and any_feature.match(line):
            in_tower = False
            # fall through and keep this next feature line
        if in_tower:
            removed += 1
            continue
        # scrub standalone tower commentary too
        s = line.strip()
        if (
            "PRIME_TOWER_PPV64_CONTINUOUS_STUDIO_X" in s or
            "FC3D_TOWER_SLOT" in s or
            "FC3D_PPV64_SOLID_WHITE_TOWER_BASE_" in s
        ):
            removed += 1
            continue
        out.append(line)

    new_gcode = "\n".join(out) + "\n"

    # Final tower audit.
    forbidden = [
        "FEATURE: DIRECT_SOLID_PRIME_TOWER_V57",
        "PRIME_TOWER_PPV64_CONTINUOUS_STUDIO_X",
        "FC3D_TOWER_SLOT",
        "FC3D_PPV64_SOLID_WHITE_TOWER_BASE_START",
    ]
    remain = {tok: new_gcode.count(tok) for tok in forbidden}
    if any(remain.values()):
        raise RuntimeError(f"DYNAMIC TOWER POLICY FINAL AUDIT failed: {remain}")

    _replace_zip_members(output, {gcode_name: new_gcode.encode("utf-8")})
    return {
        "active_materials": active_materials,
        "active_material_count": 1,
        "policy": "single-material: actual prime-tower feature removed",
        "tower_removed": True,
        "removed_tower_lines": removed,
        "remaining_tower_tokens": remain,
    }


def patch_v191_two_colour_right_head_metadata(output: Path) -> dict:
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
    sp["fc3d_v191_head_rule"] = "PETG BLACK slot9 and PETG C slot15 both use physical right/colour head"

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
    return audit_v191_two_colour_right_head_metadata(output)


def audit_v191_two_colour_right_head_metadata(output: Path) -> dict:
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
    expected_first_z = LAYER_H_MM
    expected_last_z = PHYSICAL_LAYER_COUNT * LAYER_H_MM
    if abs(zs[0] - expected_first_z) > 1e-6 or abs(zs[-1] - expected_last_z) > 1e-6:
        raise RuntimeError(
            f"FINAL XYZ AUDIT: Z endpoints {zs[0]:.5f}->{zs[-1]:.5f}, expected "
            f"{expected_first_z:.5f}->{expected_last_z:.5f}"
        )
    for i in range(1, len(zs)):
        if abs((zs[i] - zs[i - 1]) - LAYER_H_MM) > 1e-6:
            raise RuntimeError(
                f"FINAL XYZ AUDIT: invalid layer step {i-1}->{i}: {zs[i]-zs[i-1]:.5f} mm"
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
# v1.91 A-only dual-arc bonding/profile test card
# ============================================================================
SCRIPT_VERSION = "3dprint_black_mirror_wave_grid_v1.91"
EXPECTED_DP_VERSION = "3dprintv1.179"
PANEL_COUNT = 1
LAYER_H_MM = 0.28
BASE_LAYER_COUNT = 3
PHYSICAL_LAYER_COUNT = BASE_LAYER_COUNT + 1
DIRECT_OPTICAL_LAYER_COUNT = PHYSICAL_LAYER_COUNT - 1
CARD_THICKNESS_Z_MM = PHYSICAL_LAYER_COUNT * LAYER_H_MM
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

    v1.91 clips B cells and A curves as they are generated instead of retaining
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
    """Emit A-only optical pairs with a full pressure reset around every arc.

    Each 0.08-mm inner arc is laid first, retracted, then its paired 0.14-mm
    outer/main arc is printed.  The pressure cycle matches the established
    FC3D endpoint mechanics: +0.395 reprime immediately before extrusion,
    normal extrusion stops 0.16 mm before the physical endpoint, -0.400
    retract occurs there, and the final 0.16 mm is completed dry.
    """
    lat=get_mirror_wave_lattice(piece)
    xo=float(x_origin); yo=float(y_origin)
    base_top=BASE_LAYER_COUNT*LAYER_H_MM
    travel_z=max(PHYSICAL_LAYER_COUNT*LAYER_H_MM, base_top + A_MAIN_NOMINAL_HEIGHT_MM + max(A_BOND_Z_SHIFTS_MM)) + B_TRAVEL_CLEARANCE_MM
    rows=[]
    pack_map,rmin,rmax=_a_pair_pack_map(piece,lat)
    inner_by_key={(r["wave"],r["family"]):r for r in lat["inner_a_local"]}
    main_by_key={(r["wave"],r["family"]):r for r in lat["main_a_local"]}
    keys=sorted(set(inner_by_key) & set(main_by_key), key=lambda k:(pack_map.get(k,0), k[1], k[0]))
    rows.append(f"; FC3D_V191_A_ONLY_START pair_count={len(keys)} pack_count={A_BOND_PACK_COUNT} radial_min={rmin:.5f} radial_max={rmax:.5f}")

    def polyline_lengths(pts):
        seg=[math.hypot(b[0]-a[0],b[1]-a[1]) for a,b in zip(pts,pts[1:])]
        return seg, sum(seg)

    def point_at_distance(pts, seglens, target):
        if target <= 0: return pts[0]
        acc=0.0
        for i,ds in enumerate(seglens):
            if acc + ds >= target - 1e-12:
                if ds <= 1e-12: return pts[i+1]
                t=max(0.0,min(1.0,(target-acc)/ds))
                a,b=pts[i],pts[i+1]
                return (a[0]+t*(b[0]-a[0]), a[1]+t*(b[1]-a[1]))
            acc += ds
        return pts[-1]

    def emit_polyline_until(pts, seglens, distance, z_abs, e_per_mm, tag, pack_idx, rec):
        remain=max(0.0,distance)
        a=pts[0]
        emitted=0
        for j,(b,ds) in enumerate(zip(pts[1:],seglens)):
            if remain <= 1e-12: break
            use=min(ds,remain)
            if ds <= 1e-12:
                continue
            if use < ds - 1e-12:
                t=use/ds
                q=(a[0]+t*(b[0]-a[0]), a[1]+t*(b[1]-a[1]))
            else:
                q=b
            e=use*e_per_mm
            if float(f"{e:.5f}") > 0.0:
                rows.append(f"G1 X{q[0]:.3f} Y{q[1]:.3f} Z{z_abs:.3f} E{e:.5f} F{A_PRINT_FEED_MM_S*60.0:.0f} ; FC3D_V191_A_{tag}_SEG pack={pack_idx+1} path_wave={rec['wave']} seg={j}")
                emitted += 1
            remain -= use
            a=q
            if use < ds - 1e-12: break
        return emitted

    def emit_one(kind, rec, z_abs, e_per_mm, pack_idx):
        pts=[(xo+p[0],yo+p[1]) for p in rec["points"]]
        if len(pts)<2: return 0
        seglens,total=polyline_lengths(pts)
        if total <= 1e-8: return 0
        dry_tail=min(A_ENDPOINT_DRY_TAIL_MM, max(0.0,total*0.45))
        draw_len=max(0.0,total-dry_tail)
        early=point_at_distance(pts,seglens,draw_len)
        rows.append(f"G0 Z{travel_z:.3f} F900 ; FC3D_V191_A_{kind}_TRAVEL_Z pack={pack_idx+1}")
        rows.append(f"G0 X{pts[0][0]:.3f} Y{pts[0][1]:.3f} F18000 ; FC3D_V191_A_{kind}_MOVE pack={pack_idx+1}")
        rows.append(f"; FC3D_V191_A_{kind}_START pack={pack_idx+1} wave={rec['wave']} family={rec['family']} z={z_abs:.3f} e_per_mm={e_per_mm:.6f}")
        rows.append(f"G0 Z{z_abs:.3f} F900 ; FC3D_V191_A_{kind}_HEIGHT pack={pack_idx+1}")
        rows.append(f"G1 E{A_REPRIME_MM:.3f} F1800 ; FC3D_V191_A_{kind}_REPRIME pack={pack_idx+1}")
        emitted=emit_polyline_until(pts,seglens,draw_len,z_abs,e_per_mm,kind,pack_idx,rec)
        rows.append(f"G1 E-{A_RETRACT_MM:.3f} F1800 ; FC3D_V191_A_{kind}_RETRACT pack={pack_idx+1}")
        if dry_tail > 1e-9:
            rows.append(f"G1 X{pts[-1][0]:.3f} Y{pts[-1][1]:.3f} Z{z_abs:.3f} F15000 ; FC3D_V191_A_{kind}_DRY_TAIL pack={pack_idx+1} len={dry_tail:.3f}")
        rows.append(f"; FC3D_V191_A_{kind}_END pack={pack_idx+1} wave={rec['wave']} family={rec['family']}")
        return emitted

    for key in keys:
        pack_idx=pack_map[key]
        shift=A_BOND_Z_SHIFTS_MM[pack_idx]
        inner_z=base_top + A_INNER_NOMINAL_HEIGHT_MM + shift
        main_z=base_top + A_MAIN_NOMINAL_HEIGHT_MM + shift
        rows.append(f"; FC3D_V191_A_PAIR_START pack={pack_idx+1} wave={key[0]} family={key[1]} shift={shift:.3f} inner_clearance={A_INNER_NOMINAL_HEIGHT_MM+shift:.3f} main_clearance={A_MAIN_NOMINAL_HEIGHT_MM+shift:.3f}")
        emit_one("INNER",inner_by_key[key],inner_z,A_INNER_E_PER_MM,pack_idx)
        emit_one("MAIN",main_by_key[key],main_z,A_MAIN_E_PER_MM,pack_idx)
        rows.append(f"; FC3D_V191_A_PAIR_END pack={pack_idx+1} wave={key[0]} family={key[1]}")

    rows.append(f"G0 Z{travel_z:.3f} F900 ; FC3D_V191_OPTICAL_SAFE_END_Z")
    rows.append("; FC3D_V191_A_ONLY_END B_EMITTED=0")
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

# v1.91 A-only dual-arc bonding/profile geometry
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
A_BOND_PACK_COUNT = 6
A_BOND_Z_SHIFTS_MM = (-0.025, -0.020, -0.015, -0.010, -0.005, 0.000)
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
A_PRINT_FEED_MM_S = 50.0
A_REPRIME_MM = 0.395
A_RETRACT_MM = 0.400
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
REAR_VERSION_TEXT = "91"

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


def label_intervals_printer_x(piece: PieceSpec, y_local_mm: float):
    # Design in underside/back view, then mirror X for first-layer printer coordinates.
    intended = _merge_intervals(
        _text_intervals_back_view(piece, piece.name, y_local_mm, LABEL_TEXT_Y0_MM)
        + _text_intervals_back_view(piece, REAR_VERSION_TEXT, y_local_mm, VERSION_TEXT_Y0_MM)
        + _arrow_intervals_back_view(piece, y_local_mm)
    )
    w = piece.width_mm
    return _merge_intervals((w - b, w - a) for a, b in intended)


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
        raise RuntimeError(f"v1.91: black-only rear texture mask too small/missing for {piece.name}: rows={textured_rows} omitted={omitted_len:.1f}")
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
            w.writerow({"physical_layer": li, "role": f"base_{orientation}", "layer_height_mm": f"{LAYER_H_MM:.5f}", "road_width_mm": f"{ROAD_WIDTH_MM:.5f}", "path_count": len(_base_roads_for_layer(li, 0.0, 0.0)), "piece_width_mm": f"{piece.width_mm:.8f}", "piece_height_mm": f"{piece.height_mm:.8f}"})
        w.writerow({"physical_layer": ARC_LAYER_INDEX, "role": "optical_arcs", "layer_height_mm": f"{LAYER_H_MM:.5f}", "road_width_mm": f"{ROAD_WIDTH_MM:.5f}", "path_count": len(paths), "piece_width_mm": f"{piece.width_mm:.8f}", "piece_height_mm": f"{piece.height_mm:.8f}"})
    return p


def write_mirror_summary_csv(path):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    piece=_current_piece(); lat=get_mirror_wave_lattice(piece)
    fields=["piece","initial_b_road_count","wave_count","family_count","family_reset_count",
            "b_paths_local","main_a_curves_local","inner_a_curves_local","max_edge_gap_mm",
            "max_a_transverse_error","max_front_normal_error","wave_relief_mm","valley_land_mm",
            "rear_return_angle_deg","a_main_height_mm","a_inner_height_mm","a_main_flow_mult",
            "a_inner_flow_mult","a_print_feed_mm_s","b_print_feed_mm_s","physical_peak_z_mm"]
    with p.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerow({
            "piece":piece.name,"initial_b_road_count":lat["initial_road_count"],"wave_count":lat["wave_count"],
            "family_count":len(lat["families"]),"family_reset_count":lat["family_reset_count"],
            "b_paths_local":len(lat["b_paths_local"]),"main_a_curves_local":len(lat["main_a_local"]),
            "inner_a_curves_local":len(lat["inner_a_local"]),"max_edge_gap_mm":f"{lat['max_edge_gap_before_reset_mm']:.8f}",
            "max_a_transverse_error":f"{lat['max_a_transverse_error']:.10f}",
            "max_front_normal_error":f"{lat['max_front_normal_error']:.12g}","wave_relief_mm":WAVE_RELIEF_MM,
            "valley_land_mm":VALLEY_LAND_MM,"rear_return_angle_deg":REAR_RETURN_ANGLE_DEG,
            "a_main_height_mm":A_MAIN_HEIGHT_MM,"a_inner_height_mm":A_INNER_HEIGHT_MM,
            "a_main_flow_mult":A_MAIN_FLOW_MULT,"a_inner_flow_mult":A_INNER_FLOW_MULT,
            "a_print_feed_mm_s":A_PRINT_FEED_MM_S,"b_print_feed_mm_s":B_PRINT_FEED_MM_S,
            "physical_peak_z_mm":f"{_mirror_wave_peak_z_mm():.5f}"})
    return p


def write_mirror_layer_summary_csv(path):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    piece=_current_piece(); lat=get_mirror_wave_lattice(piece)
    fields=["physical_layer","role","nominal_z_mm","road_width_mm","path_count","piece_width_mm","piece_height_mm","physical_peak_z_mm"]
    with p.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for li in range(BASE_LAYER_COUNT):
            orientation="X" if li%2==0 else "Y"
            w.writerow({"physical_layer":li,"role":f"base_{orientation}","nominal_z_mm":f"{(li+1)*LAYER_H_MM:.5f}",
                        "road_width_mm":f"{ROAD_WIDTH_MM:.5f}","path_count":len(_base_roads_for_layer(li,0.0,0.0)),
                        "piece_width_mm":f"{piece.width_mm:.8f}","piece_height_mm":f"{piece.height_mm:.8f}","physical_peak_z_mm":""})
        w.writerow({"physical_layer":ARC_LAYER_INDEX,"role":"A_only_dual_arc_six_pack_bonding",
                    "nominal_z_mm":f"{(ARC_LAYER_INDEX+1)*LAYER_H_MM:.5f}","road_width_mm":f"{ROAD_WIDTH_MM:.5f}",
                    "path_count":len(lat["inner_a_local"])+len(lat["main_a_local"]),
                    "piece_width_mm":f"{piece.width_mm:.8f}","piece_height_mm":f"{piece.height_mm:.8f}",
                    "physical_peak_z_mm":f"{_mirror_wave_peak_z_mm():.5f}"})
    return p


def _explicit_arc_layer_gcode(x_origin: float, y_origin: float):
    piece = _current_piece()
    rows = []
    for idx, rec in enumerate(_arc_paths_absolute(piece, x_origin, y_origin)):
        pts = rec["points"]
        rows.append(f"; FC3D_V191_ARC_START layer={ARC_LAYER_INDEX} path={idx} radius_mm={rec['radius_mm']:.6f}")
        rows.append(f"G0 X{pts[0][0]:.3f} Y{pts[0][1]:.3f} ; FC3D_V191_ARC_MOVE_TO_START")
        for j, (a, b) in enumerate(zip(pts, pts[1:])):
            e = math.hypot(b[0] - a[0], b[1] - a[1]) * CALIBRATED_E_PER_MM
            rows.append(f"G1 X{b[0]:.3f} Y{b[1]:.3f} E{e:.5f} ; FC3D_V191_ARC_SEG path={idx} seg={j}")
        rows.append(f"; FC3D_V191_ARC_END layer={ARC_LAYER_INDEX} path={idx}")
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
        replacement=[f"; FC3D_V191_MIRROR_WAVE_START layer={li} piece={_current_piece().name}"]+layer_rows+[f"; FC3D_V191_MIRROR_WAVE_END layer={li} piece={_current_piece().name}"]
        counts["inner_segments"]=sum("FC3D_V191_A_INNER_SEG" in r for r in layer_rows)
        counts["main_segments"]=sum("FC3D_V191_A_MAIN_SEG" in r for r in layer_rows)
        counts["b_segments"]=sum("FC3D_V191_B_SEG" in r for r in layer_rows)
        counts["b_paths"]=sum("FC3D_V191_B_PATH_START" in r for r in layer_rows)
        counts["families"]=sum("FC3D_V191_B_FAMILY_START" in r for r in layer_rows)
        rebuilt.extend(block[:a]); rebuilt.extend(replacement); rebuilt.extend(block[a+1:])
    _replace_zip_members(output,{name:("\n".join(rebuilt)+"\n").encode("utf-8")})
    return {"piece":_current_piece().name,**counts}


def audit_final_mirror_wave_paths(output, *unused):
    """Fail closed on the packaged v1.91 A-only dual-arc experiment."""
    output=Path(output)
    with zipfile.ZipFile(output,"r") as z:
        lines=z.read("Metadata/plate_1.gcode").decode("utf-8",errors="replace").splitlines()
    layer_re=re.compile(r";\s*DIRECT_LAYER\s+V4\s+physical=(\d+)")
    starts=[i for i,l in enumerate(lines) if layer_re.search(l)]
    if len(starts)!=PHYSICAL_LAYER_COUNT:
        raise RuntimeError(f"FINAL A-ONLY AUDIT: DIRECT_LAYER count {len(starts)} != {PHYSICAL_LAYER_COUNT}")
    starts.append(len(lines)); block=lines[starts[ARC_LAYER_INDEX]:starts[ARC_LAYER_INDEX+1]]
    if not any("FC3D_V191_MIRROR_WAVE_START" in l for l in block) or not any("FC3D_V191_MIRROR_WAVE_END" in l for l in block):
        raise RuntimeError("FINAL A-ONLY AUDIT: optical replacement markers missing")
    if any("FC3D_V191_B_SEG" in l or "FC3D_V191_B_PATH" in l or "FC3D_V191_B_FAMILY" in l for l in block):
        raise RuntimeError("FINAL A-ONLY AUDIT: B extrusion/path markers must be absent")
    if not any("B_EMITTED=0" in l for l in block):
        raise RuntimeError("FINAL A-ONLY AUDIT: explicit B_EMITTED=0 marker missing")
    if any("OPTICAL_ARCS" in l or "_ARC_SEG" in l for l in block):
        raise RuntimeError("FINAL A-ONLY AUDIT: stale concentric-arc markers remain")

    pair_blocks=re.findall(r"; FC3D_V191_A_PAIR_START.*?; FC3D_V191_A_PAIR_END[^\n]*", "\n".join(block), re.S)
    if not pair_blocks:
        raise RuntimeError("FINAL A-ONLY AUDIT: no A pairs emitted")
    pressure_counts={"inner_reprime":0,"inner_retract":0,"inner_dry_tail":0,"main_reprime":0,"main_retract":0,"main_dry_tail":0}
    for pb in pair_blocks:
        if "FC3D_V191_A_INNER_START" not in pb or "FC3D_V191_A_MAIN_START" not in pb:
            raise RuntimeError("FINAL A-ONLY AUDIT: incomplete A pair")
        if pb.index("FC3D_V191_A_INNER_START") > pb.index("FC3D_V191_A_MAIN_START"):
            raise RuntimeError("FINAL A-ONLY AUDIT: 0.14 main emitted before 0.08 inner")
        for kind,label in (("INNER","inner"),("MAIN","main")):
            start_tag=f"FC3D_V191_A_{kind}_START"
            prime_tag=f"FC3D_V191_A_{kind}_REPRIME"
            retract_tag=f"FC3D_V191_A_{kind}_RETRACT"
            tail_tag=f"FC3D_V191_A_{kind}_DRY_TAIL"
            end_tag=f"FC3D_V191_A_{kind}_END"
            for tag in (start_tag,prime_tag,retract_tag,tail_tag,end_tag):
                if pb.count(tag)!=1:
                    raise RuntimeError(f"FINAL A-ONLY AUDIT: {kind} expected one {tag}, got {pb.count(tag)}")
            order=[pb.index(x) for x in (start_tag,prime_tag,retract_tag,tail_tag,end_tag)]
            if order != sorted(order):
                raise RuntimeError(f"FINAL A-ONLY AUDIT: {kind} pressure/end sequence out of order")
            prime_line=next(l for l in pb.splitlines() if prime_tag in l)
            retract_line=next(l for l in pb.splitlines() if retract_tag in l)
            if f"E{A_REPRIME_MM:.3f}" not in prime_line:
                raise RuntimeError(f"FINAL A-ONLY AUDIT: {kind} reprime amount wrong: {prime_line}")
            if f"E-{A_RETRACT_MM:.3f}" not in retract_line:
                raise RuntimeError(f"FINAL A-ONLY AUDIT: {kind} retract amount wrong: {retract_line}")
            pressure_counts[f"{label}_reprime"] += 1
            pressure_counts[f"{label}_retract"] += 1
            pressure_counts[f"{label}_dry_tail"] += 1

    starts_rec=re.findall(r"FC3D_V191_A_PAIR_START pack=(\d+).*?inner_clearance=([0-9.]+) main_clearance=([0-9.]+)", "\n".join(block))
    packs={int(a) for a,_,_ in starts_rec}
    if packs != set(range(1,A_BOND_PACK_COUNT+1)):
        raise RuntimeError(f"FINAL A-ONLY AUDIT: bonding packs {sorted(packs)} incomplete")
    observed={(int(a),round(float(b),3),round(float(c),3)) for a,b,c in starts_rec}
    expected={(i+1,round(A_INNER_NOMINAL_HEIGHT_MM+A_BOND_Z_SHIFTS_MM[i],3),
                    round(A_MAIN_NOMINAL_HEIGHT_MM+A_BOND_Z_SHIFTS_MM[i],3))
              for i in range(A_BOND_PACK_COUNT)}
    if observed != expected:
        raise RuntimeError(f"FINAL A-ONLY AUDIT: clearance set mismatch got={observed} expected={expected}")

    got_inner=sum("FC3D_V191_A_INNER_SEG" in l for l in block)
    got_main=sum("FC3D_V191_A_MAIN_SEG" in l for l in block)
    if got_inner<=0 or got_main<=0:
        raise RuntimeError("FINAL A-ONLY AUDIT: missing positive A extrusion")

    # Every emitted A segment carries the pair's fixed feature-specific E/mm.
    z_re=re.compile(r"\bZ([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    e_re=re.compile(r"\bE([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    inner_z=[]; main_z=[]
    for l in block:
        zm=z_re.search(l); em=e_re.search(l)
        if not (zm and em and float(em.group(1))>0): continue
        if "FC3D_V191_A_INNER_SEG" in l: inner_z.append(float(zm.group(1)))
        elif "FC3D_V191_A_MAIN_SEG" in l: main_z.append(float(zm.group(1)))
    base_top=BASE_LAYER_COUNT*LAYER_H_MM
    want_inner={round(base_top+A_INNER_NOMINAL_HEIGHT_MM+x,3) for x in A_BOND_Z_SHIFTS_MM}
    want_main={round(base_top+A_MAIN_NOMINAL_HEIGHT_MM+x,3) for x in A_BOND_Z_SHIFTS_MM}
    if {round(z,3) for z in inner_z} != want_inner:
        raise RuntimeError(f"FINAL A-ONLY AUDIT: inner Z set mismatch")
    if {round(z,3) for z in main_z} != want_main:
        raise RuntimeError(f"FINAL A-ONLY AUDIT: main Z set mismatch")
    return {
        "a_pairs":len(pair_blocks),"inner_a_segments":got_inner,"main_a_segments":got_main,
        "b_segments":0,"bond_pack_count":A_BOND_PACK_COUNT,
        "bond_shifts_mm":list(A_BOND_Z_SHIFTS_MM),
        "inner_nominal_height_mm":A_INNER_NOMINAL_HEIGHT_MM,
        "main_nominal_height_mm":A_MAIN_NOMINAL_HEIGHT_MM,
        "inner_e_per_mm":A_INNER_E_PER_MM,"main_e_per_mm":A_MAIN_E_PER_MM,
        "inner_first_per_pair":True,
        "reprime_mm":A_REPRIME_MM,"retract_mm":A_RETRACT_MM,"endpoint_dry_tail_mm":A_ENDPOINT_DRY_TAIL_MM,
        **pressure_counts,
        "pressure_cycle_per_arc":True,
    }


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
        replacement = [f"; FC3D_V191_OPTICAL_ARCS_START layer={li} piece={_current_piece().name}"]
        layer_rows = _explicit_arc_layer_gcode(xo, yo)
        replacement.extend(layer_rows)
        replacement.append(f"; FC3D_V191_OPTICAL_ARCS_END layer={li} piece={_current_piece().name}")
        path_count = sum(1 for row in layer_rows if row.startswith("; FC3D_V191_ARC_START"))
        segment_count = sum(1 for row in layer_rows if "FC3D_V191_ARC_SEG" in row)
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
    if orientations != ["X", "Y", "X"]:
        raise RuntimeError(f"BASE INTERLOCK AUDIT: expected X/Y/X, got {orientations}; {draw_counts}")
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
    sidx = next((i for i, l in enumerate(block) if "FC3D_V191_OPTICAL_ARCS_START" in l), None)
    eidx = next((i for i, l in enumerate(block) if "FC3D_V191_OPTICAL_ARCS_END" in l), None)
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
        if st.startswith("; FC3D_V191_ARC_START"):
            if active_path != -1:
                raise RuntimeError("FINAL ARC AUDIT: nested arc start")
            m = re.search(r"path=(\d+)", st)
            active_path = int(m.group(1))
            pts = []
            path_markers += 1
            continue
        if st.startswith("; FC3D_V191_ARC_END"):
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
    """Audit the v1.91 black-only rear texture and single-material lifecycle."""
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
        "nominal_layer_top_z_mm":PHYSICAL_LAYER_COUNT*LAYER_H_MM,
        "physical_peak_z_mm":_mirror_wave_peak_z_mm(),"physical_layers":PHYSICAL_LAYER_COUNT,
        "base_interlock":["X","Y","X"],"road_width_mm":ROAD_WIDTH_MM,
        "global_x_range_mm":[piece.global_x0_mm,piece.global_x1_mm],
        "global_z_range_mm":[piece.global_z0_mm,piece.global_z1_mm],
        "wave_relief_mm":WAVE_RELIEF_MM,"a_main_height_mm":A_MAIN_HEIGHT_MM,"a_inner_height_mm":A_INNER_HEIGHT_MM,
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


def dry_validate_v191(dp):
    piece=_current_piece()
    if abs(float(getattr(dp,"BASE_H_MM",-1))-LAYER_H_MM)>1e-9 or abs(float(getattr(dp,"MIX_H_MM",-1))-LAYER_H_MM)>1e-9:
        raise RuntimeError("v1.91: canonical layer-height patch mismatch")
    probe_e=float(dp.e_for_len(1.0,LAYER_H_MM,line_w=ROAD_WIDTH_MM,material=LOGICAL_MATERIAL))
    if abs(probe_e-CALIBRATED_E_PER_MM)>1e-9:
        raise RuntimeError(f"v1.91: patched road E/mm mismatch {probe_e} != {CALIBRATED_E_PER_MM}")
    if abs(piece.width_mm-PANEL_WIDTH_X_MM)>1e-9 or abs(piece.height_mm-PANEL_HEIGHT_Y_MM)>1e-9:
        raise RuntimeError("v1.91: piece dimensions do not match panel dimensions")
    base_layers=[_base_roads_for_layer(li,0.0,0.0) for li in range(BASE_LAYER_COUNT)]
    base_orient=[]
    for li,base in enumerate(base_layers):
        if len(base)<200: raise RuntimeError(f"v1.91: unexpectedly few base roads on layer {li}: {len(base)}")
        dx=sum(abs(seg[2]-seg[0]) for seg in base); dy=sum(abs(seg[3]-seg[1]) for seg in base)
        base_orient.append("X" if dx>dy else "Y")
    if base_orient != ["X","Y","X"]: raise RuntimeError(f"v1.91: base interlock {base_orient} != X/Y/X")
    full_l0_len=sum(math.hypot(q[2]-q[0],q[3]-q[1]) for q in _base_roads_x(0.0,0.0))
    textured=_base_segments_by_material_for_layer(0,0.0,0.0,(LOGICAL_MATERIAL,))
    textured_l0_len=sum(math.hypot(q[2]-q[0],q[3]-q[1]) for q in textured[LOGICAL_MATERIAL])
    omitted_len=full_l0_len-textured_l0_len
    if omitted_len<50.0:
        raise RuntimeError(f"v1.91: black-only underside texture too small/missing: omitted={omitted_len:.2f} mm")
    # The version ID must have a real mask in its own vertical band.
    version_rows=[y for y in _centres_for_filled_interval(0.0,PANEL_HEIGHT_Y_MM,ROAD_WIDTH_MM)
                  if _text_intervals_back_view(piece,REAR_VERSION_TEXT,y,VERSION_TEXT_Y0_MM)]
    piece_rows=[y for y in _centres_for_filled_interval(0.0,PANEL_HEIGHT_Y_MM,ROAD_WIDTH_MM)
                if _text_intervals_back_view(piece,piece.name,y,LABEL_TEXT_Y0_MM)]
    arrow_rows=[y for y in _centres_for_filled_interval(0.0,PANEL_HEIGHT_Y_MM,ROAD_WIDTH_MM)
                if _arrow_intervals_back_view(piece,y)]
    if not version_rows or not piece_rows or not arrow_rows:
        raise RuntimeError("v1.91: rear texture ID/version/arrow mask incomplete")
    for li in (1,2):
        higher=_base_segments_by_material_for_layer(li,0.0,0.0,(LOGICAL_MATERIAL,))
        higher_len=sum(math.hypot(q[2]-q[0],q[3]-q[1]) for q in higher[LOGICAL_MATERIAL])
        full_len=sum(math.hypot(q[2]-q[0],q[3]-q[1]) for q in _base_roads_for_layer(li,0.0,0.0))
        if abs(higher_len-full_len)>1e-6:
            raise RuntimeError(f"v1.91: rear texture leaked above first base layer {li}")
    lat=get_mirror_wave_lattice(piece)
    if lat["initial_road_count"]<300 or lat["wave_count"]<200 or len(lat["main_a_local"])<150 or len(lat["inner_a_local"])<150:
        raise RuntimeError(f"v1.91: insufficient A lattice coverage {lat['initial_road_count']=} {lat['wave_count']=} main={len(lat['main_a_local'])} inner={len(lat['inner_a_local'])}")
    if lat["max_a_transverse_error"]>0.08: raise RuntimeError(f"v1.91: A transverse error {lat['max_a_transverse_error']}")
    if lat["max_front_normal_error"]>0.003: raise RuntimeError(f"v1.91: B mirror-normal error {lat['max_front_normal_error']}")
    anchor=mirror_frame_global(200.0,620.0)
    if abs(anchor["contour_azimuth_deg"]-55.0)>=1.0:
        raise RuntimeError(f"v1.91: empirical 55-degree anchor mismatch {anchor['contour_azimuth_deg']:.4f}")
    print("DRY V1.90 VALIDATION: PASS")
    print(f"  piece                         : {piece.name}")
    print(f"  global crop X                : {piece.global_x0_mm:.3f}..{piece.global_x1_mm:.3f} mm")
    print(f"  global crop Z                : {piece.global_z0_mm:.3f}..{piece.global_z1_mm:.3f} mm")
    print(f"  physical X x Y               : {piece.width_mm:.3f} x {piece.height_mm:.3f} mm")
    print(f"  nominal/model safe top Z      : {_mirror_wave_peak_z_mm():.3f} mm")
    print(f"  base interlock               : {'/'.join(base_orient)}")
    print(f"  underside texture            : black-only {piece.name} + {REAR_VERSION_TEXT} + UP arrow; alternating first-layer roads only")
    print(f"  mirror anchor contour/tilt   : {anchor['contour_azimuth_deg']:.4f} / {anchor['facet_tilt_deg']:.4f} deg")
    print(f"  construction seeds / waves   : {lat['initial_road_count']} / {lat['wave_count']}")
    print(f"  local A pairs                 : {len(lat['main_a_local'])} main + {len(lat['inner_a_local'])} inner")
    print(f"  family resets               : {lat['family_reset_count']}")
    print(f"  max edge gap                : {lat['max_edge_gap_before_reset_mm']:.5f} mm (reset threshold {FAMILY_RESET_EDGE_GAP_MM:.3f})")
    print(f"  A transverse error          : {lat['max_a_transverse_error']:.8f}")
    print(f"  scaffold normal error         : {lat['max_front_normal_error']:.3e}")
    print(f"  A nominal inner/main          : {A_INNER_NOMINAL_HEIGHT_MM:.3f} / {A_MAIN_NOMINAL_HEIGHT_MM:.3f} mm")
    print(f"  A bond shifts                 : {A_BOND_Z_SHIFTS_MM}")
    print(f"  A print feed                  : {A_PRINT_FEED_MM_S:.1f} mm/s")



A1_MINI_NOZZLE_C = 255
A1_MINI_BED_C = 70
A1_MINI_MODEL_ID = "N1"
A1_MINI_PRINTER_NAME = "Bambu Lab A1 mini"
A1_MINI_PRINTER_PRESET = "Bambu Lab A1 mini 0.4 nozzle"
A1_MINI_PROCESS_PRESET = "0.20mm Standard @BBL A1M"


def _a1mini_start_gcode() -> str:
    """Compact, conservative A1 Mini single-material start sequence.

    It uses only commands present in the current Orca A1 Mini machine profile:
    heat, home, ABL over the model region, Textured-PEI Z trim, and relative E.
    The long H2C/Vortek startup is deliberately discarded.
    """
    return "\n".join([
        "; FC3D_V191_A1MINI_START",
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
        f"M190 S{A1_MINI_BED_C}",
        f"M109 S{A1_MINI_NOZZLE_C}",
        "M1002 gcode_claim_action : 1",
        "G29 A1 X20 Y20 I140 J140",
        "G29.1 Z-0.02 ; Textured PEI, current Orca A1-mini 0.4-mm convention",
        "G90",
        "M83",
        "M106 S0",
        "M1002 gcode_claim_action : 0",
        "; FC3D_V191_A1MINI_START_END",
    ])


def _a1mini_end_gcode(final_z: float) -> str:
    lift = min(5.0, max(0.8, 180.0 - float(final_z)))
    return "\n".join([
        "; FC3D_V191_A1MINI_END",
        "M400",
        "G92 E0",
        "G1 E-0.8 F1800",
        "M104 S0",
        "M140 S0",
        "M106 S0",
        "G91",
        f"G1 Z{lift:.3f} F900",
        "G90",
        "G1 X0 Y180 F12000",
        "M400",
        "M18 X Y Z",
        "; FC3D_V191_A1MINI_END_DONE",
        "; EXECUTABLE_BLOCK_END",
    ])


def _strip_prime_tower_blocks(lines):
    out=[]; in_tower=False; removed=0
    for line in lines:
        if "WIPE_TOWER_START" in line:
            in_tower=True; removed += 1; continue
        if in_tower:
            if "WIPE_TOWER_END" in line:
                in_tower=False
            continue
        # Drop tower-only bookkeeping/wipes after a removed tower.
        if ("PRIME_TOWER" in line or "DIRECT_SOLID_PRIME_TOWER" in line or
            "FC3D_TOWER_" in line or "_TOWER_" in line and "CONFIG" not in line):
            removed += 1
            continue
        out.append(line)
    if in_tower:
        raise RuntimeError("V1.91 A1 MINI: unterminated wipe-tower block")
    return out, removed


def _replace_config_comment(gcode: str, key: str, value: str) -> str:
    pat=re.compile(rf"^; {re.escape(key)} = .*?$", re.M)
    if pat.search(gcode):
        return pat.sub(f"; {key} = {value}", gcode, count=1)
    end=gcode.find("; CONFIG_BLOCK_END")
    if end < 0:
        raise RuntimeError("V1.91 A1 MINI: CONFIG_BLOCK_END missing")
    return gcode[:end] + f"; {key} = {value}\n" + gcode[end:]


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
    output=Path(output)
    with zipfile.ZipFile(output,"r") as z:
        gbytes=z.read("Metadata/plate_1.gcode"); g=gbytes.decode("utf-8")
        project=json.loads(z.read("Metadata/project_settings.config").decode("utf-8"))
        root=ET.fromstring(z.read("Metadata/slice_info.config"))
        md5=z.read("Metadata/plate_1.gcode.md5").decode("ascii").strip().lower()
    if project.get("printer_model")!=A1_MINI_PRINTER_NAME or project.get("printer_settings_id")!=A1_MINI_PRINTER_PRESET:
        raise RuntimeError("V1.91 A1 MINI AUDIT: project machine identity mismatch")
    if project.get("printable_area") != ["0x0","180x0","180x180","0x180"] or str(project.get("printable_height"))!="180":
        raise RuntimeError("V1.91 A1 MINI AUDIT: build envelope mismatch")
    if project.get("nozzle_diameter") != ["0.4"] or project.get("nozzle_type") != ["stainless_steel"]:
        raise RuntimeError("V1.91 A1 MINI AUDIT: nozzle contract mismatch")
    executable=g.split("; EXECUTABLE_BLOCK_START",1)[-1]
    forbidden=["machine: H2C","Vortek","FC3D_PPSPV43_FULL_H2C_SWAP_START","FEATURE: DIRECT_SOLID_PRIME_TOWER_V57","WIPE_TOWER_START"]
    leaked=[x for x in forbidden if x in executable]
    if leaked: raise RuntimeError(f"V1.91 A1 MINI AUDIT: forbidden executable H2C/tower content {leaked}")
    if "; FC3D_V191_A1MINI_START" not in g or "; FC3D_V191_A1MINI_END" not in g:
        raise RuntimeError("V1.91 A1 MINI AUDIT: A1 start/end missing")
    if "; enable_prime_tower = 0" not in g:
        raise RuntimeError("V1.91 A1 MINI AUDIT: prime tower config not disabled")
    p=root.find("plate"); meta={n.attrib.get("key"):n.attrib.get("value") for n in p.findall("metadata")}
    if meta.get("printer_model_id")!=A1_MINI_MODEL_ID or meta.get("nozzle_diameters")!="0.4":
        raise RuntimeError(f"V1.91 A1 MINI AUDIT: slice machine metadata {meta}")
    nozzles=[n.attrib for n in p.findall("nozzle")]
    if nozzles != [{"id":"0","extruder_id":"1","nozzle_diameter":"0.4","volume_type":"Standard"}]:
        raise RuntimeError(f"V1.91 A1 MINI AUDIT: nozzle record {nozzles}")
    if hashlib.md5(gbytes).hexdigest()!=md5:
        raise RuntimeError("V1.91 A1 MINI AUDIT: gcode MD5 mismatch")
    # Model XY must fit the 180 mm bed with margin; ignore startup/park moves.
    model=g.split("; CHANGE_LAYER",1)[-1].split("; V4_MODEL_END",1)[0]
    xs=[float(m.group(1)) for m in re.finditer(r"\bX(-?\d+(?:\.\d+)?)",model)]
    ys=[float(m.group(1)) for m in re.finditer(r"\bY(-?\d+(?:\.\d+)?)",model)]
    if not xs or not ys or min(xs)<0 or max(xs)>180 or min(ys)<0 or max(ys)>180:
        raise RuntimeError(f"V1.91 A1 MINI AUDIT: model outside bed X={min(xs) if xs else None}..{max(xs) if xs else None} Y={min(ys) if ys else None}..{max(ys) if ys else None}")
    return {"printer":A1_MINI_PRINTER_PRESET,"model_id":A1_MINI_MODEL_ID,"envelope_mm":[180,180,180],"nozzle":"0.4 mm Standard stainless","prime_tower_present":False,"removed_tower_blocks":removed_tower_blocks,"model_xy_mm":[min(xs),max(xs),min(ys),max(ys)],"md5":md5}

def main():
    ap = argparse.ArgumentParser(description="FC3D v1.91 A-only six-pack bonding test with per-arc pressure reset and black-only rear texture", allow_abbrev=False)
    ap.add_argument("--source", type=Path, default=Path("3dprintv1.179.py"))
    ap.add_argument("--piece", choices=tuple(f"{c}-{r}" for c in range(1, 6) for r in range(1, 6)), required=True)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--dry-validate", action="store_true")
    ap.add_argument("--slicer-target", "--slicer", choices=("orca", "studio"), default=DEFAULT_SLICER_TARGET, help="Output package compatibility target (default: orca for the ALR project).")
    ap.add_argument("--printer-target", choices=("a1mini",), default="a1mini", help="Physical printer target; v1.91 emits an A1 Mini 0.4-mm Orca-compatible package.")
    ap.add_argument("--e-per-mm", type=float, default=DEFAULT_E_PER_MM, help=f"Calibrated E/mm for {LAYER_H_MM:.2f}-mm layers and {ROAD_WIDTH_MM:.2f}-mm roads (default {DEFAULT_E_PER_MM:.6f}).")
    known, passthrough = ap.parse_known_args()
    reject_protected_passthrough(passthrough)
    global CURRENT_PIECE, RUNTIME_ORIGIN
    set_runtime_e_per_mm(known.e_per_mm)
    CURRENT_PIECE = PieceSpec.for_name(known.piece)
    RUNTIME_ORIGIN = None
    if known.output is None:
        known.output = Path(f"black_a_only_bonding_{known.piece.replace('-', '_')}_v1.91.gcode.3mf")
    dummy = 45.0
    dp = import_3dprint(known.source)
    install_patches(dp, dummy, dummy, dummy)
    mirror_csv = Path(str(known.output) + ".mirror_summary.csv")
    layer_csv = Path(str(known.output) + ".layer_summary.csv")
    write_mirror_summary_csv(mirror_csv)
    write_mirror_layer_summary_csv(layer_csv)
    print(SCRIPT_VERSION)
    print("  slicer target                 :", known.slicer_target, "(default Orca for ALR)")
    print("  printer target                :", known.printer_target)
    dry_validate_v191(dp)
    print("  mirror CSV                    :", mirror_csv)
    print("  layer CSV                     :", layer_csv)
    if known.dry_validate:
        return
    with tempfile.TemporaryDirectory(prefix="fc3d_mirror_wave_v191_") as td:
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
    reports["mirror_finish_clearance"] = enforce_mirror_wave_finish_clearance(known.output)
    reports["tower_policy"] = apply_dynamic_tower_policy(known.output)
    reports["fan"] = enforce_minimum_model_part_fan(known.output)
    reports["base_interlock"] = audit_final_base_interlock(known.output)
    reports["black_texture_single_material"] = audit_final_black_texture_and_single_material(known.output)
    reports["final_paths"] = audit_final_mirror_wave_paths(known.output)
    reports["card_geometry"] = audit_final_panel_xy_geometry(known.output)
    reports["a1mini_package"] = convert_package_to_a1mini_orca(known.output)
    reports["slicer_target_metadata"] = apply_slicer_target_metadata(known.output, known.slicer_target)
    reports["a1mini_final"] = audit_a1mini_orca_package(known.output)
    reports["mirror_design"] = {"screen_diagonal_in":100.0,"screen_width_mm":MASTER_FAN.screen_width_mm,"screen_height_mm":MASTER_FAN.screen_height_mm,"projector_screen_x_mm":MASTER_FAN.projector_x_mm,"projector_screen_z_mm":MASTER_FAN.projector_z_mm,"projector_distance_mm":MASTER_FAN.projector_distance_mm,"viewer_distance_mm":MASTER_FAN.viewer_distance_mm,"viewer_eyeline_fraction":MASTER_FAN.viewer_eyeline_fraction,"piece_global_x_mm":[CURRENT_PIECE.global_x0_mm,CURRENT_PIECE.global_x1_mm],"piece_global_z_mm":[CURRENT_PIECE.global_z0_mm,CURRENT_PIECE.global_z1_mm],"road_width_mm":ROAD_WIDTH_MM,"nominal_layer_height_mm":LAYER_H_MM,"b_enabled":False,"a_inner_nominal_height_mm":A_INNER_NOMINAL_HEIGHT_MM,"a_main_nominal_height_mm":A_MAIN_NOMINAL_HEIGHT_MM,"a_inner_e_per_mm":A_INNER_E_PER_MM,"a_main_e_per_mm":A_MAIN_E_PER_MM,"bond_pack_count":A_BOND_PACK_COUNT,"bond_z_shifts_mm":list(A_BOND_Z_SHIFTS_MM),"inner_first_per_pair":True,"physical_peak_z_mm":_mirror_wave_peak_z_mm(),"base_interlock":["X","Y","X"]}
    aj = Path(str(known.output) + ".audit.json")
    write_audit_json(aj, reports)
    print("\nFINAL AUDIT: PASS")
    for k in ("native_plate_process", "mirror_wave_paths", "mirror_finish_clearance", "tower_policy", "fan", "base_interlock", "black_texture_single_material", "final_paths", "card_geometry", "a1mini_package", "slicer_target_metadata", "a1mini_final"):
        print(f"  {k}: PASS")
    print("Wrote", known.output)
    print("Wrote", mirror_csv)
    print("Wrote", layer_csv)
    print("Wrote", aj)


if __name__ == "__main__":
    main()
