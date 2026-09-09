#!/usr/bin/env python3
"""FC3D v1.159: consolidated 0.4 mm ALR exporter with v1.158 behaviour.

Requires only canonical 3dprintv1.179.py (plus NumPy and Pillow). All converter
geometry, thin-cap emission, horizontal field, colour scheduling and audits
are defined here as ordinary Python. No previous converter is imported,
patched, generated or executed. Only the canonical 3dprint emitter is patched.

This revision deliberately does NOT add a 0.2 mm mode or solid-white rear text.
The first-layer alternating-line texture, 0.4 mm roads and established process
are preserved. Independent CLI runs have independent configuration state.

Provenance: original repository v158/v157/v156 chain; plumbing is the exact
copy embedded by v156, not the separately published v106 variant.
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
import csv
from dataclasses import dataclass
from typing import List, Any
import numpy as _np
from typing import Iterable
import argparse, hashlib, json, math, re, sys, tempfile, types, zipfile

@dataclass(frozen=True)
class MasterFan:
    """Global screen geometry used to orient tangent/concentric arc roads."""
    diagonal_in: float = 100.0
    projector_below_screen_mm: float = 225.0
    projector_distance_mm: float = 470.0
    viewer_distance_mm: float = 2500.0
    viewer_eyeline_fraction: float = 0.0

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

class ThinCapError(ValueError):
    pass

# Fixed machine, material and construction-scaffold constants.
A1_MINI_BED_C = 70

A1_MINI_MODEL_ID = 'N1'

A1_MINI_NOZZLE_C = 255

A1_MINI_PRINTER_NAME = 'Bambu Lab A1 mini'

A1_MINI_PRINTER_PRESET = 'Bambu Lab A1 mini 0.4 nozzle'

A1_MINI_PROCESS_PRESET = '0.20mm Standard @BBL A1M'

ARC_LAYER_INDEX = 3

ARC_PROFILE_WIDTH_MM = 0.4

ARROW_HEAD_HALF_W_BASE_MM = 8.5

ARROW_HEAD_Y0_MM = 86.5

ARROW_HEAD_Y1_MM = 102.5

ARROW_SHAFT_HALF_W_MM = 2.25

ARROW_SHAFT_Y0_MM = 75.5

ARROW_SHAFT_Y1_MM = 88.5

A_INNER_HEIGHT_MM = 0.08

A_MAIN_E_PER_MM = 0.037608

A_MAIN_HEIGHT_MM = 0.14

A_MAIN_NOMINAL_HEIGHT_MM = 0.288

A_PRINT_FEED_MM_S = 250.0

A_REPRIME_MM = 0.795

A_RETRACT_MM = 0.8

A_TRACE_STEP_MM = 0.2

BASE_LAYER_COUNT = 3

BASE_TOP_Z_MM = 0.4

BLACK_ASSIGNMENT = 'PETG:BLACK'

BLACK_HEX = '#161616'

BLACK_NAME = 'BLACK'

BLACK_RAW_TOOL = 8

BLACK_SLOT_ONE_BASED = 9

B_FRONT_MAX_STEP_MM = 0.5

B_ROAD_CENTER_PITCH_MM = 0.4

CALIBRATED_E_PER_MM = 0.01567

CAP_HEIGHT_MM = 0.165

CAP_MAX_MM = 0.28

CAP_PHYSICAL_HEIGHT_MM = 0.198

CHANGE_TO_BLACK = (';===== A1mini 20250822 =====\n'
 'G392 S0\n'
 'M1007 S0\n'
 'M620 S0A\n'
 'M204 S9000\n'
 'G1 Z3.88 F1200\n'
 '\n'
 'M400\n'
 'M106 P1 S0\n'
 'M106 P2 S0\n'
 'M104 S255\n'
 '\n'
 'G1 X180 F18000\n'
 '\n'
 'M620.11 S0\n'
 'M400\n'
 '\n'
 'M620.1 E F199.5593065314098 T255\n'
 'M620.10 A0 F199.5593065314098\n'
 'T0\n'
 'M620.1 E F199.5593065314098 T255\n'
 'M620.10 A1 F199.5593065314098 L83.14971105475408 H0.4 T255\n'
 '\n'
 'G1 Y90 F9000\n'
 '\n'
 '\n'
 'M620.11 S0\n'
 '\n'
 'M400\n'
 'G92 E0\n'
 'M628 S0\n'
 '\n'
 '; FLUSH_START\n'
 '; always use highest temperature to flush\n'
 'M400\n'
 'M1002 set_filament_type:UNKNOWN\n'
 'M109 S255\n'
 'M106 P1 S60\n'
 'G1 E23.7 F199.5593065314098 ; do not need pulsatile flushing for start part\n'
 'G1 E1.1889942210950815 F50\n'
 'G1 E13.673433542593438 F199.5593065314098\n'
 'G1 E1.1889942210950815 F50\n'
 'G1 E13.673433542593438 F199.5593065314098\n'
 'G1 E1.1889942210950815 F50\n'
 'G1 E13.673433542593438 F199.5593065314098\n'
 'G1 E1.1889942210950815 F50\n'
 'G1 E13.673433542593438 F199.5593065314098\n'
 '; FLUSH_END\n'
 'G1 E-2 F1800\n'
 'G1 E2 F300\n'
 'M400\n'
 'M1002 set_filament_type:PETG\n'
 '\n'
 '\n'
 '\n'
 '\n'
 '\n'
 '\n'
 '\n'
 'M629\n'
 '\n'
 'M400\n'
 'M106 P1 S60\n'
 'M109 S255\n'
 'G1 E5 F199.5593065314098 ;Compensate for filament spillage during waiting temperature\n'
 'M400\n'
 'G92 E0\n'
 'G1 E-2 F1800\n'
 'M400\n'
 'M106 P1 S178\n'
 'M400 S3\n'
 'G1 X-3.5 F18000\n'
 'G1 X-13.5 F3000\n'
 'G1 X-3.5 F18000\n'
 'G1 X-13.5 F3000\n'
 'G1 X-3.5 F18000\n'
 'G1 X-13.5 F3000\n'
 'G1 X-3.5 F18000\n'
 'G1 X-13.5 F3000\n'
 'M400\n'
 'G1 Z3.88 F3000\n'
 'M106 P1 S0\n'
 'M204 S8000\n'
 '\n'
 'M622.1 S0\n'
 'M9833 F3.3333333333333335 A0.3 ; cali dynamic extrusion compensation\n'
 'M1002 judge_flag filament_need_cali_flag\n'
 'M622 J1\n'
 '  G92 E0\n'
 '  G1 E-2 F1800\n'
 '  M400\n'
 '  \n'
 '  M106 P1 S178\n'
 '  M400 S7\n'
 '  G1 X0 F18000\n'
 '  G1 X-13.5 F3000\n'
 '  G1 X0 F18000 ;wipe and shake\n'
 '  G1 X-13.5 F3000\n'
 '  G1 X0 F12000 ;wipe and shake\n'
 '  G1 X-13.5 F3000\n'
 '  G1 X0 F12000 ;wipe and shake\n'
 '  M400\n'
 '  M106 P1 S0 \n'
 'M623\n'
 '\n'
 'M621 S0A\n'
 'G392 S0\n'
 '\n'
 'M1007 S1\n')

CHANGE_TO_WHITE = (';===== A1mini 20250822 =====\n'
 'G392 S0\n'
 'M1007 S0\n'
 'M620 S1A\n'
 'M204 S9000\n'
 'G1 Z3.64 F1200\n'
 '\n'
 'M400\n'
 'M106 P1 S0\n'
 'M106 P2 S0\n'
 'M104 S255\n'
 '\n'
 'G1 X180 F18000\n'
 '\n'
 'M620.11 S0\n'
 'M400\n'
 '\n'
 'M620.1 E F199.5593065314098 T255\n'
 'M620.10 A0 F199.5593065314098\n'
 'T1\n'
 'M620.1 E F199.5593065314098 T255\n'
 'M620.10 A1 F199.5593065314098 L124.72456658213113 H0.4 T255\n'
 '\n'
 'G1 Y90 F9000\n'
 '\n'
 '\n'
 'M620.11 S0\n'
 '\n'
 'M400\n'
 'G92 E0\n'
 'M628 S0\n'
 '\n'
 '; FLUSH_START\n'
 '; always use highest temperature to flush\n'
 'M400\n'
 'M1002 set_filament_type:UNKNOWN\n'
 'M109 S255\n'
 'M106 P1 S60\n'
 'G1 E23.7 F199.5593065314098 ; do not need pulsatile flushing for start part\n'
 'G1 E2.0204913316426225 F50\n'
 'G1 E23.23565031389016 F199.5593065314098\n'
 'G1 E2.0204913316426225 F50\n'
 'G1 E23.23565031389016 F199.5593065314098\n'
 'G1 E2.0204913316426225 F50\n'
 'G1 E23.23565031389016 F199.5593065314098\n'
 'G1 E2.0204913316426225 F50\n'
 'G1 E23.23565031389016 F199.5593065314098\n'
 '; FLUSH_END\n'
 'G1 E-2 F1800\n'
 'G1 E2 F300\n'
 'M400\n'
 'M1002 set_filament_type:PETG\n'
 '\n'
 '\n'
 '\n'
 '\n'
 '\n'
 '\n'
 '\n'
 'M629\n'
 '\n'
 'M400\n'
 'M106 P1 S60\n'
 'M109 S255\n'
 'G1 E5 F199.5593065314098 ;Compensate for filament spillage during waiting temperature\n'
 'M400\n'
 'G92 E0\n'
 'G1 E-2 F1800\n'
 'M400\n'
 'M106 P1 S178\n'
 'M400 S3\n'
 'G1 X-3.5 F18000\n'
 'G1 X-13.5 F3000\n'
 'G1 X-3.5 F18000\n'
 'G1 X-13.5 F3000\n'
 'G1 X-3.5 F18000\n'
 'G1 X-13.5 F3000\n'
 'G1 X-3.5 F18000\n'
 'G1 X-13.5 F3000\n'
 'M400\n'
 'G1 Z3.64 F3000\n'
 'M106 P1 S0\n'
 'M204 S8000\n'
 '\n'
 'M622.1 S0\n'
 'M9833 F3.3333333333333335 A0.3 ; cali dynamic extrusion compensation\n'
 'M1002 judge_flag filament_need_cali_flag\n'
 'M622 J1\n'
 '  G92 E0\n'
 '  G1 E-2 F1800\n'
 '  M400\n'
 '  \n'
 '  M106 P1 S178\n'
 '  M400 S7\n'
 '  G1 X0 F18000\n'
 '  G1 X-13.5 F3000\n'
 '  G1 X0 F18000 ;wipe and shake\n'
 '  G1 X-13.5 F3000\n'
 '  G1 X0 F12000 ;wipe and shake\n'
 '  G1 X-13.5 F3000\n'
 '  G1 X0 F12000 ;wipe and shake\n'
 '  M400\n'
 '  M106 P1 S0 \n'
 'M623\n'
 '\n'
 'M621 S1A\n'
 'G392 S0\n'
 '\n'
 'M1007 S1\n')

CURRENT_PIECE = None

CURRENT_PIECE_NAME = ''

CURRENT_REAR_PARAMETER_TEXT = ''

DEFAULT_E_PER_MM = 0.01567

DEFAULT_SLICER_TARGET = 'orca'

DIRECT_OPTICAL_LAYER_COUNT = 3

EXPECTED_DP_VERSION = '3dprintv1.179'

FAMILY_RESET_EDGE_GAP_MM = 0.2

FIRST_LAYER_H_MM = 0.2

HORIZONTAL_PERCENT = 0.0

LABEL_GLYPHS = {'0': ('01110', '10001', '10011', '10101', '11001', '10001', '01110'),
 '1': ('01110', '00110', '00110', '00110', '00110', '00110', '11111'),
 '2': ('11110', '00001', '00001', '11110', '10000', '10000', '11111'),
 '3': ('11110', '00001', '00001', '01110', '00001', '00001', '11110'),
 '4': ('10010', '10010', '10010', '11111', '00010', '00010', '00010'),
 '5': ('11111', '10000', '10000', '11110', '00001', '00001', '11110'),
 '6': ('01111', '10000', '10000', '11110', '10001', '10001', '01110'),
 '7': ('11111', '00001', '00010', '00100', '01000', '01000', '01000'),
 '8': ('01110', '10001', '10001', '01110', '10001', '10001', '01110'),
 '9': ('01110', '10001', '10001', '01111', '00001', '00001', '11110'),
 '-': ('00000', '00000', '00000', '11111', '00000', '00000', '00000'),
 'A': ('01110', '10001', '10001', '11111', '10001', '10001', '10001'),
 'P': ('11110', '10001', '10001', '11110', '10000', '10000', '10000'),
 'S': ('01111', '10000', '10000', '01110', '00001', '00001', '11110'),
 '%': ('11001', '11010', '00100', '00100', '01000', '10110', '00110'),
 ' ': ('000', '000', '000', '000', '000', '000', '000'),
 'X': ('10001', '10001', '01010', '00100', '01010', '10001', '10001'),
 'Y': ('10001', '10001', '01010', '00100', '00100', '00100', '00100'),
 '.': ('00', '00', '00', '00', '00', '11', '11'),
 'D': ('11110', '10001', '10001', '10001', '10001', '10001', '11110'),
 'E': ('11111', '10000', '10000', '11110', '10000', '10000', '11111'),
 'H': ('10001', '10001', '10001', '11111', '10001', '10001', '10001'),
 'W': ('10001', '10001', '10001', '10101', '10101', '10101', '01010'),
 'K': ('10001', '10010', '10100', '11000', '10100', '10010', '10001'),
 'L': ('10000', '10000', '10000', '10000', '10000', '10000', '11111'),
 'V': ('10001', '10001', '10001', '10001', '10001', '01010', '00100'),
 'R': ('11110', '10001', '10001', '11110', '10100', '10010', '10001'),
 'C': ('01111', '10000', '10000', '10000', '10000', '10000', '01111')}

LABEL_LINE_Y0_MM = (5.0, 23.0, 41.0, 59.0)

LAYER_HEIGHT_MM = 0.24

LAYER_H_MM = 0.1

LAYER_MAP = 'WWK'

LOGICAL_MATERIAL = 'W'

MASTER_FAN = MasterFan()

MINIMUM_PITCH_MM = 0.0

MIN_EMITTED_CHORD_MM = 0.8

MIN_MODEL_PART_FAN_PWM = 128

MODE_PROFILES = {'single-arc': {'tier_counts': (1,), 'smooth': False, 'placement': 'inner_to_outer'},
 'pyramid-3-2-1': {'tier_counts': (3, 2, 1), 'smooth': False, 'placement': 'outer_to_inner'},
 'pyramid-2-1': {'tier_counts': (2, 1), 'smooth': False, 'placement': 'outer_to_inner'},
 'smooth1': {'tier_counts': (1,), 'smooth': True, 'placement': 'outer_to_inner'},
 'smooth2': {'tier_counts': (2, 1), 'smooth': True, 'placement': 'outer_to_inner'},
 'smooth3': {'tier_counts': (3, 2, 1), 'smooth': True, 'placement': 'outer_to_inner'}}

NOMINAL_TOP_Z_MM = 1.174

OPTICAL_MODE = 'pyramid-3-2-1'

ORCA_PRODUCER_VERSION = '2.5.0-dev'

PANEL_HEIGHT_Y_MM = 124.5

PANEL_HEIGHT_Z_MM = 124.5

PANEL_WIDTH_X_MM = 110.69009321481776

PHYSICAL_HEIGHT_SCALE = 1.2

PHYSICAL_LAYER_COUNT = 4

PHYSICAL_LAYER_HEIGHT_MM = 0.288

PHYSICAL_TOL_MM = 0.0005

PROTECTED_UNDERLYING_OPTIONS = {'--card',
 '--close-gaps-mm',
 '--direct-layer-images',
 '--direct-layout',
 '--directional-block-mm',
 '--edge-aa',
 '--endpoint-trim-mm',
 '--filament-assignment-json',
 '--image',
 '--output',
 '--print-width-mm',
 '--rp-pitch-mm',
 '--skip-absent-layer-materials',
 '--tool-map-json'}

REAR_ARROW_DIRECTION = 'opposite-v138'

REAR_PARAMETER_TEXT = '1-2  158 | WWK | V75% L0.24 | S1.2 H0 C16'

REAR_RETURN_ANGLE_DEG = 67.5

REAR_TEXT_LINES = ('1-2  158', 'WWK', 'V75% L0.24', 'S1.2 H0 C16')

REAR_VERSION_TEXT = '159'

REVISION = 159

ROAD_WIDTH_MM = 0.4

RP_PITCH_MM = 0.4

RUNTIME_ORIGIN = None

SCREEN_SAMPLE_HEIGHT_MM = 124.5

SCRIPT_VERSION = '3dprint_black_mirror_wave_grid_v1.159'

SMOOTH_EMBED_DEPTH_MM = 0.02

SMOOTH_E_PER_MM = 0.01567

SMOOTH_LAYER_HEIGHT_MM = 0.1

SMOOTH_MAX_NOZZLE_PENETRATION_MM = None

SMOOTH_NOZZLE_FLAT_DIAMETER_MM = None

SMOOTH_REAR_MAX_EMBED_MM = 0.1

SMOOTH_XY_SPEED_MM_S = 30.0

SMOOTH_Z_SPEED_LIMIT_MM_S = 30.0

SPACING_MODEL = 'mapped-white'

STACK_H = 312

STACK_W = 277

STRUCTURAL_E_PER_MM = 0.01567

TIER_PHYSICAL_HEIGHTS_MM = (0.288, 0.288, 0.198)

TIER_TOP_Z_MM = (0.688, 0.976, 1.174)

TOP_SUPPORT_FILL_DEPTH_MM = 0.08

TOP_SUPPORT_FILL_EFFECTIVE_Z_MM = 0.42

TOP_SUPPORT_FILL_E_PER_MM = 0.0039175

TOP_SUPPORT_FILL_FEED_MM_S = 250.0

TOP_SUPPORT_FILL_G29_DELTA_MM = 0.02

TOP_SUPPORT_FILL_VE = 0.25

VALLEY_LAND_MM = 0.1

VISIBILITY_PERCENT = 75.0

WAVESET_TOTAL_PEAK_MM = 0.3

WAVE_RELIEF_MM = 0.32

_BLOCKER_ARRAY_CACHE = {}

_MIRROR_LATTICE_CACHE = {}

_OPTICAL_LATTICE_CACHE = {}

_WHITE_ARRAY_CACHE = {}

_WHITE_SAMPLE_CACHE = {}

# ---- reject_protected_passthrough ----
def reject_protected_passthrough(args: Sequence[str]) -> None:
    for token in args:
        opt = token.split("=", 1)[0]
        if opt in PROTECTED_UNDERLYING_OPTIONS:
            raise RuntimeError(
                f"{opt} is controlled by {SCRIPT_VERSION} and cannot be "
                "overridden through passthrough arguments."
            )


# ---- import_3dprint ----
def import_3dprint(source: Path):
    source = Path(source)
    if not source.exists():
        raise FileNotFoundError(
            f"Cannot find {source}. Put this wrapper beside "
            f"{EXPECTED_DP_VERSION}.py or pass --source with its full path."
        )

    source_text = source.read_text(encoding="utf-8")
    source_text = _patch_emitter_source(source_text)
    module_name = "fc3d_canonical_emitter_v159"
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


# ---- _blank_segments ----
def _blank_segments(material_order: Sequence[str]) -> Dict[str, list]:
    out = {str(m): [] for m in material_order}
    out.setdefault(LOGICAL_MATERIAL, [])
    return out


# ---- _centres_for_filled_interval ----
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


# ---- make_layer_segments ----
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


# ---- install_patches ----
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

    def canonical_right_head_material_selector(material, raw_tool, w_hotend_index):
        if str(material) == LOGICAL_MATERIAL:
            return _canonical_hotend_for_material(material, raw_tool, w_hotend_index)
        return orig_hotend_for_material(material, raw_tool, w_hotend_index)

    dp.h2c_native_hotend_for_material = canonical_right_head_material_selector

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
        # v1.159 is deliberately single-material black throughout. Rear marking
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
    dp.audit_job_material_and_tower_contract = _make_job_material_tower_audit(
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


# ---- _replace_zip_members ----
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


# ---- _find_gcode_producer_line ----
def _find_gcode_producer_line(lines: Sequence[str]) -> int:
    for i, line in enumerate(lines[:32]):
        if line.startswith("; BambuStudio ") or line.startswith("; generated by OrcaSlicer "):
            return i
    raise RuntimeError("V1.90 SLICER TARGET: no recognised slicer producer line in G-code header")


# ---- apply_slicer_target_metadata ----
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


# ---- audit_slicer_target_metadata ----
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


# ---- _mirror_wave_peak_z_mm ----
def _mirror_wave_peak_z_mm():
    return max(NOMINAL_TOP_Z_MM, BASE_TOP_Z_MM + A_MAIN_NOMINAL_HEIGHT_MM + WAVESET_TOTAL_PEAK_MM)


# ---- apply_dynamic_tower_policy ----
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
                f"G1 Z{mz.group(1)}{feed} ; FC3D_V1159_TOWER_EXIT_HOP_SANITIZED_Z_ONLY"
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

    # v1.159: all real v1.179 FC3D_TOWER_SLOT emission owners have now been
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


# ---- enforce_minimum_model_part_fan ----
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


# ---- _unit3 ----
def _unit3(v):
    m = math.sqrt(sum(float(q) * float(q) for q in v))
    if m <= 1e-12:
        raise ValueError("zero-length 3D vector")
    return tuple(float(q) / m for q in v)


# ---- _line_angle_deg ----
def _line_angle_deg(angle_deg: float) -> float:
    """Return an unoriented line angle in [-90, 90)."""
    a = float(angle_deg)
    while a >= 90.0:
        a -= 180.0
    while a < -90.0:
        a += 180.0
    return a


# ---- mirror_frame_global ----
def mirror_frame_global(x, y):
    """Original mirror tilt, optionally rotating the local arc field horizontally."""
    f = _ideal_mirror_frame_global(x, y)
    if not HORIZONTAL_PERCENT:
        return f
    f = dict(f)
    theta = math.atan2(f['b_unit'][1], f['b_unit'][0])
    delta = (-math.pi / 2 - theta + math.pi) % (2 * math.pi) - math.pi
    angle = theta + delta * HORIZONTAL_PERCENT / 100
    b = (math.cos(angle), math.sin(angle))
    a = (-b[1], b[0])
    f.update(b_unit=b, b_rise_unit=(-b[0], -b[1]), a_unit=a,
             normal_azimuth_deg=_line_angle_deg(math.degrees(angle)),
             contour_azimuth_deg=_line_angle_deg(math.degrees(angle) + 90))
    f['ideal_normal_unit'] = f['normal_unit']
    tilt = math.radians(f['facet_tilt_deg'])
    n = (math.sin(tilt) * b[0], math.sin(tilt) * b[1], math.cos(tilt))
    f['normal_unit'] = n
    inc = tuple(-v for v in f['projector_unit'])
    dot = sum(v * w for v, w in zip(inc, n))
    f['reflection_error'] = math.sqrt(sum((inc[i] - 2 * dot * n[i] - f['viewer_unit'][i]) ** 2 for i in range(3)))
    return f


# ---- _unit_surface_normal_from_tangents ----
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


# ---- integrate_b_front_global ----
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


# ---- _advance_b_rise_global ----
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


# ---- build_wave_cell_global ----
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


# ---- _resample_polyline2 ----
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


# ---- _clip_segment_rect3 ----
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


# ---- _clip_polyline3_to_piece ----
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


# ---- _clip_polyline2_to_piece ----
def _clip_polyline2_to_piece(points, piece, inset_mm=None):
    p3=[(x,z,0.0) for x,z in points]
    return [[(q[0],q[1]) for q in seg] for seg in _clip_polyline3_to_piece(p3,piece,inset_mm)]


# ---- _append_clipped_b_cell_local ----
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


# ---- _trace_a_streamline_global ----
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


# ---- generate_mirror_wave_lattice ----
def generate_mirror_wave_lattice(piece: PieceSpec):
    """Build the full A/B curvilinear lattice before any G-code concerns.

    B roads rise opposite the ideal normal projection. Corresponding crests are
    connected to make the main A curves; the lower inner A curve is derived from
    the same local tilt. Families are re-meshed only at valleys if the edge gap
    exceeds half a nominal road width.

    v1.159 clips B cells and A curves as they are generated instead of retaining
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


# ---- get_mirror_wave_lattice ----
def get_mirror_wave_lattice(piece: PieceSpec):
    key=(piece.name, round(piece.global_x0_mm,9), round(piece.global_z0_mm,9))
    rec=_MIRROR_LATTICE_CACHE.get(key)
    if rec is None:
        rec=generate_mirror_wave_lattice(piece)
        _MIRROR_LATTICE_CACHE[key]=rec
    return rec


# ---- _explicit_mirror_wave_layer_gcode ----
def _explicit_mirror_wave_layer_gcode(piece, x_origin, y_origin):
    """Emit v158 optical motion directly, including corrected executable cap Z.

    Cap E preserves the two-step numeric rounding of the validated v158 output:
    common-height E to five decimals, then cap ratio to eight decimals. This is
    intentional for regression equivalence, not a second runtime patch.
    """
    lattice = get_optical_lattice(piece)
    xo, yo = float(x_origin), float(y_origin)
    counts = _mode_profile()['tier_counts']
    cap_z = TIER_TOP_Z_MM[-1]
    travel_z = cap_z + .160
    # v158 leaves its final (non-extruding) safe lift at the full-tier envelope.
    safe_end_z = BASE_TOP_Z_MM + len(counts) * PHYSICAL_LAYER_HEIGHT_MM + .160
    rows = [f'; FC3D_V1159_OPTICAL_START mode=mapped-pyramid layer_map={LAYER_MAP} visibility={VISIBILITY_PERCENT}% '
            f'dose_height={LAYER_HEIGHT_MM:.3f} physical_height_scale={PHYSICAL_HEIGHT_SCALE:.3f} '
            f'physical_layer_height={PHYSICAL_LAYER_HEIGHT_MM:.3f} stacks={len(lattice["printable"])}'
            f' cap_dose_height={CAP_HEIGHT_MM:.3f} cap_physical_height={CAP_PHYSICAL_HEIGHT_MM:.3f}',
            f'; FC3D_V1159_HORIZONTAL percent={HORIZONTAL_PERCENT:g} target=screen-horizontal',
            f'; FC3D_V1159_VIEWER_TARGET x={MASTER_FAN.viewer_x_mm:.3f} '
            f'eye_above_screen_bottom={MASTER_FAN.viewer_z_mm:.3f} distance={MASTER_FAN.viewer_distance_mm:.3f}',
            f'; FC3D_V1159_SUPPORT_START tiers={len(counts)}']
    rt = sys.modules[__name__]
    ordering = {(g['tier'], r): i for i, g in enumerate(_colour_groups(rt)) for r in g['roads']}
    blocks = []
    road_no = 0
    for tier, count in enumerate(counts):
        is_cap = tier == len(counts) - 1
        z_abs = cap_z if is_cap else BASE_TOP_Z_MM + (tier + 1) * PHYSICAL_LAYER_HEIGHT_MM
        for stack_no, plan in enumerate(lattice['printable'], 1):
            for road_index in range(count):
                pts = [(xo + p[0], yo + p[1]) for p in plan['roads'][(tier, road_index)]]
                total = _polyline_length2(pts)
                dry = min(.160, max(0., total * .45))
                draw = max(0., total - dry)
                if draw <= 1e-8:
                    continue
                draw_pts = _coalesce_curve_for_emission(_polyline_prefix_for_length(pts, draw))
                road_no += 1
                block = [f'; FC3D_V1159_SUPPORT_ROAD_START road={road_no} stack={stack_no} tier={tier+1} tier_road={road_index+1} z={z_abs:.3f}',
                         f'G0 Z{travel_z:.3f} F900 ; FC3D_V1159_SUPPORT_TRAVEL_Z',
                         f'G0 X{pts[0][0]:.3f} Y{pts[0][1]:.3f} F18000 ; FC3D_V1159_SUPPORT_MOVE',
                         f'G0 Z{z_abs:.3f} F900 ; FC3D_V1159_SUPPORT_HEIGHT',
                         f'G1 E{A_REPRIME_MM:.3f} F1800 ; FC3D_V1159_SUPPORT_REPRIME']
                for segment, (a, b) in enumerate(zip(draw_pts, draw_pts[1:])):
                    distance = _gcode_chord_length(a, b)
                    extrusion = distance * A_MAIN_E_PER_MM
                    if round(extrusion, 5) > 0:
                        etext = f'{extrusion:.5f}'
                        if is_cap:
                            etext = f'{float(etext) * (CAP_HEIGHT_MM / LAYER_HEIGHT_MM):.8f}'.rstrip('0').rstrip('.')
                        block.append(f'G1 X{b[0]:.3f} Y{b[1]:.3f} Z{z_abs:.3f} E{etext} '
                                     f'F{A_PRINT_FEED_MM_S * 60:.0f} ; FC3D_V1159_SUPPORT_SEG road={road_no} seg={segment}')
                block.append(f'G1 E-{A_RETRACT_MM:.3f} F1800 ; FC3D_V1159_SUPPORT_RETRACT')
                if dry > 1e-9:
                    block.append(f'G1 X{pts[-1][0]:.3f} Y{pts[-1][1]:.3f} Z{z_abs:.3f} F15000 '
                                 f'; FC3D_V1159_SUPPORT_DRY_TAIL len={dry:.3f}')
                block.append(f'; FC3D_V1159_SUPPORT_ROAD_END road={road_no}')
                blocks.append((ordering[tier+1, road_index+1], road_no, block))
    for _, _, block in sorted(blocks):
        rows.extend(block)
    rows.extend([f'; FC3D_V1159_SUPPORT_END roads={road_no}',
                 f'G0 Z{safe_end_z:.3f} F900 ; FC3D_V1159_OPTICAL_SAFE_END_Z',
                 f'; FC3D_V1159_OPTICAL_END support_roads={road_no} smooth_paths=0'])
    return rows


# ---- set_runtime_e_per_mm ----
def set_runtime_e_per_mm(value: float):
    global CALIBRATED_E_PER_MM
    value = float(value)
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError("e-per-mm must be a finite positive value")
    CALIBRATED_E_PER_MM = value
    return value


# ---- _current_piece ----
def _current_piece() -> PieceSpec:
    if CURRENT_PIECE is None:
        raise RuntimeError("piece not selected")
    return CURRENT_PIECE


# ---- _coord_key ----
def _coord_key(a, b):
    return tuple(round(float(v), 4) for v in (*a, *b))


# ---- _base_roads_x ----
def _base_roads_x(x_origin: float, y_origin: float):
    x0 = float(x_origin)
    x1 = x0 + PANEL_WIDTH_X_MM
    half = ROAD_WIDTH_MM / 2.0
    ys = _centres_for_filled_interval(0.0, PANEL_HEIGHT_Y_MM, ROAD_WIDTH_MM)
    return [(x0 + half, float(y_origin) + y, x1 - half, float(y_origin) + y, 1.0) for y in ys]


# ---- _base_roads_y ----
def _base_roads_y(x_origin: float, y_origin: float):
    y0 = float(y_origin)
    y1 = y0 + PANEL_HEIGHT_Y_MM
    half = ROAD_WIDTH_MM / 2.0
    xs = _centres_for_filled_interval(0.0, PANEL_WIDTH_X_MM, ROAD_WIDTH_MM)
    return [(float(x_origin) + x, y0 + half, float(x_origin) + x, y1 - half, 1.0) for x in xs]


# ---- _base_roads_for_layer ----
def _base_roads_for_layer(logical_layer: int, x_origin: float, y_origin: float):
    li = int(logical_layer)
    if not 0 <= li < BASE_LAYER_COUNT:
        raise ValueError(li)
    # Mechanical interlock: every structural layer swaps raster direction.
    return _base_roads_x(x_origin, y_origin) if li % 2 == 0 else _base_roads_y(x_origin, y_origin)


# ---- _merge_intervals ----
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


# ---- label_intervals_printer_x ----
def label_intervals_printer_x(piece, y_local_mm):
    """Rotate card ID, revision, mode/parameters and arrow together by 180 deg."""
    raw=_unrotated_label_intervals(piece,piece.height_mm-float(y_local_mm))
    return _merge_intervals((piece.width_mm-b,piece.width_mm-a) for a,b in raw)


# ---- _subtract_intervals ----
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


# ---- _base_segments_by_material_for_layer ----
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
        raise RuntimeError(f"v1.159: black-only rear texture mask too small/missing for {piece.name}: rows={textured_rows} omitted={omitted_len:.1f}")
    return out


# ---- _placeholder_segment ----
def _placeholder_segment(x_origin: float, y_origin: float):
    return (float(x_origin) + 0.20, float(y_origin) + 0.20,
            float(x_origin) + 0.60, float(y_origin) + 0.60, 1.0)


# ---- apply_mirror_wave_paths ----
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
        replacement=[f"; FC3D_V1159_MIRROR_WAVE_START layer={li} piece={_current_piece().name}"]+layer_rows+[f"; FC3D_V1159_MIRROR_WAVE_END layer={li} piece={_current_piece().name}"]
        counts["inner_segments"]=0
        counts["main_segments"]=sum("FC3D_V1159_A_ROAD_SEG" in r for r in layer_rows)
        counts["b_segments"]=sum("FC3D_V1159_B_SEG" in r for r in layer_rows)
        counts["b_paths"]=sum("FC3D_V1159_B_PATH_START" in r for r in layer_rows)
        counts["families"]=sum("FC3D_V1159_B_FAMILY_START" in r for r in layer_rows)
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
        entry_prefix[prime_i]="G1 E-0.400 F1800 ; FC3D_V1159_A_ENTRY_EXTRA_RETRACT base_minus_0.400_to_a1_minus_0.800"
        rebuilt.extend(entry_prefix); rebuilt.extend(replacement); rebuilt.extend(block[a+1:])
    _replace_zip_members(output,{name:("\n".join(rebuilt)+"\n").encode("utf-8")})
    return {"piece":_current_piece().name,**counts}


# ---- audit_final_base_interlock ----
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


# ---- audit_final_black_texture_and_single_material ----
def audit_final_black_texture_and_single_material(output):
    """Audit the v1.159 black-only rear texture and single-material lifecycle."""
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


# ---- _a1mini_start_gcode ----
def _a1mini_start_gcode() -> str:
    """Reduced A1 Mini single-material start derived from Orca A1 Mini ordering.

    Keep the nozzle below PETG print temperature during cleaning/probing, enable
    the ABL mesh before G29, commit the completed probe, then block at 255 C and
    condition the already-loaded black PETG in the unused front bed margin.
    Conditioning exits retracted by the active A-road retract for the canonical model contract.
    """
    return "\n".join([
        "; FC3D_V1159_A1MINI_START",
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

        "; FC3D_V1159_A1MINI_NOZZLE_WIPE_START",
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
        "; FC3D_V1159_A1MINI_NOZZLE_WIPE_END",

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

        "; FC3D_V1159_A1MINI_CONDITION_START",
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
        "; FC3D_V1159_A1MINI_CONDITION_END state=RETRACTED",
        "M106 S0",
        "M1002 gcode_claim_action : 0",
        "; FC3D_V1159_A1MINI_START_END",
    ])


# ---- _a1mini_end_gcode ----
def _a1mini_end_gcode(final_z: float) -> str:
    # Relative lift can never command beyond the A1 Mini's 180-mm Z envelope.
    clearance = max(0.0, 180.0 - float(final_z) - 0.20)
    lift = min(5.0, clearance)
    rows = [
        "; FC3D_V1159_A1MINI_END",
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
        "; FC3D_V1159_A1MINI_END_DONE",
        "; EXECUTABLE_BLOCK_END",
    ]
    return "\n".join(rows)


# ---- _strip_prime_tower_blocks ----
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


# ---- _replace_config_comment ----
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


# ---- convert_package_to_a1mini_orca ----
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


# ---- audit_a1mini_orca_package ----
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
        "; FC3D_V1159_A1MINI_START",
        "; FC3D_V1159_A1MINI_NOZZLE_WIPE_START",
        "; FC3D_V1159_A1MINI_NOZZLE_WIPE_END",
        "; FC3D_V1159_A1MINI_CONDITION_START",
        "; FC3D_V1159_A1MINI_CONDITION_END state=RETRACTED",
        "; FC3D_V1159_A1MINI_END",
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
        start_i = next(i for i in exec_range if lines[i].strip() == "; FC3D_V1159_A1MINI_START")
        wipe_start_i = next(i for i in range(start_i + 1, exec_end_i) if lines[i].strip() == "; FC3D_V1159_A1MINI_NOZZLE_WIPE_START")
        wipe_end_i = next(i for i in range(wipe_start_i + 1, exec_end_i) if lines[i].strip() == "; FC3D_V1159_A1MINI_NOZZLE_WIPE_END")
        g29_i = next(i for i in range(wipe_end_i + 1, exec_end_i) if re.match(r"^\s*G29\s+A1\b", lines[i]))
        cond_start_i = next(i for i in range(g29_i + 1, exec_end_i) if lines[i].strip() == "; FC3D_V1159_A1MINI_CONDITION_START")
        cond_end_i = next(i for i in range(cond_start_i + 1, exec_end_i) if lines[i].strip() == "; FC3D_V1159_A1MINI_CONDITION_END state=RETRACTED")
        first_layer_i = next(i for i in range(cond_end_i + 1, exec_end_i) if lines[i].strip() == "; CHANGE_LAYER")
        a1_end_i = next(i for i in range(first_layer_i + 1, exec_end_i) if lines[i].strip() == "; FC3D_V1159_A1MINI_END")
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
        "sanitized_tower_exit_hops": g.count("FC3D_V1159_TOWER_EXIT_HOP_SANITIZED_Z_ONLY"),
        "md5": md5,
    }


# ---- _waveset_advance_point_inward ----
def _waveset_advance_point_inward(x,z,distance_mm,max_step_mm=0.05):
    x=float(x); z=float(z); rem=max(0.0,float(distance_mm))
    while rem>1e-12:
        ds=min(float(max_step_mm),rem)
        f0=mirror_frame_global(x,z); d0=f0["b_unit"]
        mx=x+0.5*d0[0]*ds; mz=z+0.5*d0[1]*ds
        fm=mirror_frame_global(mx,mz); d=fm["b_unit"]
        x+=d[0]*ds; z+=d[1]*ds; rem-=ds
    return (x,z)


# ---- _waveset_advance_curve_inward ----
def _waveset_advance_curve_inward(curve,distance_mm):
    return [_waveset_advance_point_inward(x,z,distance_mm) for x,z in curve]


# ---- _waveset_clip_curve ----
def _waveset_clip_curve(curve,piece):
    segs=_clip_polyline2_to_piece(curve,piece)
    if len(segs)>1:
        raise RuntimeError(f"v1.159 wave curve split into {len(segs)} clipped segments")
    return segs[0] if segs else []


# ---- _polyline_length2 ----
def _polyline_length2(points):
    return sum(math.hypot(b[0]-a[0],b[1]-a[1]) for a,b in zip(points,points[1:]))


# ---- apply_top_support_valley_fill ----
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
    if any("FC3D_V1159_TOP_VALLEY_FILL_" in l for l in support_block):
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
        "; FC3D_V1159_TOP_VALLEY_FILL_START no_new_logical_layer=1",
        f"; FC3D_V1159_TOP_VALLEY_FILL_RULE ve={TOP_SUPPORT_FILL_VE:.3f} depth={TOP_SUPPORT_FILL_DEPTH_MM:.3f} effective_z={TOP_SUPPORT_FILL_EFFECTIVE_Z_MM:.3f} commanded_z={BASE_TOP_Z_MM:.3f}",
        f"; FC3D_V1159_TOP_VALLEY_FILL_RASTER source_roads={len(fixed)} filler_roads={len(centres_desc)} pitch_min={min(diffs):.6f} pitch_max={max(diffs):.6f}",
        "M400",
        f"G29.1 Z{trim_target:.5f} ; FC3D_V1159_TOP_VALLEY_FILL_G29_SET baseline={baseline:.5f} delta={TOP_SUPPORT_FILL_G29_DELTA_MM:.5f}",
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
            f"; FC3D_V1159_TOP_VALLEY_FILL_ROAD_START index={idx + 1}/{len(centres_desc)} y={y:.5f}",
            f"G1 X{x0:.3f} Y{y:.5f} F{TOP_SUPPORT_FILL_FEED_MM_S * 60.0:.0f} ; FC3D_V1159_TOP_VALLEY_FILL_MOVE",
            "G1 E0.38000 F1800 ; FC3D_V1159_TOP_VALLEY_FILL_PREPRIME",
            "G1 E0.02000 F1800 ; FC3D_V1159_TOP_VALLEY_FILL_FINAL_PRIME",
            f"G1 X{x1:.3f} Y{y:.5f} E{e_road:.5f} F{TOP_SUPPORT_FILL_FEED_MM_S * 60.0:.0f} ; FC3D_V1159_TOP_VALLEY_FILL_DRAW",
            "G1 E-0.40000 F1800 ; FC3D_V1159_TOP_VALLEY_FILL_RETRACT",
            f"; FC3D_V1159_TOP_VALLEY_FILL_ROAD_END index={idx + 1}/{len(centres_desc)}",
        ]
        current_low = not current_low
    fill.append("; FC3D_V1159_TOP_VALLEY_FILL_END state=RETRACTED trim=ACTIVE")

    # Restore plate baseline only after the existing next-layer safe lift.
    lift_i = None
    down_i = None
    z_re = re.compile(r"\bZ([-+0-9.]+)")
    for i in range(change_i + 1, optical_start):
        if re.match(r"^\s*G[01]\b", lines[i]):
            zm = z_re.search(lines[i])
            if zm and float(zm.group(1)) > BASE_TOP_Z_MM + LAYER_H_MM + 0.2:
                lift_i = i
                break
    if lift_i is None:
        raise RuntimeError("V1.101 TOP FILL: next-layer safe lift missing for G29 restore")
    for i in range(lift_i + 1, optical_start):
        if re.match(r"^\s*G[01]\b", lines[i]):
            zm = z_re.search(lines[i])
            if zm and abs(float(zm.group(1)) - (BASE_TOP_Z_MM + LAYER_H_MM)) < 1e-6:
                down_i = i
                break
    if down_i is None:
        raise RuntimeError("V1.101 TOP FILL: nominal optical descent missing after safe lift")

    out = lines[:change_i] + fill + lines[change_i:lift_i + 1] + [
        "M400",
        f"G29.1 Z{baseline:.5f} ; FC3D_V1159_TOP_VALLEY_FILL_G29_RESTORE after_safe_lift=1",
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


# ---- audit_top_support_valley_fill ----
def audit_top_support_valley_fill(output: Path) -> dict:
    """Independent fail-closed audit of the v1.159 top-support filler."""
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
    if text.count("FC3D_V1159_TOP_VALLEY_FILL_START") != 1 or text.count("FC3D_V1159_TOP_VALLEY_FILL_END") != 1:
        raise RuntimeError("V1.101 TOP FILL AUDIT: fill boundary markers missing/duplicated")
    draws = [l for l in lines if "FC3D_V1159_TOP_VALLEY_FILL_DRAW" in l]
    starts_r = [l for l in lines if "FC3D_V1159_TOP_VALLEY_FILL_ROAD_START" in l]
    retracts = [l for l in lines if "FC3D_V1159_TOP_VALLEY_FILL_RETRACT" in l]
    pre = [l for l in lines if "FC3D_V1159_TOP_VALLEY_FILL_PREPRIME" in l]
    fin = [l for l in lines if "FC3D_V1159_TOP_VALLEY_FILL_FINAL_PRIME" in l]
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
        if "FC3D_V1159_TOP_VALLEY_FILL_DRAW" not in l:
            continue
        xm, ym, em, fm = x_re.search(l), y_re.search(l), e_re.search(l), f_re.search(l)
        if not (xm and ym and em and fm):
            raise RuntimeError(f"V1.101 TOP FILL AUDIT: malformed draw {l}")
        if abs(float(fm.group(1)) - TOP_SUPPORT_FILL_FEED_MM_S * 60.0) > 1e-6:
            raise RuntimeError(f"V1.101 TOP FILL AUDIT: wrong draw feed {l}")
        j = i - 1
        while j >= 0 and "FC3D_V1159_TOP_VALLEY_FILL_MOVE" not in lines[j]:
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
    set_lines = [l for l in lines if "FC3D_V1159_TOP_VALLEY_FILL_G29_SET" in l]
    restore_lines = [l for l in lines if "FC3D_V1159_TOP_VALLEY_FILL_G29_RESTORE" in l]
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
        if re.match(r"^\s*G[01]\b", l) and (m := z_re.search(l)):
            prior_z.append(float(m.group(1)))
    if not prior_z or max(prior_z) <= BASE_TOP_Z_MM + LAYER_H_MM + 0.2:
        raise RuntimeError(f"V1.101 TOP FILL AUDIT: G29 restore not performed after safe lift: {prior_z}")
    start_i = next(i for i, l in enumerate(lines) if "FC3D_V1159_TOP_VALLEY_FILL_START" in l)
    end_i = next(i for i, l in enumerate(lines) if "FC3D_V1159_TOP_VALLEY_FILL_END" in l)
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


# ---- normalize_a1mini_orca_reference_metadata ----
def normalize_a1mini_orca_reference_metadata(output: Path) -> dict:
    """Normalize non-executable metadata to the working Orca A1 Mini reference.

    The embedded templates are copied byte-for-byte from the user's Orca 2.5.0
    cube that successfully printed through Bambu Connect.  Only metadata/config
    is replaced here.  The already-audited executable A1 startup/model/end block
    is not reconstructed or resliced.
    """
    output = Path(output)
    gname = 'Metadata/plate_1.gcode'
    pname = 'Metadata/project_settings.config'
    sname = 'Metadata/slice_info.config'
    plate_name = 'Metadata/plate_1.json'
    seq_name = 'Metadata/filament_sequence.json'
    model_settings_name = 'Metadata/model_settings.config'
    model_name = '3D/3dmodel.model'
    required = (gname, pname, sname, plate_name, seq_name, model_settings_name, model_name)
    with zipfile.ZipFile(output, 'r') as z:
        missing = [n for n in required if n not in z.namelist()]
        if missing:
            raise RuntimeError(f'V1.101 ORCA REFERENCE METADATA: missing members {missing}')
        old_g = z.read(gname).decode('utf-8', errors='strict')
        old_project = json.loads(z.read(pname).decode('utf-8'))
        slice_root = ET.fromstring(z.read(sname))
        plate = json.loads(z.read(plate_name).decode('utf-8'))
        model_settings_root = ET.fromstring(z.read(model_settings_name))
        model_text = z.read(model_name).decode('utf-8', errors='strict')
    native_project = json.loads('{\r\n\t"accel_to_decel_enable": "1",\r\n\t"accel_to_decel_factor": "50%",\r\n\t"activate_air_filtration": [\r\n\t\t"0"\r\n\t],\r\n\t"activate_air_filtration_during_print": [\r\n\t\t"1"\r\n\t],\r\n\t"activate_air_filtration_on_completion": [\r\n\t\t"1"\r\n\t],\r\n\t"activate_chamber_temp_control": [\r\n\t\t"0"\r\n\t],\r\n\t"adaptive_bed_mesh_margin": "0",\r\n\t"adaptive_pressure_advance": [\r\n\t\t"0"\r\n\t],\r\n\t"adaptive_pressure_advance_bridges": [\r\n\t\t"0"\r\n\t],\r\n\t"adaptive_pressure_advance_model": [\r\n\t\t"0,0,0\\n0,0,0"\r\n\t],\r\n\t"adaptive_pressure_advance_overhangs": [\r\n\t\t"0"\r\n\t],\r\n\t"additional_cooling_fan_speed": [\r\n\t\t"0"\r\n\t],\r\n\t"additional_fan_full_speed_layer": [\r\n\t\t"0"\r\n\t],\r\n\t"align_infill_direction_to_model": "0",\r\n\t"alternate_extra_wall": "0",\r\n\t"auxiliary_fan": "0",\r\n\t"bbl_calib_mark_logo": "1",\r\n\t"bbl_use_printhost": "0",\r\n\t"bed_custom_model": "",\r\n\t"bed_custom_texture": "",\r\n\t"bed_exclude_area": [],\r\n\t"bed_mesh_max": "99999,99999",\r\n\t"bed_mesh_min": "-99999,-99999",\r\n\t"bed_mesh_probe_distance": "50,50",\r\n\t"bed_temperature_formula": "by_first_filament",\r\n\t"before_layer_change_gcode": "",\r\n\t"best_object_pos": "0.7,0.5",\r\n\t"bottom_layer_direction": "-1",\r\n\t"bottom_shell_layers": "3",\r\n\t"bottom_shell_thickness": "0",\r\n\t"bottom_solid_infill_flow_ratio": "1",\r\n\t"bottom_surface_density": "100%",\r\n\t"bottom_surface_filament_id": "0",\r\n\t"bottom_surface_fill_order": "default",\r\n\t"bottom_surface_pattern": "monotonic",\r\n\t"bridge_acceleration": [\r\n\t\t"50%"\r\n\t],\r\n\t"bridge_angle": "0",\r\n\t"bridge_density": "100%",\r\n\t"bridge_flow": "1",\r\n\t"bridge_line_width": "100%",\r\n\t"bridge_no_support": "0",\r\n\t"bridge_speed": [\r\n\t\t"50"\r\n\t],\r\n\t"brim_ears_detection_length": "1",\r\n\t"brim_ears_max_angle": "125",\r\n\t"brim_ears_outer_only": "0",\r\n\t"brim_flow_ratio": "1",\r\n\t"brim_object_gap": "0.1",\r\n\t"brim_type": "auto_brim",\r\n\t"brim_use_efc_outline": "0",\r\n\t"brim_width": "5",\r\n\t"calib_flowrate_topinfill_special_order": "0",\r\n\t"center_of_surface_pattern": "each_surface",\r\n\t"chamber_minimal_temperature": [\r\n\t\t"0"\r\n\t],\r\n\t"chamber_temperature": [\r\n\t\t"0"\r\n\t],\r\n\t"change_extrusion_role_gcode": "",\r\n\t"change_filament_gcode": ";===== A1mini 20250822 =====\\nG392 S0\\nM1007 S0\\nM620 S[next_extruder]A\\nM204 S9000\\nG1 Z{max_layer_z + 3.0} F1200\\n\\nM400\\nM106 P1 S0\\nM106 P2 S0\\n{if nozzle_temperature[previous_extruder] > 142 && next_extruder < 255}\\nM104 S{nozzle_temperature[previous_extruder]}\\n{endif}\\n\\nG1 X180 F18000\\n\\n{if long_retractions_when_cut[previous_extruder]}\\nM620.11 S1 I[previous_extruder] E-{retraction_distances_when_cut[previous_extruder]} F1200\\n{else}\\nM620.11 S0\\n{endif}\\nM400\\n\\nM620.1 E F{flush_volumetric_speeds[previous_extruder]/2.4053*60} T{flush_temperatures[previous_extruder]}\\nM620.10 A0 F{flush_volumetric_speeds[previous_extruder]/2.4053*60}\\nT[next_extruder]\\nM620.1 E F{flush_volumetric_speeds[next_extruder]/2.4053*60} T{flush_temperatures[next_extruder]}\\nM620.10 A1 F{flush_volumetric_speeds[next_extruder]/2.4053*60} L[flush_length] H[nozzle_diameter] T{flush_temperatures[next_extruder]}\\n\\nG1 Y90 F9000\\n\\n{if next_extruder < 255}\\n\\n{if long_retractions_when_cut[previous_extruder]}\\nM620.11 S1 I[previous_extruder] E{retraction_distances_when_cut[previous_extruder]} F{flush_volumetric_speeds[previous_extruder]/2.4053*60}\\nM628 S1\\nG92 E0\\nG1 E{retraction_distances_when_cut[previous_extruder]} F{flush_volumetric_speeds[previous_extruder]/2.4053*60}\\nM400\\nM629 S1\\n{else}\\nM620.11 S0\\n{endif}\\n\\nM400\\nG92 E0\\nM628 S0\\n\\n{if flush_length_1 > 1}\\n; FLUSH_START\\n; always use highest temperature to flush\\nM400\\nM1002 set_filament_type:UNKNOWN\\nM109 S[flush_temperatures[next_extruder]]\\nM106 P1 S60\\n{if flush_length_1 > 23.7}\\nG1 E23.7 F{flush_volumetric_speeds[previous_extruder]/2.4053*60} ; do not need pulsatile flushing for start part\\nG1 E{(flush_length_1 - 23.7) * 0.02} F50\\nG1 E{(flush_length_1 - 23.7) * 0.23} F{flush_volumetric_speeds[previous_extruder]/2.4053*60}\\nG1 E{(flush_length_1 - 23.7) * 0.02} F50\\nG1 E{(flush_length_1 - 23.7) * 0.23} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{(flush_length_1 - 23.7) * 0.02} F50\\nG1 E{(flush_length_1 - 23.7) * 0.23} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{(flush_length_1 - 23.7) * 0.02} F50\\nG1 E{(flush_length_1 - 23.7) * 0.23} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\n{else}\\nG1 E{flush_length_1} F{flush_volumetric_speeds[previous_extruder]/2.4053*60}\\n{endif}\\n; FLUSH_END\\nG1 E-[old_retract_length_toolchange] F1800\\nG1 E[old_retract_length_toolchange] F300\\nM400\\nM1002 set_filament_type:{filament_type[next_extruder]}\\n{endif}\\n\\n{if flush_length_1 > 45 && flush_length_2 > 1}\\n; WIPE\\nM400\\nM106 P1 S178\\nM400 S3\\nG1 X-3.5 F18000\\nG1 X-13.5 F3000\\nG1 X-3.5 F18000\\nG1 X-13.5 F3000\\nG1 X-3.5 F18000\\nG1 X-13.5 F3000\\nM400\\nM106 P1 S0\\n{endif}\\n\\n{if flush_length_2 > 1}\\nM106 P1 S60\\n; FLUSH_START\\nG1 E{flush_length_2 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_2 * 0.02} F50\\nG1 E{flush_length_2 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_2 * 0.02} F50\\nG1 E{flush_length_2 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_2 * 0.02} F50\\nG1 E{flush_length_2 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_2 * 0.02} F50\\nG1 E{flush_length_2 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_2 * 0.02} F50\\n; FLUSH_END\\nG1 E-[new_retract_length_toolchange] F1800\\nG1 E[new_retract_length_toolchange] F300\\n{endif}\\n\\n{if flush_length_2 > 45 && flush_length_3 > 1}\\n; WIPE\\nM400\\nM106 P1 S178\\nM400 S3\\nG1 X-3.5 F18000\\nG1 X-13.5 F3000\\nG1 X-3.5 F18000\\nG1 X-13.5 F3000\\nG1 X-3.5 F18000\\nG1 X-13.5 F3000\\nM400\\nM106 P1 S0\\n{endif}\\n\\n{if flush_length_3 > 1}\\nM106 P1 S60\\n; FLUSH_START\\nG1 E{flush_length_3 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_3 * 0.02} F50\\nG1 E{flush_length_3 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_3 * 0.02} F50\\nG1 E{flush_length_3 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_3 * 0.02} F50\\nG1 E{flush_length_3 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_3 * 0.02} F50\\nG1 E{flush_length_3 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_3 * 0.02} F50\\n; FLUSH_END\\nG1 E-[new_retract_length_toolchange] F1800\\nG1 E[new_retract_length_toolchange] F300\\n{endif}\\n\\n{if flush_length_3 > 45 && flush_length_4 > 1}\\n; WIPE\\nM400\\nM106 P1 S178\\nM400 S3\\nG1 X-3.5 F18000\\nG1 X-13.5 F3000\\nG1 X-3.5 F18000\\nG1 X-13.5 F3000\\nG1 X-3.5 F18000\\nG1 X-13.5 F3000\\nM400\\nM106 P1 S0\\n{endif}\\n\\n{if flush_length_4 > 1}\\nM106 P1 S60\\n; FLUSH_START\\nG1 E{flush_length_4 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_4 * 0.02} F50\\nG1 E{flush_length_4 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_4 * 0.02} F50\\nG1 E{flush_length_4 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_4 * 0.02} F50\\nG1 E{flush_length_4 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_4 * 0.02} F50\\nG1 E{flush_length_4 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_4 * 0.02} F50\\n; FLUSH_END\\n{endif}\\n\\nM629\\n\\nM400\\nM106 P1 S60\\nM109 S{nozzle_temperature[next_extruder]}\\nG1 E5 F{flush_volumetric_speeds[next_extruder]/2.4053*60} ;Compensate for filament spillage during waiting temperature\\nM400\\nG92 E0\\nG1 E-[new_retract_length_toolchange] F1800\\nM400\\nM106 P1 S178\\nM400 S3\\nG1 X-3.5 F18000\\nG1 X-13.5 F3000\\nG1 X-3.5 F18000\\nG1 X-13.5 F3000\\nG1 X-3.5 F18000\\nG1 X-13.5 F3000\\nG1 X-3.5 F18000\\nG1 X-13.5 F3000\\nM400\\nG1 Z{max_layer_z + 3.0} F3000\\nM106 P1 S0\\n{if layer_z <= (initial_layer_print_height + 0.001)}\\nM204 S[initial_layer_acceleration]\\n{else}\\nM204 S[default_acceleration]\\n{endif}\\n{else}\\nG1 X[x_after_toolchange] Y[y_after_toolchange] Z[z_after_toolchange] F12000\\n{endif}\\n\\nM622.1 S0\\nM9833 F{outer_wall_volumetric_speed/2.4} A0.3 ; cali dynamic extrusion compensation\\nM1002 judge_flag filament_need_cali_flag\\nM622 J1\\n  G92 E0\\n  G1 E-[new_retract_length_toolchange] F1800\\n  M400\\n  \\n  M106 P1 S178\\n  M400 S7\\n  G1 X0 F18000\\n  G1 X-13.5 F3000\\n  G1 X0 F18000 ;wipe and shake\\n  G1 X-13.5 F3000\\n  G1 X0 F12000 ;wipe and shake\\n  G1 X-13.5 F3000\\n  G1 X0 F12000 ;wipe and shake\\n  M400\\n  M106 P1 S0 \\nM623\\n\\nM621 S[next_extruder]A\\nG392 S0\\n\\nM1007 S1\\n",\r\n\t"close_additional_fan_first_x_layers": [\r\n\t\t"3"\r\n\t],\r\n\t"close_fan_the_first_x_layers": [\r\n\t\t"3"\r\n\t],\r\n\t"combine_brims": "0",\r\n\t"complete_print_exhaust_fan_speed": [\r\n\t\t"70"\r\n\t],\r\n\t"cool_plate_temp": [\r\n\t\t"0"\r\n\t],\r\n\t"cool_plate_temp_initial_layer": [\r\n\t\t"0"\r\n\t],\r\n\t"cooling_filter_enabled": "0",\r\n\t"cooling_tube_length": "5",\r\n\t"cooling_tube_retraction": "91.5",\r\n\t"counterbore_hole_bridging": "none",\r\n\t"curr_bed_type": "Textured PEI Plate",\r\n\t"default_acceleration": [\r\n\t\t"6000"\r\n\t],\r\n\t"default_bed_type": "",\r\n\t"default_filament_colour": [\r\n\t\t""\r\n\t],\r\n\t"default_filament_profile": [\r\n\t\t"Bambu PLA Basic @BBL A1M"\r\n\t],\r\n\t"default_jerk": [\r\n\t\t"0"\r\n\t],\r\n\t"default_junction_deviation": [\r\n\t\t"0"\r\n\t],\r\n\t"default_nozzle_volume_type": [\r\n\t\t"Standard"\r\n\t],\r\n\t"default_print_profile": "0.20mm Standard @BBL A1M",\r\n\t"deretract_speed_extruder_change": [\r\n\t\t"0"\r\n\t],\r\n\t"deretraction_speed": [\r\n\t\t"30"\r\n\t],\r\n\t"detect_narrow_internal_solid_infill": "1",\r\n\t"detect_overhang_wall": "1",\r\n\t"detect_thin_wall": "0",\r\n\t"disable_m73": "0",\r\n\t"dont_filter_internal_bridges": "disabled",\r\n\t"dont_slow_down_outer_wall": [\r\n\t\t"0"\r\n\t],\r\n\t"draft_shield": "disabled",\r\n\t"during_print_exhaust_fan_speed": [\r\n\t\t"70"\r\n\t],\r\n\t"elefant_foot_compensation": "0",\r\n\t"elefant_foot_compensation_layers": "1",\r\n\t"elefant_foot_layers_density": "100%",\r\n\t"emit_machine_limits_to_gcode": "1",\r\n\t"enable_arc_fitting": "1",\r\n\t"enable_extra_bridge_layer": "disabled",\r\n\t"enable_filament_dynamic_map": "0",\r\n\t"enable_filament_ramming": "0",\r\n\t"enable_long_retraction_when_cut": "2",\r\n\t"enable_mixed_color_sublayer": "0",\r\n\t"enable_overhang_bridge_fan": [\r\n\t\t"1"\r\n\t],\r\n\t"enable_overhang_speed": [\r\n\t\t"1"\r\n\t],\r\n\t"enable_power_loss_recovery": "printer_configuration",\r\n\t"enable_pre_heating": "0",\r\n\t"enable_pressure_advance": [\r\n\t\t"0"\r\n\t],\r\n\t"enable_prime_tower": "1",\r\n\t"enable_support": "0",\r\n\t"enable_tower_interface_cooldown_during_tower": "0",\r\n\t"enable_tower_interface_features": "0",\r\n\t"enable_wrapping_detection": "0",\r\n\t"enforce_support_layers": "0",\r\n\t"eng_plate_temp": [\r\n\t\t"70"\r\n\t],\r\n\t"eng_plate_temp_initial_layer": [\r\n\t\t"70"\r\n\t],\r\n\t"ensure_vertical_shell_thickness": "ensure_all",\r\n\t"exclude_object": "0",\r\n\t"extra_loading_move": "-2",\r\n\t"extra_perimeters_on_overhangs": "0",\r\n\t"extra_solid_infills": "",\r\n\t"extruder_ams_count": [\r\n\t\t"1#0|4#0",\r\n\t\t""\r\n\t],\r\n\t"extruder_clearance_height_to_lid": "180",\r\n\t"extruder_clearance_height_to_rod": "25",\r\n\t"extruder_clearance_radius": "73",\r\n\t"extruder_colour": [\r\n\t\t"#018001"\r\n\t],\r\n\t"extruder_max_nozzle_count": [\r\n\t\t"1"\r\n\t],\r\n\t"extruder_nozzle_stats": [\r\n\t\t"Standard#1"\r\n\t],\r\n\t"extruder_offset": [\r\n\t\t"0x0"\r\n\t],\r\n\t"extruder_printable_area": [],\r\n\t"extruder_printable_height": [\r\n\t\t"0"\r\n\t],\r\n\t"extruder_type": [\r\n\t\t"Direct Drive"\r\n\t],\r\n\t"extruder_variant_list": [\r\n\t\t"Direct Drive Standard"\r\n\t],\r\n\t"extrusion_rate_smoothing_external_perimeter_only": "0",\r\n\t"fan_cooling_layer_time": [\r\n\t\t"30"\r\n\t],\r\n\t"fan_direction": "undefine",\r\n\t"fan_kickstart": "0",\r\n\t"fan_max_speed": [\r\n\t\t"90"\r\n\t],\r\n\t"fan_min_speed": [\r\n\t\t"40"\r\n\t],\r\n\t"fan_speedup_overhangs": "1",\r\n\t"fan_speedup_time": "0",\r\n\t"farthest_point_timelapse": "0",\r\n\t"filament_adaptive_volumetric_speed": [\r\n\t\t"0"\r\n\t],\r\n\t"filament_adhesiveness_category": [\r\n\t\t"300"\r\n\t],\r\n\t"filament_change_extrusion_role_gcode": [\r\n\t\t""\r\n\t],\r\n\t"filament_change_length": [\r\n\t\t"10"\r\n\t],\r\n\t"filament_change_length_nc": [\r\n\t\t"10"\r\n\t],\r\n\t"filament_colour": [\r\n\t\t"#000000"\r\n\t],\r\n\t"filament_colour_type": [\r\n\t\t"1"\r\n\t],\r\n\t"filament_cooling_before_tower": [\r\n\t\t"10"\r\n\t],\r\n\t"filament_cooling_final_speed": [\r\n\t\t"3.4"\r\n\t],\r\n\t"filament_cooling_initial_speed": [\r\n\t\t"2.2"\r\n\t],\r\n\t"filament_cooling_moves": [\r\n\t\t"4"\r\n\t],\r\n\t"filament_cost": [\r\n\t\t"30"\r\n\t],\r\n\t"filament_density": [\r\n\t\t"1.27"\r\n\t],\r\n\t"filament_deretraction_speed": [\r\n\t\t"nil"\r\n\t],\r\n\t"filament_dev_ams_drying_ams_limitations": [\r\n\t\t"1",\r\n\t\t"0"\r\n\t],\r\n\t"filament_dev_ams_drying_heat_distortion_temperature": [\r\n\t\t"75"\r\n\t],\r\n\t"filament_dev_ams_drying_temperature": [\r\n\t\t"65",\r\n\t\t"65",\r\n\t\t"55",\r\n\t\t"55"\r\n\t],\r\n\t"filament_dev_ams_drying_time": [\r\n\t\t"12",\r\n\t\t"12",\r\n\t\t"12",\r\n\t\t"12"\r\n\t],\r\n\t"filament_dev_chamber_drying_bed_temperature": [\r\n\t\t"80"\r\n\t],\r\n\t"filament_dev_chamber_drying_time": [\r\n\t\t"0"\r\n\t],\r\n\t"filament_dev_drying_cooling_temperature": [\r\n\t\t"55"\r\n\t],\r\n\t"filament_dev_drying_softening_temperature": [\r\n\t\t"60"\r\n\t],\r\n\t"filament_diameter": [\r\n\t\t"1.75"\r\n\t],\r\n\t"filament_end_gcode": [\r\n\t\t"; filament end gcode \\n\\n"\r\n\t],\r\n\t"filament_extruder_compatibility": [\r\n\t\t"0"\r\n\t],\r\n\t"filament_extruder_variant": [\r\n\t\t"Direct Drive Standard"\r\n\t],\r\n\t"filament_flow_ratio": [\r\n\t\t"0.95"\r\n\t],\r\n\t"filament_flush_temp": [\r\n\t\t"0"\r\n\t],\r\n\t"filament_flush_temp_fast": [\r\n\t\t"0"\r\n\t],\r\n\t"filament_flush_volumetric_speed": [\r\n\t\t"0"\r\n\t],\r\n\t"filament_ids": [\r\n\t\t"GFG99"\r\n\t],\r\n\t"filament_ironing_flow": [\r\n\t\t"nil"\r\n\t],\r\n\t"filament_ironing_inset": [\r\n\t\t"nil"\r\n\t],\r\n\t"filament_ironing_spacing": [\r\n\t\t"nil"\r\n\t],\r\n\t"filament_ironing_speed": [\r\n\t\t"nil"\r\n\t],\r\n\t"filament_is_mixed": [\r\n\t\t"0"\r\n\t],\r\n\t"filament_is_support": [\r\n\t\t"0"\r\n\t],\r\n\t"filament_loading_speed": [\r\n\t\t"28"\r\n\t],\r\n\t"filament_loading_speed_start": [\r\n\t\t"3"\r\n\t],\r\n\t"filament_long_retractions_when_cut": [\r\n\t\t"nil"\r\n\t],\r\n\t"filament_map": [\r\n\t\t"1"\r\n\t],\r\n\t"filament_map_2": [\r\n\t\t"1"\r\n\t],\r\n\t"filament_map_mode": "Auto For Flush",\r\n\t"filament_max_volumetric_speed": [\r\n\t\t"8"\r\n\t],\r\n\t"filament_minimal_purge_on_wipe_tower": [\r\n\t\t"15"\r\n\t],\r\n\t"filament_mixed_components": [\r\n\t\t""\r\n\t],\r\n\t"filament_mixed_gradient": [\r\n\t\t"0"\r\n\t],\r\n\t"filament_mixed_gradient_curve": [\r\n\t\t""\r\n\t],\r\n\t"filament_mixed_gradient_per_part": [\r\n\t\t"0"\r\n\t],\r\n\t"filament_mixed_gradient_range": [\r\n\t\t""\r\n\t],\r\n\t"filament_mixed_sublayer_ratios": [\r\n\t\t""\r\n\t],\r\n\t"filament_multi_colour": [\r\n\t\t"#000000"\r\n\t],\r\n\t"filament_multitool_ramming": [\r\n\t\t"0"\r\n\t],\r\n\t"filament_multitool_ramming_flow": [\r\n\t\t"10"\r\n\t],\r\n\t"filament_multitool_ramming_volume": [\r\n\t\t"10"\r\n\t],\r\n\t"filament_notes": [\r\n\t\t""\r\n\t],\r\n\t"filament_nozzle_map": [\r\n\t\t"0"\r\n\t],\r\n\t"filament_plugin_config_overrides": "",\r\n\t"filament_pre_cooling_temperature": [\r\n\t\t"0"\r\n\t],\r\n\t"filament_pre_cooling_temperature_nc": [\r\n\t\t"0"\r\n\t],\r\n\t"filament_preheat_temperature_delta": [\r\n\t\t"0"\r\n\t],\r\n\t"filament_prime_volume": [\r\n\t\t"45"\r\n\t],\r\n\t"filament_prime_volume_nc": [\r\n\t\t"60"\r\n\t],\r\n\t"filament_printable": [\r\n\t\t"3"\r\n\t],\r\n\t"filament_ramming_parameters": [\r\n\t\t"120 100 6.6 6.8 7.2 7.6 7.9 8.2 8.7 9.4 9.9 10.0| 0.05 6.6 0.45 6.8 0.95 7.8 1.45 8.3 1.95 9.7 2.45 10 2.95 7.6 3.45 7.6 3.95 7.6 4.45 7.6 4.95 7.6"\r\n\t],\r\n\t"filament_ramming_travel_time": [\r\n\t\t"0"\r\n\t],\r\n\t"filament_ramming_travel_time_nc": [\r\n\t\t"0"\r\n\t],\r\n\t"filament_ramming_volumetric_speed": [\r\n\t\t"-1"\r\n\t],\r\n\t"filament_ramming_volumetric_speed_nc": [\r\n\t\t"-1"\r\n\t],\r\n\t"filament_retract_after_wipe": [\r\n\t\t"nil"\r\n\t],\r\n\t"filament_retract_before_wipe": [\r\n\t\t"nil"\r\n\t],\r\n\t"filament_retract_length_nc": [\r\n\t\t"nil"\r\n\t],\r\n\t"filament_retract_length_toolchange": [\r\n\t\t"nil"\r\n\t],\r\n\t"filament_retract_lift_above": [\r\n\t\t"nil"\r\n\t],\r\n\t"filament_retract_lift_below": [\r\n\t\t"nil"\r\n\t],\r\n\t"filament_retract_lift_enforce": [\r\n\t\t"nil"\r\n\t],\r\n\t"filament_retract_restart_extra": [\r\n\t\t"nil"\r\n\t],\r\n\t"filament_retract_restart_extra_toolchange": [\r\n\t\t"nil"\r\n\t],\r\n\t"filament_retract_when_changing_layer": [\r\n\t\t"nil"\r\n\t],\r\n\t"filament_retraction_distances_when_cut": [\r\n\t\t"nil"\r\n\t],\r\n\t"filament_retraction_length": [\r\n\t\t"nil"\r\n\t],\r\n\t"filament_retraction_minimum_travel": [\r\n\t\t"nil"\r\n\t],\r\n\t"filament_retraction_speed": [\r\n\t\t"nil"\r\n\t],\r\n\t"filament_self_index": [\r\n\t\t"1"\r\n\t],\r\n\t"filament_settings_id": [\r\n\t\t"Generic PETG @BBL A1M"\r\n\t],\r\n\t"filament_shrink": [\r\n\t\t"100%"\r\n\t],\r\n\t"filament_shrinkage_compensation_z": [\r\n\t\t"100%"\r\n\t],\r\n\t"filament_soluble": [\r\n\t\t"0"\r\n\t],\r\n\t"filament_stamping_distance": [\r\n\t\t"0"\r\n\t],\r\n\t"filament_stamping_loading_speed": [\r\n\t\t"0"\r\n\t],\r\n\t"filament_start_gcode": [\r\n\t\t"; filament start gcode\\n{if (bed_temperature[current_extruder] >80)||(bed_temperature_initial_layer[current_extruder] >80)}M106 P3 S255\\n{elsif (bed_temperature[current_extruder] >60)||(bed_temperature_initial_layer[current_extruder] >60)}M106 P3 S180\\n{endif}\\n\\n{if activate_air_filtration[current_extruder] && support_air_filtration}\\nM106 P3 S{during_print_exhaust_fan_speed_num[current_extruder]} \\n{endif}"\r\n\t],\r\n\t"filament_toolchange_delay": [\r\n\t\t"0"\r\n\t],\r\n\t"filament_tower_interface_pre_extrusion_dist": [\r\n\t\t"10"\r\n\t],\r\n\t"filament_tower_interface_pre_extrusion_length": [\r\n\t\t"0"\r\n\t],\r\n\t"filament_tower_interface_print_temp": [\r\n\t\t"-1"\r\n\t],\r\n\t"filament_tower_interface_purge_volume": [\r\n\t\t"20"\r\n\t],\r\n\t"filament_tower_ironing_area": [\r\n\t\t"4"\r\n\t],\r\n\t"filament_type": [\r\n\t\t"PETG"\r\n\t],\r\n\t"filament_unloading_speed": [\r\n\t\t"90"\r\n\t],\r\n\t"filament_unloading_speed_start": [\r\n\t\t"100"\r\n\t],\r\n\t"filament_vendor": [\r\n\t\t"Generic"\r\n\t],\r\n\t"filament_volume_map": [\r\n\t\t"0"\r\n\t],\r\n\t"filament_wipe": [\r\n\t\t"nil"\r\n\t],\r\n\t"filament_wipe_distance": [\r\n\t\t"nil"\r\n\t],\r\n\t"filament_z_hop": [\r\n\t\t"nil"\r\n\t],\r\n\t"filament_z_hop_types": [\r\n\t\t"nil"\r\n\t],\r\n\t"file_start_gcode": "",\r\n\t"filename_format": "{input_filename_base}_{filament_type[0]}_{print_time}.gcode",\r\n\t"fill_multiline": "1",\r\n\t"filter_out_gap_fill": "0",\r\n\t"first_layer_flow_ratio": "1",\r\n\t"first_layer_print_sequence": [\r\n\t\t"0"\r\n\t],\r\n\t"first_x_layer_fan_speed": [\r\n\t\t"0"\r\n\t],\r\n\t"flashforge_serial_number": "",\r\n\t"flush_into_infill": "0",\r\n\t"flush_into_objects": "0",\r\n\t"flush_into_support": "1",\r\n\t"flush_multiplier": [\r\n\t\t"0.05"\r\n\t],\r\n\t"flush_multiplier_fast": [\r\n\t\t"1.2",\r\n\t\t"1.2"\r\n\t],\r\n\t"flush_volumes_matrix": [\r\n\t\t"0"\r\n\t],\r\n\t"flush_volumes_vector": [\r\n\t\t"140",\r\n\t\t"140"\r\n\t],\r\n\t"from": "project",\r\n\t"full_fan_speed_layer": [\r\n\t\t"0"\r\n\t],\r\n\t"fuzzy_skin": "disabled_fuzzy",\r\n\t"fuzzy_skin_first_layer": "0",\r\n\t"fuzzy_skin_layers_between_ripple_offset": "1",\r\n\t"fuzzy_skin_mode": "displacement",\r\n\t"fuzzy_skin_noise_type": "classic",\r\n\t"fuzzy_skin_octaves": "4",\r\n\t"fuzzy_skin_persistence": "0.5",\r\n\t"fuzzy_skin_point_distance": "0.3",\r\n\t"fuzzy_skin_ripple_offset": "50%",\r\n\t"fuzzy_skin_ripples_per_layer": "15",\r\n\t"fuzzy_skin_scale": "1",\r\n\t"fuzzy_skin_thickness": "0.2",\r\n\t"gap_fill_flow_ratio": "1",\r\n\t"gap_fill_target": "nowhere",\r\n\t"gap_infill_speed": [\r\n\t\t"250"\r\n\t],\r\n\t"gcode_add_line_number": "0",\r\n\t"gcode_comments": "0",\r\n\t"gcode_flavor": "marlin",\r\n\t"gcode_label_objects": "1",\r\n\t"gcode_skip_config_block": "0",\r\n\t"grab_length": [\r\n\t\t"17.4"\r\n\t],\r\n\t"group_algo_with_time": "0",\r\n\t"gyroid_optimized": "0",\r\n\t"has_filament_switcher": "0",\r\n\t"has_scarf_joint_seam": "0",\r\n\t"head_wrap_detect_zone": [\r\n\t\t"156x152",\r\n\t\t"180x152",\r\n\t\t"180x180",\r\n\t\t"156x180"\r\n\t],\r\n\t"high_current_on_filament_swap": "0",\r\n\t"hole_to_polyhole": "0",\r\n\t"hole_to_polyhole_max_edges": "50",\r\n\t"hole_to_polyhole_threshold": "0.01",\r\n\t"hole_to_polyhole_twisted": "1",\r\n\t"host_type": "octoprint",\r\n\t"hot_plate_temp": [\r\n\t\t"70"\r\n\t],\r\n\t"hot_plate_temp_initial_layer": [\r\n\t\t"70"\r\n\t],\r\n\t"hotend_cooling_rate": [\r\n\t\t"2"\r\n\t],\r\n\t"hotend_heating_rate": [\r\n\t\t"2"\r\n\t],\r\n\t"idle_temperature": [\r\n\t\t"0"\r\n\t],\r\n\t"independent_support_layer_height": "1",\r\n\t"infill_anchor": "400%",\r\n\t"infill_anchor_max": "20",\r\n\t"infill_combination": "0",\r\n\t"infill_combination_max_layer_height": "100%",\r\n\t"infill_direction": "45",\r\n\t"infill_jerk": [\r\n\t\t"9"\r\n\t],\r\n\t"infill_lock_depth": "1",\r\n\t"infill_overhang_angle": "60",\r\n\t"infill_shift_step": "0.4",\r\n\t"infill_wall_overlap": "15%",\r\n\t"initial_layer_acceleration": [\r\n\t\t"500"\r\n\t],\r\n\t"initial_layer_fan_speed": [\r\n\t\t"-1"\r\n\t],\r\n\t"initial_layer_infill_speed": [\r\n\t\t"105"\r\n\t],\r\n\t"initial_layer_jerk": [\r\n\t\t"9"\r\n\t],\r\n\t"initial_layer_line_width": "0.5",\r\n\t"initial_layer_min_bead_width": "85%",\r\n\t"initial_layer_print_height": "0.2",\r\n\t"initial_layer_speed": [\r\n\t\t"50"\r\n\t],\r\n\t"initial_layer_travel_acceleration": [\r\n\t\t"6000"\r\n\t],\r\n\t"initial_layer_travel_jerk": [\r\n\t\t"100%"\r\n\t],\r\n\t"initial_layer_travel_speed": [\r\n\t\t"100%"\r\n\t],\r\n\t"inner_wall_acceleration": [\r\n\t\t"0"\r\n\t],\r\n\t"inner_wall_filament_id": "0",\r\n\t"inner_wall_flow_ratio": "1",\r\n\t"inner_wall_jerk": [\r\n\t\t"9"\r\n\t],\r\n\t"inner_wall_line_width": "0.45",\r\n\t"inner_wall_speed": [\r\n\t\t"300"\r\n\t],\r\n\t"input_shaping_damp_x": "0.1",\r\n\t"input_shaping_damp_y": "0.1",\r\n\t"input_shaping_emit": "0",\r\n\t"input_shaping_freq_x": "0",\r\n\t"input_shaping_freq_y": "0",\r\n\t"input_shaping_type": "Default",\r\n\t"interface_shells": "0",\r\n\t"interlocking_beam": "0",\r\n\t"interlocking_beam_layer_count": "2",\r\n\t"interlocking_beam_width": "0.8",\r\n\t"interlocking_boundary_avoidance": "2",\r\n\t"interlocking_depth": "2",\r\n\t"interlocking_orientation": "22.5",\r\n\t"internal_bridge_angle": "0",\r\n\t"internal_bridge_density": "100%",\r\n\t"internal_bridge_fan_speed": [\r\n\t\t"-1"\r\n\t],\r\n\t"internal_bridge_flow": "1",\r\n\t"internal_bridge_speed": [\r\n\t\t"150%"\r\n\t],\r\n\t"internal_solid_filament_id": "0",\r\n\t"internal_solid_infill_acceleration": [\r\n\t\t"100%"\r\n\t],\r\n\t"internal_solid_infill_flow_ratio": "1",\r\n\t"internal_solid_infill_line_width": "0.42",\r\n\t"internal_solid_infill_pattern": "monotonic",\r\n\t"internal_solid_infill_speed": [\r\n\t\t"250"\r\n\t],\r\n\t"ironing_angle": "0",\r\n\t"ironing_angle_fixed": "0",\r\n\t"ironing_expansion": "0",\r\n\t"ironing_fan_speed": [\r\n\t\t"-1"\r\n\t],\r\n\t"ironing_flow": "10%",\r\n\t"ironing_inset": "0.21",\r\n\t"ironing_pattern": "rectilinear",\r\n\t"ironing_spacing": "0.15",\r\n\t"ironing_speed": "30",\r\n\t"ironing_type": "no ironing",\r\n\t"is_infill_first": "0",\r\n\t"lateral_lattice_angle_1": "-45",\r\n\t"lateral_lattice_angle_2": "45",\r\n\t"layer_change_gcode": "; layer num/total_layer_count: {layer_num+1}/[total_layer_count]\\n; update layer progress\\nM73 L{layer_num+1}\\nM991 S0 P{layer_num} ;notify layer change\\n",\r\n\t"layer_height": "0.2",\r\n\t"lightning_overhang_angle": "45",\r\n\t"lightning_prune_angle": "45",\r\n\t"lightning_straightening_angle": "45",\r\n\t"line_width": "0.42",\r\n\t"long_retractions_when_cut": [\r\n\t\t"0"\r\n\t],\r\n\t"long_retractions_when_ec": [\r\n\t\t"0"\r\n\t],\r\n\t"machine_bed_mass_Y": "0",\r\n\t"machine_end_gcode": ";===== date: 20231229 =====================\\n;turn off nozzle clog detect\\nG392 S0\\n\\nM400 ; wait for buffer to clear\\nG92 E0 ; zero the extruder\\nG1 E-0.8 F1800 ; retract\\nG1 Z{max_layer_z + 0.5} F900 ; lower z a little\\nG1 X0 Y{first_layer_center_no_wipe_tower[1]} F18000 ; move to safe pos\\nG1 X-13.0 F3000 ; move to safe pos\\n{if !spiral_mode && print_sequence != \\"by object\\"}\\nM1002 judge_flag timelapse_record_flag\\nM622 J1\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM991 S0 P-1 ;end timelapse at safe pos\\nM623\\n{endif}\\n\\nM140 S0 ; turn off bed\\nM106 S0 ; turn off fan\\nM106 P2 S0 ; turn off remote part cooling fan\\nM106 P3 S0 ; turn off chamber cooling fan\\n\\n;G1 X27 F15000 ; wipe\\n\\n; pull back filament to AMS\\nM620 S255\\nG1 X181 F12000\\nT255\\nG1 X0 F18000\\nG1 X-13.0 F3000\\nG1 X0 F18000 ; wipe\\nM621 S255\\n\\nM104 S0 ; turn off hotend\\n\\nM400 ; wait all motion done\\nM17 S\\nM17 Z0.4 ; lower z motor current to reduce impact if there is something in the bottom\\n{if (max_layer_z + 100.0) < 180}\\n    G1 Z{max_layer_z + 100.0} F600\\n    G1 Z{max_layer_z +98.0}\\n{else}\\n    G1 Z180 F600\\n    G1 Z180\\n{endif}\\nM400 P100\\nM17 R ; restore z current\\n\\nG90\\nG1 X-13 Y180 F3600\\n\\nG91\\nG1 Z-1 F600\\nG90\\nM83\\n\\nM220 S100  ; Reset feedrate magnitude\\nM201.2 K1.0 ; Reset acc magnitude\\nM73.2   R1.0 ;Reset left time magnitude\\nM1002 set_gcode_claim_speed_level : 0\\n\\n;=====printer finish  sound=========\\nM17\\nM400 S1\\nM1006 S1\\nM1006 A0 B20 L100 C37 D20 M100 E42 F20 N100\\nM1006 A0 B10 L100 C44 D10 M100 E44 F10 N100\\nM1006 A0 B10 L100 C46 D10 M100 E46 F10 N100\\nM1006 A44 B20 L100 C39 D20 M100 E48 F20 N100\\nM1006 A0 B10 L100 C44 D10 M100 E44 F10 N100\\nM1006 A0 B10 L100 C0 D10 M100 E0 F10 N100\\nM1006 A0 B10 L100 C39 D10 M100 E39 F10 N100\\nM1006 A0 B10 L100 C0 D10 M100 E0 F10 N100\\nM1006 A0 B10 L100 C44 D10 M100 E44 F10 N100\\nM1006 A0 B10 L100 C0 D10 M100 E0 F10 N100\\nM1006 A0 B10 L100 C39 D10 M100 E39 F10 N100\\nM1006 A0 B10 L100 C0 D10 M100 E0 F10 N100\\nM1006 A44 B10 L100 C0 D10 M100 E48 F10 N100\\nM1006 A0 B10 L100 C0 D10 M100 E0 F10 N100\\nM1006 A44 B20 L100 C41 D20 M100 E49 F20 N100\\nM1006 A0 B20 L100 C0 D20 M100 E0 F20 N100\\nM1006 A0 B20 L100 C37 D20 M100 E37 F20 N100\\nM1006 W\\n;=====printer finish  sound=========\\nM400 S1\\nM18 X Y Z\\n",\r\n\t"machine_hotend_change_time": "0",\r\n\t"machine_load_filament_time": "28",\r\n\t"machine_max_acceleration_e": [\r\n\t\t"5000",\r\n\t\t"5000"\r\n\t],\r\n\t"machine_max_acceleration_extruding": [\r\n\t\t"20000",\r\n\t\t"20000"\r\n\t],\r\n\t"machine_max_acceleration_retracting": [\r\n\t\t"5000",\r\n\t\t"5000"\r\n\t],\r\n\t"machine_max_acceleration_travel": [\r\n\t\t"9000",\r\n\t\t"9000"\r\n\t],\r\n\t"machine_max_acceleration_x": [\r\n\t\t"20000",\r\n\t\t"20000"\r\n\t],\r\n\t"machine_max_acceleration_y": [\r\n\t\t"20000",\r\n\t\t"20000"\r\n\t],\r\n\t"machine_max_acceleration_z": [\r\n\t\t"1500",\r\n\t\t"1500"\r\n\t],\r\n\t"machine_max_force_Y": "0",\r\n\t"machine_max_jerk_e": [\r\n\t\t"3",\r\n\t\t"3"\r\n\t],\r\n\t"machine_max_jerk_x": [\r\n\t\t"9",\r\n\t\t"9"\r\n\t],\r\n\t"machine_max_jerk_y": [\r\n\t\t"9",\r\n\t\t"9"\r\n\t],\r\n\t"machine_max_jerk_z": [\r\n\t\t"5",\r\n\t\t"5"\r\n\t],\r\n\t"machine_max_junction_deviation": [\r\n\t\t"0.01",\r\n\t\t"0.01"\r\n\t],\r\n\t"machine_max_printed_mass": "0",\r\n\t"machine_max_speed_e": [\r\n\t\t"30",\r\n\t\t"30"\r\n\t],\r\n\t"machine_max_speed_x": [\r\n\t\t"500",\r\n\t\t"200"\r\n\t],\r\n\t"machine_max_speed_y": [\r\n\t\t"500",\r\n\t\t"200"\r\n\t],\r\n\t"machine_max_speed_z": [\r\n\t\t"30",\r\n\t\t"30"\r\n\t],\r\n\t"machine_min_extruding_rate": [\r\n\t\t"0",\r\n\t\t"0"\r\n\t],\r\n\t"machine_min_travel_rate": [\r\n\t\t"0",\r\n\t\t"0"\r\n\t],\r\n\t"machine_pause_gcode": "M400 U1",\r\n\t"machine_prepare_compensation_time": "260",\r\n\t"machine_start_gcode": ";===== machine: A1 mini =========================\\n;===== date: 20250822 ==================\\n\\n;===== start to heat heatbead&hotend==========\\nM1002 gcode_claim_action : 2\\nM1002 set_filament_type:{filament_type[initial_no_support_extruder]}\\nM104 S170\\nM140 S[bed_temperature_initial_layer_single]\\nG392 S0 ;turn off clog detect\\nM9833.2\\n;=====start printer sound ===================\\nM17\\nM400 S1\\nM1006 S1\\nM1006 A0 B0 L100 C37 D10 M100 E37 F10 N100\\nM1006 A0 B0 L100 C41 D10 M100 E41 F10 N100\\nM1006 A0 B0 L100 C44 D10 M100 E44 F10 N100\\nM1006 A0 B10 L100 C0 D10 M100 E0 F10 N100\\nM1006 A43 B10 L100 C39 D10 M100 E46 F10 N100\\nM1006 A0 B0 L100 C0 D10 M100 E0 F10 N100\\nM1006 A0 B0 L100 C39 D10 M100 E43 F10 N100\\nM1006 A0 B0 L100 C0 D10 M100 E0 F10 N100\\nM1006 A0 B0 L100 C41 D10 M100 E41 F10 N100\\nM1006 A0 B0 L100 C44 D10 M100 E44 F10 N100\\nM1006 A0 B0 L100 C49 D10 M100 E49 F10 N100\\nM1006 A0 B0 L100 C0 D10 M100 E0 F10 N100\\nM1006 A44 B10 L100 C39 D10 M100 E48 F10 N100\\nM1006 A0 B0 L100 C0 D10 M100 E0 F10 N100\\nM1006 A0 B0 L100 C39 D10 M100 E44 F10 N100\\nM1006 A0 B0 L100 C0 D10 M100 E0 F10 N100\\nM1006 A43 B10 L100 C39 D10 M100 E46 F10 N100\\nM1006 W\\nM18\\n;=====avoid end stop =================\\nG91\\nG380 S2 Z30 F1200\\nG380 S3 Z-20 F1200\\nG1 Z5 F1200\\nG90\\n\\n;===== reset machine status =================\\nM204 S6000\\n\\nM630 S0 P0\\nG91\\nM17 Z0.3 ; lower the z-motor current\\n\\nG90\\nM17 X0.7 Y0.9 Z0.5 ; reset motor current to default\\nM960 S5 P1 ; turn on logo lamp\\nG90\\nM83\\nM220 S100 ;Reset Feedrate\\nM221 S100 ;Reset Flowrate\\nM73.2   R1.0 ;Reset left time magnitude\\n;====== cog noise reduction=================\\nM982.2 S1 ; turn on cog noise reduction\\n\\n;===== prepare print temperature and material ==========\\nM400\\nM18\\nM109 S100 H170\\nM104 S170\\nM400\\nM17\\nM400\\nG28 X\\n\\nM211 X0 Y0 Z0 ;turn off soft endstop ; turn off soft endstop to prevent protential logic problem\\n\\nM975 S1 ; turn on\\n\\nG1 X0.0 F30000\\nG1 X-13.5 F3000\\n\\nM620 M ;enable remap\\nM620 S[initial_no_support_extruder]A   ; switch material if AMS exist\\n    G392 S0 ;turn on clog detect\\n    M1002 gcode_claim_action : 4\\n    M400\\n    M1002 set_filament_type:UNKNOWN\\n    M109 S[nozzle_temperature_initial_layer]\\n    M104 S250\\n    M400\\n    T[initial_no_support_extruder]\\n    G1 X-13.5 F3000\\n    M400\\n    M620.1 E F{flush_volumetric_speeds[initial_no_support_extruder]/2.4053*60} T{flush_temperatures[initial_no_support_extruder]}\\n    M109 S250 ;set nozzle to common flush temp\\n    M106 P1 S0\\n    G92 E0\\n    G1 E50 F200\\n    M400\\n    M1002 set_filament_type:{filament_type[initial_no_support_extruder]}\\n    M104 S{flush_temperatures[initial_no_support_extruder]}\\n    G92 E0\\n    G1 E50 F{flush_volumetric_speeds[initial_no_support_extruder]/2.4053*60}\\n    M400\\n    M106 P1 S178\\n    G92 E0\\n    G1 E5 F{flush_volumetric_speeds[initial_no_support_extruder]/2.4053*60}\\n    M109 S{nozzle_temperature_initial_layer[initial_no_support_extruder]-20} ; drop nozzle temp, make filament shink a bit\\n    M104 S{nozzle_temperature_initial_layer[initial_no_support_extruder]-40}\\n    G92 E0\\n    G1 E-0.5 F300\\n\\n    G1 X0 F30000\\n    G1 X-13.5 F3000\\n    G1 X0 F30000 ;wipe and shake\\n    G1 X-13.5 F3000\\n    G1 X0 F12000 ;wipe and shake\\n    G1 X0 F30000\\n    G1 X-13.5 F3000\\n    M109 S{nozzle_temperature_initial_layer[initial_no_support_extruder]-40}\\n    G392 S0 ;turn off clog detect\\nM621 S[initial_no_support_extruder]A\\n\\nM400\\nM106 P1 S0\\n;===== prepare print temperature and material end =====\\n\\n\\n;===== mech mode fast check============================\\nM1002 gcode_claim_action : 3\\nG0 X25 Y175 F20000 ; find a soft place to home\\n;M104 S0\\nG28 Z P0 T300; home z with low precision,permit 300deg temperature\\nG29.2 S0 ; turn off ABL\\nM104 S170\\n\\n; build plate detect\\nM1002 judge_flag build_plate_detect_flag\\nM622 S1\\n  G39.4\\n  M400\\nM623\\n\\nG1 Z5 F3000\\nG1 X90 Y-1 F30000\\nM400 P200\\nM970.3 Q1 A7 K0 O2\\nM974 Q1 S2 P0\\n\\nG1 X90 Y0 Z5 F30000\\nM400 P200\\nM970 Q0 A10 B50 C90 H15 K0 M20 O3\\nM974 Q0 S2 P0\\n\\nM975 S1\\nG1 F30000\\nG1 X-1 Y10\\nG28 X ; re-home XY\\n\\n;===== wipe nozzle ===============================\\nM1002 gcode_claim_action : 14\\nM975 S1\\n\\nM104 S170 ; set temp down to heatbed acceptable\\nM106 S255 ; turn on fan (G28 has turn off fan)\\nM211 S; push soft endstop status\\nM211 X0 Y0 Z0 ;turn off Z axis endstop\\n\\nM83\\nG1 E-1 F500\\nG90\\nM83\\n\\nM109 S170\\nM104 S140\\nG0 X90 Y-4 F30000\\nG380 S3 Z-5 F1200\\nG1 Z2 F1200\\nG1 X91 F10000\\nG380 S3 Z-5 F1200\\nG1 Z2 F1200\\nG1 X92 F10000\\nG380 S3 Z-5 F1200\\nG1 Z2 F1200\\nG1 X93 F10000\\nG380 S3 Z-5 F1200\\nG1 Z2 F1200\\nG1 X94 F10000\\nG380 S3 Z-5 F1200\\nG1 Z2 F1200\\nG1 X95 F10000\\nG380 S3 Z-5 F1200\\nG1 Z2 F1200\\nG1 X96 F10000\\nG380 S3 Z-5 F1200\\nG1 Z2 F1200\\nG1 X97 F10000\\nG380 S3 Z-5 F1200\\nG1 Z2 F1200\\nG1 X98 F10000\\nG380 S3 Z-5 F1200\\nG1 Z2 F1200\\nG1 X99 F10000\\nG380 S3 Z-5 F1200\\nG1 Z2 F1200\\nG1 X99 F10000\\nG380 S3 Z-5 F1200\\nG1 Z2 F1200\\nG1 X99 F10000\\nG380 S3 Z-5 F1200\\nG1 Z2 F1200\\nG1 X99 F10000\\nG380 S3 Z-5 F1200\\nG1 Z2 F1200\\nG1 X99 F10000\\nG380 S3 Z-5 F1200\\n\\nG1 Z5 F30000\\n;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;\\nG1 X25 Y175 F30000.1 ;Brush material\\nG1 Z0.2 F30000.1\\nG1 Y185\\nG91\\nG1 X-30 F30000\\nG1 Y-2\\nG1 X27\\nG1 Y1.5\\nG1 X-28\\nG1 Y-2\\nG1 X30\\nG1 Y1.5\\nG1 X-30\\nG90\\nM83\\n\\nG1 Z5 F3000\\nG0 X50 Y175 F20000 ; find a soft place to home\\nG28 Z P0 T300; home z with low precision, permit 300deg temperature\\nG29.2 S0 ; turn off ABL\\n\\nG0 X85 Y185 F10000 ;move to exposed steel surface and stop the nozzle\\nG0 Z-1.01 F10000\\nG91\\n\\nG2 I1 J0 X2 Y0 F2000.1\\nG2 I-0.75 J0 X-1.5\\nG2 I1 J0 X2\\nG2 I-0.75 J0 X-1.5\\nG2 I1 J0 X2\\nG2 I-0.75 J0 X-1.5\\nG2 I1 J0 X2\\nG2 I-0.75 J0 X-1.5\\nG2 I1 J0 X2\\nG2 I-0.75 J0 X-1.5\\nG2 I1 J0 X2\\nG2 I-0.75 J0 X-1.5\\nG2 I1 J0 X2\\nG2 I-0.75 J0 X-1.5\\nG2 I1 J0 X2\\nG2 I-0.75 J0 X-1.5\\nG2 I1 J0 X2\\nG2 I-0.75 J0 X-1.5\\nG2 I1 J0 X2\\nG2 I-0.75 J0 X-1.5\\n\\nG90\\nG1 Z5 F30000\\nG1 X25 Y175 F30000.1 ;Brush material\\nG1 Z0.2 F30000.1\\nG1 Y185\\nG91\\nG1 X-30 F30000\\nG1 Y-2\\nG1 X27\\nG1 Y1.5\\nG1 X-28\\nG1 Y-2\\nG1 X30\\nG1 Y1.5\\nG1 X-30\\nG90\\nM83\\n\\nG1 Z5\\nG0 X55 Y175 F20000 ; find a soft place to home\\nG28 Z P0 T300; home z with low precision, permit 300deg temperature\\nG29.2 S0 ; turn off ABL\\n\\nG1 Z10\\nG1 X85 Y185\\nG1 Z-1.01\\nG1 X95\\nG1 X90\\n\\nM211 R; pop softend status\\n\\nM106 S0 ; turn off fan , too noisy\\n;===== wipe nozzle end ================================\\n\\n\\n;===== wait heatbed  ====================\\nM1002 gcode_claim_action : 2\\nM104 S0\\nM190 S[bed_temperature_initial_layer_single];set bed temp\\nM109 S140\\n\\nG1 Z5 F3000\\nG29.2 S1\\nG1 X10 Y10 F20000\\n\\n;===== bed leveling ==================================\\n;M1002 set_flag g29_before_print_flag=1\\nM1002 judge_flag g29_before_print_flag\\nM622 J1\\n    M1002 gcode_claim_action : 1\\n    G29 A1 X{first_layer_print_min[0]} Y{first_layer_print_min[1]} I{first_layer_print_size[0]} J{first_layer_print_size[1]}\\n    M400\\n    M500 ; save cali data\\nM623\\n;===== bed leveling end ================================\\n\\n;===== home after wipe mouth============================\\nM1002 judge_flag g29_before_print_flag\\nM622 J0\\n\\n    M1002 gcode_claim_action : 13\\n    G28 T145\\n\\nM623\\n\\n;===== home after wipe mouth end =======================\\n\\nM975 S1 ; turn on vibration supression\\n;===== nozzle load line ===============================\\nM975 S1\\nG90\\nM83\\nT1000\\n\\nG1 X-13.5 Y0 Z10 F10000\\nG1 E1.2 F500\\nM400\\nM1002 set_filament_type:UNKNOWN\\nM109 S{nozzle_temperature[initial_extruder]}\\nM400\\n\\nM412 S1 ;    ===turn on  filament runout detection===\\nM400 P10\\n\\nG392 S0 ;turn on clog detect\\n\\nM620.3 W1; === turn on filament tangle detection===\\nM400 S2\\n\\nM1002 set_filament_type:{filament_type[initial_no_support_extruder]}\\n;M1002 set_flag extrude_cali_flag=1\\nM1002 judge_flag extrude_cali_flag\\nM622 J1\\n    M1002 gcode_claim_action : 8\\n    \\n    M400\\n    M900 K0.0 L1000.0 M1.0\\n    G90\\n    M83\\n    G0 X68 Y-4 F30000\\n    G0 Z0.3 F18000 ;Move to start position\\n    M400\\n    G0 X88 E10  F{outer_wall_volumetric_speed/(24/20)    * 60}\\n    G0 X93 E.3742  F{outer_wall_volumetric_speed/(0.3*0.5)/4     * 60}\\n    G0 X98 E.3742  F{outer_wall_volumetric_speed/(0.3*0.5)     * 60}\\n    G0 X103 E.3742  F{outer_wall_volumetric_speed/(0.3*0.5)/4     * 60}\\n    G0 X108 E.3742  F{outer_wall_volumetric_speed/(0.3*0.5)     * 60}\\n    G0 X113 E.3742  F{outer_wall_volumetric_speed/(0.3*0.5)/4     * 60}\\n    G0 Y0 Z0 F20000\\n    M400\\n    \\n    G1 X-13.5 Y0 Z10 F10000\\n    M400\\n    \\n    G1 E10 F{outer_wall_volumetric_speed/2.4*60}\\n    M983 F{outer_wall_volumetric_speed/2.4} A0.3 H[nozzle_diameter]; cali dynamic extrusion compensation\\n    M106 P1 S178\\n    M400 S7\\n    G1 X0 F18000\\n    G1 X-13.5 F3000\\n    G1 X0 F18000 ;wipe and shake\\n    G1 X-13.5 F3000\\n    G1 X0 F12000 ;wipe and shake\\n    G1 X-13.5 F3000\\n    M400\\n    M106 P1 S0\\n\\n    M1002 judge_last_extrude_cali_success\\n    M622 J0\\n        M983 F{outer_wall_volumetric_speed/2.4} A0.3 H[nozzle_diameter]; cali dynamic extrusion compensation\\n        M106 P1 S178\\n        M400 S7\\n        G1 X0 F18000\\n        G1 X-13.5 F3000\\n        G1 X0 F18000 ;wipe and shake\\n        G1 X-13.5 F3000\\n        G1 X0 F12000 ;wipe and shake\\n        M400\\n        M106 P1 S0\\n    M623\\n    \\n    G1 X-13.5 F3000\\n    M400\\n    M984 A0.1 E1 S1 F{outer_wall_volumetric_speed/2.4} H[nozzle_diameter]\\n    M106 P1 S178\\n    M400 S7\\n    G1 X0 F18000\\n    G1 X-13.5 F3000\\n    G1 X0 F18000 ;wipe and shake\\n    G1 X-13.5 F3000\\n    G1 X0 F12000 ;wipe and shake\\n    G1 X-13.5 F3000\\n    M400\\n    M106 P1 S0\\n\\nM623 ; end of \\"draw extrinsic para cali paint\\"\\n\\n;===== extrude cali test ===============================\\nM104 S{nozzle_temperature_initial_layer[initial_extruder]}\\nG90\\nM83\\nG0 X68 Y-2.5 F30000\\nG0 Z0.3 F18000 ;Move to start position\\nG0 X88 E10  F{outer_wall_volumetric_speed/(24/20)    * 60}\\nG0 X93 E.3742  F{outer_wall_volumetric_speed/(0.3*0.5)/4     * 60}\\nG0 X98 E.3742  F{outer_wall_volumetric_speed/(0.3*0.5)     * 60}\\nG0 X103 E.3742  F{outer_wall_volumetric_speed/(0.3*0.5)/4     * 60}\\nG0 X108 E.3742  F{outer_wall_volumetric_speed/(0.3*0.5)     * 60}\\nG0 X113 E.3742  F{outer_wall_volumetric_speed/(0.3*0.5)/4     * 60}\\nG0 X115 Z0 F20000\\nG0 Z5\\nM400\\n\\n;========turn off light and wait extrude temperature =============\\nM1002 gcode_claim_action : 0\\n\\nM400 ; wait all motion done before implement the emprical L parameters\\n\\n;===== for Textured PEI Plate , lower the nozzle as the nozzle was touching topmost of the texture when homing ==\\n;curr_bed_type={curr_bed_type}\\n{if curr_bed_type==\\"Textured PEI Plate\\"}\\nG29.1 Z{-0.02} ; for Textured PEI Plate\\n{endif}\\n\\nM960 S1 P0 ; turn off laser\\nM960 S2 P0 ; turn off laser\\nM106 S0 ; turn off fan\\nM106 P2 S0 ; turn off big fan\\nM106 P3 S0 ; turn off chamber fan\\n\\nM975 S1 ; turn on mech mode supression\\nG90\\nM83\\nT1000\\n\\nM211 X0 Y0 Z0 ;turn off soft endstop\\nM1007 S1\\n\\n\\n\\n",\r\n\t"machine_tool_change_time": "0",\r\n\t"machine_unload_filament_time": "34",\r\n\t"make_overhang_printable": "0",\r\n\t"make_overhang_printable_angle": "55",\r\n\t"make_overhang_printable_hole_size": "0",\r\n\t"manual_filament_change": "0",\r\n\t"master_extruder_id": "1",\r\n\t"max_bridge_length": "0",\r\n\t"max_layer_height": [\r\n\t\t"0.28"\r\n\t],\r\n\t"max_resonance_avoidance_speed": "120",\r\n\t"max_travel_detour_distance": "0",\r\n\t"max_volumetric_extrusion_rate_slope": "0",\r\n\t"max_volumetric_extrusion_rate_slope_segment_length": "3",\r\n\t"min_bead_width": "85%",\r\n\t"min_feature_size": "25%",\r\n\t"min_layer_height": [\r\n\t\t"0.08"\r\n\t],\r\n\t"min_length_factor": "0.5",\r\n\t"min_resonance_avoidance_speed": "70",\r\n\t"min_skirt_length": "0",\r\n\t"min_width_top_surface": "300%",\r\n\t"minimum_sparse_infill_area": "15",\r\n\t"mmu_segmented_region_interlocking_depth": "0",\r\n\t"mmu_segmented_region_max_width": "0",\r\n\t"name": "project_settings",\r\n\t"notes": "",\r\n\t"nozzle_diameter": [\r\n\t\t"0.4"\r\n\t],\r\n\t"nozzle_flush_dataset": [\r\n\t\t"0"\r\n\t],\r\n\t"nozzle_height": "4.76",\r\n\t"nozzle_hrc": "0",\r\n\t"nozzle_temperature": [\r\n\t\t"255"\r\n\t],\r\n\t"nozzle_temperature_initial_layer": [\r\n\t\t"255"\r\n\t],\r\n\t"nozzle_temperature_range_high": [\r\n\t\t"270"\r\n\t],\r\n\t"nozzle_temperature_range_low": [\r\n\t\t"220"\r\n\t],\r\n\t"nozzle_type": [\r\n\t\t"stainless_steel"\r\n\t],\r\n\t"nozzle_volume": [\r\n\t\t"92"\r\n\t],\r\n\t"nozzle_volume_type": [\r\n\t\t"Standard"\r\n\t],\r\n\t"only_one_wall_first_layer": "0",\r\n\t"only_one_wall_top": "1",\r\n\t"ooze_prevention": "0",\r\n\t"other_layers_print_sequence": [\r\n\t\t"0"\r\n\t],\r\n\t"other_layers_print_sequence_nums": "0",\r\n\t"outer_wall_acceleration": [\r\n\t\t"5000"\r\n\t],\r\n\t"outer_wall_filament_id": "0",\r\n\t"outer_wall_flow_ratio": "1",\r\n\t"outer_wall_jerk": [\r\n\t\t"9"\r\n\t],\r\n\t"outer_wall_line_width": "0.42",\r\n\t"outer_wall_speed": [\r\n\t\t"200"\r\n\t],\r\n\t"overhang_1_4_speed": [\r\n\t\t"0"\r\n\t],\r\n\t"overhang_2_4_speed": [\r\n\t\t"50"\r\n\t],\r\n\t"overhang_3_4_speed": [\r\n\t\t"30"\r\n\t],\r\n\t"overhang_4_4_speed": [\r\n\t\t"10"\r\n\t],\r\n\t"overhang_fan_speed": [\r\n\t\t"90"\r\n\t],\r\n\t"overhang_fan_threshold": [\r\n\t\t"10%"\r\n\t],\r\n\t"overhang_flow_ratio": "1",\r\n\t"overhang_reverse": "0",\r\n\t"overhang_reverse_internal_only": "0",\r\n\t"overhang_reverse_threshold": "50%",\r\n\t"parallel_printheads_bed_exclude_areas": [],\r\n\t"parallel_printheads_count": "1",\r\n\t"parking_pos_retraction": "92",\r\n\t"part_cooling_fan_min_pwm": "0",\r\n\t"pellet_flow_coefficient": [\r\n\t\t"0.4157"\r\n\t],\r\n\t"pellet_modded_printer": "0",\r\n\t"physical_extruder_map": [\r\n\t\t"0"\r\n\t],\r\n\t"post_process": [],\r\n\t"precise_outer_wall": "1",\r\n\t"precise_z_height": "0",\r\n\t"preferred_orientation": "0",\r\n\t"preheat_steps": "1",\r\n\t"preheat_time": "30",\r\n\t"pressure_advance": [\r\n\t\t"0.02"\r\n\t],\r\n\t"prime_tower_brim_width": "3",\r\n\t"prime_tower_enable_framework": "0",\r\n\t"prime_tower_flat_ironing": "0",\r\n\t"prime_tower_infill_gap": "150%",\r\n\t"prime_tower_skip_points": "1",\r\n\t"prime_tower_width": "35",\r\n\t"prime_volume": "45",\r\n\t"prime_volume_mode": "Default",\r\n\t"print_compatible_printers": [\r\n\t\t"Bambu Lab A1 mini 0.4 nozzle"\r\n\t],\r\n\t"print_extruder_id": [\r\n\t\t"1"\r\n\t],\r\n\t"print_extruder_variant": [\r\n\t\t"Direct Drive Standard"\r\n\t],\r\n\t"print_flow_ratio": "1",\r\n\t"print_order": "default",\r\n\t"print_plugin_config_overrides": "",\r\n\t"print_sequence": "by layer",\r\n\t"print_settings_id": "0.20mm Standard @BBL A1M",\r\n\t"printable_area": [\r\n\t\t"0x0",\r\n\t\t"180x0",\r\n\t\t"180x180",\r\n\t\t"0x180"\r\n\t],\r\n\t"printable_height": "180",\r\n\t"printer_agent": "",\r\n\t"printer_extruder_id": [\r\n\t\t"1"\r\n\t],\r\n\t"printer_extruder_variant": [\r\n\t\t"Direct Drive Standard"\r\n\t],\r\n\t"printer_model": "Bambu Lab A1 mini",\r\n\t"printer_notes": "",\r\n\t"printer_plugin_config_overrides": "",\r\n\t"printer_settings_id": "Bambu Lab A1 mini 0.4 nozzle",\r\n\t"printer_structure": "i3",\r\n\t"printer_technology": "FFF",\r\n\t"printer_variant": "0.4",\r\n\t"printhost_authorization_type": "key",\r\n\t"printhost_ssl_ignore_revoke": "0",\r\n\t"printing_by_object_gcode": "",\r\n\t"process_change_extrusion_role_gcode": "",\r\n\t"purge_in_prime_tower": "0",\r\n\t"raft_contact_distance": "0.1",\r\n\t"raft_expansion": "1.5",\r\n\t"raft_first_layer_density": "90%",\r\n\t"raft_first_layer_expansion": "2",\r\n\t"raft_layers": "0",\r\n\t"reduce_crossing_wall": "0",\r\n\t"reduce_fan_stop_start_freq": [\r\n\t\t"1"\r\n\t],\r\n\t"reduce_infill_retraction": "1",\r\n\t"relative_bridge_angle": "0",\r\n\t"required_nozzle_HRC": [\r\n\t\t"3"\r\n\t],\r\n\t"resolution": "0.012",\r\n\t"resonance_avoidance": "0",\r\n\t"retract_after_wipe": [\r\n\t\t"0%"\r\n\t],\r\n\t"retract_before_wipe": [\r\n\t\t"0%"\r\n\t],\r\n\t"retract_length_toolchange": [\r\n\t\t"2"\r\n\t],\r\n\t"retract_lift_above": [\r\n\t\t"0"\r\n\t],\r\n\t"retract_lift_below": [\r\n\t\t"179"\r\n\t],\r\n\t"retract_lift_enforce": [\r\n\t\t"All Surfaces"\r\n\t],\r\n\t"retract_restart_extra": [\r\n\t\t"0"\r\n\t],\r\n\t"retract_restart_extra_toolchange": [\r\n\t\t"0"\r\n\t],\r\n\t"retract_when_changing_layer": [\r\n\t\t"1"\r\n\t],\r\n\t"retraction_distances_when_cut": [\r\n\t\t"18"\r\n\t],\r\n\t"retraction_distances_when_ec": [\r\n\t\t"0"\r\n\t],\r\n\t"retraction_length": [\r\n\t\t"0.8"\r\n\t],\r\n\t"retraction_minimum_travel": [\r\n\t\t"1"\r\n\t],\r\n\t"retraction_speed": [\r\n\t\t"30"\r\n\t],\r\n\t"role_based_wipe_speed": "1",\r\n\t"scan_first_layer": "0",\r\n\t"scarf_angle_threshold": "155",\r\n\t"scarf_joint_flow_ratio": "1",\r\n\t"scarf_joint_speed": "100%",\r\n\t"scarf_overhang_threshold": "40%",\r\n\t"seam_gap": "10%",\r\n\t"seam_position": "aligned",\r\n\t"seam_slope_conditional": "0",\r\n\t"seam_slope_entire_loop": "0",\r\n\t"seam_slope_inner_walls": "0",\r\n\t"seam_slope_min_length": "10",\r\n\t"seam_slope_start_height": "10%",\r\n\t"seam_slope_steps": "10",\r\n\t"seam_slope_type": "none",\r\n\t"separated_infills": "0",\r\n\t"set_other_flow_ratios": "0",\r\n\t"silent_mode": "0",\r\n\t"single_extruder_multi_material": "1",\r\n\t"single_extruder_multi_material_priming": "0",\r\n\t"single_loop_draft_shield": "0",\r\n\t"skeleton_infill_density": "15%",\r\n\t"skeleton_infill_line_width": "0.45",\r\n\t"skin_infill_density": "15%",\r\n\t"skin_infill_depth": "2",\r\n\t"skin_infill_line_width": "0.45",\r\n\t"skirt_distance": "2",\r\n\t"skirt_height": "1",\r\n\t"skirt_loops": "0",\r\n\t"skirt_speed": "50",\r\n\t"skirt_start_angle": "-135",\r\n\t"skirt_type": "combined",\r\n\t"slice_closing_radius": "0.049",\r\n\t"slicing_mode": "regular",\r\n\t"slicing_pipeline_plugin": [],\r\n\t"slow_down_for_layer_cooling": [\r\n\t\t"1"\r\n\t],\r\n\t"slow_down_layer_time": [\r\n\t\t"12"\r\n\t],\r\n\t"slow_down_layers": "0",\r\n\t"slow_down_min_speed": [\r\n\t\t"20"\r\n\t],\r\n\t"slowdown_for_curled_perimeters": [\r\n\t\t"0"\r\n\t],\r\n\t"small_area_infill_flow_compensation": "0",\r\n\t"small_area_infill_flow_compensation_model": [\r\n\t\t"0,0",\r\n\t\t"\\n0.2,0.4444",\r\n\t\t"\\n0.4,0.6145",\r\n\t\t"\\n0.6,0.7059",\r\n\t\t"\\n0.8,0.7619",\r\n\t\t"\\n1.5,0.8571",\r\n\t\t"\\n2,0.8889",\r\n\t\t"\\n3,0.9231",\r\n\t\t"\\n5,0.9520",\r\n\t\t"\\n10,1"\r\n\t],\r\n\t"small_perimeter_speed": [\r\n\t\t"50%"\r\n\t],\r\n\t"small_perimeter_threshold": [\r\n\t\t"0"\r\n\t],\r\n\t"small_support_perimeter_speed": [\r\n\t\t"50%"\r\n\t],\r\n\t"small_support_perimeter_threshold": [\r\n\t\t"0"\r\n\t],\r\n\t"solid_infill_direction": "45",\r\n\t"solid_infill_rotate_template": "",\r\n\t"sparse_infill_acceleration": [\r\n\t\t"100%"\r\n\t],\r\n\t"sparse_infill_density": "15%",\r\n\t"sparse_infill_filament_id": "0",\r\n\t"sparse_infill_flow_ratio": "1",\r\n\t"sparse_infill_line_width": "0.45",\r\n\t"sparse_infill_pattern": "crosshatch",\r\n\t"sparse_infill_rotate_template": "",\r\n\t"sparse_infill_smooth_factor": "0%",\r\n\t"sparse_infill_speed": [\r\n\t\t"270"\r\n\t],\r\n\t"spiral_finishing_flow_ratio": "0",\r\n\t"spiral_mode": "0",\r\n\t"spiral_mode_max_xy_smoothing": "200%",\r\n\t"spiral_mode_smooth": "0",\r\n\t"spiral_starting_flow_ratio": "0",\r\n\t"staggered_inner_seams": "0",\r\n\t"standby_temperature_delta": "-5",\r\n\t"start_end_points": [\r\n\t\t"30x-3",\r\n\t\t"54x245"\r\n\t],\r\n\t"supertack_plate_temp": [\r\n\t\t"70"\r\n\t],\r\n\t"supertack_plate_temp_initial_layer": [\r\n\t\t"70"\r\n\t],\r\n\t"support_air_filtration": "0",\r\n\t"support_angle": "0",\r\n\t"support_base_pattern": "default",\r\n\t"support_base_pattern_spacing": "2.5",\r\n\t"support_bottom_interface_spacing": "0.5",\r\n\t"support_bottom_z_distance": "0.2",\r\n\t"support_chamber_temp_control": "0",\r\n\t"support_cooling_filter": "0",\r\n\t"support_critical_regions_only": "0",\r\n\t"support_expansion": "0",\r\n\t"support_fast_purge_mode": "0",\r\n\t"support_filament": "0",\r\n\t"support_flow_ratio": "1",\r\n\t"support_interface_bottom_layers": "2",\r\n\t"support_interface_filament": "0",\r\n\t"support_interface_flow_ratio": "1",\r\n\t"support_interface_loop_pattern": "0",\r\n\t"support_interface_not_for_body": "1",\r\n\t"support_interface_pattern": "auto",\r\n\t"support_interface_spacing": "0.5",\r\n\t"support_interface_speed": [\r\n\t\t"80"\r\n\t],\r\n\t"support_interface_top_layers": "2",\r\n\t"support_ironing": "0",\r\n\t"support_ironing_flow": "10%",\r\n\t"support_ironing_pattern": "rectilinear",\r\n\t"support_ironing_spacing": "0.1",\r\n\t"support_line_width": "0.42",\r\n\t"support_material_interface_fan_speed": [\r\n\t\t"-1"\r\n\t],\r\n\t"support_multi_bed_types": "0",\r\n\t"support_object_first_layer_gap": "0.2",\r\n\t"support_object_skip_flush": "0",\r\n\t"support_object_xy_distance": "0.35",\r\n\t"support_on_build_plate_only": "0",\r\n\t"support_parallel_printheads": "0",\r\n\t"support_remove_small_overhang": "1",\r\n\t"support_speed": [\r\n\t\t"150"\r\n\t],\r\n\t"support_style": "default",\r\n\t"support_threshold_angle": "30",\r\n\t"support_threshold_overlap": "50%",\r\n\t"support_top_z_distance": "0.2",\r\n\t"support_type": "tree(auto)",\r\n\t"symmetric_infill_y_axis": "0",\r\n\t"temperature_vitrification": [\r\n\t\t"70"\r\n\t],\r\n\t"template_custom_gcode": "",\r\n\t"textured_cool_plate_temp": [\r\n\t\t"40"\r\n\t],\r\n\t"textured_cool_plate_temp_initial_layer": [\r\n\t\t"40"\r\n\t],\r\n\t"textured_plate_temp": [\r\n\t\t"70"\r\n\t],\r\n\t"textured_plate_temp_initial_layer": [\r\n\t\t"70"\r\n\t],\r\n\t"thick_bridges": "0",\r\n\t"thick_internal_bridges": "1",\r\n\t"thumbnails": "48x48/PNG,300x300/PNG",\r\n\t"thumbnails_format": "PNG",\r\n\t"time_cost": "0",\r\n\t"time_lapse_gcode": ";===================== date: 20250206 =====================\\n{if !spiral_mode && print_sequence != \\"by object\\"}\\n; don\'t support timelapse gcode in spiral_mode and by object sequence for I3 structure printer\\n; SKIPPABLE_START\\n; SKIPTYPE: timelapse\\nM622.1 S1 ; for prev firmware, default turned on\\nM1002 judge_flag timelapse_record_flag\\nM622 J1\\nG92 E0\\nG1 Z{max_layer_z + 0.4}\\nG1 X0 Y{first_layer_center_no_wipe_tower[1]} F18000 ; move to safe pos\\nG1 X-13.0 F3000 ; move to safe pos\\nM400\\nM1004 S5 P1  ; external shutter\\nM400 P300\\nM971 S11 C11 O0\\nG92 E0\\nG1 X0 F18000\\nM623\\n\\n; SKIPTYPE: head_wrap_detect\\nM622.1 S1\\nM1002 judge_flag g39_3rd_layer_detect_flag\\nM622 J1\\n    ; enable nozzle clog detect at 3rd layer\\n    {if layer_num == 2}\\n      M400\\n      G90\\n      M83\\n      M204 S5000\\n      G0 Z2 F4000\\n      G0 X187 Y178 F20000\\n      G39 S1 X187 Y178\\n      G0 Z2 F4000\\n    {endif}\\n\\n\\n    M622.1 S1\\n    M1002 judge_flag g39_detection_flag\\n    M622 J1\\n      {if !in_head_wrap_detect_zone}\\n        M622.1 S0\\n        M1002 judge_flag g39_mass_exceed_flag\\n        M622 J1\\n        {if layer_num > 2}\\n            G392 S0\\n            M400\\n            G90\\n            M83\\n            M204 S5000\\n            G0 Z{max_layer_z + 0.4} F4000\\n            G39.3 S1\\n            G0 Z{max_layer_z + 0.4} F4000\\n            G392 S0\\n          {endif}\\n        M623\\n    {endif}\\n    M623\\nM623\\n; SKIPPABLE_END\\n{endif}\\n\\n\\n",\r\n\t"timelapse_type": "0",\r\n\t"tool_change_on_wipe_tower": "0",\r\n\t"toolchange_ordering": "default",\r\n\t"top_bottom_infill_wall_overlap": "25%",\r\n\t"top_layer_direction": "-1",\r\n\t"top_shell_layers": "5",\r\n\t"top_shell_thickness": "1",\r\n\t"top_solid_infill_flow_ratio": "1",\r\n\t"top_surface_acceleration": [\r\n\t\t"2000"\r\n\t],\r\n\t"top_surface_density": "100%",\r\n\t"top_surface_expansion": "0",\r\n\t"top_surface_expansion_direction": "inward_and_outward",\r\n\t"top_surface_expansion_margin": "0",\r\n\t"top_surface_filament_id": "0",\r\n\t"top_surface_fill_order": "default",\r\n\t"top_surface_jerk": [\r\n\t\t"9"\r\n\t],\r\n\t"top_surface_line_width": "0.42",\r\n\t"top_surface_pattern": "monotonicline",\r\n\t"top_surface_speed": [\r\n\t\t"200"\r\n\t],\r\n\t"travel_acceleration": [\r\n\t\t"10000"\r\n\t],\r\n\t"travel_jerk": [\r\n\t\t"12"\r\n\t],\r\n\t"travel_slope": [\r\n\t\t"3"\r\n\t],\r\n\t"travel_speed": [\r\n\t\t"700"\r\n\t],\r\n\t"travel_speed_z": [\r\n\t\t"0"\r\n\t],\r\n\t"tree_support_angle_slow": "25",\r\n\t"tree_support_auto_brim": "1",\r\n\t"tree_support_branch_angle": "45",\r\n\t"tree_support_branch_angle_organic": "40",\r\n\t"tree_support_branch_diameter": "2",\r\n\t"tree_support_branch_diameter_angle": "5",\r\n\t"tree_support_branch_diameter_organic": "2",\r\n\t"tree_support_branch_distance": "5",\r\n\t"tree_support_branch_distance_organic": "1",\r\n\t"tree_support_brim_width": "3",\r\n\t"tree_support_tip_diameter": "0.8",\r\n\t"tree_support_top_rate": "30%",\r\n\t"tree_support_wall_count": "0",\r\n\t"upward_compatible_machine": [\r\n\t\t"Bambu Lab P1S 0.4 nozzle",\r\n\t\t"Bambu Lab P1P 0.4 nozzle",\r\n\t\t"Bambu Lab X1 0.4 nozzle",\r\n\t\t"Bambu Lab X1 Carbon 0.4 nozzle",\r\n\t\t"Bambu Lab X1E 0.4 nozzle",\r\n\t\t"Bambu Lab A1 0.4 nozzle",\r\n\t\t"Bambu Lab H2D 0.4 nozzle",\r\n\t\t"Bambu Lab H2D Pro 0.4 nozzle",\r\n\t\t"Bambu Lab H2S 0.4 nozzle",\r\n\t\t"Bambu Lab P2S 0.4 nozzle"\r\n\t],\r\n\t"use_3mf": "0",\r\n\t"use_firmware_retraction": "0",\r\n\t"use_relative_e_distances": "1",\r\n\t"version": "02.08.01.55",\r\n\t"volumetric_speed_coefficients": [\r\n\t\t"0 0 0 0 0 0"\r\n\t],\r\n\t"wait_for_temp_on_wipe_tower": "0",\r\n\t"wall_direction": "ccw",\r\n\t"wall_distribution_count": "1",\r\n\t"wall_generator": "classic",\r\n\t"wall_loops": "2",\r\n\t"wall_maximum_deviation": "0.025",\r\n\t"wall_maximum_resolution": "0.5",\r\n\t"wall_sequence": "inner wall/outer wall",\r\n\t"wall_transition_angle": "10",\r\n\t"wall_transition_filter_deviation": "25%",\r\n\t"wall_transition_length": "100%",\r\n\t"wipe": [\r\n\t\t"1"\r\n\t],\r\n\t"wipe_before_external_loop": "0",\r\n\t"wipe_distance": [\r\n\t\t"2"\r\n\t],\r\n\t"wipe_on_loops": "0",\r\n\t"wipe_speed": "80%",\r\n\t"wipe_tower_bridging": "10",\r\n\t"wipe_tower_cone_angle": "30",\r\n\t"wipe_tower_extra_flow": "100%",\r\n\t"wipe_tower_extra_rib_length": "0",\r\n\t"wipe_tower_extra_spacing": "100%",\r\n\t"wipe_tower_filament": "0",\r\n\t"wipe_tower_fillet_wall": "1",\r\n\t"wipe_tower_max_purge_speed": "90",\r\n\t"wipe_tower_no_sparse_layers": "0",\r\n\t"wipe_tower_rib_width": "8",\r\n\t"wipe_tower_rotation_angle": "0",\r\n\t"wipe_tower_type": "type2",\r\n\t"wipe_tower_wall_type": "rib",\r\n\t"wipe_tower_x": [\r\n\t\t"29"\r\n\t],\r\n\t"wipe_tower_y": [\r\n\t\t"250"\r\n\t],\r\n\t"wiping_volumes_extruders": [\r\n\t\t"70",\r\n\t\t"70",\r\n\t\t"70",\r\n\t\t"70",\r\n\t\t"70",\r\n\t\t"70",\r\n\t\t"70",\r\n\t\t"70",\r\n\t\t"70",\r\n\t\t"70"\r\n\t],\r\n\t"wrapping_detection_gcode": "",\r\n\t"wrapping_detection_layers": "20",\r\n\t"wrapping_exclude_area": [],\r\n\t"xy_contour_compensation": "0",\r\n\t"xy_hole_compensation": "0",\r\n\t"z_hop": [\r\n\t\t"0.4"\r\n\t],\r\n\t"z_hop_types": [\r\n\t\t"Auto Lift"\r\n\t],\r\n\t"z_offset": "0",\r\n\t"zaa_dont_alternate_fill_direction": "0",\r\n\t"zaa_enabled": "0",\r\n\t"zaa_min_z": "0.05",\r\n\t"zaa_minimize_perimeter_height": "35"\r\n}\r\n')
    native_config = '; CONFIG_BLOCK_START\n; accel_to_decel_enable = 1\n; accel_to_decel_factor = 50%\n; activate_air_filtration = 0\n; activate_air_filtration_during_print = 1\n; activate_air_filtration_on_completion = 1\n; activate_chamber_temp_control = 0\n; adaptive_bed_mesh_margin = 0\n; adaptive_pressure_advance = 0\n; adaptive_pressure_advance_bridges = 0\n; adaptive_pressure_advance_model = "0,0,0\\n0,0,0"\n; adaptive_pressure_advance_overhangs = 0\n; additional_cooling_fan_speed = 0\n; additional_fan_full_speed_layer = 0\n; align_infill_direction_to_model = 0\n; alternate_extra_wall = 0\n; auxiliary_fan = 0\n; bbl_calib_mark_logo = 1\n; bbl_use_printhost = 0\n; bed_custom_model = \n; bed_custom_texture = \n; bed_exclude_area = \n; bed_mesh_max = 99999,99999\n; bed_mesh_min = -99999,-99999\n; bed_mesh_probe_distance = 50,50\n; bed_temperature_formula = by_first_filament\n; before_layer_change_gcode = \n; best_object_pos = 0.7,0.5\n; bottom_layer_direction = -1\n; bottom_shell_layers = 3\n; bottom_shell_thickness = 0\n; bottom_solid_infill_flow_ratio = 1\n; bottom_surface_density = 100%\n; bottom_surface_filament_id = 0\n; bottom_surface_fill_order = default\n; bottom_surface_pattern = monotonic\n; bridge_acceleration = 50%\n; bridge_angle = 0\n; bridge_density = 100%\n; bridge_flow = 1\n; bridge_line_width = 100%\n; bridge_no_support = 0\n; bridge_speed = 50\n; brim_ears_detection_length = 1\n; brim_ears_max_angle = 125\n; brim_ears_outer_only = 0\n; brim_flow_ratio = 1\n; brim_object_gap = 0.1\n; brim_type = auto_brim\n; brim_use_efc_outline = 0\n; brim_width = 5\n; calib_flowrate_topinfill_special_order = 0\n; center_of_surface_pattern = each_surface\n; chamber_minimal_temperature = 0\n; chamber_temperature = 0\n; change_extrusion_role_gcode = \n; change_filament_gcode = ;===== A1mini 20250822 =====\\nG392 S0\\nM1007 S0\\nM620 S[next_extruder]A\\nM204 S9000\\nG1 Z{max_layer_z + 3.0} F1200\\n\\nM400\\nM106 P1 S0\\nM106 P2 S0\\n{if nozzle_temperature[previous_extruder] > 142 && next_extruder < 255}\\nM104 S{nozzle_temperature[previous_extruder]}\\n{endif}\\n\\nG1 X180 F18000\\n\\n{if long_retractions_when_cut[previous_extruder]}\\nM620.11 S1 I[previous_extruder] E-{retraction_distances_when_cut[previous_extruder]} F1200\\n{else}\\nM620.11 S0\\n{endif}\\nM400\\n\\nM620.1 E F{flush_volumetric_speeds[previous_extruder]/2.4053*60} T{flush_temperatures[previous_extruder]}\\nM620.10 A0 F{flush_volumetric_speeds[previous_extruder]/2.4053*60}\\nT[next_extruder]\\nM620.1 E F{flush_volumetric_speeds[next_extruder]/2.4053*60} T{flush_temperatures[next_extruder]}\\nM620.10 A1 F{flush_volumetric_speeds[next_extruder]/2.4053*60} L[flush_length] H[nozzle_diameter] T{flush_temperatures[next_extruder]}\\n\\nG1 Y90 F9000\\n\\n{if next_extruder < 255}\\n\\n{if long_retractions_when_cut[previous_extruder]}\\nM620.11 S1 I[previous_extruder] E{retraction_distances_when_cut[previous_extruder]} F{flush_volumetric_speeds[previous_extruder]/2.4053*60}\\nM628 S1\\nG92 E0\\nG1 E{retraction_distances_when_cut[previous_extruder]} F{flush_volumetric_speeds[previous_extruder]/2.4053*60}\\nM400\\nM629 S1\\n{else}\\nM620.11 S0\\n{endif}\\n\\nM400\\nG92 E0\\nM628 S0\\n\\n{if flush_length_1 > 1}\\n; FLUSH_START\\n; always use highest temperature to flush\\nM400\\nM1002 set_filament_type:UNKNOWN\\nM109 S[flush_temperatures[next_extruder]]\\nM106 P1 S60\\n{if flush_length_1 > 23.7}\\nG1 E23.7 F{flush_volumetric_speeds[previous_extruder]/2.4053*60} ; do not need pulsatile flushing for start part\\nG1 E{(flush_length_1 - 23.7) * 0.02} F50\\nG1 E{(flush_length_1 - 23.7) * 0.23} F{flush_volumetric_speeds[previous_extruder]/2.4053*60}\\nG1 E{(flush_length_1 - 23.7) * 0.02} F50\\nG1 E{(flush_length_1 - 23.7) * 0.23} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{(flush_length_1 - 23.7) * 0.02} F50\\nG1 E{(flush_length_1 - 23.7) * 0.23} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{(flush_length_1 - 23.7) * 0.02} F50\\nG1 E{(flush_length_1 - 23.7) * 0.23} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\n{else}\\nG1 E{flush_length_1} F{flush_volumetric_speeds[previous_extruder]/2.4053*60}\\n{endif}\\n; FLUSH_END\\nG1 E-[old_retract_length_toolchange] F1800\\nG1 E[old_retract_length_toolchange] F300\\nM400\\nM1002 set_filament_type:{filament_type[next_extruder]}\\n{endif}\\n\\n{if flush_length_1 > 45 && flush_length_2 > 1}\\n; WIPE\\nM400\\nM106 P1 S178\\nM400 S3\\nG1 X-3.5 F18000\\nG1 X-13.5 F3000\\nG1 X-3.5 F18000\\nG1 X-13.5 F3000\\nG1 X-3.5 F18000\\nG1 X-13.5 F3000\\nM400\\nM106 P1 S0\\n{endif}\\n\\n{if flush_length_2 > 1}\\nM106 P1 S60\\n; FLUSH_START\\nG1 E{flush_length_2 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_2 * 0.02} F50\\nG1 E{flush_length_2 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_2 * 0.02} F50\\nG1 E{flush_length_2 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_2 * 0.02} F50\\nG1 E{flush_length_2 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_2 * 0.02} F50\\nG1 E{flush_length_2 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_2 * 0.02} F50\\n; FLUSH_END\\nG1 E-[new_retract_length_toolchange] F1800\\nG1 E[new_retract_length_toolchange] F300\\n{endif}\\n\\n{if flush_length_2 > 45 && flush_length_3 > 1}\\n; WIPE\\nM400\\nM106 P1 S178\\nM400 S3\\nG1 X-3.5 F18000\\nG1 X-13.5 F3000\\nG1 X-3.5 F18000\\nG1 X-13.5 F3000\\nG1 X-3.5 F18000\\nG1 X-13.5 F3000\\nM400\\nM106 P1 S0\\n{endif}\\n\\n{if flush_length_3 > 1}\\nM106 P1 S60\\n; FLUSH_START\\nG1 E{flush_length_3 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_3 * 0.02} F50\\nG1 E{flush_length_3 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_3 * 0.02} F50\\nG1 E{flush_length_3 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_3 * 0.02} F50\\nG1 E{flush_length_3 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_3 * 0.02} F50\\nG1 E{flush_length_3 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_3 * 0.02} F50\\n; FLUSH_END\\nG1 E-[new_retract_length_toolchange] F1800\\nG1 E[new_retract_length_toolchange] F300\\n{endif}\\n\\n{if flush_length_3 > 45 && flush_length_4 > 1}\\n; WIPE\\nM400\\nM106 P1 S178\\nM400 S3\\nG1 X-3.5 F18000\\nG1 X-13.5 F3000\\nG1 X-3.5 F18000\\nG1 X-13.5 F3000\\nG1 X-3.5 F18000\\nG1 X-13.5 F3000\\nM400\\nM106 P1 S0\\n{endif}\\n\\n{if flush_length_4 > 1}\\nM106 P1 S60\\n; FLUSH_START\\nG1 E{flush_length_4 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_4 * 0.02} F50\\nG1 E{flush_length_4 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_4 * 0.02} F50\\nG1 E{flush_length_4 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_4 * 0.02} F50\\nG1 E{flush_length_4 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_4 * 0.02} F50\\nG1 E{flush_length_4 * 0.18} F{flush_volumetric_speeds[next_extruder]/2.4053*60}\\nG1 E{flush_length_4 * 0.02} F50\\n; FLUSH_END\\n{endif}\\n\\nM629\\n\\nM400\\nM106 P1 S60\\nM109 S{nozzle_temperature[next_extruder]}\\nG1 E5 F{flush_volumetric_speeds[next_extruder]/2.4053*60} ;Compensate for filament spillage during waiting temperature\\nM400\\nG92 E0\\nG1 E-[new_retract_length_toolchange] F1800\\nM400\\nM106 P1 S178\\nM400 S3\\nG1 X-3.5 F18000\\nG1 X-13.5 F3000\\nG1 X-3.5 F18000\\nG1 X-13.5 F3000\\nG1 X-3.5 F18000\\nG1 X-13.5 F3000\\nG1 X-3.5 F18000\\nG1 X-13.5 F3000\\nM400\\nG1 Z{max_layer_z + 3.0} F3000\\nM106 P1 S0\\n{if layer_z <= (initial_layer_print_height + 0.001)}\\nM204 S[initial_layer_acceleration]\\n{else}\\nM204 S[default_acceleration]\\n{endif}\\n{else}\\nG1 X[x_after_toolchange] Y[y_after_toolchange] Z[z_after_toolchange] F12000\\n{endif}\\n\\nM622.1 S0\\nM9833 F{outer_wall_volumetric_speed/2.4} A0.3 ; cali dynamic extrusion compensation\\nM1002 judge_flag filament_need_cali_flag\\nM622 J1\\n  G92 E0\\n  G1 E-[new_retract_length_toolchange] F1800\\n  M400\\n  \\n  M106 P1 S178\\n  M400 S7\\n  G1 X0 F18000\\n  G1 X-13.5 F3000\\n  G1 X0 F18000 ;wipe and shake\\n  G1 X-13.5 F3000\\n  G1 X0 F12000 ;wipe and shake\\n  G1 X-13.5 F3000\\n  G1 X0 F12000 ;wipe and shake\\n  M400\\n  M106 P1 S0 \\nM623\\n\\nM621 S[next_extruder]A\\nG392 S0\\n\\nM1007 S1\\n\n; close_additional_fan_first_x_layers = 3\n; close_fan_the_first_x_layers = 3\n; combine_brims = 0\n; complete_print_exhaust_fan_speed = 70\n; cool_plate_temp = 0\n; cool_plate_temp_initial_layer = 0\n; cooling_filter_enabled = 0\n; cooling_tube_length = 5\n; cooling_tube_retraction = 91.5\n; counterbore_hole_bridging = none\n; curr_bed_type = Textured PEI Plate\n; default_acceleration = 6000\n; default_bed_type = \n; default_filament_colour = ""\n; default_filament_profile = "Bambu PLA Basic @BBL A1M"\n; default_jerk = 0\n; default_junction_deviation = 0\n; default_nozzle_volume_type = Standard\n; default_print_profile = 0.20mm Standard @BBL A1M\n; deretraction_speed = 30\n; detect_narrow_internal_solid_infill = 1\n; detect_overhang_wall = 1\n; detect_thin_wall = 0\n; disable_m73 = 0\n; dont_filter_internal_bridges = disabled\n; dont_slow_down_outer_wall = 0\n; draft_shield = disabled\n; during_print_exhaust_fan_speed = 70\n; elefant_foot_compensation = 0\n; elefant_foot_compensation_layers = 1\n; elefant_foot_layers_density = 100%\n; emit_machine_limits_to_gcode = 1\n; enable_arc_fitting = 1\n; enable_extra_bridge_layer = disabled\n; enable_filament_dynamic_map = 0\n; enable_filament_ramming = 0\n; enable_long_retraction_when_cut = 2\n; enable_mixed_color_sublayer = 0\n; enable_overhang_bridge_fan = 1\n; enable_overhang_speed = 1\n; enable_power_loss_recovery = printer_configuration\n; enable_pre_heating = 0\n; enable_pressure_advance = 0\n; enable_prime_tower = 0\n; enable_support = 0\n; enable_tower_interface_cooldown_during_tower = 0\n; enable_tower_interface_features = 0\n; enable_wrapping_detection = 0\n; enforce_support_layers = 0\n; eng_plate_temp = 70\n; eng_plate_temp_initial_layer = 70\n; ensure_vertical_shell_thickness = ensure_all\n; exclude_object = 0\n; extra_loading_move = -2\n; extra_perimeters_on_overhangs = 0\n; extra_solid_infills = \n; extruder_ams_count = 1#0|4#0;\n; extruder_clearance_height_to_lid = 180\n; extruder_clearance_height_to_rod = 25\n; extruder_clearance_radius = 73\n; extruder_colour = #000000\n; extruder_max_nozzle_count = 1\n; extruder_nozzle_stats = Standard#1\n; extruder_offset = 0x0\n; extruder_printable_area = \n; extruder_printable_height = 0\n; extruder_type = Direct Drive\n; extruder_variant_list = "Direct Drive Standard"\n; extrusion_rate_smoothing_external_perimeter_only = 0\n; fan_cooling_layer_time = 30\n; fan_direction = undefine\n; fan_kickstart = 0\n; fan_max_speed = 90\n; fan_min_speed = 40\n; fan_speedup_overhangs = 1\n; fan_speedup_time = 0\n; filament_adaptive_volumetric_speed = 0\n; filament_adhesiveness_category = 300\n; filament_change_extrusion_role_gcode = ""\n; filament_change_length = 10\n; filament_change_length_nc = 10\n; filament_colour = #000000\n; filament_cooling_before_tower = 10\n; filament_cooling_final_speed = 3.4\n; filament_cooling_initial_speed = 2.2\n; filament_cooling_moves = 4\n; filament_cost = 30\n; filament_density = 1.27\n; filament_dev_ams_drying_ams_limitations = 1;0\n; filament_dev_ams_drying_heat_distortion_temperature = 75\n; filament_dev_ams_drying_temperature = 65,65,55,55\n; filament_dev_ams_drying_time = 12,12,12,12\n; filament_dev_chamber_drying_bed_temperature = 80\n; filament_dev_chamber_drying_time = 0\n; filament_dev_drying_cooling_temperature = 55\n; filament_dev_drying_softening_temperature = 60\n; filament_diameter = 1.75\n; filament_end_gcode = "; filament end gcode \\n\\n"\n; filament_extruder_variant = "Direct Drive Standard"\n; filament_flow_ratio = 0.95\n; filament_flush_temp = 0\n; filament_flush_volumetric_speed = 0\n; filament_ids = GFG99\n; filament_is_mixed = 0\n; filament_is_support = 0\n; filament_loading_speed = 28\n; filament_loading_speed_start = 3\n; filament_map = 1\n; filament_map_2 = 0\n; filament_map_mode = Auto For Flush\n; filament_max_volumetric_speed = 8\n; filament_minimal_purge_on_wipe_tower = 15\n; filament_mixed_components = ""\n; filament_mixed_gradient = 0\n; filament_mixed_gradient_curve = ""\n; filament_mixed_gradient_per_part = 0\n; filament_mixed_gradient_range = ""\n; filament_mixed_sublayer_ratios = ""\n; filament_multi_colour = #000000\n; filament_multitool_ramming = 0\n; filament_multitool_ramming_flow = 10\n; filament_multitool_ramming_volume = 10\n; filament_notes = ""\n; filament_nozzle_map = 0\n; filament_plugin_config_overrides = \n; filament_pre_cooling_temperature = 0\n; filament_pre_cooling_temperature_nc = 0\n; filament_preheat_temperature_delta = 0\n; filament_prime_volume = 45\n; filament_prime_volume_nc = 60\n; filament_printable = 3\n; filament_ramming_parameters = "120 100 6.6 6.8 7.2 7.6 7.9 8.2 8.7 9.4 9.9 10.0| 0.05 6.6 0.45 6.8 0.95 7.8 1.45 8.3 1.95 9.7 2.45 10 2.95 7.6 3.45 7.6 3.95 7.6 4.45 7.6 4.95 7.6"\n; filament_ramming_travel_time = 0\n; filament_ramming_travel_time_nc = 0\n; filament_ramming_volumetric_speed = -1\n; filament_ramming_volumetric_speed_nc = -1\n; filament_self_index = 1\n; filament_settings_id = "Generic PETG @BBL A1M"\n; filament_shrink = 100%\n; filament_shrinkage_compensation_z = 100%\n; filament_soluble = 0\n; filament_stamping_distance = 0\n; filament_stamping_loading_speed = 0\n; filament_start_gcode = "; filament start gcode\\n{if (bed_temperature[current_extruder] >80)||(bed_temperature_initial_layer[current_extruder] >80)}M106 P3 S255\\n{elsif (bed_temperature[current_extruder] >60)||(bed_temperature_initial_layer[current_extruder] >60)}M106 P3 S180\\n{endif}\\n\\n{if activate_air_filtration[current_extruder] && support_air_filtration}\\nM106 P3 S{during_print_exhaust_fan_speed_num[current_extruder]} \\n{endif}"\n; filament_toolchange_delay = 0\n; filament_tower_interface_pre_extrusion_dist = 10\n; filament_tower_interface_pre_extrusion_length = 0\n; filament_tower_interface_print_temp = -1\n; filament_tower_interface_purge_volume = 20\n; filament_tower_ironing_area = 4\n; filament_type = PETG\n; filament_unloading_speed = 90\n; filament_unloading_speed_start = 100\n; filament_vendor = Generic\n; filament_volume_map = 0\n; file_start_gcode = \n; filename_format = {input_filename_base}_{filament_type[0]}_{print_time}.gcode\n; fill_multiline = 1\n; filter_out_gap_fill = 0\n; first_layer_flow_ratio = 1\n; first_layer_print_sequence = 0\n; first_x_layer_fan_speed = 0\n; flashforge_serial_number = \n; flush_into_infill = 0\n; flush_into_objects = 0\n; flush_into_support = 1\n; flush_multiplier = 0.05\n; flush_volumes_matrix = 0\n; flush_volumes_vector = 140,140\n; full_fan_speed_layer = 0\n; fuzzy_skin = disabled_fuzzy\n; fuzzy_skin_first_layer = 0\n; fuzzy_skin_layers_between_ripple_offset = 1\n; fuzzy_skin_mode = displacement\n; fuzzy_skin_noise_type = classic\n; fuzzy_skin_octaves = 4\n; fuzzy_skin_persistence = 0.5\n; fuzzy_skin_point_distance = 0.3\n; fuzzy_skin_ripple_offset = 50%\n; fuzzy_skin_ripples_per_layer = 15\n; fuzzy_skin_scale = 1\n; fuzzy_skin_thickness = 0.2\n; gap_fill_flow_ratio = 1\n; gap_fill_target = nowhere\n; gap_infill_speed = 250\n; gcode_add_line_number = 0\n; gcode_comments = 0\n; gcode_flavor = marlin\n; gcode_label_objects = 1\n; gcode_skip_config_block = 0\n; grab_length = 17.4\n; group_algo_with_time = 0\n; gyroid_optimized = 0\n; has_filament_switcher = 0\n; has_scarf_joint_seam = 0\n; head_wrap_detect_zone = 156x152,180x152,180x180,156x180\n; high_current_on_filament_swap = 0\n; hole_to_polyhole = 0\n; hole_to_polyhole_max_edges = 50\n; hole_to_polyhole_threshold = 0.01\n; hole_to_polyhole_twisted = 1\n; host_type = octoprint\n; hot_plate_temp = 70\n; hot_plate_temp_initial_layer = 70\n; hotend_cooling_rate = 2\n; hotend_heating_rate = 2\n; idle_temperature = 0\n; independent_support_layer_height = 1\n; infill_anchor = 400%\n; infill_anchor_max = 20\n; infill_combination = 0\n; infill_combination_max_layer_height = 100%\n; infill_direction = 45\n; infill_jerk = 9\n; infill_lock_depth = 1\n; infill_overhang_angle = 60\n; infill_shift_step = 0.4\n; infill_wall_overlap = 15%\n; initial_layer_acceleration = 500\n; initial_layer_fan_speed = -1\n; initial_layer_infill_speed = 105\n; initial_layer_jerk = 9\n; initial_layer_line_width = 0.5\n; initial_layer_min_bead_width = 85%\n; initial_layer_print_height = 0.2\n; initial_layer_speed = 50\n; initial_layer_travel_acceleration = 6000\n; initial_layer_travel_jerk = 100%\n; initial_layer_travel_speed = 100%\n; inner_wall_acceleration = 0\n; inner_wall_filament_id = 0\n; inner_wall_flow_ratio = 1\n; inner_wall_jerk = 9\n; inner_wall_line_width = 0.45\n; inner_wall_speed = 300\n; input_shaping_damp_x = 0.1\n; input_shaping_damp_y = 0.1\n; input_shaping_emit = 0\n; input_shaping_freq_x = 0\n; input_shaping_freq_y = 0\n; input_shaping_type = Default\n; interface_shells = 0\n; interlocking_beam = 0\n; interlocking_beam_layer_count = 2\n; interlocking_beam_width = 0.8\n; interlocking_boundary_avoidance = 2\n; interlocking_depth = 2\n; interlocking_orientation = 22.5\n; internal_bridge_angle = 0\n; internal_bridge_density = 100%\n; internal_bridge_fan_speed = -1\n; internal_bridge_flow = 1\n; internal_bridge_speed = 150%\n; internal_solid_filament_id = 0\n; internal_solid_infill_acceleration = 100%\n; internal_solid_infill_flow_ratio = 1\n; internal_solid_infill_line_width = 0.42\n; internal_solid_infill_pattern = monotonic\n; internal_solid_infill_speed = 250\n; ironing_angle = 0\n; ironing_angle_fixed = 0\n; ironing_expansion = 0\n; ironing_fan_speed = -1\n; ironing_flow = 10%\n; ironing_inset = 0.21\n; ironing_pattern = rectilinear\n; ironing_spacing = 0.15\n; ironing_speed = 30\n; ironing_type = no ironing\n; is_infill_first = 0\n; lateral_lattice_angle_1 = -45\n; lateral_lattice_angle_2 = 45\n; layer_change_gcode = ; layer num/total_layer_count: {layer_num+1}/[total_layer_count]\\n; update layer progress\\nM73 L{layer_num+1}\\nM991 S0 P{layer_num} ;notify layer change\\n\n; layer_height = 0.2\n; lightning_overhang_angle = 45\n; lightning_prune_angle = 45\n; lightning_straightening_angle = 45\n; line_width = 0.42\n; long_retractions_when_cut = 0\n; long_retractions_when_ec = 0\n; machine_bed_mass_Y = 0\n; machine_end_gcode = ;===== date: 20231229 =====================\\n;turn off nozzle clog detect\\nG392 S0\\n\\nM400 ; wait for buffer to clear\\nG92 E0 ; zero the extruder\\nG1 E-0.8 F1800 ; retract\\nG1 Z{max_layer_z + 0.5} F900 ; lower z a little\\nG1 X0 Y{first_layer_center_no_wipe_tower[1]} F18000 ; move to safe pos\\nG1 X-13.0 F3000 ; move to safe pos\\n{if !spiral_mode && print_sequence != \\"by object\\"}\\nM1002 judge_flag timelapse_record_flag\\nM622 J1\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM400 P100\\nM971 S11 C11 O0\\nM991 S0 P-1 ;end timelapse at safe pos\\nM623\\n{endif}\\n\\nM140 S0 ; turn off bed\\nM106 S0 ; turn off fan\\nM106 P2 S0 ; turn off remote part cooling fan\\nM106 P3 S0 ; turn off chamber cooling fan\\n\\n;G1 X27 F15000 ; wipe\\n\\n; pull back filament to AMS\\nM620 S255\\nG1 X181 F12000\\nT255\\nG1 X0 F18000\\nG1 X-13.0 F3000\\nG1 X0 F18000 ; wipe\\nM621 S255\\n\\nM104 S0 ; turn off hotend\\n\\nM400 ; wait all motion done\\nM17 S\\nM17 Z0.4 ; lower z motor current to reduce impact if there is something in the bottom\\n{if (max_layer_z + 100.0) < 180}\\n    G1 Z{max_layer_z + 100.0} F600\\n    G1 Z{max_layer_z +98.0}\\n{else}\\n    G1 Z180 F600\\n    G1 Z180\\n{endif}\\nM400 P100\\nM17 R ; restore z current\\n\\nG90\\nG1 X-13 Y180 F3600\\n\\nG91\\nG1 Z-1 F600\\nG90\\nM83\\n\\nM220 S100  ; Reset feedrate magnitude\\nM201.2 K1.0 ; Reset acc magnitude\\nM73.2   R1.0 ;Reset left time magnitude\\nM1002 set_gcode_claim_speed_level : 0\\n\\n;=====printer finish  sound=========\\nM17\\nM400 S1\\nM1006 S1\\nM1006 A0 B20 L100 C37 D20 M100 E42 F20 N100\\nM1006 A0 B10 L100 C44 D10 M100 E44 F10 N100\\nM1006 A0 B10 L100 C46 D10 M100 E46 F10 N100\\nM1006 A44 B20 L100 C39 D20 M100 E48 F20 N100\\nM1006 A0 B10 L100 C44 D10 M100 E44 F10 N100\\nM1006 A0 B10 L100 C0 D10 M100 E0 F10 N100\\nM1006 A0 B10 L100 C39 D10 M100 E39 F10 N100\\nM1006 A0 B10 L100 C0 D10 M100 E0 F10 N100\\nM1006 A0 B10 L100 C44 D10 M100 E44 F10 N100\\nM1006 A0 B10 L100 C0 D10 M100 E0 F10 N100\\nM1006 A0 B10 L100 C39 D10 M100 E39 F10 N100\\nM1006 A0 B10 L100 C0 D10 M100 E0 F10 N100\\nM1006 A44 B10 L100 C0 D10 M100 E48 F10 N100\\nM1006 A0 B10 L100 C0 D10 M100 E0 F10 N100\\nM1006 A44 B20 L100 C41 D20 M100 E49 F20 N100\\nM1006 A0 B20 L100 C0 D20 M100 E0 F20 N100\\nM1006 A0 B20 L100 C37 D20 M100 E37 F20 N100\\nM1006 W\\n;=====printer finish  sound=========\\nM400 S1\\nM18 X Y Z\\n\n; machine_hotend_change_time = 0\n; machine_load_filament_time = 28\n; machine_max_acceleration_e = 5000,5000\n; machine_max_acceleration_extruding = 20000,20000\n; machine_max_acceleration_retracting = 5000,5000\n; machine_max_acceleration_travel = 9000,9000\n; machine_max_acceleration_x = 20000,20000\n; machine_max_acceleration_y = 20000,20000\n; machine_max_acceleration_z = 1500,1500\n; machine_max_force_Y = 0\n; machine_max_jerk_e = 3,3\n; machine_max_jerk_x = 9,9\n; machine_max_jerk_y = 9,9\n; machine_max_jerk_z = 5,5\n; machine_max_junction_deviation = 0.01,0.01\n; machine_max_printed_mass = 0\n; machine_max_speed_e = 30,30\n; machine_max_speed_x = 500,200\n; machine_max_speed_y = 500,200\n; machine_max_speed_z = 30,30\n; machine_min_extruding_rate = 0,0\n; machine_min_travel_rate = 0,0\n; machine_pause_gcode = M400 U1\n; machine_prepare_compensation_time = 260\n; machine_start_gcode = ;===== machine: A1 mini =========================\\n;===== date: 20250822 ==================\\n\\n;===== start to heat heatbead&hotend==========\\nM1002 gcode_claim_action : 2\\nM1002 set_filament_type:{filament_type[initial_no_support_extruder]}\\nM104 S170\\nM140 S[bed_temperature_initial_layer_single]\\nG392 S0 ;turn off clog detect\\nM9833.2\\n;=====start printer sound ===================\\nM17\\nM400 S1\\nM1006 S1\\nM1006 A0 B0 L100 C37 D10 M100 E37 F10 N100\\nM1006 A0 B0 L100 C41 D10 M100 E41 F10 N100\\nM1006 A0 B0 L100 C44 D10 M100 E44 F10 N100\\nM1006 A0 B10 L100 C0 D10 M100 E0 F10 N100\\nM1006 A43 B10 L100 C39 D10 M100 E46 F10 N100\\nM1006 A0 B0 L100 C0 D10 M100 E0 F10 N100\\nM1006 A0 B0 L100 C39 D10 M100 E43 F10 N100\\nM1006 A0 B0 L100 C0 D10 M100 E0 F10 N100\\nM1006 A0 B0 L100 C41 D10 M100 E41 F10 N100\\nM1006 A0 B0 L100 C44 D10 M100 E44 F10 N100\\nM1006 A0 B0 L100 C49 D10 M100 E49 F10 N100\\nM1006 A0 B0 L100 C0 D10 M100 E0 F10 N100\\nM1006 A44 B10 L100 C39 D10 M100 E48 F10 N100\\nM1006 A0 B0 L100 C0 D10 M100 E0 F10 N100\\nM1006 A0 B0 L100 C39 D10 M100 E44 F10 N100\\nM1006 A0 B0 L100 C0 D10 M100 E0 F10 N100\\nM1006 A43 B10 L100 C39 D10 M100 E46 F10 N100\\nM1006 W\\nM18\\n;=====avoid end stop =================\\nG91\\nG380 S2 Z30 F1200\\nG380 S3 Z-20 F1200\\nG1 Z5 F1200\\nG90\\n\\n;===== reset machine status =================\\nM204 S6000\\n\\nM630 S0 P0\\nG91\\nM17 Z0.3 ; lower the z-motor current\\n\\nG90\\nM17 X0.7 Y0.9 Z0.5 ; reset motor current to default\\nM960 S5 P1 ; turn on logo lamp\\nG90\\nM83\\nM220 S100 ;Reset Feedrate\\nM221 S100 ;Reset Flowrate\\nM73.2   R1.0 ;Reset left time magnitude\\n;====== cog noise reduction=================\\nM982.2 S1 ; turn on cog noise reduction\\n\\n;===== prepare print temperature and material ==========\\nM400\\nM18\\nM109 S100 H170\\nM104 S170\\nM400\\nM17\\nM400\\nG28 X\\n\\nM211 X0 Y0 Z0 ;turn off soft endstop ; turn off soft endstop to prevent protential logic problem\\n\\nM975 S1 ; turn on\\n\\nG1 X0.0 F30000\\nG1 X-13.5 F3000\\n\\nM620 M ;enable remap\\nM620 S[initial_no_support_extruder]A   ; switch material if AMS exist\\n    G392 S0 ;turn on clog detect\\n    M1002 gcode_claim_action : 4\\n    M400\\n    M1002 set_filament_type:UNKNOWN\\n    M109 S[nozzle_temperature_initial_layer]\\n    M104 S250\\n    M400\\n    T[initial_no_support_extruder]\\n    G1 X-13.5 F3000\\n    M400\\n    M620.1 E F{flush_volumetric_speeds[initial_no_support_extruder]/2.4053*60} T{flush_temperatures[initial_no_support_extruder]}\\n    M109 S250 ;set nozzle to common flush temp\\n    M106 P1 S0\\n    G92 E0\\n    G1 E50 F200\\n    M400\\n    M1002 set_filament_type:{filament_type[initial_no_support_extruder]}\\n    M104 S{flush_temperatures[initial_no_support_extruder]}\\n    G92 E0\\n    G1 E50 F{flush_volumetric_speeds[initial_no_support_extruder]/2.4053*60}\\n    M400\\n    M106 P1 S178\\n    G92 E0\\n    G1 E5 F{flush_volumetric_speeds[initial_no_support_extruder]/2.4053*60}\\n    M109 S{nozzle_temperature_initial_layer[initial_no_support_extruder]-20} ; drop nozzle temp, make filament shink a bit\\n    M104 S{nozzle_temperature_initial_layer[initial_no_support_extruder]-40}\\n    G92 E0\\n    G1 E-0.5 F300\\n\\n    G1 X0 F30000\\n    G1 X-13.5 F3000\\n    G1 X0 F30000 ;wipe and shake\\n    G1 X-13.5 F3000\\n    G1 X0 F12000 ;wipe and shake\\n    G1 X0 F30000\\n    G1 X-13.5 F3000\\n    M109 S{nozzle_temperature_initial_layer[initial_no_support_extruder]-40}\\n    G392 S0 ;turn off clog detect\\nM621 S[initial_no_support_extruder]A\\n\\nM400\\nM106 P1 S0\\n;===== prepare print temperature and material end =====\\n\\n\\n;===== mech mode fast check============================\\nM1002 gcode_claim_action : 3\\nG0 X25 Y175 F20000 ; find a soft place to home\\n;M104 S0\\nG28 Z P0 T300; home z with low precision,permit 300deg temperature\\nG29.2 S0 ; turn off ABL\\nM104 S170\\n\\n; build plate detect\\nM1002 judge_flag build_plate_detect_flag\\nM622 S1\\n  G39.4\\n  M400\\nM623\\n\\nG1 Z5 F3000\\nG1 X90 Y-1 F30000\\nM400 P200\\nM970.3 Q1 A7 K0 O2\\nM974 Q1 S2 P0\\n\\nG1 X90 Y0 Z5 F30000\\nM400 P200\\nM970 Q0 A10 B50 C90 H15 K0 M20 O3\\nM974 Q0 S2 P0\\n\\nM975 S1\\nG1 F30000\\nG1 X-1 Y10\\nG28 X ; re-home XY\\n\\n;===== wipe nozzle ===============================\\nM1002 gcode_claim_action : 14\\nM975 S1\\n\\nM104 S170 ; set temp down to heatbed acceptable\\nM106 S255 ; turn on fan (G28 has turn off fan)\\nM211 S; push soft endstop status\\nM211 X0 Y0 Z0 ;turn off Z axis endstop\\n\\nM83\\nG1 E-1 F500\\nG90\\nM83\\n\\nM109 S170\\nM104 S140\\nG0 X90 Y-4 F30000\\nG380 S3 Z-5 F1200\\nG1 Z2 F1200\\nG1 X91 F10000\\nG380 S3 Z-5 F1200\\nG1 Z2 F1200\\nG1 X92 F10000\\nG380 S3 Z-5 F1200\\nG1 Z2 F1200\\nG1 X93 F10000\\nG380 S3 Z-5 F1200\\nG1 Z2 F1200\\nG1 X94 F10000\\nG380 S3 Z-5 F1200\\nG1 Z2 F1200\\nG1 X95 F10000\\nG380 S3 Z-5 F1200\\nG1 Z2 F1200\\nG1 X96 F10000\\nG380 S3 Z-5 F1200\\nG1 Z2 F1200\\nG1 X97 F10000\\nG380 S3 Z-5 F1200\\nG1 Z2 F1200\\nG1 X98 F10000\\nG380 S3 Z-5 F1200\\nG1 Z2 F1200\\nG1 X99 F10000\\nG380 S3 Z-5 F1200\\nG1 Z2 F1200\\nG1 X99 F10000\\nG380 S3 Z-5 F1200\\nG1 Z2 F1200\\nG1 X99 F10000\\nG380 S3 Z-5 F1200\\nG1 Z2 F1200\\nG1 X99 F10000\\nG380 S3 Z-5 F1200\\nG1 Z2 F1200\\nG1 X99 F10000\\nG380 S3 Z-5 F1200\\n\\nG1 Z5 F30000\\n;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;\\nG1 X25 Y175 F30000.1 ;Brush material\\nG1 Z0.2 F30000.1\\nG1 Y185\\nG91\\nG1 X-30 F30000\\nG1 Y-2\\nG1 X27\\nG1 Y1.5\\nG1 X-28\\nG1 Y-2\\nG1 X30\\nG1 Y1.5\\nG1 X-30\\nG90\\nM83\\n\\nG1 Z5 F3000\\nG0 X50 Y175 F20000 ; find a soft place to home\\nG28 Z P0 T300; home z with low precision, permit 300deg temperature\\nG29.2 S0 ; turn off ABL\\n\\nG0 X85 Y185 F10000 ;move to exposed steel surface and stop the nozzle\\nG0 Z-1.01 F10000\\nG91\\n\\nG2 I1 J0 X2 Y0 F2000.1\\nG2 I-0.75 J0 X-1.5\\nG2 I1 J0 X2\\nG2 I-0.75 J0 X-1.5\\nG2 I1 J0 X2\\nG2 I-0.75 J0 X-1.5\\nG2 I1 J0 X2\\nG2 I-0.75 J0 X-1.5\\nG2 I1 J0 X2\\nG2 I-0.75 J0 X-1.5\\nG2 I1 J0 X2\\nG2 I-0.75 J0 X-1.5\\nG2 I1 J0 X2\\nG2 I-0.75 J0 X-1.5\\nG2 I1 J0 X2\\nG2 I-0.75 J0 X-1.5\\nG2 I1 J0 X2\\nG2 I-0.75 J0 X-1.5\\nG2 I1 J0 X2\\nG2 I-0.75 J0 X-1.5\\n\\nG90\\nG1 Z5 F30000\\nG1 X25 Y175 F30000.1 ;Brush material\\nG1 Z0.2 F30000.1\\nG1 Y185\\nG91\\nG1 X-30 F30000\\nG1 Y-2\\nG1 X27\\nG1 Y1.5\\nG1 X-28\\nG1 Y-2\\nG1 X30\\nG1 Y1.5\\nG1 X-30\\nG90\\nM83\\n\\nG1 Z5\\nG0 X55 Y175 F20000 ; find a soft place to home\\nG28 Z P0 T300; home z with low precision, permit 300deg temperature\\nG29.2 S0 ; turn off ABL\\n\\nG1 Z10\\nG1 X85 Y185\\nG1 Z-1.01\\nG1 X95\\nG1 X90\\n\\nM211 R; pop softend status\\n\\nM106 S0 ; turn off fan , too noisy\\n;===== wipe nozzle end ================================\\n\\n\\n;===== wait heatbed  ====================\\nM1002 gcode_claim_action : 2\\nM104 S0\\nM190 S[bed_temperature_initial_layer_single];set bed temp\\nM109 S140\\n\\nG1 Z5 F3000\\nG29.2 S1\\nG1 X10 Y10 F20000\\n\\n;===== bed leveling ==================================\\n;M1002 set_flag g29_before_print_flag=1\\nM1002 judge_flag g29_before_print_flag\\nM622 J1\\n    M1002 gcode_claim_action : 1\\n    G29 A1 X{first_layer_print_min[0]} Y{first_layer_print_min[1]} I{first_layer_print_size[0]} J{first_layer_print_size[1]}\\n    M400\\n    M500 ; save cali data\\nM623\\n;===== bed leveling end ================================\\n\\n;===== home after wipe mouth============================\\nM1002 judge_flag g29_before_print_flag\\nM622 J0\\n\\n    M1002 gcode_claim_action : 13\\n    G28 T145\\n\\nM623\\n\\n;===== home after wipe mouth end =======================\\n\\nM975 S1 ; turn on vibration supression\\n;===== nozzle load line ===============================\\nM975 S1\\nG90\\nM83\\nT1000\\n\\nG1 X-13.5 Y0 Z10 F10000\\nG1 E1.2 F500\\nM400\\nM1002 set_filament_type:UNKNOWN\\nM109 S{nozzle_temperature[initial_extruder]}\\nM400\\n\\nM412 S1 ;    ===turn on  filament runout detection===\\nM400 P10\\n\\nG392 S0 ;turn on clog detect\\n\\nM620.3 W1; === turn on filament tangle detection===\\nM400 S2\\n\\nM1002 set_filament_type:{filament_type[initial_no_support_extruder]}\\n;M1002 set_flag extrude_cali_flag=1\\nM1002 judge_flag extrude_cali_flag\\nM622 J1\\n    M1002 gcode_claim_action : 8\\n    \\n    M400\\n    M900 K0.0 L1000.0 M1.0\\n    G90\\n    M83\\n    G0 X68 Y-4 F30000\\n    G0 Z0.3 F18000 ;Move to start position\\n    M400\\n    G0 X88 E10  F{outer_wall_volumetric_speed/(24/20)    * 60}\\n    G0 X93 E.3742  F{outer_wall_volumetric_speed/(0.3*0.5)/4     * 60}\\n    G0 X98 E.3742  F{outer_wall_volumetric_speed/(0.3*0.5)     * 60}\\n    G0 X103 E.3742  F{outer_wall_volumetric_speed/(0.3*0.5)/4     * 60}\\n    G0 X108 E.3742  F{outer_wall_volumetric_speed/(0.3*0.5)     * 60}\\n    G0 X113 E.3742  F{outer_wall_volumetric_speed/(0.3*0.5)/4     * 60}\\n    G0 Y0 Z0 F20000\\n    M400\\n    \\n    G1 X-13.5 Y0 Z10 F10000\\n    M400\\n    \\n    G1 E10 F{outer_wall_volumetric_speed/2.4*60}\\n    M983 F{outer_wall_volumetric_speed/2.4} A0.3 H[nozzle_diameter]; cali dynamic extrusion compensation\\n    M106 P1 S178\\n    M400 S7\\n    G1 X0 F18000\\n    G1 X-13.5 F3000\\n    G1 X0 F18000 ;wipe and shake\\n    G1 X-13.5 F3000\\n    G1 X0 F12000 ;wipe and shake\\n    G1 X-13.5 F3000\\n    M400\\n    M106 P1 S0\\n\\n    M1002 judge_last_extrude_cali_success\\n    M622 J0\\n        M983 F{outer_wall_volumetric_speed/2.4} A0.3 H[nozzle_diameter]; cali dynamic extrusion compensation\\n        M106 P1 S178\\n        M400 S7\\n        G1 X0 F18000\\n        G1 X-13.5 F3000\\n        G1 X0 F18000 ;wipe and shake\\n        G1 X-13.5 F3000\\n        G1 X0 F12000 ;wipe and shake\\n        M400\\n        M106 P1 S0\\n    M623\\n    \\n    G1 X-13.5 F3000\\n    M400\\n    M984 A0.1 E1 S1 F{outer_wall_volumetric_speed/2.4} H[nozzle_diameter]\\n    M106 P1 S178\\n    M400 S7\\n    G1 X0 F18000\\n    G1 X-13.5 F3000\\n    G1 X0 F18000 ;wipe and shake\\n    G1 X-13.5 F3000\\n    G1 X0 F12000 ;wipe and shake\\n    G1 X-13.5 F3000\\n    M400\\n    M106 P1 S0\\n\\nM623 ; end of \\"draw extrinsic para cali paint\\"\\n\\n;===== extrude cali test ===============================\\nM104 S{nozzle_temperature_initial_layer[initial_extruder]}\\nG90\\nM83\\nG0 X68 Y-2.5 F30000\\nG0 Z0.3 F18000 ;Move to start position\\nG0 X88 E10  F{outer_wall_volumetric_speed/(24/20)    * 60}\\nG0 X93 E.3742  F{outer_wall_volumetric_speed/(0.3*0.5)/4     * 60}\\nG0 X98 E.3742  F{outer_wall_volumetric_speed/(0.3*0.5)     * 60}\\nG0 X103 E.3742  F{outer_wall_volumetric_speed/(0.3*0.5)/4     * 60}\\nG0 X108 E.3742  F{outer_wall_volumetric_speed/(0.3*0.5)     * 60}\\nG0 X113 E.3742  F{outer_wall_volumetric_speed/(0.3*0.5)/4     * 60}\\nG0 X115 Z0 F20000\\nG0 Z5\\nM400\\n\\n;========turn off light and wait extrude temperature =============\\nM1002 gcode_claim_action : 0\\n\\nM400 ; wait all motion done before implement the emprical L parameters\\n\\n;===== for Textured PEI Plate , lower the nozzle as the nozzle was touching topmost of the texture when homing ==\\n;curr_bed_type={curr_bed_type}\\n{if curr_bed_type==\\"Textured PEI Plate\\"}\\nG29.1 Z{-0.02} ; for Textured PEI Plate\\n{endif}\\n\\nM960 S1 P0 ; turn off laser\\nM960 S2 P0 ; turn off laser\\nM106 S0 ; turn off fan\\nM106 P2 S0 ; turn off big fan\\nM106 P3 S0 ; turn off chamber fan\\n\\nM975 S1 ; turn on mech mode supression\\nG90\\nM83\\nT1000\\n\\nM211 X0 Y0 Z0 ;turn off soft endstop\\nM1007 S1\\n\\n\\n\\n\n; machine_tool_change_time = 0\n; machine_unload_filament_time = 34\n; make_overhang_printable = 0\n; make_overhang_printable_angle = 55\n; make_overhang_printable_hole_size = 0\n; manual_filament_change = 0\n; master_extruder_id = 1\n; max_bridge_length = 0\n; max_layer_height = 0.28\n; max_resonance_avoidance_speed = 120\n; max_travel_detour_distance = 0\n; max_volumetric_extrusion_rate_slope = 0\n; max_volumetric_extrusion_rate_slope_segment_length = 3\n; min_bead_width = 85%\n; min_feature_size = 25%\n; min_layer_height = 0.08\n; min_length_factor = 0.5\n; min_resonance_avoidance_speed = 70\n; min_skirt_length = 0\n; min_width_top_surface = 300%\n; minimum_sparse_infill_area = 15\n; mmu_segmented_region_interlocking_depth = 0\n; mmu_segmented_region_max_width = 0\n; notes = \n; nozzle_diameter = 0.4\n; nozzle_flush_dataset = 0\n; nozzle_height = 4.76\n; nozzle_hrc = 0\n; nozzle_temperature = 255\n; nozzle_temperature_initial_layer = 255\n; nozzle_temperature_range_high = 270\n; nozzle_temperature_range_low = 220\n; nozzle_type = stainless_steel\n; nozzle_volume = 92\n; nozzle_volume_type = Standard\n; only_one_wall_first_layer = 0\n; only_one_wall_top = 1\n; ooze_prevention = 0\n; other_layers_print_sequence = 0\n; other_layers_print_sequence_nums = 0\n; outer_wall_acceleration = 5000\n; outer_wall_filament_id = 0\n; outer_wall_flow_ratio = 1\n; outer_wall_jerk = 9\n; outer_wall_line_width = 0.42\n; outer_wall_speed = 200\n; overhang_1_4_speed = 0\n; overhang_2_4_speed = 50\n; overhang_3_4_speed = 30\n; overhang_4_4_speed = 10\n; overhang_fan_speed = 90\n; overhang_fan_threshold = 10%\n; overhang_flow_ratio = 1\n; overhang_reverse = 0\n; overhang_reverse_internal_only = 0\n; overhang_reverse_threshold = 50%\n; parallel_printheads_bed_exclude_areas = \n; parallel_printheads_count = 1\n; parking_pos_retraction = 92\n; part_cooling_fan_min_pwm = 0\n; pellet_flow_coefficient = 0.4157\n; pellet_modded_printer = 0\n; physical_extruder_map = 0\n; plugins = \n; post_process = \n; precise_outer_wall = 1\n; precise_z_height = 0\n; preferred_orientation = 0\n; preheat_steps = 1\n; preheat_time = 30\n; pressure_advance = 0.02\n; prime_tower_brim_width = 3\n; prime_tower_enable_framework = 0\n; prime_tower_flat_ironing = 0\n; prime_tower_infill_gap = 150%\n; prime_tower_skip_points = 1\n; prime_tower_width = 35\n; prime_volume = 45\n; print_compatible_printers = "Bambu Lab A1 mini 0.4 nozzle"\n; print_extruder_id = 1\n; print_extruder_variant = "Direct Drive Standard"\n; print_flow_ratio = 1\n; print_order = default\n; print_plugin_config_overrides = \n; print_sequence = by layer\n; print_settings_id = 0.20mm Standard @BBL A1M\n; printable_area = 0x0,180x0,180x180,0x180\n; printable_height = 180\n; printer_agent = \n; printer_extruder_id = 1\n; printer_extruder_variant = "Direct Drive Standard"\n; printer_model = Bambu Lab A1 mini\n; printer_notes = \n; printer_plugin_config_overrides = \n; printer_settings_id = Bambu Lab A1 mini 0.4 nozzle\n; printer_structure = i3\n; printer_technology = FFF\n; printer_variant = 0.4\n; printhost_authorization_type = key\n; printhost_ssl_ignore_revoke = 0\n; printing_by_object_gcode = \n; process_change_extrusion_role_gcode = \n; purge_in_prime_tower = 0\n; raft_contact_distance = 0.1\n; raft_expansion = 1.5\n; raft_first_layer_density = 90%\n; raft_first_layer_expansion = 2\n; raft_layers = 0\n; reduce_crossing_wall = 0\n; reduce_fan_stop_start_freq = 1\n; reduce_infill_retraction = 1\n; relative_bridge_angle = 0\n; required_nozzle_HRC = 3\n; resolution = 0.012\n; resonance_avoidance = 0\n; retract_after_wipe = 0%\n; retract_before_wipe = 0%\n; retract_length_toolchange = 2\n; retract_lift_above = 0\n; retract_lift_below = 179\n; retract_lift_enforce = All Surfaces\n; retract_restart_extra = 0\n; retract_restart_extra_toolchange = 0\n; retract_when_changing_layer = 1\n; retraction_distances_when_cut = 18\n; retraction_distances_when_ec = 0\n; retraction_length = 0.8\n; retraction_minimum_travel = 1\n; retraction_speed = 30\n; role_based_wipe_speed = 1\n; scan_first_layer = 0\n; scarf_angle_threshold = 155\n; scarf_joint_flow_ratio = 1\n; scarf_joint_speed = 100%\n; scarf_overhang_threshold = 40%\n; seam_gap = 10%\n; seam_position = aligned\n; seam_slope_conditional = 0\n; seam_slope_entire_loop = 0\n; seam_slope_inner_walls = 0\n; seam_slope_min_length = 10\n; seam_slope_start_height = 10%\n; seam_slope_steps = 10\n; seam_slope_type = none\n; separated_infills = 0\n; set_other_flow_ratios = 0\n; silent_mode = 0\n; single_extruder_multi_material = 1\n; single_extruder_multi_material_priming = 0\n; single_loop_draft_shield = 0\n; skeleton_infill_density = 15%\n; skeleton_infill_line_width = 0.45\n; skin_infill_density = 15%\n; skin_infill_depth = 2\n; skin_infill_line_width = 0.45\n; skirt_distance = 2\n; skirt_height = 1\n; skirt_loops = 0\n; skirt_speed = 50\n; skirt_start_angle = -135\n; skirt_type = combined\n; slice_closing_radius = 0.049\n; slicing_mode = regular\n; slicing_pipeline_plugin = \n; slow_down_for_layer_cooling = 1\n; slow_down_layer_time = 12\n; slow_down_layers = 0\n; slow_down_min_speed = 20\n; slowdown_for_curled_perimeters = 0\n; small_area_infill_flow_compensation = 0\n; small_area_infill_flow_compensation_model = 0,0;"\\n0.2,0.4444";"\\n0.4,0.6145";"\\n0.6,0.7059";"\\n0.8,0.7619";"\\n1.5,0.8571";"\\n2,0.8889";"\\n3,0.9231";"\\n5,0.9520";"\\n10,1"\n; small_perimeter_speed = 50%\n; small_perimeter_threshold = 0\n; small_support_perimeter_speed = 50%\n; small_support_perimeter_threshold = 0\n; solid_infill_direction = 45\n; solid_infill_rotate_template = \n; sparse_infill_acceleration = 100%\n; sparse_infill_density = 15%\n; sparse_infill_filament_id = 0\n; sparse_infill_flow_ratio = 1\n; sparse_infill_line_width = 0.45\n; sparse_infill_pattern = crosshatch\n; sparse_infill_rotate_template = \n; sparse_infill_smooth_factor = 0%\n; sparse_infill_speed = 270\n; spiral_finishing_flow_ratio = 0\n; spiral_mode = 0\n; spiral_mode_max_xy_smoothing = 200%\n; spiral_mode_smooth = 0\n; spiral_starting_flow_ratio = 0\n; staggered_inner_seams = 0\n; standby_temperature_delta = -5\n; start_end_points = 30x-3,54x245\n; supertack_plate_temp = 70\n; supertack_plate_temp_initial_layer = 70\n; support_air_filtration = 0\n; support_angle = 0\n; support_base_pattern = default\n; support_base_pattern_spacing = 2.5\n; support_bottom_interface_spacing = 0.5\n; support_bottom_z_distance = 0.2\n; support_chamber_temp_control = 0\n; support_cooling_filter = 0\n; support_critical_regions_only = 0\n; support_expansion = 0\n; support_filament = 0\n; support_flow_ratio = 1\n; support_interface_bottom_layers = 2\n; support_interface_filament = 0\n; support_interface_flow_ratio = 1\n; support_interface_loop_pattern = 0\n; support_interface_not_for_body = 1\n; support_interface_pattern = auto\n; support_interface_spacing = 0.5\n; support_interface_speed = 80\n; support_interface_top_layers = 2\n; support_ironing = 0\n; support_ironing_flow = 10%\n; support_ironing_pattern = rectilinear\n; support_ironing_spacing = 0.1\n; support_line_width = 0.42\n; support_material_interface_fan_speed = -1\n; support_multi_bed_types = 0\n; support_object_first_layer_gap = 0.2\n; support_object_skip_flush = 0\n; support_object_xy_distance = 0.35\n; support_on_build_plate_only = 0\n; support_parallel_printheads = 0\n; support_remove_small_overhang = 1\n; support_speed = 150\n; support_style = default\n; support_threshold_angle = 30\n; support_threshold_overlap = 50%\n; support_top_z_distance = 0.2\n; support_type = tree(auto)\n; symmetric_infill_y_axis = 0\n; temperature_vitrification = 70\n; template_custom_gcode = \n; textured_cool_plate_temp = 40\n; textured_cool_plate_temp_initial_layer = 40\n; textured_plate_temp = 70\n; textured_plate_temp_initial_layer = 70\n; thick_bridges = 0\n; thick_internal_bridges = 1\n; thumbnails = 48x48/PNG,300x300/PNG\n; thumbnails_format = PNG\n; time_cost = 0\n; time_lapse_gcode = ;===================== date: 20250206 =====================\\n{if !spiral_mode && print_sequence != \\"by object\\"}\\n; don\'t support timelapse gcode in spiral_mode and by object sequence for I3 structure printer\\n; SKIPPABLE_START\\n; SKIPTYPE: timelapse\\nM622.1 S1 ; for prev firmware, default turned on\\nM1002 judge_flag timelapse_record_flag\\nM622 J1\\nG92 E0\\nG1 Z{max_layer_z + 0.4}\\nG1 X0 Y{first_layer_center_no_wipe_tower[1]} F18000 ; move to safe pos\\nG1 X-13.0 F3000 ; move to safe pos\\nM400\\nM1004 S5 P1  ; external shutter\\nM400 P300\\nM971 S11 C11 O0\\nG92 E0\\nG1 X0 F18000\\nM623\\n\\n; SKIPTYPE: head_wrap_detect\\nM622.1 S1\\nM1002 judge_flag g39_3rd_layer_detect_flag\\nM622 J1\\n    ; enable nozzle clog detect at 3rd layer\\n    {if layer_num == 2}\\n      M400\\n      G90\\n      M83\\n      M204 S5000\\n      G0 Z2 F4000\\n      G0 X187 Y178 F20000\\n      G39 S1 X187 Y178\\n      G0 Z2 F4000\\n    {endif}\\n\\n\\n    M622.1 S1\\n    M1002 judge_flag g39_detection_flag\\n    M622 J1\\n      {if !in_head_wrap_detect_zone}\\n        M622.1 S0\\n        M1002 judge_flag g39_mass_exceed_flag\\n        M622 J1\\n        {if layer_num > 2}\\n            G392 S0\\n            M400\\n            G90\\n            M83\\n            M204 S5000\\n            G0 Z{max_layer_z + 0.4} F4000\\n            G39.3 S1\\n            G0 Z{max_layer_z + 0.4} F4000\\n            G392 S0\\n          {endif}\\n        M623\\n    {endif}\\n    M623\\nM623\\n; SKIPPABLE_END\\n{endif}\\n\\n\\n\n; timelapse_type = 0\n; tool_change_on_wipe_tower = 0\n; toolchange_ordering = default\n; top_bottom_infill_wall_overlap = 25%\n; top_layer_direction = -1\n; top_shell_layers = 5\n; top_shell_thickness = 1\n; top_solid_infill_flow_ratio = 1\n; top_surface_acceleration = 2000\n; top_surface_density = 100%\n; top_surface_expansion = 0\n; top_surface_expansion_direction = inward_and_outward\n; top_surface_expansion_margin = 0\n; top_surface_filament_id = 0\n; top_surface_fill_order = default\n; top_surface_jerk = 9\n; top_surface_line_width = 0.42\n; top_surface_pattern = monotonicline\n; top_surface_speed = 200\n; travel_acceleration = 10000\n; travel_jerk = 12\n; travel_slope = 3\n; travel_speed = 700\n; travel_speed_z = 0\n; tree_support_angle_slow = 25\n; tree_support_auto_brim = 1\n; tree_support_branch_angle = 45\n; tree_support_branch_angle_organic = 40\n; tree_support_branch_diameter = 2\n; tree_support_branch_diameter_angle = 5\n; tree_support_branch_diameter_organic = 2\n; tree_support_branch_distance = 5\n; tree_support_branch_distance_organic = 1\n; tree_support_brim_width = 3\n; tree_support_tip_diameter = 0.8\n; tree_support_top_rate = 30%\n; tree_support_wall_count = 0\n; upward_compatible_machine = "Bambu Lab P1S 0.4 nozzle";"Bambu Lab P1P 0.4 nozzle";"Bambu Lab X1 0.4 nozzle";"Bambu Lab X1 Carbon 0.4 nozzle";"Bambu Lab X1E 0.4 nozzle";"Bambu Lab A1 0.4 nozzle";"Bambu Lab H2D 0.4 nozzle";"Bambu Lab H2D Pro 0.4 nozzle";"Bambu Lab H2S 0.4 nozzle";"Bambu Lab P2S 0.4 nozzle"\n; use_3mf = 0\n; use_firmware_retraction = 0\n; use_relative_e_distances = 1\n; volumetric_speed_coefficients = "0 0 0 0 0 0"\n; wait_for_temp_on_wipe_tower = 0\n; wall_direction = ccw\n; wall_distribution_count = 1\n; wall_generator = classic\n; wall_loops = 2\n; wall_maximum_deviation = 0.025\n; wall_maximum_resolution = 0.5\n; wall_sequence = inner wall/outer wall\n; wall_transition_angle = 10\n; wall_transition_filter_deviation = 25%\n; wall_transition_length = 100%\n; wipe = 1\n; wipe_before_external_loop = 0\n; wipe_distance = 2\n; wipe_on_loops = 0\n; wipe_speed = 80%\n; wipe_tower_bridging = 10\n; wipe_tower_cone_angle = 30\n; wipe_tower_extra_flow = 100%\n; wipe_tower_extra_rib_length = 0\n; wipe_tower_extra_spacing = 100%\n; wipe_tower_filament = 0\n; wipe_tower_fillet_wall = 1\n; wipe_tower_max_purge_speed = 90\n; wipe_tower_no_sparse_layers = 0\n; wipe_tower_rib_width = 8\n; wipe_tower_rotation_angle = 0\n; wipe_tower_type = type2\n; wipe_tower_wall_type = rib\n; wipe_tower_x = 29.000\n; wipe_tower_x = 29\n; wipe_tower_y = 250.000\n; wipe_tower_y = 250\n; wiping_volumes_extruders = 70,70,70,70,70,70,70,70,70,70\n; wrapping_detection_gcode = \n; wrapping_detection_layers = 20\n; wrapping_exclude_area = \n; xy_contour_compensation = 0\n; xy_hole_compensation = 0\n; z_hop = 0.4\n; z_hop_types = Auto Lift\n; z_offset = 0\n; zaa_dont_alternate_fill_direction = 0\n; zaa_enabled = 0\n; zaa_min_z = 0.05\n; zaa_minimize_perimeter_height = 35\n; first_layer_bed_temperature = 70\n; first_layer_temperature = 255\n; CONFIG_BLOCK_END'
    preserve_project_keys = ('layer_height', 'initial_layer_print_height', 'initial_layer_line_width', 'line_width', 'outer_wall_line_width', 'inner_wall_line_width', 'sparse_infill_line_width', 'top_surface_line_width', 'support_line_width', 'print_sequence', 'spiral_mode')
    preserved_project = {k: old_project[k] for k in preserve_project_keys if k in old_project}
    project = dict(native_project)
    project.update(preserved_project)
    project.update({'printer_model': A1_MINI_PRINTER_NAME, 'printer_settings_id': A1_MINI_PRINTER_PRESET, 'print_settings_id': A1_MINI_PROCESS_PRESET, 'print_compatible_printers': [A1_MINI_PRINTER_PRESET], 'printer_structure': 'i3', 'printable_area': ['0x0', '180x0', '180x180', '0x180'], 'printable_height': '180', 'nozzle_diameter': ['0.4'], 'nozzle_type': ['stainless_steel'], 'nozzle_volume': ['92'], 'nozzle_volume_type': ['Standard'], 'default_nozzle_volume_type': ['Standard'], 'printer_extruder_id': ['1'], 'print_extruder_id': ['1'], 'printer_extruder_variant': ['Direct Drive Standard'], 'print_extruder_variant': ['Direct Drive Standard'], 'filament_settings_id': ['Generic PETG @BBL A1M'], 'filament_type': ['PETG'], 'filament_colour': ['#000000'], 'filament_multi_colour': ['#000000'], 'filament_ids': ['GFG99'], 'filament_map': ['1'], 'filament_map_2': ['1'], 'filament_nozzle_map': ['0'], 'physical_extruder_map': ['0'], 'extruder_ams_count': ['1#0|4#0', ''], 'enable_prime_tower': '0', 'prime_tower_enable_framework': '0', 'curr_bed_type': 'Textured PEI Plate', 'ensure_vertical_shell_thickness': 'ensure_all', 'raft_first_layer_expansion': '2', 'prime_tower_brim_width': '3', 'machine_start_gcode': _a1mini_start_gcode() + '\n', 'machine_end_gcode': _a1mini_end_gcode(_mirror_wave_peak_z_mm()) + '\n'})
    project.pop('prime_tower_lift_height', None)
    a = old_g.find('; CONFIG_BLOCK_START')
    b0 = old_g.find('; CONFIG_BLOCK_END')
    if a < 0 or b0 < 0 or b0 <= a:
        raise RuntimeError('V1.101 ORCA REFERENCE METADATA: CONFIG_BLOCK boundaries missing')
    b = b0 + len('; CONFIG_BLOCK_END')
    new_g = old_g[:a] + native_config + old_g[b:]
    preserve_config_keys = preserve_project_keys
    for key in preserve_config_keys:
        m = re.search(f'^; {re.escape(key)} = (.*)$', old_g, re.M)
        if m:
            new_g = _replace_config_comment(new_g, key, m.group(1))
    for key, value in {'enable_prime_tower': '0', 'prime_tower_enable_framework': '0', 'curr_bed_type': 'Textured PEI Plate', 'ensure_vertical_shell_thickness': 'ensure_all', 'raft_first_layer_expansion': '2', 'prime_tower_brim_width': '3', 'machine_start_gcode': _a1mini_start_gcode().replace('\n', '\\n'), 'machine_end_gcode': _a1mini_end_gcode(_mirror_wave_peak_z_mm()).replace('\n', '\\n')}.items():
        new_g = _replace_config_comment(new_g, key, value)
    header_patch = {'filament': '1', 'filament_density': '1.27', 'filament_diameter': '1.75'}
    for key, value in header_patch.items():
        pat = re.compile(f'^; {re.escape(key)}:\\s*.*$', re.M)
        if len(pat.findall(new_g)) != 1:
            raise RuntimeError(f'V1.101 ORCA REFERENCE METADATA: expected one header {key} line')
        new_g = pat.sub(lambda _m, k=key, v=value: f'; {k}: {v}', new_g, count=1)
    config_contract = {'default_filament_profile': '"Bambu PLA Basic @BBL A1M"', 'filament_settings_id': '"Generic PETG @BBL A1M"', 'filament_colour': '#000000', 'filament_type': 'PETG', 'filament_ids': 'GFG99', 'filament_map': '1', 'filament_map_2': '0', 'filament_nozzle_map': '0', 'filament_extruder_variant': '"Direct Drive Standard"', 'filament_max_volumetric_speed': '8', 'filament_flow_ratio': '0.95', 'extruder_ams_count': '1#0|4#0;', 'physical_extruder_map': '0', 'single_extruder_multi_material': '1', 'printer_extruder_id': '1', 'print_extruder_id': '1', 'printer_extruder_variant': '"Direct Drive Standard"', 'print_extruder_variant': '"Direct Drive Standard"', 'extruder_max_nozzle_count': '1', 'extruder_nozzle_stats': 'Standard#1', 'extruder_variant_list': '"Direct Drive Standard"', 'extruder_type': 'Direct Drive', 'extruder_offset': '0x0', 'extruder_colour': '#000000', 'extruder_printable_area': '', 'extruder_printable_height': '0'}
    for key, value in config_contract.items():
        new_g = _replace_config_comment(new_g, key, value)
    header = slice_root.find('header')
    if header is None:
        header = ET.Element('header')
        slice_root.insert(0, header)
    header_items = {n.attrib.get('key'): n for n in header.findall('header_item')}
    for key, value in (('X-BBL-Client-Type', 'slicer'), ('X-BBL-Client-Version', '02.08.01.55'), ('OrcaSlicer-Version', '2.5.0-dev')):
        node = header_items.get(key)
        if node is None:
            node = ET.SubElement(header, 'header_item', key=key, value=value)
        else:
            node.set('value', value)
    plate_node = slice_root.find('plate')
    if plate_node is None:
        raise RuntimeError('V1.101 ORCA REFERENCE METADATA: slice_info has no plate')
    meta_nodes = {n.attrib.get('key'): n for n in plate_node.findall('metadata') if n.attrib.get('key')}
    for key, value in (('printer_model_id', 'N1'), ('nozzle_diameters', '0.4'), ('nozzle_volume_type', '0'), ('has_filament_switcher', 'false'), ('filament_maps', '1'), ('limit_filament_maps', '0')):
        node = meta_nodes.get(key)
        if node is None:
            ET.SubElement(plate_node, 'metadata', key=key, value=value)
        else:
            node.set('value', value)
    old_fil = plate_node.find('filament')
    used_m = old_fil.attrib.get('used_m', '0.00') if old_fil is not None else '0.00'
    used_g = old_fil.attrib.get('used_g', '0.00') if old_fil is not None else '0.00'
    for node in list(plate_node.findall('filament')):
        plate_node.remove(node)
    ET.SubElement(plate_node, 'filament', {'id': '1', 'tray_info_idx': 'GFG99', 'type': 'PETG', 'color': '#000000', 'used_m': used_m, 'used_g': used_g, 'group_id': '0', 'nozzle_diameter': '0.40', 'volume_type': 'Standard', 'used_for_object': 'true', 'used_for_support': 'false'})
    for node in list(plate_node.findall('nozzle')):
        plate_node.remove(node)
    ET.SubElement(plate_node, 'nozzle', {'id': '0', 'extruder_id': '1', 'nozzle_diameter': '0.4', 'volume_type': 'Standard'})
    layer_lists = plate_node.find('layer_filament_lists')
    if layer_lists is not None:
        existing_ranges = [n.attrib.get('layer_ranges') for n in list(layer_lists) if n.attrib.get('layer_ranges')]
        for node in list(layer_lists):
            layer_lists.remove(node)
        layer_ranges = existing_ranges[0] if existing_ranges else f'0 {PHYSICAL_LAYER_COUNT - 1}'
        ET.SubElement(layer_lists, 'layer_filament_list', filament_list='0', layer_ranges=layer_ranges)
    plate['bed_type'] = 'textured_plate'
    plate['filament_colors'] = ['#000000']
    plate['filament_ids'] = [0]
    plate['first_extruder'] = 0
    plate['nozzle_diameter'] = 0.4000000059604645
    seq = {'plate_1': {'nozzle_sequence': [0], 'optimal_assignment': [0], 'sequence': [1]}}
    ms_plate = model_settings_root.find('plate')
    if ms_plate is None:
        raise RuntimeError('V1.101 ORCA REFERENCE METADATA: model_settings has no plate')
    ms_meta = {n.attrib.get('key'): n for n in ms_plate.findall('metadata') if n.attrib.get('key')}
    for key, value in (('filament_maps', '1'), ('filament_volume_maps', '0')):
        node = ms_meta.get(key)
        if node is None:
            ET.SubElement(ms_plate, 'metadata', key=key, value=value)
        else:
            node.set('value', value)
    if 'fc3d_active_filament_one_based' in ms_meta:
        ms_meta['fc3d_active_filament_one_based'].set('value', '1')
    app_pat = re.compile('<metadata name="Application">.*?</metadata>')
    if len(app_pat.findall(model_text)) != 1:
        raise RuntimeError('V1.101 ORCA REFERENCE METADATA: 3D model Application metadata missing/ambiguous')
    model_text = app_pat.sub('<metadata name="Application">BambuStudio-02.08.01.55</metadata>', model_text, count=1)
    orca_pat = re.compile('<metadata name="OrcaSlicer">.*?</metadata>')
    if orca_pat.search(model_text):
        model_text = orca_pat.sub('<metadata name="OrcaSlicer">2.5.0-dev</metadata>', model_text, count=1)
    else:
        app_line = '<metadata name="Application">BambuStudio-02.08.01.55</metadata>'
        model_text = model_text.replace(app_line, app_line + '\n <metadata name="OrcaSlicer">2.5.0-dev</metadata>', 1)
    replacements = {gname: new_g.encode('utf-8'), pname: json.dumps(project, separators=(',', ':'), ensure_ascii=False).encode('utf-8'), sname: ET.tostring(slice_root, encoding='utf-8', xml_declaration=True), plate_name: json.dumps(plate, separators=(',', ':'), ensure_ascii=False).encode('utf-8'), seq_name: json.dumps(seq, separators=(',', ':'), ensure_ascii=False).encode('utf-8'), model_settings_name: ET.tostring(model_settings_root, encoding='utf-8', xml_declaration=True), model_name: model_text.encode('utf-8')}
    _replace_zip_members(output, replacements)
    return audit_a1mini_orca_reference_metadata(output)


# ---- audit_a1mini_orca_reference_metadata ----
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


# ---- main ----
def main(argv=None):
    ap = argparse.ArgumentParser(description='FC3D v1.159: standalone 0.4 mm mapped K/W converter with v158 thin-cap behaviour', allow_abbrev=False)
    ap.add_argument('--source', type=Path, default=Path('3dprintv1.179.py'))
    ap.add_argument('--piece', choices=tuple(f'{c}-{r}' for c in range(1, 6) for r in range(1, 6)), required=True)
    ap.add_argument('--layer-map', default='kkkwwk', help='bottom-to-top leading arc colours; K black, W white; 1-16 tiers')
    ap.add_argument('--layer-height-mm', type=float, default=.24, help='common optical material-dose height, up to 0.28 mm')
    ap.add_argument('--cap-height-mm', type=float, help='final/top K material-dose height; default equals --layer-height-mm')
    ap.add_argument('--physical-height-scale', type=float, default=1.4, help='optical Z spacing multiplier; never multiplies extrusion')
    ap.add_argument('--visibility-percent', type=float, required=True, help='minimum projector visibility of each W front quarter, 0-100')
    ap.add_argument('--horizontal-percent', type=float, default=0., help='rotate arcs towards horizontal: 0 original, 100 horizontal')
    ap.add_argument('--minimum-pitch-mm', type=float, default=0., help='optional minimum normal ridge pitch')
    ap.add_argument('--printer-target', choices=('a1mini',), default='a1mini')
    ap.add_argument('--slicer-target', '--slicer', choices=('orca', 'studio'), default='orca')
    ap.add_argument('--output', type=Path)
    ap.add_argument('--dry-validate', action='store_true')
    ap.add_argument('--audit', action='store_true', help='accepted for convenience; package audits always run')
    known, passthrough = ap.parse_known_args(argv)
    try:
        rt = _mapped_runtime(known.layer_map, known.layer_height_mm, known.physical_height_scale,
                             known.visibility_percent, known.piece, known.minimum_pitch_mm,
                             known.horizontal_percent, known.cap_height_mm)
    except ValueError as e:
        ap.error(str(e))
    reject_protected_passthrough(passthrough)
    schedule = _tower_schedule(rt)
    print(SCRIPT_VERSION, flush=True)
    print(f'  {LAYER_MAP}: {len(LAYER_MAP)} tiers, {sum(_mode_profile()["tier_counts"])} arcs per pyramid', flush=True)
    print(f'  optical tier step {PHYSICAL_LAYER_HEIGHT_MM:.3f} mm; feature height {NOMINAL_TOP_Z_MM-.4:.3f} mm; base top Z0.400', flush=True)
    try:
        report = optical_spacing_report(CURRENT_PIECE)
    except ValueError as e:
        ap.error(str(e))
    print(json.dumps(report, indent=2), flush=True)
    print('  rear marking: ' + ' / '.join(REAR_TEXT_LINES), flush=True)
    if known.dry_validate:
        print('DRY VALIDATION: PASS', flush=True)
        return
    if not known.source.is_file():
        ap.error(f'canonical source not found: {known.source}')
    final_output = known.output or _mapped_output_name(rt)
    if len(final_output.name) > 100:
        ap.error('choose an output basename of 100 characters or fewer for Bambu Connect')
    package = final_output.with_name(final_output.name + '.v159working.gcode.3mf')
    dp = import_3dprint(known.source)
    install_patches(dp, 45., 45., 45.)
    with tempfile.TemporaryDirectory(prefix='fc3d_v159_') as td:
        placeholder = Path(td) / 'placeholder.png'
        Image.new('RGB', (8, 2), (22, 22, 22)).save(placeholder)
        args = [str(known.source), '--direct-layer-images', ','.join([str(placeholder)] * DIRECT_OPTICAL_LAYER_COUNT),
                '--direct-layout', '4x2', '--center-x', '90.000', '--center-y', '90.000', '--output', str(package),
                '--rp-pitch-mm', f'{RP_PITCH_MM:.6f}', '--print-width-mm', f'{ROAD_WIDTH_MM:.6f}',
                '--endpoint-trim-mm', '0', '--close-gaps-mm', '0', '--directional-block-mm', '0', '--edge-aa', 'off',
                '--skip-absent-layer-materials', 'on', '--progress', 'on', '--filament-assignment-json',
                json.dumps({LOGICAL_MATERIAL: BLACK_ASSIGNMENT}, separators=(',', ':'))]
        old = sys.argv
        try:
            sys.argv = args + passthrough
            dp.main()
        finally:
            sys.argv = old
    apply_mirror_wave_paths(package)
    apply_top_support_valley_fill(package)
    apply_dynamic_tower_policy(package)
    enforce_minimum_model_part_fan(package)
    audit_final_base_interlock(package)
    audit_final_black_texture_and_single_material(package)
    audit_top_support_valley_fill(package)
    convert_package_to_a1mini_orca(package)
    normalize_a1mini_orca_reference_metadata(package)
    apply_slicer_target_metadata(package, known.slicer_target)
    global CURRENT_PIECE_NAME, CURRENT_REAR_PARAMETER_TEXT
    CURRENT_PIECE_NAME = known.piece
    CURRENT_REAR_PARAMETER_TEXT = REAR_PARAMETER_TEXT
    _patch_native_lifecycle_and_revision(package, schedule['max_deposited_z'])
    colour = _apply_contrast(package, rt)
    audit = _audit_package(package, rt, known.piece)
    audit['horizontal_geometry'] = _audit_horizontal_motion(package, rt)
    audit.update(revision=REVISION, script_version=SCRIPT_VERSION,
                 exporter_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                 canonical_source_sha256=hashlib.sha256(known.source.read_bytes()).hexdigest(),
                 cap_height_mm=CAP_HEIGHT_MM, cap_physical_height_mm=CAP_PHYSICAL_HEIGHT_MM,
                 tier_physical_heights_mm=list(TIER_PHYSICAL_HEIGHTS_MM))
    _replace_zip(package, {'Metadata/fc3d_mapped_pyramid_audit.json': json.dumps(audit, indent=2).encode()})
    package.replace(final_output)
    print('PACKAGED G-CODE AUDIT: PASS', flush=True)
    print(f'  {colour["optical_roads"]} optical roads; {colour["colour_changes"]} colour changes; {len(colour["tower_heights_mm"])} prime-tower layers', flush=True)
    print('Saved: ' + str(final_output), flush=True)


# ---- _unrotated_label_intervals ----
def _unrotated_label_intervals(piece, y_local_mm):
    text = []
    for line, y0 in zip(REAR_TEXT_LINES, LABEL_LINE_Y0_MM):
        if line:
            text += _text_intervals(piece, line, y_local_mm, y0)
    return _merge_intervals(text + _arrow_intervals(piece, y_local_mm))


# ---- _gcode_xy ----
def _gcode_xy(point):
    """The XY point the printer receives after three-decimal G-code output."""
    return round(float(point[0]),3),round(float(point[1]),3)


# ---- _gcode_chord_length ----
def _gcode_chord_length(a, b):
    ar=_gcode_xy(a); br=_gcode_xy(b)
    return math.hypot(br[0]-ar[0],br[1]-ar[1])


# ---- _polyline_prefix_for_length ----
def _polyline_prefix_for_length(points, wanted_length):
    """Return the original absolute curve up to an exact arc-length position."""
    source=[(float(p[0]),float(p[1])) for p in points]
    if not source:
        return []
    remaining=max(0.0,float(wanted_length)); out=[source[0]]
    for a,b in zip(source,source[1:]):
        ds=math.hypot(b[0]-a[0],b[1]-a[1])
        if ds <= 1e-12:
            continue
        if remaining >= ds-1e-12:
            out.append(b); remaining-=ds
            if remaining <= 1e-12:
                return out
            continue
        t=remaining/ds
        out.append((a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t))
        return out
    return out


# ---- _coalesce_curve_for_emission ----
def _coalesce_curve_for_emission(points):
    """Keep absolute source-curve points at >=0.8-mm chords plus the endpoint."""
    source=[(float(p[0]),float(p[1])) for p in points]
    if len(source) <= 2:
        return source
    emitted=[source[0]]
    for point in source[1:-1]:
        if _gcode_chord_length(emitted[-1],point) >= MIN_EMITTED_CHORD_MM:
            emitted.append(point)
    if _gcode_xy(source[-1]) == _gcode_xy(emitted[-1]):
        emitted[-1]=source[-1]
    elif source[-1] != emitted[-1]:
        emitted.append(source[-1])
    return emitted


# ---- _du_for_frame ----
def _du_for_frame(frame):
    theta=max(1e-6,math.radians(frame["facet_tilt_deg"]))
    return PHYSICAL_LAYER_HEIGHT_MM/max(1e-9,math.tan(theta))


# ---- _stack_cross_section_profile ----
def _stack_cross_section_profile(facet_tilt_deg):
    theta = max(1e-6, math.radians(float(facet_tilt_deg)))
    du = PHYSICAL_LAYER_HEIGHT_MM / max(1e-9, math.tan(theta))
    counts = _mode_profile()["tier_counts"]
    tiers = []
    for tier, count in enumerate(counts):
        shift = 0.0 if OPTICAL_MODE == "single-arc" else tier * du
        tiers.append({
            "tier": tier + 1,
            "road_count": count,
            "base_height_mm": tier * PHYSICAL_LAYER_HEIGHT_MM,
            "centres_u_mm": [shift + (i + 0.5) * ARC_PROFILE_WIDTH_MM for i in range(count)],
        })
    base_centres = tiers[0]["centres_u_mm"]
    return {
        "tiers": tiers,
        "height_mm": len(counts) * PHYSICAL_LAYER_HEIGHT_MM,
        "base_width_mm": counts[0] * ARC_PROFILE_WIDTH_MM,
        "du_mm": du,
        "front_base_edge_u_mm": max(base_centres) + 0.5 * ARC_PROFILE_WIDTH_MM,
        "rear_base_edge_u_mm": min(base_centres) - 0.5 * ARC_PROFILE_WIDTH_MM,
    }


# ---- _physical_envelope_gap ----
def _physical_envelope_gap(current, previous):
    if not current:
        return float("-inf")
    if not _mode_profile()["smooth"]:
        distances = [math.hypot(c[0] - p[0], c[1] - p[1]) for c, p in zip(current, previous)]
        if OPTICAL_MODE == "single-arc":
            return min(distances) - ARC_PROFILE_WIDTH_MM
        gaps = []
        for c, p, distance in zip(current, previous, distances):
            dc = _du_for_frame(mirror_frame_global(c[0], c[1]))
            dp = _du_for_frame(mirror_frame_global(p[0], p[1]))
            for tier, count in enumerate(_mode_profile()["tier_counts"]):
                gaps.append(distance + tier * dc - tier * dp - count * ARC_PROFILE_WIDTH_MM)
        return min(gaps)
    gaps = []
    for near, far in zip(current, previous):
        distance = math.hypot(near[0] - far[0], near[1] - far[1])
        near_rear, _ = _smooth_assembly_extents(near)
        _, far_front = _smooth_assembly_extents(far)
        gaps.append(distance + near_rear - far_front)
    return min(gaps)


# ---- _full_arc_physical_gap ----
def _full_arc_physical_gap(current, previous, piece):
    if not HORIZONTAL_PERCENT:
        return _original_full_arc_physical_gap(current, previous, piece)
    def nearby(points):
        halo = 2. + len(LAYER_MAP) * ARC_PROFILE_WIDTH_MM
        ids = [i for i, p in enumerate(points) if piece.global_x0_mm - halo <= p[0] <= piece.global_x1_mm + halo
               and piece.global_z0_mm - halo <= p[1] <= piece.global_z1_mm + halo]
        return points[max(0, min(ids) - 1):min(len(points), max(ids) + 2)] if ids else []
    def distance(points, line):
        p = np.asarray(points)
        a = np.asarray(line[:-1])
        v = np.diff(np.asarray(line), axis=0)
        q = p[:, None, :] - a[None, :, :]
        vv = np.sum(v * v, axis=1)
        t = np.clip(np.sum(q * v[None, :, :], axis=2) / np.maximum(vv, 1e-20), 0, 1)
        d = q - t[:, :, None] * v[None, :, :]
        d2 = np.sum(d * d, axis=2)
        return float(np.sqrt(np.min(d2)))
    gaps = []
    for tier, count in enumerate(_mode_profile()['tier_counts']):
        outer = nearby(_offset_road_curve(previous, tier, count - 1))
        inner = nearby(_offset_road_curve(current, tier, 0))
        if len(outer) < 2 or len(inner) < 2:
            continue
        for point in nearby(previous)[::8]:
            _horizontal_normal_intersection(point, current)
        d = min(distance(outer, inner), distance(inner, outer))
        gaps.append(d - ARC_PROFILE_WIDTH_MM - .002)
    return min(gaps) if gaps else float('inf')


# ---- _reference_setup ----
def _reference_setup(piece):
    if not HORIZONTAL_PERCENT:
        return _original_reference_setup(piece)
    cx = (piece.global_x0_mm + piece.global_x1_mm) / 2
    cy = (piece.global_z0_mm + piece.global_z1_mm) / 2
    b = mirror_frame_global(cx, cy)['b_unit']
    corners = [(x, y) for x in (piece.global_x0_mm, piece.global_x1_mm)
               for y in (piece.global_z0_mm, piece.global_z1_mm)]
    corner = min(corners, key=lambda p: p[0] * b[0] + p[1] * b[1])
    seed = _waveset_advance_point_inward(*corner, .4)
    length = 1.15 * math.hypot(piece.width_mm, piece.height_mm)
    return dict(curve=_trace_a_streamline_global(*seed, length, length, 1.),
                advance='seed', seed=seed, negative=length, positive=length, piece=piece)


# ---- _advance_candidate ----
def _advance_candidate(previous, setup, distance):
    if not HORIZONTAL_PERCENT:
        return _original_advance_candidate(previous, setup, distance)
    mid = _curve_midpoint_in_piece(previous, setup['piece'])
    seed = _waveset_advance_point_inward(*mid, distance)
    return _trace_a_streamline_global(*seed, setup['negative'], setup['positive'], 1.), seed


# ---- _curve_midpoint_in_piece ----
def _curve_midpoint_in_piece(curve, piece):
    halo=ROAD_WIDTH_MM
    eligible=[p for p in curve if piece.global_x0_mm-halo<=p[0]<=piece.global_x1_mm+halo and
              piece.global_z0_mm-halo<=p[1]<=piece.global_z1_mm+halo]
    return eligible[len(eligible)//2] if eligible else curve[len(curve)//2]


# ---- _advance_midpoint ----
def _advance_midpoint(point, distance):
    if _mode_profile()["placement"] == "outer_to_inner":
        return _waveset_advance_point_inward(point[0], point[1], distance)
    return _advance_b_rise_global(point[0], point[1], distance, B_FRONT_MAX_STEP_MM)[0]


# ---- _offset_road_curve ----
def _offset_road_curve(curve, tier, road_index):
    if OPTICAL_MODE == "single-arc":
        return list(curve)
    out = []
    for x, z in curve:
        frame = mirror_frame_global(x, z)
        profile = _stack_cross_section_profile(frame["facet_tilt_deg"])
        centre = profile["tiers"][tier]["centres_u_mm"][road_index]
        leading = max(profile["tiers"][0]["centres_u_mm"])
        # Smooth reference curves are the leading base road.  Retain the old P
        # origin convention so legacy P output is byte-for-byte unaffected.
        offset = centre - leading if _mode_profile()["smooth"] else centre
        out.append((x + frame["b_unit"][0] * offset,
                    z + frame["b_unit"][1] * offset))
    return out


# ---- _clip_roads ----
def _clip_roads(curve, piece):
    roads = {}
    for tier, count in enumerate(_mode_profile()["tier_counts"]):
        for road_index in range(count):
            clips = _waveset_clip_curve(_offset_road_curve(curve, tier, road_index), piece)
            roads[(tier, road_index)] = [
                (p[0] - piece.global_x0_mm, p[1] - piece.global_z0_mm) for p in clips]
    return roads


# ---- get_optical_lattice ----
def get_optical_lattice(piece):
    key = (piece.name, LAYER_MAP, LAYER_HEIGHT_MM, PHYSICAL_HEIGHT_SCALE,
           VISIBILITY_PERCENT, MINIMUM_PITCH_MM, HORIZONTAL_PERCENT, CAP_HEIGHT_MM)
    if key not in _OPTICAL_LATTICE_CACHE:
        _OPTICAL_LATTICE_CACHE[key] = _mapped_generate_lattice(piece)
    return _OPTICAL_LATTICE_CACHE[key]


# ---- optical_spacing_report ----
def optical_spacing_report(piece):
    result = _mapped_spacing_report(piece)
    result.update(revision=REVISION, cap_height_mm=CAP_HEIGHT_MM,
        cap_physical_height_mm=CAP_PHYSICAL_HEIGHT_MM,
        tier_physical_heights_mm=list(TIER_PHYSICAL_HEIGHTS_MM),
        support_height_mm=sum(TIER_PHYSICAL_HEIGHTS_MM),
        model_top_z_mm=BASE_TOP_Z_MM + sum(TIER_PHYSICAL_HEIGHTS_MM),
        thin_cap_definition='final/top K tier only; W tiers retain v1.156 geometry and dose',
        horizontal_percent=HORIZONTAL_PERCENT,
        horizontal_definition='local arc angle rotated towards screen horizontal; 0 preserves original, 100 horizontal',
        minimum_pitch_mm=MINIMUM_PITCH_MM)
    return result


# ---- _mode_profile ----
def _mode_profile():
    return MODE_PROFILES[OPTICAL_MODE]


# ---- _support_linear_max ----
def _support_linear_max(profile, gradient, lower=-float('inf'), upper=float('inf')):
    """Exact max of P(u)+gradient*u on clipped half-ellipse support roads."""
    a = 0.5 * ARC_PROFILE_WIDTH_MM
    height = PHYSICAL_LAYER_HEIGHT_MM
    best, location = -float('inf'), None
    for tier in profile['tiers']:
        base = tier['base_height_mm']
        for center in tier['centres_u_mm']:
            lo, hi = max(lower, center-a), min(upper, center+a)
            if hi < lo:
                continue
            stationary = center + gradient*a*a / math.hypot(height, gradient*a)
            u = min(hi, max(lo, stationary))
            top = base + height*math.sqrt(max(0.0, 1.0-((u-center)/a)**2))
            value = top + gradient*u
            if value > best:
                best, location = value, u
    return best, location


# ---- _flat_tip_contact_max ----
def _flat_tip_contact_max(profile, slope, intercept, start, end, radius):
    """Static 2D swept flat-tip estimate; original support, no melt prediction."""
    lo, hi = min(start,end), max(start,end)
    if slope > 0:
        ranges = ((lo-radius,lo+radius,0.0,-slope*lo-intercept),
                  (lo+radius,hi+radius,-slope,slope*radius-intercept))
    elif slope < 0:
        ranges = ((lo-radius,hi-radius,-slope,-slope*radius-intercept),
                  (hi-radius,hi+radius,0.0,-slope*hi-intercept))
    else:
        ranges = ((lo-radius,hi+radius,0.0,-intercept),)
    return max((_support_linear_max(profile,g,a,b)[0]+k for a,b,g,k in ranges),
               default=-float('inf'))


# ---- _smooth_cross_section_profile ----
def _smooth_cross_section_profile(facet_tilt_deg, support=None):
    """Fit a fixed optical slope to the immutable support by vertical embedding."""
    if not _mode_profile()['smooth']:
        raise ValueError('smooth cross-section requested for a non-smooth mode')
    angle = float(facet_tilt_deg)
    if not math.isfinite(angle) or not 0.0 < angle < 89.9:
        raise ValueError('smoothing optical angle must be finite and between 0 and 89.9 degrees')
    theta = math.radians(angle)
    slope = math.tan(theta)
    profile = _stack_cross_section_profile(angle) if support is None else support
    leading = max(profile['tiers'][0]['centres_u_mm'])
    crest_u = profile['tiers'][-1]['centres_u_mm'][0]
    h, embed = SMOOTH_LAYER_HEIGHT_MM, SMOOTH_EMBED_DEPTH_MM
    tangent, touch_u = _support_linear_max(profile,slope,crest_u)
    intercept = tangent + h - embed
    crest_h = intercept-slope*crest_u
    front_u = (intercept-h)/slope
    if crest_h <= h+1e-9 or front_u <= crest_u+1e-9:
        raise ValueError('smoothing embed depth leaves no rising optical face above the valley')
    if OPTICAL_MODE == 'smooth1':
        rear_angle = theta
    else:
        rear_angle = math.atan2(profile['height_mm'],
                                abs(crest_u-profile['rear_base_edge_u_mm']))
    rear_slope = math.tan(rear_angle)
    rear_u = crest_u-(crest_h-h)/rear_slope
    rear_intercept = crest_h-rear_slope*crest_u
    # Clip the tests to the actual printed front and rear legs, including the
    # level landing if it lies inside the footprint of the rearmost road.
    front_max = _support_linear_max(profile,slope,crest_u,front_u)[0]-intercept+h
    if not math.isfinite(front_max) or abs(front_max-embed) > 1e-7:
        raise ValueError(f'{OPTICAL_MODE} smoothing embed depth {embed:.6f} mm cannot be achieved '
                         'on the printed front face: the support contact lies beyond the derived foot; '
                         'reduce embedding depth or increase support height')
    rear_max = _support_linear_max(profile,-rear_slope,rear_u,crest_u)[0]-rear_intercept+h
    valley_max = _support_linear_max(profile,0.0,upper=rear_u)[0]
    rear_max = max(rear_max,valley_max)
    if rear_max > SMOOTH_REAR_MAX_EMBED_MM+1e-9:
        raise ValueError(f'{OPTICAL_MODE} rear smoothing embed {rear_max:.6f} mm exceeds '
                         f'limit {SMOOTH_REAR_MAX_EMBED_MM:.6f} mm at optical angle {angle:.4f}; '
                         'front fit and support/back angle have not been altered')
    nozzle_max = None
    if SMOOTH_NOZZLE_FLAT_DIAMETER_MM is not None:
        radius = SMOOTH_NOZZLE_FLAT_DIAMETER_MM/2.0
        front_contact = _flat_tip_contact_max(profile,-slope,intercept,crest_u,front_u,radius)
        rear_contact = _flat_tip_contact_max(profile,rear_slope,rear_intercept,rear_u,crest_u,radius)
        # A level valley can still sweep into the rear edge of this assembly.
        valley_contact = _support_linear_max(profile,0.0,upper=rear_u+radius)[0]-h
        nozzle_max = max(0.0,front_contact,rear_contact,valley_contact)
        if (SMOOTH_MAX_NOZZLE_PENETRATION_MM is not None and
                nozzle_max > SMOOTH_MAX_NOZZLE_PENETRATION_MM+1e-9):
            raise ValueError(f'{OPTICAL_MODE} nozzle penetration {nozzle_max:.6f} mm exceeds '
                             f'declared limit {SMOOTH_MAX_NOZZLE_PENETRATION_MM:.6f} mm '
                             f'for flat diameter {SMOOTH_NOZZLE_FLAT_DIAMETER_MM:.3f} mm')
    return {
        'leading_base_u_mm':leading,
        'front_foot_u_mm':front_u,'front_foot_height_mm':h,
        'front_angle_deg':angle,'crest_u_mm':crest_u,'crest_height_mm':crest_h,
        'rear_angle_deg':math.degrees(rear_angle),
        'rear_foot_u_mm':rear_u,'rear_foot_height_mm':h,
        'smooth_layer_height_mm':h,'smooth_e_per_mm':SMOOTH_E_PER_MM,
        'smooth_embed_depth_mm':embed,'front_embed_max_mm':front_max,
        'rear_embed_max_mm':rear_max,'front_touch_u_mm':touch_u,
        'derived_front_distance_mm':front_u-leading-0.5*ARC_PROFILE_WIDTH_MM,
        'nozzle_penetration_max_mm':nozzle_max,
        'support_contact_model':'half_ellipse_vertical',
    }


# ---- _smooth_local_profile ----
def _smooth_local_profile(center):
    frame = mirror_frame_global(float(center[0]), float(center[1]))
    support = _stack_cross_section_profile(frame["facet_tilt_deg"])
    smooth = _smooth_cross_section_profile(frame["facet_tilt_deg"], support)
    leading = smooth["leading_base_u_mm"]
    return frame, support, smooth, {
        "front_foot": smooth["front_foot_u_mm"] - leading,
        "crest": smooth["crest_u_mm"] - leading,
        "rear_foot": smooth["rear_foot_u_mm"] - leading,
    }


# ---- _smooth_assembly_extents ----
def _smooth_assembly_extents(center):
    frame, support, smooth, local = _smooth_local_profile(center)
    leading = smooth["leading_base_u_mm"]
    centres = [u - leading for tier in support["tiers"] for u in tier["centres_u_mm"]]
    centres.extend(local.values())
    radius = 0.5 * ARC_PROFILE_WIDTH_MM
    return min(centres) - radius, max(centres) + radius


# ---- _white_samples ----
def _white_samples(center, count=256):
    key=(tuple(center),int(count),LAYER_MAP,LAYER_HEIGHT_MM,PHYSICAL_HEIGHT_SCALE)
    if key in _WHITE_SAMPLE_CACHE:return _WHITE_SAMPLE_CACHE[key]
    cx,cz=center;frame=mirror_frame_global(cx,cz)
    profile=_stack_cross_section_profile(frame['facet_tilt_deg'])
    a=ARC_PROFILE_WIDTH_MM/2;h=PHYSICAL_LAYER_HEIGHT_MM;out=[]
    for tier in profile['tiers']:
        if tier['tier'] not in _target_tiers():continue
        u0=max(tier['centres_u_mm']);base=tier['base_height_mm']
        for j in range(count):
            phi=(j+.5)*math.pi/(2*count);co=math.cos(phi);si=math.sin(phi)
            u=u0+a*co;z=base+h*si
            # Different tiers occupy disjoint nominal height bands. Same-tier
            # roads touch at their feet; the leading quarter is not buried.
            nx,nz=h*co,a*si;nm=math.hypot(nx,nz)
            out.append(dict(tier=tier['tier'],point_mm=(cx+frame['b_unit'][0]*u,cz+frame['b_unit'][1]*u),
                height_mm=z,normal=(frame['b_unit'][0]*nx/nm,frame['b_unit'][1]*nx/nm,nz/nm),
                weight=math.hypot(a*si,h*co)*math.pi/(2*count)))
    _WHITE_SAMPLE_CACHE[key]=out
    return out


# ---- _white_pair_visibility ----
def _white_pair_visibility(visible,blocker,count=256,extra_blockers=()):
    points,normals,weights,tiers=_white_arrays(visible,count)
    p=(MASTER_FAN.projector_x_mm,MASTER_FAN.projector_z_mm,MASTER_FAN.projector_distance_mm)
    v=(MASTER_FAN.viewer_x_mm,MASTER_FAN.viewer_z_mm,MASTER_FAN.viewer_distance_mm)
    wp=_np.ones(len(points),dtype=bool);wv=wp.copy()
    for c in [visible,blocker]+list(extra_blockers):
        wp&=_white_ray_mask(points,normals,c,p)
        wv&=_white_ray_mask(points,normals,c,v)
    rows=[]
    for ti in _target_tiers():
        sel=tiers==ti;w=float(weights[sel].sum())
        if w<=0:raise ValueError(f'leading tier {ti} has no exposed target surface')
        rows.append(dict(tier=ti,projector_fraction=float(weights[sel&wp].sum())/w,
            viewer_fraction=float(weights[sel&wv].sum())/w,joint_fraction=float(weights[sel&wp&wv].sum())/w))
    return dict(rows=rows,projector_min=min(q['projector_fraction'] for q in rows),
        viewer_min=min(q['viewer_fraction'] for q in rows),joint_min=min(q['joint_fraction'] for q in rows))


# ---- _white_full_metrics ----
def _white_full_metrics(current, previous, piece, count=128):
    if not HORIZONTAL_PERCENT:
        return _original_white_full_metrics(current, previous, piece, count)
    eligible = [p for p in previous if piece.global_x0_mm <= p[0] <= piece.global_x1_mm
                and piece.global_z0_mm <= p[1] <= piece.global_z1_mm]
    if not eligible:
        return None
    ids = sorted(set(round(j * (len(eligible) - 1) / 8) for j in range(9)))
    records = [_white_pair_visibility(eligible[i], _horizontal_normal_intersection(eligible[i], current), count) for i in ids]
    return {k: min(r[k] for r in records) for k in ('projector_min', 'viewer_min', 'joint_min')}


# ---- _target_tiers ----
def _target_tiers():
    white = [i+1 for i,c in enumerate(LAYER_MAP) if c == 'W']
    return white or list(range(1, len(LAYER_MAP)+1))


# ---- _white_arrays ----
def _white_arrays(center,count):
    key=(tuple(center),int(count),LAYER_MAP,LAYER_HEIGHT_MM,PHYSICAL_HEIGHT_SCALE)
    if key not in _WHITE_ARRAY_CACHE:
        s=_white_samples(center,count)
        _WHITE_ARRAY_CACHE[key]=(_np.array([[*q['point_mm'],q['height_mm']] for q in s]),
            _np.array([q['normal'] for q in s]),_np.array([q['weight'] for q in s]),
            _np.array([q['tier'] for q in s]))
    return _WHITE_ARRAY_CACHE[key]


# ---- _white_ray_mask ----
def _white_ray_mask(points, normals, center, target):
    """Finite half-ellipse blockers, including the actual final cap height."""
    key = (tuple(center), LAYER_MAP, LAYER_HEIGHT_MM, PHYSICAL_HEIGHT_SCALE, CAP_HEIGHT_MM)
    if key not in _BLOCKER_ARRAY_CACHE:
        cx, cz = map(float, center)
        frame = mirror_frame_global(cx, cz)
        profile = _stack_cross_section_profile(frame['facet_tilt_deg'])
        roads = [(uc, tier['base_height_mm'], TIER_PHYSICAL_HEIGHTS_MM[ti])
                 for ti, tier in enumerate(profile['tiers']) for uc in tier['centres_u_mm']]
        _BLOCKER_ARRAY_CACHE[key] = (np.asarray(frame['b_unit'], float), np.asarray(roads, float))
    b, roads = _BLOCKER_ARRAY_CACHE[key]
    pts = np.asarray(points, float)
    nrms = np.asarray(normals, float)
    target = np.asarray(target, float)
    ray = target[None, :] - pts
    dist = np.linalg.norm(ray, axis=1)
    ray /= dist[:, None]
    facing = np.sum(nrms * ray, axis=1) > 0
    q0 = ((pts[:, :2] - np.asarray(center, float)[None, :]) @ b)[:, None]
    dq = (ray[:, :2] @ b)[:, None]
    rh = ray[:, 2, None]
    h0 = pts[:, 2, None]
    a = float(ARC_PROFILE_WIDTH_MM) / 2.0
    uc = roads[:, 0][None, :]
    base = roads[:, 1][None, :]
    hh = roads[:, 2][None, :]
    lo = np.maximum(1.0e-5, (base - h0) / rh)
    hi = np.minimum(dist[:, None], (base + hh - h0) / rh)
    v0 = h0 - base
    aa = (dq / a) ** 2 + (rh / hh) ** 2
    bb = 2.0 * ((q0 - uc) * dq / (a*a) + v0 * rh / (hh*hh))
    cc = ((q0 - uc) / a) ** 2 + (v0 / hh) ** 2 - 1.0
    t = np.maximum(lo, np.minimum(hi, -bb / (2.0 * aa)))
    blocked = np.any((hi > lo) & ((aa*t*t + bb*t + cc) < -1.0e-8), axis=1)
    return facing & ~blocked


# ---- _mapped_pair_metrics ----
def _mapped_pair_metrics(current,previous,piece,stride=1,profile_sample_count=None):
    r=_white_pair_visibility(previous[0],current[0],256)
    gap=_physical_envelope_gap(current,previous)
    margin=r['projector_min']-VISIBILITY_PERCENT/100
    return dict(physical_gap_min_mm=gap,visibility_margin_min=margin,
        visibility_clear=margin>=-1e-9,sample_count=1,profile_sample_count=256,white_visibility=r)


# ---- _mapped_available_visibility ----
def _mapped_available_visibility(piece):
    values=[]
    for fx in (0.,.5,1.):
        for fy in (0.,.5,1.):
            c=(piece.global_x0_mm+fx*piece.width_mm,piece.global_z0_mm+fy*piece.height_mm)
            # A duplicate own stack introduces no extra occlusion.
            values.append(_white_pair_visibility(c,c,512)['projector_min'])
    return min(values)


# ---- _mapped_generate_lattice ----
def _mapped_generate_lattice(piece):
    available=_mapped_available_visibility(piece)
    if available+1e-9<VISIBILITY_PERCENT/100:
        raise ValueError(f'{LAYER_MAP}: own-pyramid shading limits the least-lit target tier to '
                         f'about {available*100:.1f}% on this card; requested {VISIBILITY_PERCENT:g}%. '
                         'Reduce visibility or change scale/map. Wider spacing cannot remove self-shadow.')
    setup=_reference_setup(piece);previous=setup['curve'];plans=[];seen=False
    limit=max(8.,len(LAYER_MAP)*ARC_PROFILE_WIDTH_MM*5)
    target=VISIBILITY_PERCENT/100
    for slot in range(1000):
        clipped=_clip_roads(previous,piece);printable=all(len(v)>=2 for v in clipped.values())
        if printable:seen=True
        elif seen:break
        mid=_curve_midpoint_in_piece(previous,piece)
        def point_ok(distance):
            current=_advance_midpoint(mid,distance)
            metrics=_mapped_pair_metrics([current],[mid],piece)
            return metrics['physical_gap_min_mm']>=0 and metrics['visibility_clear']
        low=MINIMUM_PITCH_MM;high=max(MINIMUM_PITCH_MM,.45,len(LAYER_MAP)*ARC_PROFILE_WIDTH_MM)
        for attempt in range(80):
            if point_ok(high):break
            low=high;high*=1.15
            if high>limit:raise ValueError(f'{piece.name}: requested visibility needs pitch above {limit:g} mm')
        else:raise RuntimeError('mapped midpoint search did not converge')
        for _ in range(12):
            d=(low+high)/2
            if point_ok(d):high=d
            else:low=d
        def full(distance):
            curve,seed=_advance_candidate(previous,setup,distance)
            gap=_full_arc_physical_gap(curve,previous,piece)
            white=_white_full_metrics(curve,previous,piece,256)
            return curve,seed,gap,white
        curve,seed,gap,white=full(high)
        def good(gap,white):return gap>=0 and (white is None or white['projector_min']>=target-1e-9)
        # Finite, monotone bracket: never repeat a coarse/fine disagreement.
        if not good(gap,white):
            low=high
            for _ in range(60):
                high+=max(.04,-gap+1e-7,.025*high)
                if high>limit:raise ValueError(f'{piece.name}: full-arc shadow constraint exceeds {limit:g} mm pitch')
                curve,seed,gap,white=full(high)
                if good(gap,white):break
                low=high
            else:raise RuntimeError('mapped full-arc search did not converge')
            for _ in range(9):
                d=(low+high)/2;trial=full(d)
                if good(trial[2],trial[3]):high=d;curve,seed,gap,white=trial
                else:low=d
        metrics=_mapped_pair_metrics([_advance_midpoint(mid,high)],[mid],piece)
        plans.append(dict(slot=slot,curve=previous,roads=clipped,printable=printable,
            next_pitch_mm=high,next_metrics=metrics,next_full_arc_physical_gap_mm=gap,
            white_full_metrics=white))
        if setup['advance']=='seed':setup['seed']=seed
        previous=curve
        if slot%15==0:print(f'  spacing: {slot+1} assemblies solved; pitch {high:.3f} mm',flush=True)
        if not printable and not _waveset_clip_curve(curve,piece) and seen:break
    else:raise RuntimeError('mapped lattice exceeded 1000 assemblies')
    printable=[p for p in plans if p['printable']]
    if len(printable)<2:raise ValueError('fewer than two complete pyramids fit this card')
    return dict(piece=piece.name,mode='mapped-pyramid',plans=plans,printable=printable,
        own_visibility_limit=available)


# ---- _height_decimal ----
def _height_decimal(value):
    from decimal import Decimal
    return format(Decimal(str(value)).normalize(),"f")


# ---- _height_code ----
def _height_code(value):
    text=_height_decimal(value)
    if not text.startswith("0."): raise ValueError("layer height must be below 1 mm for the compact rear code")
    return text[2:].ljust(2,"0")


# ---- _scale_code ----
def _scale_code(physical_height_scale):
    from decimal import Decimal
    value=Decimal(str(physical_height_scale))
    if value <= 0: raise ValueError("physical height scale must be greater than zero")
    if value.as_tuple().exponent < -2: raise ValueError("physical height scale supports at most two decimal places")
    text=format(value.normalize(),"f")
    if "." not in text: text += ".0"
    whole,fraction=text.split(".",1)
    fraction=fraction.rstrip("0") or "0"
    return whole+fraction


# ---- _smooth_code ----
def _smooth_code(value):
    return "00" if float(value)==0.0 else _height_code(value)


# ---- _validate_options ----
def _validate_options(mode, layer_height, visibility, physical_height_scale=1.0,
                      smooth_embed_depth=0.02, smooth_layer_height=0.10,
                      smooth_rear_max_embed=None, smooth_nozzle_flat_diameter=None,
                      smooth_max_nozzle_penetration=None, smooth_xy_speed=30.0):
    if mode not in ('single-arc','pyramid-3-2-1','pyramid-2-1','smooth1','smooth2','smooth3'):
        raise ValueError(f'unknown print mode {mode!r}')
    def finite(value,name):
        if not math.isfinite(float(value)):raise ValueError(f'{name} must be finite')
    finite(layer_height,'layer height');finite(physical_height_scale,'physical height scale')
    finite(visibility,'visibility percent')
    if not 0.0 < float(layer_height) < 1.0:
        raise ValueError('layer height must be greater than 0 and below 1 mm')
    if not 0.0 < float(physical_height_scale):
        raise ValueError('physical height scale must be greater than zero')
    _scale_code(physical_height_scale)
    if float(layer_height)*float(physical_height_scale) >= 1.0:
        raise ValueError('scaled physical layer height must remain below 1 mm')
    if int(visibility)!=visibility or not 0 <= int(visibility) <= 100:
        raise ValueError('visibility percent must be a whole number from 0 to 100')
    if mode.startswith('smooth'):
        finite(smooth_xy_speed,'smooth XY speed')
        if not 0.01 <= float(smooth_xy_speed) <= 500.0:
            raise ValueError('smooth XY speed must be between 0.01 and 500 mm/s')
        from decimal import Decimal
        if Decimal(str(smooth_xy_speed)).normalize().as_tuple().exponent < -2:
            raise ValueError('smooth XY speed supports at most two decimal places')
        finite(smooth_layer_height,'smooth layer height');finite(smooth_embed_depth,'smooth embed depth')
        if not 0.0 < float(smooth_layer_height) < 1.0:
            raise ValueError('smooth layer height must be greater than zero and below 1 mm')
        if not 0.0 <= float(smooth_embed_depth) < float(smooth_layer_height):
            raise ValueError('smooth embed depth must be nonnegative and below the smooth layer height')
        _smooth_code(smooth_embed_depth);_smooth_code(smooth_layer_height)
        if smooth_rear_max_embed is not None:
            finite(smooth_rear_max_embed,'smooth rear max embed')
            if float(smooth_rear_max_embed)<0:raise ValueError('smooth rear max embed must be nonnegative')
        if smooth_nozzle_flat_diameter is not None:
            finite(smooth_nozzle_flat_diameter,'smooth nozzle flat diameter')
            if not 0.4 <= float(smooth_nozzle_flat_diameter) <= 5.0:
                raise ValueError('smooth nozzle flat diameter must be between 0.4 and 5 mm for this 0.4 mm nozzle')
        if smooth_max_nozzle_penetration is not None:
            finite(smooth_max_nozzle_penetration,'smooth max nozzle penetration')
            if smooth_nozzle_flat_diameter is None:
                raise ValueError('smooth max nozzle penetration requires a supplied smooth nozzle flat diameter')
            if float(smooth_max_nozzle_penetration,smooth_xy_speed)<0:raise ValueError('smooth max nozzle penetration must be nonnegative')


# ---- _replace_zip ----
def _replace_zip(output:Path,repl:dict[str,bytes]):
    output=Path(output)
    with zipfile.ZipFile(output,"r") as zin:
        infos=zin.infolist(); data={i.filename:zin.read(i.filename) for i in infos}
    data.update(repl); tmp=output.with_suffix(output.suffix+".v159tmp")
    with zipfile.ZipFile(tmp,"w") as zout:
        for i in infos: zout.writestr(i,data[i.filename])
        existing={i.filename for i in infos}
        for name,content in data.items():
            if name not in existing:zout.writestr(name,content)
    tmp.replace(output)


# ---- _patch_native_lifecycle_and_revision ----
def _patch_native_lifecycle_and_revision(output, max_layer_z):
    output=Path(output)
    with zipfile.ZipFile(output,"r") as z:
        g=z.read("Metadata/plate_1.gcode").decode("utf-8","strict")
        project=json.loads(z.read("Metadata/project_settings.config").decode("utf-8"))
    ex0=g.find("; EXECUTABLE_BLOCK_START"); ex1=g.find("; EXECUTABLE_BLOCK_END",ex0+1)
    if ex0<0 or ex1<0: raise RuntimeError(f"{SCRIPT_VERSION}: executable block missing")
    sb=g.find("; FC3D_V1159_A1MINI_START",ex0,ex1); se=g.find("; FC3D_V1159_A1MINI_START_END",sb,ex1)
    if sb>=0 and se>=0:
        se2=g.find("\n",se); se2=len(g) if se2<0 else se2+1; g=g[:sb]+_native_start()+"\n"+g[se2:]
    else:
        body=g.find("\n",ex0)+1; first_model=g.find("; CHANGE_LAYER",body,ex1)
        if body<=0 or first_model<0: raise RuntimeError(f"{SCRIPT_VERSION}: canonical startup boundary missing")
        g=g[:body]+_native_start()+"\n"+g[first_model:]
    model_end=g.rfind("; V4_MODEL_END"); ex1=g.find("; EXECUTABLE_BLOCK_END",model_end)
    eb=g.find("; FC3D_V1159_A1MINI_END",model_end,ex1); ee=g.find("; FC3D_V1159_A1MINI_END_DONE",eb,ex1)
    ending=_native_end(max_layer_z,90.0)
    if eb>=0 and ee>=0:
        ee2=g.find("\n",ee); ee2=len(g) if ee2<0 else ee2+1; g=g[:eb]+ending+"\n"+g[ee2:]
    else:
        model_line=g.find("\n",model_end)
        if model_line<0 or ex1<0: raise RuntimeError(f"{SCRIPT_VERSION}: canonical ending boundary missing")
        g=g[:model_line+1]+ending+"\n"+g[ex1:]
    for old in ("FC3D_V1159","FC3D_V1105","FC3D_V1131"): g=g.replace(old,"FC3D_V1159")
    for old in ("V1.159","v1.159","V1.105","v1.105","V1.131","v1.131"): g=g.replace(old,"V1.159" if old[0]=="V" else "v1.159")
    label=f"; FC3D_V1159_REAR_LABEL card={CURRENT_PIECE_NAME} text={CURRENT_REAR_PARAMETER_TEXT} revision=159 rotation=180 arrow=opposite-v138\n"
    model=g.find("; CHANGE_LAYER")
    if model>=0: g=g[:model]+label+g[model:]
    project["machine_start_gcode"]=_native_start(); project["machine_end_gcode"]=ending+"\n"
    newb=g.encode("utf-8")
    _replace_zip(output,{"Metadata/plate_1.gcode":newb,"Metadata/plate_1.gcode.md5":(hashlib.md5(newb).hexdigest()+"\n").encode("ascii"),
                         "Metadata/project_settings.config":json.dumps(project,separators=(",",":")).encode("utf-8")})


# ---- _audit_backplate_process ----
def _audit_backplate_process(gcode, rt):
    """Fail closed on structural and top-valley material doses."""
    gcode=_ct_without_detours(gcode)
    layer_re=re.compile(r";\s*DIRECT_LAYER\s+V4\s+physical=(\d+)")
    value_re=re.compile(r"\b([XYE])([-+0-9.]+)")
    current_layer=None; xy=None
    structural={1:[],2:[]}; valley=[]
    for line in gcode.splitlines():
        match=layer_re.search(line)
        if match:
            current_layer=int(match.group(1)); xy=None
            continue
        if not (line.startswith("G0") or line.startswith("G1")):
            continue
        values={key:float(value) for key,value in value_re.findall(line)}
        old=xy
        if old is None:
            if "X" in values and "Y" in values: xy=(values["X"],values["Y"])
            continue
        nx=values.get("X",old[0]); ny=values.get("Y",old[1]); xy=(nx,ny)
        if values.get("E",0.0)<=0.0 or ("X" not in values and "Y" not in values):
            continue
        distance=math.hypot(nx-old[0],ny-old[1])
        if distance<=1e-9:
            continue
        ratio=values["E"]/distance
        if "TOP_VALLEY_FILL_DRAW" in line:
            valley.append(ratio)
        elif current_layer in structural:
            structural[current_layer].append(ratio)
    expected_structural=rt.STRUCTURAL_E_PER_MM
    for layer,ratios in structural.items():
        if not ratios or max(abs(value-expected_structural) for value in ratios)>2e-6:
            bounds=(min(ratios),max(ratios)) if ratios else None
            raise RuntimeError(f"{SCRIPT_VERSION}: structural layer {layer} E/mm mismatch {bounds}")
    expected_valley=0.25*rt.DEFAULT_E_PER_MM
    if not valley or max(abs(value-expected_valley) for value in valley)>2e-6:
        bounds=(min(valley),max(valley)) if valley else None
        raise RuntimeError(f"{SCRIPT_VERSION}: 25% top-valley E/mm mismatch {bounds}")
    return {"structural_e_per_mm":expected_structural,
            "structural_layer_1_moves":len(structural[1]),
            "structural_layer_2_moves":len(structural[2]),
            "top_valley_fill_e_per_mm":expected_valley,
            "top_valley_fill_moves":len(valley)}


# ---- _audit_optical_block ----
def _audit_optical_block(block, rt):
    """Audit fixed-Z support and variable-Z smoothing as distinct motion families."""
    xr=re.compile(r"\bX([-+0-9.]+)"); yr=re.compile(r"\bY([-+0-9.]+)")
    zr=re.compile(r"\bZ([-+0-9.]+)"); er=re.compile(r"\bE([-+0-9.]+)")
    support_lengths=[]; current_support=None
    support_ratios=[]; smooth_ratios=[]; smooth_z=[]
    tier_ratios={i:[] for i in range(1,len(rt.LAYER_MAP)+1)}; active_tier=None
    actual_cap=_audit_actual_cap_block(block,rt,rt.CAP_HEIGHT_MM)
    smooth_xy_speeds=[]; smooth_z_speeds=[]; z_limited=0
    position=None; pending_xy=None
    for line in block.splitlines():
        if "FC3D_V1159_SUPPORT_ROAD_START" in line:
            current_support=[]; support_lengths.append(current_support); position=None
            active_tier=int(re.search(r"\btier=(\d+)",line)[1])
        elif "FC3D_V1159_SMOOTH_PATH_START" in line:
            position=None; pending_xy=None
        elif "FC3D_V1159_SUPPORT_MOVE" in line or "FC3D_V1159_SMOOTH_MOVE" in line:
            mx=xr.search(line); my=yr.search(line)
            if not (mx and my): raise RuntimeError(f"{SCRIPT_VERSION}: path move lacks XY")
            pending_xy=(float(mx.group(1)),float(my.group(1)))
        elif "FC3D_V1159_SUPPORT_HEIGHT" in line or "FC3D_V1159_SMOOTH_HEIGHT" in line:
            mz=zr.search(line)
            if pending_xy is None or not mz: raise RuntimeError(f"{SCRIPT_VERSION}: path height lacks position")
            position=pending_xy+(float(mz.group(1)),)
        elif "FC3D_V1159_SUPPORT_SEG" in line or "FC3D_V1159_SMOOTH_SEG" in line:
            mx=xr.search(line); my=yr.search(line); mz=zr.search(line); me=er.search(line)
            if position is None or not all((mx,my,mz,me)):
                raise RuntimeError(f"{SCRIPT_VERSION}: malformed XYZ extrusion segment")
            point=(float(mx.group(1)),float(my.group(1)),float(mz.group(1)))
            distance=math.sqrt(sum((b-a)**2 for a,b in zip(position,point)))
            if distance <= 1e-9: raise RuntimeError(f"{SCRIPT_VERSION}: zero-length extrusion segment")
            ratio=float(me.group(1))/distance
            if "SUPPORT_SEG" in line:
                if current_support is None: raise RuntimeError(f"{SCRIPT_VERSION}: support segment outside road")
                current_support.append(distance); support_ratios.append(ratio)
                tier_ratios[active_tier].append(ratio)
                if "F15000" not in line: raise RuntimeError(f"{SCRIPT_VERSION}: support feed mismatch")
            else:
                smooth_ratios.append(ratio); smooth_z.append(point[2])
                mf=re.search(r"\bF([-+0-9.]+)",line)
                if not mf:raise RuntimeError(f"{SCRIPT_VERSION}: smoothing feed missing")
                feed=float(mf.group(1))/60.0
                if not math.isfinite(feed) or feed<=0:raise RuntimeError(f"{SCRIPT_VERSION}: smoothing speed invalid")
                xy=math.hypot(point[0]-position[0],point[1]-position[1])
                dz=abs(point[2]-position[2])
                vx=feed*xy/distance; vz=feed*dz/distance
                smooth_xy_speeds.append(vx);smooth_z_speeds.append(vz)
                if vx>rt.SMOOTH_XY_SPEED_MM_S+1e-6 or vz>rt.SMOOTH_Z_SPEED_LIMIT_MM_S+1e-6:
                    raise RuntimeError(f"{SCRIPT_VERSION}: smoothing axis speed exceeded: XY={vx:g} Z={vz:g}")
                duration=max(xy/rt.SMOOTH_XY_SPEED_MM_S,dz/rt.SMOOTH_Z_SPEED_LIMIT_MM_S)
                if abs(feed-distance/duration)>0.011/60.0:
                    raise RuntimeError(f"{SCRIPT_VERSION}: smoothing feed does not match requested XY speed/Z cap")
                if dz/rt.SMOOTH_Z_SPEED_LIMIT_MM_S>xy/rt.SMOOTH_XY_SPEED_MM_S:z_limited+=1
            position=point
    support=block.count("FC3D_V1159_SUPPORT_ROAD_START")
    smooth=block.count("FC3D_V1159_SMOOTH_PATH_START")
    if not support or (support,block.count("FC3D_V1159_SUPPORT_REPRIME"),
                       block.count("FC3D_V1159_SUPPORT_RETRACT"),
                       block.count("FC3D_V1159_SUPPORT_ROAD_END")) != (support,)*4:
        raise RuntimeError(f"{SCRIPT_VERSION}: support pressure-cycle audit failed")
    if any(not lengths for lengths in support_lengths):
        raise RuntimeError(f"{SCRIPT_VERSION}: empty support road")
    ordinary=[distance for lengths in support_lengths for distance in lengths[:-1]]
    if ordinary and min(ordinary) < rt.MIN_EMITTED_CHORD_MM-1e-9:
        raise RuntimeError(f"{SCRIPT_VERSION}: short non-final support chord {min(ordinary):.6f} mm")
    for tier, ratios in tier_ratios.items():
        wanted=rt.A_MAIN_E_PER_MM*(rt.CAP_HEIGHT_MM/rt.LAYER_HEIGHT_MM if tier==len(rt.LAYER_MAP) else 1.)
        if not ratios or abs(sum(ratios)/len(ratios)-wanted)>8e-5:
            raise RuntimeError(f"{SCRIPT_VERSION}: tier {tier} support extrusion audit failed")
    tiers={int(m.group(1)) for m in re.finditer(r"SUPPORT_ROAD_START[^\n]* tier=([0-9]+)",block)}
    expected=set(range(1,len(rt._mode_profile()["tier_counts"])+1))
    if tiers != expected: raise RuntimeError(f"{SCRIPT_VERSION}: support tier audit {tiers} != {expected}")
    if rt._mode_profile()["smooth"]:
        if not smooth or (smooth,block.count("FC3D_V1159_SMOOTH_REPRIME"),
                          block.count("FC3D_V1159_SMOOTH_RETRACT"),
                          block.count("FC3D_V1159_SMOOTH_PATH_END")) != (smooth,)*4:
            raise RuntimeError(f"{SCRIPT_VERSION}: smoothing pressure-cycle audit failed")
        if not smooth_ratios or abs(sum(smooth_ratios)/len(smooth_ratios)-rt.SMOOTH_E_PER_MM)>8e-5:
            raise RuntimeError(f"{SCRIPT_VERSION}: smoothing extrusion audit failed")
        if len({round(z,3) for z in smooth_z}) < 3:
            raise RuntimeError(f"{SCRIPT_VERSION}: smoothing paths do not vary Z")
        for kind in ("front_foot","crest","rear_foot"):
            if f"kind={kind}" not in block: raise RuntimeError(f"{SCRIPT_VERSION}: smoothing path lacks {kind}")
    elif smooth:
        raise RuntimeError(f"{SCRIPT_VERSION}: smoothing paths emitted in non-smooth mode")
    return {"actual_cap_gcode":actual_cap,"cap_height_mm":rt.CAP_HEIGHT_MM,
            "cap_physical_height_mm":rt.CAP_PHYSICAL_HEIGHT_MM,
            "cap_draw_e_per_mm":rt.A_MAIN_E_PER_MM*rt.CAP_HEIGHT_MM/rt.LAYER_HEIGHT_MM,
            "support_roads":support,"smooth_paths":smooth,"tiers":sorted(tiers),
            "support_segments":len(support_ratios),"smooth_segments":len(smooth_ratios),
            "support_mean_e_per_mm":sum(support_ratios)/len(support_ratios),
            "smooth_mean_e_per_mm":sum(smooth_ratios)/len(smooth_ratios) if smooth_ratios else None,
            "support_normal_chord_min_mm":min(ordinary) if ordinary else None,
            "smooth_z_min_mm":min(smooth_z) if smooth_z else None,
            "smooth_z_max_mm":max(smooth_z) if smooth_z else None,
            "smooth_requested_xy_speed_mm_s":rt.SMOOTH_XY_SPEED_MM_S if smooth else None,
            "smooth_z_speed_limit_mm_s":rt.SMOOTH_Z_SPEED_LIMIT_MM_S if smooth else None,
            "smooth_xy_speed_min_mm_s":min(smooth_xy_speeds) if smooth_xy_speeds else None,
            "smooth_xy_speed_max_mm_s":max(smooth_xy_speeds) if smooth_xy_speeds else None,
            "smooth_z_speed_max_mm_s":max(smooth_z_speeds) if smooth_z_speeds else None,
            "smooth_z_limited_segments":z_limited}


# ---- _audit_smooth_gcode_contact ----
def _audit_smooth_gcode_contact(block, rt):
    """Independent contact audit of emitted XYZ against emitted support roads.

    Uses NumPy already required by the canonical emitter, no SciPy dependency.
    Support is the declared 0.4-mm half-ellipse model. Geometry is sampled at
    <=0.01 mm XY intervals; output rounding/model tolerance is 0.005 mm.
    Optional flat-disk contact is a conservative static footprint, not a
    prediction of melt flow, nozzle cone clearance or final surface shape.
    """
    import numpy as np
    token=re.compile(r'([XYZEF])([-+]?(?:\d+(?:\.\d*)?|\.\d+))')
    position=np.full(3,np.nan)
    supports=[];moves=[];kinds=[];lines=[];paths=[];path=0
    for lineno,line in enumerate(block.splitlines(),1):
        if 'SMOOTH_PATH_START' in line:
            match=re.search(r'\bpath=(\d+)',line)
            if match:path=int(match.group(1))
        if not re.match(r'^G[01]\s',line):continue
        values={key:float(value) for key,value in token.findall(line.split(';',1)[0])}
        old=position.copy()
        for j,key in enumerate('XYZ'):
            if key in values:position[j]=values[key]
        if '_SUPPORT_SEG ' not in line and '_SMOOTH_SEG ' not in line:continue
        if not np.isfinite(old).all() or not np.isfinite(position).all() or values.get('E',0)<=0:
            raise RuntimeError(f'{SCRIPT_VERSION}: contact audit found malformed extrusion at block line {lineno}')
        if '_SUPPORT_SEG ' in line:
            if abs(old[2]-position[2])>1e-8:
                raise RuntimeError(f'{SCRIPT_VERSION}: support is not constant Z in contact audit')
            supports.append((old.copy(),position.copy()))
        else:
            match=re.search(r'\bkind=(\w+)',line)
            if not match:raise RuntimeError(f'{SCRIPT_VERSION}: smoothing contact move lacks a kind')
            kind=match.group(1)
            if kind=='crest':family=0
            elif kind=='rear_foot':family=1
            elif kind=='front_foot':family=2
            elif kind=='boundary':family=0 if position[2]>old[2]+1e-9 else (1 if position[2]<old[2]-1e-9 else 2)
            else:raise RuntimeError(f'{SCRIPT_VERSION}: unknown smoothing point kind {kind}')
            moves.append((old.copy(),position.copy()));kinds.append(family);lines.append(lineno);paths.append(path)
    if not supports or not moves:
        raise RuntimeError(f'{SCRIPT_VERSION}: smoothing contact audit requires support and smoothing extrusion')
    supports=np.asarray(supports);moves=np.asarray(moves);kinds=np.asarray(kinds,dtype=np.int8)
    a,b=supports[:,0,:2],supports[:,1,:2];delta=b-a
    lengths2=np.sum(delta*delta,axis=1)
    if np.any(lengths2<=0):raise RuntimeError(f'{SCRIPT_VERSION}: zero-length support contact primitive')
    xy_lengths=np.linalg.norm(moves[:,1,:2]-moves[:,0,:2],axis=1)
    counts=np.maximum(1,np.ceil(xy_lengths/.01).astype(np.int64))
    ids=np.repeat(np.arange(len(moves)),counts+1)
    offsets=np.repeat(np.cumsum(np.r_[0,counts[:-1]+1]),counts+1)
    fractions=(np.arange(len(ids))-offsets)/counts[ids]
    points=moves[ids,0]+(moves[ids,1]-moves[ids,0])*fractions[:,None]
    radius=rt.ARC_PROFILE_WIDTH_MM/2.
    flat=rt.SMOOTH_NOZZLE_FLAT_DIAMETER_MM
    tip_radius=0. if flat is None else flat/2.
    reach=radius+tip_radius
    box_lo=np.floor(np.minimum(a,b)-reach-1e-9).astype(np.int64)
    box_hi=np.floor(np.maximum(a,b)+reach+1e-9).astype(np.int64)
    cells=np.floor(points[:,:2]).astype(np.int64)
    origin=np.minimum(box_lo.min(axis=0),cells.min(axis=0))
    ymax=max(int(box_hi[:,1].max()),int(cells[:,1].max()))
    stride=ymax-int(origin[1])+1
    grid={}
    for i,(lo,hi) in enumerate(zip(box_lo,box_hi)):
        for x in range(int(lo[0]),int(hi[0])+1):
            for y in range(int(lo[1]),int(hi[1])+1):
                key=(x-int(origin[0]))*stride+y-int(origin[1])
                grid.setdefault(key,[]).append(i)
    keys=(cells[:,0]-origin[0])*stride+cells[:,1]-origin[1]
    order=np.argsort(keys,kind='stable');sorted_keys=keys[order]
    boundaries=np.r_[0,np.flatnonzero(sorted_keys[1:]!=sorted_keys[:-1])+1,len(order)]
    best=np.full(3,-np.inf);locations=[None,None,None];nozzle_best=-np.inf;nozzle_location=None
    height=rt.PHYSICAL_LAYER_HEIGHT_MM
    radii=(0.,) if flat is None else (0.,tip_radius)
    for start,end in zip(boundaries[:-1],boundaries[1:]):
        support_ids=grid.get(int(sorted_keys[start]))
        if not support_ids:continue
        support_ids=np.asarray(support_ids,dtype=np.int64)
        av=a[support_ids];dv=delta[support_ids];dl=lengths2[support_ids]
        road_tops=supports[support_ids,1,2]
        for chunk in range(int(start),int(end),512):
            sample_ids=order[chunk:min(chunk+512,int(end))]
            xyz=points[sample_ids]
            projection=np.clip(np.sum((xyz[:,None,:2]-av[None,:,:])*dv[None,:,:],axis=2)/dl[None,:],0.,1.)
            distance=np.linalg.norm(xyz[:,None,:2]-av[None,:,:]-projection[:,:,None]*dv[None,:,:],axis=2)
            for nr,rr in enumerate(radii):
                d=np.maximum(distance-rr,0.)
                surface=road_tops[None,:]-height+height*np.sqrt(np.maximum(0.,1.-(d/radius)**2))
                surface[d>radius]=-np.inf
                top=np.maximum(rt.BASE_TOP_Z_MM,np.max(surface,axis=1))
                penetration=top-xyz[:,2]
                if nr==0:
                    embedding=penetration+rt.SMOOTH_LAYER_HEIGHT_MM
                    family=kinds[ids[sample_ids]]
                    for k in range(3):
                        candidates=np.flatnonzero(family==k)
                        if not len(candidates):continue
                        win=candidates[np.argmax(embedding[candidates])]
                        if embedding[win]>best[k]:
                            best[k]=embedding[win]
                            mid=int(ids[sample_ids[win]])
                            locations[k]={'xyz_mm':xyz[win].tolist(),'path':int(paths[mid]),
                                          'optical_block_line':int(lines[mid])}
                else:
                    win=int(np.argmax(penetration))
                    if penetration[win]>nozzle_best:
                        nozzle_best=float(penetration[win]);mid=int(ids[sample_ids[win]])
                        nozzle_location={'xyz_mm':xyz[win].tolist(),'path':int(paths[mid]),
                                         'optical_block_line':int(lines[mid])}
    tolerance=.005
    if not math.isfinite(float(best[0])) or abs(float(best[0])-rt.SMOOTH_EMBED_DEPTH_MM)>tolerance:
        raise RuntimeError(f'{SCRIPT_VERSION}: emitted front smoothing embed {best[0]:.6f} mm '
                           f'does not match requested {rt.SMOOTH_EMBED_DEPTH_MM:.6f} mm '
                           f'(tolerance {tolerance:.3f} mm)')
    rear=max(float(best[1]),float(best[2]))
    if not math.isfinite(rear) or rear>rt.SMOOTH_REAR_MAX_EMBED_MM+tolerance:
        raise RuntimeError(f'{SCRIPT_VERSION}: emitted rear smoothing embed {rear:.6f} mm exceeds '
                           f'limit {rt.SMOOTH_REAR_MAX_EMBED_MM:.6f} mm')
    if flat is not None and not math.isfinite(nozzle_best):
        raise RuntimeError(f'{SCRIPT_VERSION}: nozzle footprint audit has no contact samples')
    if (flat is not None and rt.SMOOTH_MAX_NOZZLE_PENETRATION_MM is not None and
            nozzle_best>rt.SMOOTH_MAX_NOZZLE_PENETRATION_MM+tolerance):
        raise RuntimeError(f'{SCRIPT_VERSION}: emitted nozzle penetration {nozzle_best:.6f} mm exceeds '
                           f'limit {rt.SMOOTH_MAX_NOZZLE_PENETRATION_MM:.6f} mm')
    return {'status':'PASS','support_model':'0.4 mm wide half-ellipse; height = physical support tier height',
            'embedding_convention':'nominal vertical underside = commanded Z minus smooth height',
            'xy_sample_step_max_mm':.01,'output_geometry_tolerance_mm':tolerance,
            'support_segments':len(supports),'smooth_segments':len(moves),'samples':len(points),
            'requested_front_embed_mm':rt.SMOOTH_EMBED_DEPTH_MM,'front_embed_max_mm':float(best[0]),
            'rear_embed_limit_mm':rt.SMOOTH_REAR_MAX_EMBED_MM,'rear_embed_max_mm':float(best[1]),
            'valley_embed_max_mm':float(best[2]) if math.isfinite(float(best[2])) else None,
            'worst_front':locations[0],'worst_rear':locations[1],
            'nozzle_flat_diameter_mm':flat,
            'nozzle_contact_status':('NOT_EVALUATED_DIAMETER_NOT_SUPPLIED' if flat is None else
                                     ('ESTIMATED_NO_LIMIT_SUPPLIED' if rt.SMOOTH_MAX_NOZZLE_PENETRATION_MM is None else 'PASS_DECLARED_FLAT_FOOTPRINT_LIMIT')),
            'nozzle_penetration_max_mm':max(0.,nozzle_best) if flat is not None else None,
            'nozzle_penetration_limit_mm':rt.SMOOTH_MAX_NOZZLE_PENETRATION_MM,
            'worst_nozzle':nozzle_location,
            'limitation':'Original undeformed support model; actual bead shape, nozzle cone, prior smoothing deformation and melt flow are not simulated.'}


# ---- _audit_package ----
def _audit_package(output, rt, piece_name):
    with zipfile.ZipFile(output,"r") as z:
        if z.testzip() is not None: raise RuntimeError(f"{SCRIPT_VERSION}: corrupt archive")
        gb=z.read("Metadata/plate_1.gcode"); g=gb.decode("utf-8","strict")
        md5=z.read("Metadata/plate_1.gcode.md5").decode("ascii").strip().lower()
    if md5 != hashlib.md5(gb).hexdigest(): raise RuntimeError(f"{SCRIPT_VERSION}: MD5 mismatch")
    for token in ("FC3D_V1159_A1MINI_START","FC3D_V1159_A1MINI_START_END",
                  "FC3D_V1159_A1MINI_NATIVE_END_BEGIN","FC3D_V1159_A1MINI_NATIVE_END_DONE"):
        if token not in g: raise RuntimeError(f"{SCRIPT_VERSION}: lifecycle missing {token}")
    label=(f"FC3D_V1159_REAR_LABEL card={piece_name} text={rt.REAR_PARAMETER_TEXT} "
           f"revision=159 rotation=180 arrow={rt.REAR_ARROW_DIRECTION}")
    if label not in g: raise RuntimeError(f"{SCRIPT_VERSION}: rear label metadata missing")
    begin=g.find("FC3D_V1159_OPTICAL_START"); end=g.find("FC3D_V1159_OPTICAL_END",begin)
    if begin < 0 or end < 0: raise RuntimeError(f"{SCRIPT_VERSION}: optical block missing")
    viewer=(f"FC3D_V1159_VIEWER_TARGET x={rt.MASTER_FAN.viewer_x_mm:.3f} "
            f"eye_above_screen_bottom={rt.MASTER_FAN.viewer_z_mm:.3f} distance={rt.MASTER_FAN.viewer_distance_mm:.3f}")
    if viewer not in g[begin:end]:
        raise RuntimeError(f"{SCRIPT_VERSION}: viewer target metadata missing or inconsistent")
    motion=_audit_optical_block(_ct_without_detours(g[begin:end]),rt)
    backplate=_audit_backplate_process(g,rt)
    contact=_audit_smooth_gcode_contact(g[begin:end],rt) if rt._mode_profile()["smooth"] else None
    spacing=rt.optical_spacing_report(rt.PieceSpec.for_name(piece_name))
    if spacing["physical_gap_min_mm"] < -rt.PHYSICAL_TOL_MM or not spacing["full_required_profile_clear"]:
        raise RuntimeError(f"{SCRIPT_VERSION}: optical spacing audit failed {spacing}")
    return {"mode":"mapped-pyramid","layer_map":rt.LAYER_MAP,"visibility_percent":rt.VISIBILITY_PERCENT,
            "layer_height_mm":rt.LAYER_HEIGHT_MM,"physical_height_scale":rt.PHYSICAL_HEIGHT_SCALE,
            "physical_layer_height_mm":rt.PHYSICAL_LAYER_HEIGHT_MM,
            "smooth_embed_depth_mm":rt.SMOOTH_EMBED_DEPTH_MM if rt._mode_profile()["smooth"] else None,
            "smooth_layer_height_mm":rt.SMOOTH_LAYER_HEIGHT_MM if rt._mode_profile()["smooth"] else None,
            "support_tier_counts":spacing["support_tier_counts"],
            "support_height_mm":spacing["support_height_mm"],
            "shadow_blocker":spacing["shadow_blocker"],
            "viewer_eye_above_screen_bottom_mm":rt.MASTER_FAN.viewer_z_mm,
            "viewer_distance_mm":rt.MASTER_FAN.viewer_distance_mm,
            **backplate,**motion,"smoothing_contact":contact,"pitch_min_mm":spacing["pitch_mm"]["min"],
            "physical_gap_min_mm":spacing["physical_gap_min_mm"],
            "visibility_margin_min":spacing["visibility_margin_min"],
            "rear_label":rt.REAR_PARAMETER_TEXT,"rear_arrow_direction":rt.REAR_ARROW_DIRECTION,
            "startup":"PASS","end":"PASS"}


# ---- _ct_without_detours ----
def _ct_without_detours(g):
    return re.sub(r'^; FC3D_CT_DETOUR_BEGIN[^\n]*\n.*?^; FC3D_CT_DETOUR_END\n','',g,flags=re.M|re.S)


# ---- _ct_state ----
def _ct_state(before):
    state={'X':None,'Y':None,'Z':None,'F':1800.,'accel':8000.,'fan':128.}
    last_e=None;last_e_line=''
    for l in before.splitlines():
        s=l.split(';')[0].strip()
        if re.match(r'G[01]\s',s):
            for k,v in re.findall(r'\b([XYZF])([-+\d.]+)',s):state[k]=float(v)
            if re.match(r'G1 E[-+\d.]+(?: F[-+\d.]+)?$',s):last_e=float(re.search(r'\bE([-+\d.]+)',s)[1]);last_e_line=l
        m=re.match(r'M204 S([-+\d.]+)',s)
        if m:state['accel']=float(m[1])
        m=re.match(r'M106 (?:P1 )?S([-+\d.]+)',s)
        if m:state['fan']=float(m[1])
    if last_e not in (-.4,-.8):raise RuntimeError('contrast detour entry retract is not known')
    state['debt']=.8 if 'A_ENTRY_EXTRA_RETRACT' in last_e_line else -last_e
    if any(state[k] is None for k in 'XYZ'):raise RuntimeError('contrast detour position unknown')
    return state


# ---- _ct_detour ----
def _ct_detour(heights,state,change=None,safe_z=4.,maximum=1.):
    rows=['; FC3D_CT_DETOUR_BEGIN']
    debt=state['debt']
    if change is not None:
        rows+= [f'; FC3D_CT_CHANGE_BEGIN next_tool={change}',_ct_change_macro(change,maximum).strip(),
                f'G1 E{2-debt:.3f} F300 ; FC3D_CT_ADJUST_MACRO_RETRACT', '; FC3D_CT_CHANGE_END']
    for z in heights:
        dose=.03326 if abs(z-.2)<1e-8 else .01567
        rows += [f'; FC3D_CT_TOWER_BEGIN z={z:.3f}', 'G90','M83',f'G0 Z{safe_z:.3f} F900','G0 X8.000 Y40.000 F6000',
                 f'G0 Z{z:.3f} F900','M204 S500',f'G1 E{debt:.3f} F1800']
        for row in range(31):
            x=28. if row%2==0 else 8.;y=40.+row*.4
            rows.append(f'G1 X{x:.3f} Y{y:.3f} E{20*dose:.6f} F1800 ; FC3D_CT_TOWER_DRAW')
            if row<30:rows.append(f'G1 X{x:.3f} Y{y+.4:.3f} E{.4*dose:.6f} F1800 ; FC3D_CT_TOWER_DRAW')
        rows += [f'G1 E-{debt:.3f} F1800', '; FC3D_CT_TOWER_END']
    rows += [f'G0 Z{safe_z:.3f} F900',f'G0 X{state["X"]:.6f} Y{state["Y"]:.6f} F6000',f'G0 Z{state["Z"]:.6f} F900',
             f'M204 S{state["accel"]:g}',f'M106 P1 S{state["fan"]:g}',f'G1 F{state["F"]:g}','; FC3D_CT_DETOUR_END']
    return '\n'.join(rows)+'\n'


# ---- _apply_contrast ----
def _apply_contrast(output,rt):
    import xml.etree.ElementTree as ET
    with zipfile.ZipFile(output) as z:
        original=g=z.read('Metadata/plate_1.gcode').decode()
        project=json.loads(z.read('Metadata/project_settings.config'));plate=json.loads(z.read('Metadata/plate_1.json'))
        root=ET.fromstring(z.read('Metadata/slice_info.config'))
    schedule=_tower_schedule(rt);batches=schedule['batches']
    if not schedule['changes']:
        _replace_zip(output,{'Metadata/filament_sequence.json':json.dumps({'plate_1':{
            'nozzle_sequence':[0],'optimal_assignment':[0],'sequence':[1]}}).encode()})
        return _audit_contrast(output,rt)
    def detour(heights,state,change=None):
        return _ct_detour(heights,state,change,schedule['safe_z'],schedule['max_deposited_z'])
    layers=list(re.finditer(r'^; CHANGE_LAYER$',g,re.M));insertions=[]
    if len(layers)!=4:raise RuntimeError('contrast expected three base layers and optical stage')
    for boundary,heights in [(layers[1].start(),batches[0]),(layers[2].start(),batches[1])]:
        insertions.append((boundary,detour(heights,_ct_state(g[:boundary]))))
    boundary=g.index('; DIRECT_LAYER V4 physical=3 ')
    insertions.append((boundary,detour(batches[2],_ct_state(g[:boundary]))))
    for change in schedule['changes']:
        tier,road=change['tier'],change['road']
        m=re.search(r'^; FC3D_V1159_SUPPORT_ROAD_START[^\n]* tier='+str(tier)+r' tier_road='+str(road)+r' ',g,re.M)
        if not m:raise RuntimeError('mapped pyramid: missing colour boundary')
        insertions.append((m.start(),detour(change['heights'],_ct_state(g[:m.start()]),change['tool'])))
    for at,block in sorted(insertions,reverse=True):g=g[:at]+block+g[at:]
    if _ct_without_detours(g)!=original:raise RuntimeError('colour detours changed model paths')
    colours=['#000000','#FFFFFF']
    for key,value in list(project.items()):
        if isinstance(value,list) and len(value)==1 and (key.startswith('filament_') or key.startswith('nozzle_temperature') or key in ('temperature_vitrification','idle_temperature') or 'bed_temperature' in key):project[key]=value*2
    project.update(filament_colour=colours,filament_multi_colour=colours,filament_type=['PETG']*2,
        filament_settings_id=['Generic PETG @BBL A1M']*2,filament_ids=['GFG99']*2,
        filament_map=['1']*2,filament_map_2=['1']*2,filament_nozzle_map=['0']*2,physical_extruder_map=['0']*2,
        enable_prime_tower='1',prime_tower_width='20',wipe_tower_x=['8'],wipe_tower_y=['40'],
        flush_volumes_matrix=['0','300','200','0'],flush_multiplier=['1']*2,
        fc3d_colour_roles=['A1 black base and non-W roads','A2 mapped W leading roads: '+rt.LAYER_MAP],fc3d_layer_map=rt.LAYER_MAP,
        change_filament_gcode='; FC3D mapped colour changes are embedded in executable G-code')
    for key in ('filament_colour','filament_multi_colour','filament_type','filament_settings_id','filament_ids','filament_map','filament_map_2','filament_nozzle_map','nozzle_temperature','nozzle_temperature_initial_layer','flush_volumes_matrix','flush_multiplier','enable_prime_tower','change_filament_gcode'):
        val=project[key];text=';'.join(val) if isinstance(val,list) else str(val)
        g=re.sub(r'^; '+re.escape(key)+r' = .*$',lambda _:f'; {key} = {text}',g,flags=re.M)
    plate.update(filament_colors=colours,filament_ids=[0,1],first_extruder=0)
    coords=[];x=y=None;used={0:0.,1:0.};tool=0
    model=g[g.index('; CHANGE_LAYER'):g.index('; V4_MODEL_END')]
    for l in model.splitlines():
        tm=re.match(r'T([012])\s*$',l)
        if tm:tool=int(tm[1])
        if not re.match(r'G[01]\s',l):continue
        v={k:float(a) for k,a in re.findall(r'\b([XYE])([-+\d.]+)',l)}
        old=(x,y);x=v.get('X',x);y=v.get('Y',y)
        if v.get('E',0)>0 and ('X' in v or 'Y' in v):
            used[tool]+=v['E']
            if ('SUPPORT_SEG' in l) and None not in old:coords.extend([old,(x,y)])
    bb=[min(x for x,y in coords)-.2,min(y for x,y in coords)-.2,max(x for x,y in coords)+.2,max(y for x,y in coords)+.2]
    if bb[0]<=28.2 or min(bb)<0 or max(bb)>180:raise RuntimeError('prime pad conflicts with model or bed')
    # Retain the larger inherited backplate footprint if present.
    inherited=plate.get('bbox_all',bb)
    for o in plate.get('bbox_objects',[]):
        if isinstance(o,dict):o['bbox']=bb;o['area']=(bb[2]-bb[0])*(bb[3]-bb[1])
    plate['bbox_all']=[min(7.8,bb[0],inherited[0]),min(39.8,bb[1],inherited[1]),max(28.2,bb[2],inherited[2]),max(52.2,bb[3],inherited[3])]
    pn=root.find('plate')
    for n in list(pn):
        if n.tag in ('filament','layer_filament_lists'):pn.remove(n)
    for tool,colour in enumerate(colours):ET.SubElement(pn,'filament',dict(id=str(tool+1),tray_info_idx='GFG99',type='PETG',color=colour,
        used_m=f'{used[tool]/1000:.5f}',used_g=f'{used[tool]*2.4053*1.27/1000:.5f}',group_id='0',nozzle_diameter='0.40',volume_type='Standard',used_for_object='true',used_for_support='false'))
    lists=ET.SubElement(pn,'layer_filament_lists')
    for tools,layers in [('0','0 2'),('0 1','3 3')]:ET.SubElement(lists,'layer_filament_list',dict(filament_list=tools,layer_ranges=layers))
    for key,value in dict(has_filament_switcher='true',filament_maps='1 1',fc3d_active_raw_tools='0,1',fc3d_active_filament_one_based='1,2').items():
        node=next((n for n in pn.findall('metadata') if n.get('key')==key),None)
        if node is None:node=ET.SubElement(pn,'metadata',dict(key=key))
        node.set('value',value)
    # Header material arrays must agree with Connect/3MF material identities.
    headers={
        'filament':'1,2','filament_density':'1.27,1.27','filament_diameter':'1.75,1.75',
        'total filament length [mm]':','.join(f'{used[i]:.5f}' for i in range(2)),
        'total filament volume [cm^3]':','.join(f'{used[i]*2.4053/1000:.5f}' for i in range(2)),
        'total filament weight [g]':','.join(f'{used[i]*2.4053*1.27/1000:.5f}' for i in range(2)),
        'max_z_height':f'{_tower_schedule(rt)["max_deposited_z"]:.3f}'}
    for key,value in headers.items():
        g,count=re.subn(r'^; '+re.escape(key)+r'\s*:.*$',lambda _:f'; {key}: {value}',g,flags=re.M)
        if count!=1:raise RuntimeError('contrast header field missing: '+key)
    b=g.encode();_replace_zip(output,{'Metadata/plate_1.gcode':b,'Metadata/plate_1.gcode.md5':(hashlib.md5(b).hexdigest()+'\n').encode(),
        'Metadata/project_settings.config':json.dumps(project,separators=(',',':')).encode(),
        'Metadata/plate_1.json':json.dumps(plate,separators=(',',':')).encode(),
        'Metadata/slice_info.config':ET.tostring(root,encoding='utf-8',xml_declaration=True),
        'Metadata/filament_sequence.json':json.dumps({'plate_1':{'nozzle_sequence':[0]*(1+len(schedule['changes'])),'optimal_assignment':[0,0],'sequence':[1]+[c['tool']+1 for c in schedule['changes']]}}).encode()})
    return _audit_contrast(output,rt)


# ---- _audit_contrast ----
def _audit_contrast(output,rt):
    with zipfile.ZipFile(output) as z:
        g=z.read('Metadata/plate_1.gcode').decode();plate=json.loads(z.read('Metadata/plate_1.json'))
        seq=json.loads(z.read('Metadata/filament_sequence.json'))['plate_1']
    groups=_colour_groups(rt);wanted=[q['tool'] for q in groups if q['change'] is not None]
    if seq['sequence']!=[1]+[t+1 for t in wanted]:raise RuntimeError('mapped colour sequence metadata disagrees')
    tool=None;model=False;detour=False;optical=False;tier=road=None;switches=[];counts={0:0,1:0};seen=set();ids=[]
    for line in g.splitlines():
        if line=='; CHANGE_LAYER':model=True
        if line=='; V4_MODEL_END':break
        m=re.match(r'T(\d+)\s*$',line)
        if m and int(m[1])<255:
            tool=int(m[1])
            if model:switches.append(tool)
        if 'CT_DETOUR_BEGIN' in line:detour=True
        if 'CT_DETOUR_END' in line:detour=False;continue
        if 'OPTICAL_START' in line:optical=True
        if not model or detour:continue
        if 'SUPPORT_ROAD_START' in line:
            tier=int(re.search(r' tier=(\d+)',line)[1]);road=int(re.search(r'tier_road=(\d+)',line)[1])
            ids.append(int(re.search(r' road=(\d+)',line)[1]))
        if 'SUPPORT_SEG' in line:
            if tool!=_road_tool(rt,tier,road):raise RuntimeError('mapped leading-edge colour ownership mismatch')
            counts[tool]+=1;seen.add((tier,road,tool))
        elif 'SMOOTH_SEG' in line:raise RuntimeError('unexpected smoothing pass')
        elif (not optical or 'TOP_VALLEY_FILL_DRAW' in line) and re.match(r'G[01] ',line) and re.search(r'\b[XY][-\d]',line) and re.search(r'\bE(?:0\.[0-9]*[1-9]|[1-9])',line):
            if tool!=0:raise RuntimeError('backplate/fill must remain black')
    expected={(i,r,_road_tool(rt,i,r)) for i,c in enumerate(rt._mode_profile()['tier_counts'],1) for r in range(1,c+1)}
    if switches!=wanted or seen!=expected:raise RuntimeError('mapped material sequence or tier coverage failed')
    if len(ids)!=len(set(ids)):raise RuntimeError('an optical road was emitted twice')
    schedule=_tower_schedule(rt)
    heights=[float(v) for v in re.findall(r'CT_TOWER_BEGIN z=([\d.]+)',g)]
    if heights!=[h for batch in schedule['batches'] for h in batch]:raise RuntimeError('tower layer sequence failed')
    for block in re.findall(r'; FC3D_CT_DETOUR_BEGIN\n.*?; FC3D_CT_DETOUR_END',g,re.S):
        if 'CT_CHANGE_BEGIN' in block and not re.search(r'^M109 S255\b',block,re.M):raise RuntimeError('PETG heat wait missing')
    spacing=rt.optical_spacing_report(rt.CURRENT_PIECE)
    report=dict(status='PASS',revision=REVISION,script_version=SCRIPT_VERSION,cap_height_mm=rt.CAP_HEIGHT_MM,cap_physical_height_mm=rt.CAP_PHYSICAL_HEIGHT_MM,printer='a1mini',layer_map=rt.LAYER_MAP,
        materials={'A1':'black backplate and every non-W road','A2':'mapped W leading roads only'},
        colour_changes=len(wanted),raw_tool_sequence=[0]+wanted,tower_heights_mm=heights,
        draw_segments=counts,optical_roads=len(ids),spacing=spacing,spacing_model=rt.SPACING_MODEL,
        purge_mm3={'black_to_white':300,'white_to_black':200},
        limitation='Inherited undeformed half-ellipse envelope; actual PETG bead shape, opacity and optical gain are unmeasured.')
    _replace_zip(output,{'Metadata/fc3d_selective_white_audit.json':json.dumps(report,indent=2).encode()})
    return report


# ---- _tower_schedule ----
def _tower_schedule(rt):
    tiers = [round(z, 3) for z in rt.TIER_TOP_Z_MM]
    base = float(rt.BASE_TOP_Z_MM)
    if any(b <= a for a, b in zip([base] + tiers, tiers)):
        raise ValueError('tier spacing is below G-code Z resolution')
    if tiers[-1] > 150:
        raise ValueError('optical stack exceeds the A1 mini build height allowance')
    changes = [g for g in _colour_groups(rt) if g['change'] is not None]
    if not changes:
        return dict(tiers=tiers, batches=[], changes=[], max_deposited_z=tiers[-1], safe_z=max(4., tiers[-1]+1.))
    batches = [[.2], [.3], [.4]]
    last = 4
    scheduled = []
    for group in changes:
        end = max(last+1, int(math.ceil(tiers[group['tier']-1] * 10 - 1e-8)))
        heights = [round(i/10, 1) for i in range(last+1, end+1)]
        last = end
        batches.append(heights)
        scheduled.append(dict(tier=group['tier'], road=group['roads'][0], tool=group['tool'], heights=heights))
    maximum = max(tiers[-1], last/10)
    return dict(tiers=tiers, batches=batches, changes=scheduled,
                max_deposited_z=maximum, safe_z=max(4., maximum+1.))


# ---- _ct_change_macro ----
def _ct_change_macro(change,maximum):
    template=CHANGE_TO_WHITE if change==1 else CHANGE_TO_BLACK
    result,n=re.subn(r'^G1 Z[\d.]+ F(1200|3000)$',lambda m:f'G1 Z{maximum+3:.3f} F{m[1]}',template,flags=re.M)
    if n!=2:raise RuntimeError('colour change lift template changed unexpectedly')
    return result


# ---- _mapped_runtime ----
def _mapped_runtime(layer_map='kkkwwk', layer_height=.24, scale=1.4,
                    visibility=50, piece='1-2', minimum_pitch=0.,
                    horizontal_percent=0., cap_height_mm=None):
    """Configure one job in this module. The CLI runs one job per process.

    This is configuration, not a loader/patcher for earlier converters. Load a
    separate module instance when independent concurrent runtimes are required.
    """
    global LAYER_MAP, LAYER_HEIGHT_MM, PHYSICAL_HEIGHT_SCALE, VISIBILITY_PERCENT
    global PHYSICAL_LAYER_HEIGHT_MM, A_MAIN_NOMINAL_HEIGHT_MM, A_MAIN_E_PER_MM
    global STRUCTURAL_E_PER_MM, NOMINAL_TOP_Z_MM, CURRENT_PIECE, RUNTIME_ORIGIN
    global MINIMUM_PITCH_MM, HORIZONTAL_PERCENT, SPACING_MODEL, REAR_TEXT_LINES
    global REAR_PARAMETER_TEXT, CAP_HEIGHT_MM, CAP_PHYSICAL_HEIGHT_MM
    global TIER_PHYSICAL_HEIGHTS_MM, TIER_TOP_Z_MM
    global _OPTICAL_LATTICE_CACHE, _WHITE_SAMPLE_CACHE, _WHITE_ARRAY_CACHE
    global _BLOCKER_ARRAY_CACHE, _MIRROR_LATTICE_CACHE
    mapping = str(layer_map).upper()
    if not re.fullmatch('[KW]+', mapping):
        raise ValueError('layer map must contain only K and W, bottom to top')
    if len(mapping) > 16:
        raise ValueError('layer map supports 1 to 16 optical tiers')
    if not math.isfinite(layer_height) or not 0 < layer_height <= .28:
        raise ValueError('material-dose layer height must be greater than zero and at most 0.28 mm')
    if not math.isfinite(visibility) or not 0 <= visibility <= 100:
        raise ValueError('visibility must be from 0 to 100 percent')
    _validate_options('pyramid-3-2-1', layer_height, int(visibility), scale)
    cap = _validate_cap(mapping, layer_height, cap_height_mm)
    if not math.isfinite(minimum_pitch) or not 0 <= minimum_pitch <= 20:
        raise ValueError('minimum pitch must be from zero to 20 mm')
    if not math.isfinite(horizontal_percent) or not 0 <= horizontal_percent <= 100:
        raise ValueError('horizontal percent must be finite and from 0 to 100')
    LAYER_MAP = mapping
    LAYER_HEIGHT_MM = float(layer_height)
    PHYSICAL_HEIGHT_SCALE = float(scale)
    VISIBILITY_PERCENT = float(visibility)
    PHYSICAL_LAYER_HEIGHT_MM = LAYER_HEIGHT_MM * PHYSICAL_HEIGHT_SCALE
    A_MAIN_NOMINAL_HEIGHT_MM = PHYSICAL_LAYER_HEIGHT_MM
    A_MAIN_E_PER_MM = 0.1567 * LAYER_HEIGHT_MM
    STRUCTURAL_E_PER_MM = 0.01567 * (LAYER_H_MM / .10)
    MINIMUM_PITCH_MM = float(minimum_pitch)
    HORIZONTAL_PERCENT = float(horizontal_percent)
    MODE_PROFILES[OPTICAL_MODE] = dict(tier_counts=tuple(range(len(mapping), 0, -1)),
                                     smooth=False, placement='outer_to_inner')
    CURRENT_PIECE = PieceSpec.for_name(piece)
    RUNTIME_ORIGIN = None
    SPACING_MODEL = 'mapped-white'
    set_runtime_e_per_mm(STRUCTURAL_E_PER_MM)
    CAP_HEIGHT_MM = cap
    CAP_PHYSICAL_HEIGHT_MM = cap * PHYSICAL_HEIGHT_SCALE
    rt = sys.modules[__name__]
    TIER_PHYSICAL_HEIGHTS_MM = _tier_physical_heights(rt, cap)
    TIER_TOP_Z_MM = _tier_top_zs(rt, cap)
    NOMINAL_TOP_Z_MM = TIER_TOP_Z_MM[-1]
    # Preserve v158 label order and rounding: e.g. 0.165 is labelled C16.
    REAR_TEXT_LINES = (f'{piece}  {REVISION}', mapping,
        f'V{visibility:g}% L{LAYER_HEIGHT_MM:g}',
        f'S{PHYSICAL_HEIGHT_SCALE:g}' + (f' P{minimum_pitch:g}' if minimum_pitch else '')
        + f' C{int(round(cap * 100)):02d} H{horizontal_percent:g}')
    REAR_PARAMETER_TEXT = ' | '.join(REAR_TEXT_LINES)
    _OPTICAL_LATTICE_CACHE = {}
    _WHITE_SAMPLE_CACHE = {}
    _WHITE_ARRAY_CACHE = {}
    _BLOCKER_ARRAY_CACHE = {}
    _MIRROR_LATTICE_CACHE = {}
    return rt


# ---- _mapped_output_name ----
def _mapped_output_name(rt):
    def slug(value):
        return format(float(value), '.8g').replace('.', 'p')
    # Keep the original short-name policy; the cap and revision are explicit.
    base = (f'ALR_{rt.LAYER_MAP}_{rt.CURRENT_PIECE.name}_V{slug(rt.VISIBILITY_PERCENT)}'
            f'_L{slug(rt.LAYER_HEIGHT_MM)}_S{slug(rt.PHYSICAL_HEIGHT_SCALE)}'
            + (f'_P{slug(rt.MINIMUM_PITCH_MM)}' if rt.MINIMUM_PITCH_MM else '')
            + f'_H{slug(rt.HORIZONTAL_PERCENT)}_C{slug(rt.CAP_HEIGHT_MM)}_v159.gcode.3mf')
    if len(base.encode('utf-8')) > 96:
        digest = hashlib.sha256(base.encode()).hexdigest()[:16]
        base = f'ALR_{rt.LAYER_MAP}_{rt.CURRENT_PIECE.name}_C{slug(rt.CAP_HEIGHT_MM)}_{digest}_v159.gcode.3mf'
    return Path(base)


# ---- _road_tool ----
def _road_tool(rt,tier,road):
    return int(rt.LAYER_MAP[tier-1]=='W' and road==len(rt.LAYER_MAP)-tier+1)


# ---- _colour_groups ----
def _colour_groups(rt):
    groups=[];tool=0
    for tier,count in enumerate(rt._mode_profile()['tier_counts'],1):
        bytool={t:[r for r in range(1,count+1) if _road_tool(rt,tier,r)==t] for t in (0,1)}
        # Start each tier with the material already loaded, then the other.
        # Thus adjacent WW tiers need only one outward and one return swap.
        for t in (tool,1-tool):
            if not bytool[t]:continue
            change=t if t!=tool else None
            groups.append(dict(tier=tier,tool=t,roads=bytool[t],change=change));tool=t
    return groups


# ---- _audit_horizontal_motion ----
def _audit_horizontal_motion(output,rt):
    """Check actual output XY/E against the solved per-road paths."""
    with zipfile.ZipFile(output) as z:g=z.read('Metadata/plate_1.gcode').decode()
    block=g[g.index('FC3D_V1159_OPTICAL_START'):g.index('FC3D_V1159_OPTICAL_END')]
    if f'HORIZONTAL percent={rt.HORIZONTAL_PERCENT:g} target=screen-horizontal' not in block:
        raise RuntimeError('horizontal G-code parameter metadata differs')
    clean=_ct_without_detours(block)
    piece=rt.CURRENT_PIECE;plans=rt.get_optical_lattice(piece)['printable']
    position={};segments=0;angles=[];origin=rt.RUNTIME_ORIGIN
    if origin is None:raise RuntimeError('horizontal audit requires the actual runtime origin')
    for road in re.findall(r'; FC3D_V1159_SUPPORT_ROAD_START[^\n]*\n.*?; FC3D_V1159_SUPPORT_ROAD_END[^\n]*',clean,re.S):
        m=re.search(r'stack=(\d+) tier=(\d+) tier_road=(\d+)',road);stack,tier,index=map(int,m.groups())
        local=plans[stack-1]['roads'][(tier-1,index-1)]
        start=re.search(r'G0 X([-\d.]+) Y([-\d.]+)',road)
        inferred=(float(start[1])-local[0][0],float(start[2])-local[0][1])
        if math.dist(origin,inferred)>.001:raise RuntimeError('horizontal road origin differs')
        absolute=[(origin[0]+p[0],origin[1]+p[1]) for p in local]
        length=rt._polyline_length2(absolute);dry=min(.16,max(0.,length*.45))
        expected=rt._coalesce_curve_for_emission(rt._polyline_prefix_for_length(absolute,max(0.,length-dry)))
        actual=[]
        for line in road.splitlines():
            if re.match(r'G[01] ',line):
                before=dict(position);position.update({k:float(v) for k,v in re.findall(r'\b([XYZ])([-\d.]+)',line.split(';')[0])})
            if 'SUPPORT_SEG' in line:
                actual.append((position['X'],position['Y']));segments+=1
                dx=position['X']-before['X'];dy=position['Y']-before['Y'];ds=math.hypot(dx,dy)
                if ds>=.79:
                    point=((position['X']+before['X'])/2-origin[0]+piece.global_x0_mm,
                           (position['Y']+before['Y'])/2-origin[1]+piece.global_z0_mm)
                    b=rt.mirror_frame_global(*point)['b_unit']
                    angles.append(math.degrees(math.asin(min(1.,abs(dx*b[0]+dy*b[1])/ds))))
        if actual!=[tuple(round(v,3) for v in p) for p in expected[1:]]:
            raise RuntimeError('horizontal packaged road does not match solved geometry')
    if not segments:raise RuntimeError('no horizontal optical segments audited')
    error=max(angles,default=0.)
    if rt.HORIZONTAL_PERCENT and error>1.0:raise RuntimeError(f'horizontal emitted tangent error {error:.4f} degrees exceeds 1 degree')
    local_spacing=[]
    if rt.HORIZONTAL_PERCENT and len(plans)>1:
        for fx in (.05,.5,.95):
            for fy in (.05,.5,.95):
                target=(piece.global_x0_mm+fx*piece.width_mm,piece.global_z0_mm+fy*piece.height_mm)
                choices=[(math.dist(target,p),i,p) for i,plan in enumerate(plans[:-1]) for p in plan['curve']]
                _,i,point=min(choices)
                next_point=rt._horizontal_normal_intersection(point,plans[i+1]['curve'])
                local_spacing.append(dict(target_mm=target,sampled_mm=point,pitch_mm=math.dist(point,next_point)))
    return dict(status='PASS',horizontal_percent=rt.HORIZONTAL_PERCENT,spacing_model=rt.SPACING_MODEL,
                segments=segments,max_emitted_tangent_error_deg=error,geometry_matches_package=True,
                local_spacing=local_spacing)


# ---- _ideal_mirror_frame_global ----
def _ideal_mirror_frame_global(x_mm: float, z_mm: float):
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


# ---- _original_reference_setup ----
def _original_reference_setup(piece):
    base = get_mirror_wave_lattice(piece)
    if _mode_profile()["placement"] == "outer_to_inner":
        candidates = []
        for rec in base["main_a_curves"]:
            clips = _clip_polyline2_to_piece(rec["points"], piece)
            if clips:
                pts = clips[0]
                radii = [math.hypot(x - MASTER_FAN.projector_x_mm,
                                    z - MASTER_FAN.projector_z_mm) for x, z in pts]
                candidates.append((sum(radii) / len(radii), rec))
        if not candidates:
            raise RuntimeError(f"{piece.name}: no outer reference arc")
        full = [(float(x), float(z)) for x, z in max(candidates, key=lambda q: q[0])[1]["points"]]
        halo = 0.5 * max(piece.width_mm, piece.height_mm)
        idx = [i for i, (x, z) in enumerate(full)
               if piece.global_x0_mm - halo <= x <= piece.global_x1_mm + halo
               and piece.global_z0_mm - halo <= z <= piece.global_z1_mm + halo]
        a = max(0, min(idx) - 2)
        b = min(len(full), max(idx) + 3)
        return {"curve": _resample_polyline2(full[a:b], 1.0), "advance": "curve"}
    first = base["main_a_local"][0]
    rec = next(r for r in base["main_a_curves"]
               if r["wave"] == first["wave"] and r["family"] == first["family"])
    pts = [(float(x), float(z)) for x, z in rec["points"]]
    pc = (0.5 * (piece.global_x0_mm + piece.global_x1_mm),
          0.5 * (piece.global_z0_mm + piece.global_z1_mm))
    si = min(range(len(pts)), key=lambda i: math.hypot(pts[i][0] - pc[0], pts[i][1] - pc[1]))
    return {"curve": _trace_a_streamline_global(
                pts[si][0], pts[si][1], _polyline_length2(pts[:si + 1]),
                _polyline_length2(pts[si:]), A_TRACE_STEP_MM),
            "advance": "seed", "seed": pts[si],
            "negative": _polyline_length2(pts[:si + 1]),
            "positive": _polyline_length2(pts[si:])}


# ---- _original_advance_candidate ----
def _original_advance_candidate(previous, setup, distance):
    if setup["advance"] == "curve":
        return _waveset_advance_curve_inward(previous,distance),None
    seed,_=_advance_b_rise_global(setup["seed"][0],setup["seed"][1],distance,B_FRONT_MAX_STEP_MM)
    return _trace_a_streamline_global(seed[0],seed[1],setup["negative"],setup["positive"],A_TRACE_STEP_MM),seed


# ---- _original_white_full_metrics ----
def _original_white_full_metrics(current,previous,piece,count=128):
    eligible=[i for i,(c,p) in enumerate(zip(current,previous)) if
        (piece.global_x0_mm<=p[0]<=piece.global_x1_mm and piece.global_z0_mm<=p[1]<=piece.global_z1_mm)]
    if not eligible:return None
    ids=sorted(set(eligible[round(j*(len(eligible)-1)/8)] for j in range(9)))
    records=[_white_pair_visibility(previous[i],current[i],count) for i in ids]
    return dict(projector_min=min(r['projector_min'] for r in records),viewer_min=min(r['viewer_min'] for r in records),joint_min=min(r['joint_min'] for r in records))


# ---- _original_full_arc_physical_gap ----
def _original_full_arc_physical_gap(current, previous, piece):
    """Minimum finite-envelope gap over every relevant corresponding point."""
    if len(current) != len(previous):
        raise RuntimeError("v1.159: corresponding full curves differ")
    halo=ARC_PROFILE_WIDTH_MM*(max(_mode_profile()["tier_counts"]) if not _mode_profile()["smooth"] else 1.0)
    indices=[]
    for i,(c,p) in enumerate(zip(current,previous)):
        if ((piece.global_x0_mm-halo<=c[0]<=piece.global_x1_mm+halo and
             piece.global_z0_mm-halo<=c[1]<=piece.global_z1_mm+halo) or
            (piece.global_x0_mm-halo<=p[0]<=piece.global_x1_mm+halo and
             piece.global_z0_mm-halo<=p[1]<=piece.global_z1_mm+halo)):
            indices.append(i)
    if not indices: return float("inf")
    return _physical_envelope_gap([current[i] for i in indices],[previous[i] for i in indices])


# ---- _mapped_spacing_report ----
def _mapped_spacing_report(piece):
    lat=get_optical_lattice(piece);plans=lat['plans'];pitches=[p['next_pitch_mm'] for p in plans]
    white=[p['white_full_metrics'] for p in plans if p['white_full_metrics']]
    minima={k:min(v[k] for v in white) for k in ('projector_min','viewer_min','joint_min')}
    gap=min(p['next_full_arc_physical_gap_mm'] for p in plans)
    centre=(piece.global_x0_mm+piece.width_mm/2,piece.global_z0_mm+piece.height_mm/2)
    section=_stack_cross_section_profile(mirror_frame_global(*centre)['facet_tilt_deg'])
    all_centres=[u for tier in section['tiers'] for u in tier['centres_u_mm']]
    return dict(result='PASS',mode='mapped-pyramid',layer_map=LAYER_MAP,
        layer_height_mm=LAYER_HEIGHT_MM,physical_height_scale=PHYSICAL_HEIGHT_SCALE,
        physical_layer_height_mm=PHYSICAL_LAYER_HEIGHT_MM,visibility_percent=VISIBILITY_PERCENT,minimum_pitch_mm=MINIMUM_PITCH_MM,
        printable_stacks=len(lat['printable']),support_tier_counts=list(_mode_profile()['tier_counts']),
        support_height_mm=section['height_mm'],base_width_mm=section['base_width_mm'],
        full_footprint_at_card_centre_mm=max(all_centres)-min(all_centres)+ARC_PROFILE_WIDTH_MM,
        model_top_z_mm=BASE_TOP_Z_MM+section['height_mm'],white_leading_tiers=_target_tiers() if 'W' in LAYER_MAP else [],
        shadow_blocker='every road in the own and adjacent pyramids',
        spacing_sample_policy='256 surface samples per target tier; midpoint solve and nine positions per arc pair',
        white_surface_target='exposed front quarter of each mapped W leading road' if 'W' in LAYER_MAP else 'all K leading front quarters (no white tiers)',
        visibility_definition='minimum projector-visible arclength fraction of EACH target tier; viewer/joint reported separately',
        pitch_mm=dict(min=min(pitches),mean=sum(pitches)/len(pitches),max=max(pitches)),
        physical_gap_min_mm=gap,white_visibility_minima=minima,
        own_visibility_limit_percent=100*lat['own_visibility_limit'],
        visibility_margin_min=minima['projector_min']-VISIBILITY_PERCENT/100,
        full_required_profile_clear=minima['projector_min']>=VISIBILITY_PERCENT/100-1e-9,
        bead_model='inherited undeformed half ellipse; optical gain is not predicted by this audit')


# ---- _validate_cap ----
def _validate_cap(mapping: str, layer_height_mm: float, cap_height_mm: float | None) -> float:
    mapping = str(mapping).upper()
    layer_height_mm = float(layer_height_mm)
    cap = layer_height_mm if cap_height_mm is None else float(cap_height_mm)
    if not math.isfinite(cap) or not 0.0 < cap <= CAP_MAX_MM:
        raise ThinCapError(f"cap height must be greater than zero and at most {CAP_MAX_MM:.2f} mm")
    if cap_height_mm is not None and (not mapping or mapping[-1] != "K"):
        raise ThinCapError("--cap-height-mm requires the final/top layer-map tier to be K")
    return cap


# ---- _tier_physical_heights ----
def _tier_physical_heights(rt, cap_height_mm: float):
    n = len(rt.LAYER_MAP)
    common = float(rt.PHYSICAL_LAYER_HEIGHT_MM)
    cap = float(cap_height_mm) * float(rt.PHYSICAL_HEIGHT_SCALE)
    return tuple([common] * max(0, n - 1) + [cap])


# ---- _tier_top_zs ----
def _tier_top_zs(rt, cap_height_mm: float):
    z = float(rt.BASE_TOP_Z_MM)
    out = []
    for h in _tier_physical_heights(rt, cap_height_mm):
        z += h
        out.append(z)
    return tuple(out)


# ---- _audit_actual_cap_block ----
def _audit_actual_cap_block(block: str, rt, cap_height_mm: float) -> dict:
    expected = tuple(float(z) for z in rt.TIER_TOP_Z_MM)
    cap_tier = len(rt.LAYER_MAP)
    expected_e = float(rt.A_MAIN_E_PER_MM) * float(cap_height_mm) / float(rt.LAYER_HEIGHT_MM)
    active = None
    pos = None
    ratios = []
    seen = {i: 0 for i in range(1, cap_tier + 1)}
    for line in block.splitlines():
        if "SUPPORT_ROAD_START" in line:
            mt=re.search(r"\btier=(\d+)",line); mz=re.search(r"\bz=([-+0-9.]+)",line)
            if not (mt and mz): raise RuntimeError(f"{SCRIPT_VERSION}: support marker lacks tier/Z")
            active=int(mt.group(1)); seen[active]+=1; pos=None
            if abs(float(mz.group(1))-expected[active-1])>5.1e-4:
                raise RuntimeError(f"{SCRIPT_VERSION}: tier {active} road marker Z mismatch")
            continue
        if active is None: continue
        if "SUPPORT_ROAD_END" in line:
            active=None; pos=None; continue
        if not re.match(r"G[01] ",line): continue
        vals={k:float(v) for k,v in re.findall(r"\b([XYZE])([-+0-9.]+)",line.split(';')[0])}
        if "SUPPORT_MOVE" in line:
            if "X" in vals and "Y" in vals: pos=(vals["X"],vals["Y"])
            continue
        if "SUPPORT_HEIGHT" in line:
            mz=re.search(r"\bZ([-+0-9.]+)",line)
            if not mz or abs(float(mz.group(1))-expected[active-1])>5.1e-4:
                raise RuntimeError(f"{SCRIPT_VERSION}: tier {active} descent Z mismatch")
            continue
        if "SUPPORT_SEG" in line or "SUPPORT_DRY_TAIL" in line:
            mz=re.search(r"\bZ([-+0-9.]+)",line)
            if not mz or abs(float(mz.group(1))-expected[active-1])>5.1e-4:
                raise RuntimeError(f"{SCRIPT_VERSION}: tier {active} executable segment Z mismatch")
            if "X" in vals and "Y" in vals:
                new=(vals["X"],vals["Y"])
                if active==cap_tier and "SUPPORT_SEG" in line and pos is not None and "E" in vals:
                    ds=math.hypot(new[0]-pos[0],new[1]-pos[1])
                    if ds>1e-9: ratios.append(vals["E"]/ds)
                pos=new
    if any(v==0 for v in seen.values()): raise RuntimeError(f"{SCRIPT_VERSION}: missing tier in executable audit {seen}")
    if not ratios: raise RuntimeError(f"{SCRIPT_VERSION}: no cap extrusion segments in executable audit")
    mean=sum(ratios)/len(ratios)
    if abs(mean-expected_e)>8e-5: raise RuntimeError(f"{SCRIPT_VERSION}: cap E/mm {mean:.8f} != {expected_e:.8f}")
    return {"status":"PASS","tier_top_z_mm":list(expected),"cap_draw_e_per_mm":mean,
            "cap_segment_count":len(ratios),"tier_road_counts":seen}


# ---- _horizontal_normal_intersection ----
def _horizontal_normal_intersection(point, curve):
    b = mirror_frame_global(*point)['b_unit']
    hits = []
    for a, c in zip(curve, curve[1:]):
        dx, dy = c[0] - a[0], c[1] - a[1]
        den = b[0] * dy - b[1] * dx
        if abs(den) < 1e-12:
            continue
        px, py = a[0] - point[0], a[1] - point[1]
        t = (px * dy - py * dx) / den
        u = (px * b[1] - py * b[0]) / den
        if -1e-9 <= u <= 1 + 1e-9 and t >= -1e-8:
            hits.append((t, (point[0] + t * b[0], point[1] + t * b[1])))
    if not hits:
        raise RuntimeError('horizontal adjacent row has no normal intersection')
    return min(hits, key=lambda h: h[0])[1]


# ---- _text_intervals ----
def _text_intervals(piece, text, y_local_mm, y0_mm):
    """The existing fitted 5x7 glyphs; rear texture still omits alternating roads."""
    widths = [len(LABEL_GLYPHS[c][0]) for c in text]
    cols = sum(widths) + max(0, len(text) - 1)
    pixel = min(1.8, (piece.width_mm - 6) / max(1, cols))
    row = int(math.floor((float(y_local_mm) - y0_mm) / pixel))
    if not 0 <= row < 7:
        return []
    cursor = (piece.width_mm - cols * pixel) / 2
    out = []
    for c in text:
        out.extend((cursor + j * pixel, cursor + (j+1) * pixel)
                   for j, v in enumerate(LABEL_GLYPHS[c][row]) if v == '1')
        cursor += (len(LABEL_GLYPHS[c][0]) + 1) * pixel
    return _merge_intervals(out)


# ---- _arrow_intervals ----
def _arrow_intervals(piece, y_local_mm):
    """Reverse v1.138's half-size arrow; retain the shared legend rotation."""
    y = ARROW_SHAFT_Y0_MM + ARROW_HEAD_Y1_MM - float(y_local_mm)
    cx = piece.width_mm / 2.0
    out = []
    if ARROW_SHAFT_Y0_MM <= y <= ARROW_SHAFT_Y1_MM:
        out.append((cx - ARROW_SHAFT_HALF_W_MM, cx + ARROW_SHAFT_HALF_W_MM))
    if ARROW_HEAD_Y0_MM <= y <= ARROW_HEAD_Y1_MM:
        frac = max(0.0, min(1.0, (ARROW_HEAD_Y1_MM - y) /
                                (ARROW_HEAD_Y1_MM - ARROW_HEAD_Y0_MM)))
        half = ARROW_HEAD_HALF_W_BASE_MM * frac
        if half > 1e-9:
            out.append((cx - half, cx + half))
    return _merge_intervals(out)


# ---- _native_start ----
def _native_start() -> str:
    """Resolved single-black-PETG A1 Mini startup derived from Orca's
    current Bambu Lab A1 mini 0.4 nozzle machine_start_gcode (2025-08-22).

    The stock placeholders are resolved for this job: initial tool/AMS slot 0,
    70 C Textured PEI bed, 255 C PETG nozzle and 8 mm3/s conservative flush
    volumetric speed.  Optional firmware-controlled dynamic-flow calibration is
    left to the printer; the stock always-run front extrusion calibration line
    is retained.  No FC3D model-pressure retract is added here.
    """
    flush_feed = 8.0 / 2.4053 * 60.0
    # Equivalent of Orca outer_wall_volumetric_speed=8 mm3/s for the stock
    # front calibration geometry; these are only startup purge/calibration moves.
    cali_slow = 8.0 / (0.3 * 0.5) / 4.0 * 60.0
    cali_fast = 8.0 / (0.3 * 0.5) * 60.0
    cali_bulk = 8.0 / (24.0 / 20.0) * 60.0
    lines = [
        "; FC3D_V1159_A1MINI_START",
        "; native basis: Orca Bambu Lab A1 mini 0.4 nozzle / 20250822",
        "; resolved job: AMS tool 0 / Generic PETG black / bed 70C / nozzle 255C",
        ";===== start to heat heatbed&hotend ==========",
        "M1002 gcode_claim_action : 2",
        "M1002 set_filament_type:PETG",
        "M104 S170",
        "M140 S70",
        "G392 S0",
        "M9833.2",
        "M17",
        "G90",
        "M83",
        "M220 S100",
        "M221 S100",
        "M73.2 R1.0",
        "M982.2 S1",
        ";===== prepare print temperature and material ==========",
        "M400",
        "M18",
        "M109 S100 H170",
        "M104 S170",
        "M400",
        "M17",
        "M400",
        "G28 X",
        "M211 X0 Y0 Z0",
        "M975 S1",
        "G1 X0.0 F30000",
        "G1 X-13.5 F3000",
        "M620 M ; enable AMS remap",
        "M620 S0A ; switch/load black PETG from AMS tool 0",
        "G392 S0",
        "M1002 gcode_claim_action : 4",
        "M400",
        "M1002 set_filament_type:UNKNOWN",
        "M109 S255",
        "M104 S250",
        "M400",
        "T0",
        "G1 X-13.5 F3000",
        "M400",
        f"M620.1 E F{flush_feed:.3f} T255",
        "M109 S250",
        "M106 P1 S0",
        "G92 E0",
        "G1 E50 F200",
        "M400",
        "M1002 set_filament_type:PETG",
        "M104 S255",
        "G92 E0",
        f"G1 E50 F{flush_feed:.3f}",
        "M400",
        "M106 P1 S178",
        "G92 E0",
        f"G1 E5 F{flush_feed:.3f}",
        "M109 S235 ; native -20C shrink step",
        "M104 S215 ; native -40C wipe target",
        "G92 E0",
        "G1 E-0.5 F300",
        "G1 X0 F30000",
        "G1 X-13.5 F3000",
        "G1 X0 F30000",
        "G1 X-13.5 F3000",
        "G1 X0 F12000",
        "G1 X0 F30000",
        "G1 X-13.5 F3000",
        "M109 S215",
        "G392 S0",
        "M621 S0A ; finish AMS load lifecycle",
        "M400",
        "M106 P1 S0",
        ";===== prepare print temperature and material end =====",
        ";===== A1 Mini home / nozzle wipe =======================",
        "M1002 gcode_claim_action : 3",
        "G0 X25 Y175 F20000",
        "G28 Z P0 T300",
        "G29.2 S0",
        "M104 S170",
        "G1 Z5 F3000",
        "G1 F30000",
        "G1 X-1 Y10",
        "G28 X",
        "M1002 gcode_claim_action : 14",
        "M975 S1",
        "M104 S170",
        "M106 S255",
        "M211 S",
        "M211 X0 Y0 Z0",
        "M83",
        "G1 E-1 F500",
        "G90",
        "M83",
        "M109 S170",
        "M104 S140",
        "G0 X90 Y-4 F30000",
    ]
    # Preserve the stock A1 repeated steel/nozzle contact cleaning sweep.
    for x in list(range(90, 100)) + [99, 99, 99, 99]:
        lines += ["G380 S3 Z-5 F1200", "G1 Z2 F1200", f"G1 X{x} F10000"]
    lines += [
        "G1 Z5 F30000",
        "G1 X25 Y175 F30000.1",
        "G1 Z0.2 F30000.1",
        "G1 Y185",
        "G91",
        "G1 X-30 F30000",
        "G1 Y-2",
        "G1 X27",
        "G1 Y1.5",
        "G1 X-28",
        "G1 Y-2",
        "G1 X30",
        "G1 Y1.5",
        "G1 X-30",
        "G90",
        "M83",
        "G1 Z5 F3000",
        "M211 R",
        "M106 S0",
        ";===== wait heatbed / probe at 140C ====================",
        "M1002 gcode_claim_action : 2",
        "M104 S0",
        "M190 S70",
        "M109 S140",
        "G1 Z5 F3000",
        "G29.2 S1",
        "G1 X10 Y10 F20000",
        ";===== bed leveling ==================================",
        "M1002 gcode_claim_action : 1",
        "G29 A1 X20 Y20 I140 J140",
        "M400",
        "M500",
        ";===== bed leveling end ==============================",
        "M975 S1",
        ";===== nozzle load line ==============================",
        "M975 S1",
        "G90",
        "M83",
        "T1000",
        "G1 X-13.5 Y0 Z10 F10000",
        "G1 E1.2 F500",
        "M400",
        "M1002 set_filament_type:UNKNOWN",
        "M109 S255",
        "M400",
        "M412 S1",
        "M400 P10",
        "G392 S0",
        "M620.3 W1",
        "M400 S2",
        "M1002 set_filament_type:PETG",
        ";===== extrude cali test =============================",
        "M104 S255",
        "G90",
        "M83",
        "G0 X68 Y-2.5 F30000",
        "G0 Z0.3 F18000",
        f"G0 X88 E10 F{cali_bulk:.3f}",
        f"G0 X93 E0.3742 F{cali_slow:.3f}",
        f"G0 X98 E0.3742 F{cali_fast:.3f}",
        f"G0 X103 E0.3742 F{cali_slow:.3f}",
        f"G0 X108 E0.3742 F{cali_fast:.3f}",
        f"G0 X113 E0.3742 F{cali_slow:.3f}",
        "G0 X115 Z0 F20000",
        "G0 Z5",
        "M400",
        "M1002 gcode_claim_action : 0",
        "; Textured PEI native Z trim",
        "G29.1 Z-0.02",
        "M960 S1 P0",
        "M960 S2 P0",
        "M106 S0",
        "M106 P2 S0",
        "M106 P3 S0",
        "M975 S1",
        "G90",
        "M83",
        "T1000",
        "M211 X0 Y0 Z0",
        "M1007 S1",
        "; final model temperature is explicit and blocking",
        "M104 S255",
        "M109 S255",
        "; FC3D_V1159_A1MINI_START_END state=PRESSURE_NEUTRAL",
    ]
    return "\n".join(lines)


# ---- _native_end ----
def _native_end(max_layer_z: float, first_layer_center_y: float) -> str:
    max_layer_z = float(max_layer_z)
    first_layer_center_y = float(first_layer_center_y)
    z_hi = min(180.0, max_layer_z + 100.0)
    z_settle = min(180.0, max_layer_z + 98.0)
    lines = [
        "; FC3D_V1159_A1MINI_NATIVE_END_BEGIN source=Orca_A1mini_0.4_20231229",
        ";===== date: 20231229 =====================",
        ";turn off nozzle clog detect",
        "G392 S0",
        "M400 ; wait for buffer to clear",
        "G92 E0 ; zero the extruder",
        "G1 E-0.8 F1800 ; retract",
        f"G1 Z{max_layer_z + 0.5:.3f} F900 ; clear printed wave",
        f"G1 X0 Y{first_layer_center_y:.3f} F18000 ; move to safe pos",
        "G1 X-13.0 F3000 ; move to safe pos",
        "M1002 judge_flag timelapse_record_flag",
        "M622 J1",
    ]
    # Exact current native timelapse sweep count from the A1 Mini profile.
    for _ in range(30):
        lines.extend(("M400 P100", "M971 S11 C11 O0"))
    lines.extend([
        "M991 S0 P-1 ; end timelapse at safe pos",
        "M623",
        "M140 S0 ; turn off bed",
        "M106 S0 ; turn off fan",
        "M106 P2 S0 ; turn off remote part cooling fan",
        "M106 P3 S0 ; turn off chamber cooling fan",
        "; pull back filament to AMS",
        "M620 S255",
        "G1 X181 F12000",
        "T255",
        "G1 X0 F18000",
        "G1 X-13.0 F3000",
        "G1 X0 F18000 ; wipe",
        "M621 S255",
        "M104 S0 ; turn off hotend",
        "M400 ; wait all motion done",
        "M17 S",
        "M17 Z0.4 ; lower z motor current to reduce impact",
        f"G1 Z{z_hi:.3f} F600",
        f"G1 Z{z_settle:.3f}",
        "M400 P100",
        "M17 R ; restore z current",
        "G90",
        "G1 X-13 Y180 F3600",
        "G91",
        "G1 Z-1 F600",
        "G90",
        "M83",
        "M220 S100  ; Reset feedrate magnitude",
        "M201.2 K1.0 ; Reset acc magnitude",
        "M73.2 R1.0 ; Reset left time magnitude",
        "M1002 set_gcode_claim_speed_level : 0",
        ";=====printer finish sound=========",
        "M17",
        "M400 S1",
        "M1006 S1",
        "M1006 A0 B20 L100 C37 D20 M100 E42 F20 N100",
        "M1006 A0 B10 L100 C44 D10 M100 E44 F10 N100",
        "M1006 A0 B10 L100 C46 D10 M100 E46 F10 N100",
        "M1006 A44 B20 L100 C39 D20 M100 E48 F20 N100",
        "M1006 A0 B10 L100 C44 D10 M100 E44 F10 N100",
        "M1006 A0 B10 L100 C0 D10 M100 E0 F10 N100",
        "M1006 A0 B10 L100 C39 D10 M100 E39 F10 N100",
        "M1006 A0 B10 L100 C0 D10 M100 E0 F10 N100",
        "M1006 A0 B10 L100 C44 D10 M100 E44 F10 N100",
        "M1006 A0 B10 L100 C0 D10 M100 E0 F10 N100",
        "M1006 A0 B10 L100 C39 D10 M100 E39 F10 N100",
        "M1006 A0 B10 L100 C0 D10 M100 E0 F10 N100",
        "M1006 A44 B10 L100 C0 D10 M100 E48 F10 N100",
        "M1006 A0 B10 L100 C0 D10 M100 E0 F10 N100",
        "M1006 A44 B20 L100 C41 D20 M100 E49 F20 N100",
        "M1006 A0 B20 L100 C0 D20 M100 E0 F20 N100",
        "M1006 A0 B20 L100 C37 D20 M100 E37 F20 N100",
        "M1006 W",
        ";=====printer finish sound=========",
        "M400 S1",
        "M18 X Y Z",
        "; FC3D_V1159_A1MINI_NATIVE_END_DONE",
    ])
    return "\n".join(lines)


# ---- _patch_emitter_source ----
def _patch_emitter_source(source_text: str) -> str:
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
                raise RuntimeError("FC3D_V1159_BASE_MULTI_MATERIAL base has no present material")
            carryover_hit = False
            tower_slot_count = len(material_order)
            tower_slot_order = list(material_order)
            filler_slots = 0
            g.append("; FC3D_V1159_BASE_MULTI_MATERIAL present=" + ",".join(present_materials) + " order=" + ",".join(material_order))
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
                    g.append(f"; FC3D_V1159_TOWER_DROPPED_AFTER_LABEL physical={physical} material={mat}")
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
            raise RuntimeError(f"v1.159 fail closed: expected exactly one canonical v1.179 {label} patch target, found {count}")
        source_text = source_text.replace(old, new, 1)
    return source_text


# ---- _canonical_hotend_for_material ----
def _canonical_hotend_for_material(material, raw_tool, w_hotend_index):
    # H2C compatibility path: logical W is mapped to the physical BLACK spool
    # in the colour/right head. v1.159 itself is single-material.
    if str(material) == LOGICAL_MATERIAL:
        return 0
    return 1 - int(w_hotend_index)


# ---- _make_job_material_tower_audit ----
def _make_job_material_tower_audit(original_audit):
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
            if "FC3D_V1159_TOWER_DROPPED_AFTER_LABEL" in line:
                dropped[current] = True
            if line.strip().startswith("; FC3D_TOWER_SLOT "):
                mm = re.search(r"canonical_slot=([WFRYGCB])\s+slot=(\d+)/(\d+)\s+role=([^\s]+)", line)
                if mm:
                    actual_slots[current].append((mm.group(1), int(mm.group(2)), int(mm.group(3)), mm.group(4)))
        if [x[0] for x in actual_slots.get(0, [])] != [LOGICAL_MATERIAL]:
            raise RuntimeError(f"v1.159 dynamic tower audit: base slots {actual_slots.get(0)} != W only")
        if [x[0] for x in actual_slots.get(1, [])] != [LOGICAL_MATERIAL]:
            raise RuntimeError(f"v1.159 dynamic tower audit: second-layer slots {actual_slots.get(1)} != W only")
        for li in range(2, PHYSICAL_LAYER_COUNT):
            if actual_slots.get(li):
                raise RuntimeError(f"v1.159 dynamic tower audit: tower slots remain on layer {li}: {actual_slots[li]}")
            if not dropped.get(li):
                raise RuntimeError(f"v1.159 dynamic tower audit: missing tower-drop marker on layer {li}")
        if not tower_present.get(0) or not tower_present.get(1) or any(tower_present.get(li) for li in range(2, PHYSICAL_LAYER_COUNT)):
            raise RuntimeError(f"v1.159 dynamic tower audit: tower presence is {tower_present}")

        # Preserve v1.179's excluded-material/lifecycle audit by giving only its
        # fixed-topology tower checker a synthetic canonical view. Actual tower
        # topology has already been checked above against the v1.159 contract.
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
        report["v159_dynamic_tower"] = {
            "actual_slots": {str(k): v for k, v in actual_slots.items()},
            "tower_present": {str(k): bool(v) for k, v in tower_present.items()},
            "dropped": {str(k): bool(v) for k, v in dropped.items()},
        }
        return report
    return audit


if __name__ == '__main__':
    try:
        main()
    except ThinCapError as exc:
        raise SystemExit(f'{SCRIPT_VERSION}: {exc}')
