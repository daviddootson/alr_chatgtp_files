#!/usr/bin/env python3
"""FC3D v1.107 corrected ALR wave topology.

v1.106 is retained unchanged as the diagnostic predecessor.  This wrapper
SHA-gates that exact source, advances its revision labels in memory, and replaces
the Layer-4 wave topology with long, continuous local-u roads.  Each road runs
through repeated XYZ wave cells while neighbouring roads converge as they head
inward.  A set ends only after a complete wave cell reaches the nominal zero-gap
spacing; the next set then restarts with fewer roads near 0.60-mm centres.

Orca is the authoritative preview path for this moving-Z experiment.  Wave height
is emitted as real coordinated G1 X/Y/Z motion, not G29.1 stair steps.
"""

from __future__ import annotations

import hashlib
import math
import re
import sys
import types
import zipfile
from pathlib import Path

SCRIPT_VERSION = "3dprint_black_mirror_wave_grid_v1.107"
REAR_VERSION_TEXT = "107"
BASE_SCRIPT_VERSION = "3dprint_black_mirror_wave_grid_v1.106"
EXPECTED_V106_SHA256 = "a7e14bf818033aff390f69fd0e27368a8917a8a60dbb9c29c5d1a5c308814e80"

WAVESET_BUILD_ORDER = "outer_to_inner"
WAVESET_TOTAL_PEAK_MM = 0.300
WAVESET_HIDDEN_RISE_MM = 0.050
WAVESET_OPTICAL_RISE_MM = 0.250
WAVESET_BASE_LEAD_MM = 0.100
WAVESET_HIDDEN_RUN_MM = 0.400
WAVESET_RETURN_ANGLE_DEG = 45.0
WAVESET_RETURN_RUN_MM = WAVESET_TOTAL_PEAK_MM / math.tan(math.radians(WAVESET_RETURN_ANGLE_DEG))
WAVESET_PRINT_FEED_MM_S = 50.0
WAVESET_RESET_CENTER_SPACING_MM = 0.600
WAVESET_MIN_CENTER_SPACING_MM = 0.400
WAVESET_PITCH_TOL_MM = 0.002
WAVESET_DIRECTION_TOL_DEG = 5.0
WAVESET_MAX_STEP_MM = 0.050
WAVESET_PROFILE_MODEL = "continuous_long_u_profile_direct_xyz_exact_front_hidden_top"

_RUNTIME = None
_U_PROFILE_CACHE = {}


def _base_wrapper_path() -> Path:
    here = Path(__file__).resolve()
    if "v1.107" not in here.name:
        raise RuntimeError(f"{SCRIPT_VERSION}: filename must contain v1.107: {here.name}")
    base = here.with_name(here.name.replace("v1.107", "v1.106", 1))
    if not base.exists():
        raise FileNotFoundError(f"{SCRIPT_VERSION}: required predecessor not found beside wrapper: {base.name}")
    return base


def _transform_predecessor_source(source: str) -> str:
    # Revision first.  This keeps every inherited diagnostic/startup/audit marker
    # internally consistent while v1.106 itself remains byte-for-byte untouched.
    for old, new in (
        ("v1.106", "v1.107"),
        ("V1106", "V1107"),
        ("v1106", "v1107"),
        ("v106", "v107"),
    ):
        source = source.replace(old, new)

    source = source.replace(
        "black_a_only_wave_sets_true_normal_valleyfill25_",
        "black_a_only_u_profile_wave_sets_valleyfill25_",
    )
    source = source.replace(
        '"role":"A_only_true_normal_wave_sets"',
        '"role":"A_only_u_profile_wave_sets"',
    )
    source = source.replace(
        '"path_count":len(lat["main_a_local"]),',
        '"path_count":get_true_normal_wave_sets(piece)["long_road_count"],',
        1,
    )
    source = source.replace(
        'counts["main_segments"]=sum("FC3D_V1107_A_ROAD_SEG" in r for r in layer_rows)',
        'counts["main_segments"]=sum("FC3D_V1107_U_PROFILE_SEG" in r for r in layer_rows)',
        1,
    )
    source = source.replace('"true_normal_wave_sets":True', '"u_profile_wave_sets":True')
    return source


def _registered_exec(source: str):
    name = "__fc3d_alr_v1107_runtime__"
    mod = types.ModuleType(name)
    mod.__file__ = str(Path(__file__).resolve())
    mod.__package__ = None
    sys.modules[name] = mod
    try:
        exec(compile(source, str(Path(__file__).resolve()), "exec"), mod.__dict__)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return mod


def _load_runtime():
    base = _base_wrapper_path()
    data = base.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != EXPECTED_V106_SHA256:
        raise RuntimeError(
            f"{SCRIPT_VERSION}: predecessor SHA-256 changed: {actual}; expected {EXPECTED_V106_SHA256}"
        )
    source = data.decode("utf-8")
    if 'SCRIPT_VERSION = "3dprint_black_mirror_wave_grid_v1.106"' not in source:
        raise RuntimeError(f"{SCRIPT_VERSION}: predecessor version literal missing")
    transformed = _transform_predecessor_source(source)
    runtime = _registered_exec(transformed)
    if runtime.__dict__.get("SCRIPT_VERSION") != SCRIPT_VERSION:
        raise RuntimeError(
            f"{SCRIPT_VERSION}: transformed runtime version is {runtime.__dict__.get('SCRIPT_VERSION')!r}"
        )
    runtime.REAR_VERSION_TEXT = REAR_VERSION_TEXT
    return runtime


def _rt():
    if _RUNTIME is None:
        raise RuntimeError(f"{SCRIPT_VERSION}: runtime not installed")
    return _RUNTIME


def _polyline_length2(points):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]))


def _spacing(points):
    vals = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:])]
    if not vals:
        return None
    return {"min": min(vals), "mean": sum(vals) / len(vals), "max": max(vals), "samples": len(vals)}


def _sample_polyline_intervals(points, intervals: int):
    pts = [(float(x), float(z)) for x, z in points]
    n = int(intervals)
    if len(pts) < 2 or n < 1:
        return []
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    total = cum[-1]
    if total <= 1e-12:
        return []
    out = []
    j = 0
    for k in range(n + 1):
        target = total * k / n
        while j + 1 < len(cum) and cum[j + 1] < target - 1e-12:
            j += 1
        if j + 1 >= len(cum):
            out.append(pts[-1])
            continue
        den = max(cum[j + 1] - cum[j], 1e-12)
        t = (target - cum[j]) / den
        out.append((
            pts[j][0] + t * (pts[j + 1][0] - pts[j][0]),
            pts[j][1] + t * (pts[j + 1][1] - pts[j][1]),
        ))
    return out


def _sample_set_start(curve, piece, max_roads=None):
    rt = _rt()
    clipped = rt._waveset_clip_curve(curve, piece)
    if len(clipped) < 2:
        return [], None
    total = _polyline_length2(clipped)
    if total < WAVESET_RESET_CENTER_SPACING_MM - WAVESET_PITCH_TOL_MM:
        return [], None
    intervals = max(1, int(math.floor(total / WAVESET_RESET_CENTER_SPACING_MM)))
    if max_roads is not None:
        intervals = min(intervals, max(1, int(max_roads) - 1))
    while intervals >= 1:
        pts = _sample_polyline_intervals(clipped, intervals)
        sp = _spacing(pts)
        if sp and sp["min"] >= WAVESET_RESET_CENTER_SPACING_MM - WAVESET_PITCH_TOL_MM:
            return pts, sp
        intervals -= 1
    return [], None


def _advance_inward_xy_path(x_mm, z_mm, distance_mm, max_step_mm=WAVESET_MAX_STEP_MM):
    rt = _rt()
    x = float(x_mm)
    z = float(z_mm)
    rem = max(0.0, float(distance_mm))
    out = [(x, z)]
    while rem > 1e-12:
        ds = min(float(max_step_mm), rem)
        f0 = rt.mirror_frame_global(x, z)
        d0 = f0["b_unit"]
        mx = x + 0.5 * d0[0] * ds
        mz = z + 0.5 * d0[1] * ds
        fm = rt.mirror_frame_global(mx, mz)
        d = fm["b_unit"]
        x += d[0] * ds
        z += d[1] * ds
        rem -= ds
        out.append((x, z))
    return out


def _segments_from_xy_path(points, h0, h1, role, cell_index):
    if len(points) < 2:
        return []
    lengths = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:])]
    total = sum(lengths)
    acc = 0.0
    out = []
    for i, (a, b, ds) in enumerate(zip(points, points[1:], lengths)):
        fa = 0.0 if total <= 1e-12 else acc / total
        acc += ds
        fb = 1.0 if total <= 1e-12 else acc / total
        p0 = (a[0], a[1], float(h0) + (float(h1) - float(h0)) * fa)
        p1 = (b[0], b[1], float(h0) + (float(h1) - float(h0)) * fb)
        out.append({"p0": p0, "p1": p1, "role": role, "cell_index": int(cell_index), "seg_index": i})
    return out


def _build_u_wave_cell(start_xy, cell_index):
    rt = _rt()
    sx, sz = map(float, start_xy)

    lead_xy = _advance_inward_xy_path(sx, sz, WAVESET_BASE_LEAD_MM)
    lead = _segments_from_xy_path(lead_xy, 0.0, 0.0, "LEAD", cell_index)
    foot = lead_xy[-1]

    front_rec = rt.integrate_b_front_global(
        foot[0], foot[1], WAVESET_OPTICAL_RISE_MM, WAVESET_MAX_STEP_MM
    )
    front_pts = [(float(x), float(z), float(h)) for x, z, h in front_rec["points"]]
    front = [
        {"p0": a, "p1": b, "role": "OPTICAL_FRONT", "cell_index": int(cell_index), "seg_index": i}
        for i, (a, b) in enumerate(zip(front_pts, front_pts[1:]))
    ]
    crest = front_pts[-1]

    hidden_xy = _advance_inward_xy_path(crest[0], crest[1], WAVESET_HIDDEN_RUN_MM)
    hidden = _segments_from_xy_path(
        hidden_xy, WAVESET_OPTICAL_RISE_MM, WAVESET_TOTAL_PEAK_MM,
        "HIDDEN_TOP", cell_index,
    )
    hidden_end = hidden[-1]["p1"] if hidden else crest

    return_xy = _advance_inward_xy_path(hidden_end[0], hidden_end[1], WAVESET_RETURN_RUN_MM)
    ret = _segments_from_xy_path(
        return_xy, WAVESET_TOTAL_PEAK_MM, 0.0, "RETURN", cell_index
    )
    end = ret[-1]["p1"] if ret else hidden_end

    return {
        "segments": lead + front + hidden + ret,
        "foot": (foot[0], foot[1], 0.0),
        "crest": crest,
        "hidden_end": hidden_end,
        "end": end,
        "front_normal_error": float(front_rec["max_normal_error"]),
    }


def _curve_still_intersects_piece(points, piece):
    rt = _rt()
    try:
        return bool(rt._waveset_clip_curve(points, piece))
    except RuntimeError:
        return True


def generate_u_profile_wave_sets(piece):
    """Generate continuous local-u roads with transverse convergence/reset sets.

    A set owns a fixed collection of long roads sampled around one outer valley
    contour.  Each road proceeds inward through repeated complete wave cells.
    The same road count is retained until the adjacent-road spacing at a completed
    valley reaches ~0.40 mm.  The next set resamples that complete valley contour
    with fewer roads to restore ~0.60-mm starting centres.
    """
    key = (
        piece.name, WAVESET_TOTAL_PEAK_MM, WAVESET_HIDDEN_RISE_MM,
        WAVESET_BASE_LEAD_MM, WAVESET_HIDDEN_RUN_MM,
        WAVESET_RETURN_ANGLE_DEG, WAVESET_RESET_CENTER_SPACING_MM,
        WAVESET_MIN_CENTER_SPACING_MM,
    )
    if key in _U_PROFILE_CACHE:
        return _U_PROFILE_CACHE[key]

    rt = _rt()
    outer = rt._waveset_outer_reference_curve(piece)
    start_points, start_spacing = _sample_set_start(outer, piece)
    if len(start_points) < 2:
        raise RuntimeError(f"{piece.name}: v1.107 could not establish an outer 0.60-mm wave set")

    sets = []
    all_cells = []
    all_long_roads = []
    compat_roads = []
    set_index = 1
    global_cell = 0
    total_cell_guard = 0
    previous_set_road_count = None

    while len(start_points) >= 2:
        total_cell_guard += 1
        if total_cell_guard > 100:
            raise RuntimeError(f"{piece.name}: v1.107 wave-set reset guard tripped")

        if previous_set_road_count is not None and len(start_points) >= previous_set_road_count:
            raise RuntimeError(
                f"{piece.name}: v1.107 reset did not reduce road count: "
                f"{len(start_points)} >= {previous_set_road_count}"
            )

        roads = [
            {"set_index": set_index, "road_index": i + 1, "segments": [], "start_global": (p[0], p[1], 0.0)}
            for i, p in enumerate(start_points)
        ]
        current = [(float(x), float(z)) for x, z in start_points]
        set_cells = []
        end_reason = None

        for local_cell in range(1, 801):
            if not _curve_still_intersects_piece(current, piece):
                end_reason = "coupon_boundary"
                break

            global_cell += 1
            next_points = []
            crest_contour = []
            hidden_contour = []
            front_errors = []

            for j, p in enumerate(current):
                cell = _build_u_wave_cell(p, global_cell)
                roads[j]["segments"].extend(cell["segments"])
                q = cell["end"]
                next_points.append((q[0], q[1]))
                crest_contour.append((cell["crest"][0], cell["crest"][1]))
                hidden_contour.append((cell["hidden_end"][0], cell["hidden_end"][1]))
                front_errors.append(cell["front_normal_error"])

            sp = _spacing(next_points)
            if sp is None:
                end_reason = "coupon_boundary"
                break
            hidden_clear = rt._waveset_hidden_surface_clearance(crest_contour, hidden_contour, piece)
            if hidden_clear["samples"] and hidden_clear["endpoint_clearance_min_mm"] < rt.WAVESET_HIDDEN_PROJECTOR_MARGIN_MM - 1e-9:
                raise RuntimeError(f"v1.107 hidden top visible to projector: {hidden_clear}")

            cell_rec = {
                "set_index": set_index,
                "cell_index": global_cell,
                "local_cell_index": local_cell,
                "start_contour": list(current),
                "crest_contour": crest_contour,
                "hidden_contour": hidden_contour,
                "end_contour": list(next_points),
                "pitch": sp,
                "front_normal_error": max(front_errors) if front_errors else 0.0,
                "hidden_clearance": hidden_clear,
            }
            set_cells.append(cell_rec)
            all_cells.append(cell_rec)
            compat_roads.append({
                "role": "OPTICAL_CREST",
                "set_index": set_index,
                "cell_index": global_cell,
                "points_global": crest_contour,
            })
            current = next_points

            # Finish the whole wave cell first, then reset the complete set.
            if sp["min"] <= WAVESET_MIN_CENTER_SPACING_MM + WAVESET_PITCH_TOL_MM:
                end_reason = "zero_gap"
                break

            if not _curve_still_intersects_piece(current, piece):
                end_reason = "coupon_boundary"
                break
        else:
            raise RuntimeError(f"{piece.name}: v1.107 exceeded 800 cells in one set")

        if not set_cells:
            break
        if end_reason is None:
            end_reason = "coupon_boundary"

        for road in roads:
            road["end_global"] = road["segments"][-1]["p1"] if road["segments"] else road["start_global"]
            road["cell_count"] = len(set_cells)
        set_rec = {
            "set_index": set_index,
            "roads": roads,
            "cells": set_cells,
            "road_count": len(roads),
            "start_spacing": start_spacing,
            "end_spacing": set_cells[-1]["pitch"],
            "end_reason": end_reason,
        }
        sets.append(set_rec)
        all_long_roads.extend(roads)

        if end_reason != "zero_gap":
            break

        previous_set_road_count = len(roads)
        next_start, next_spacing = _sample_set_start(
            current, piece, max_roads=previous_set_road_count - 1
        )
        if len(next_start) < 2:
            break
        start_points = next_start
        start_spacing = next_spacing
        set_index += 1

    if not sets or not all_cells or not all_long_roads:
        raise RuntimeError(f"{piece.name}: v1.107 generated no u-profile wave geometry")

    pitch_values = [c["pitch"]["mean"] for c in all_cells]
    front_errors = [c["front_normal_error"] for c in all_cells]
    hidden_values = [
        c["hidden_clearance"]["endpoint_clearance_min_mm"]
        for c in all_cells if c["hidden_clearance"]["samples"]
    ]
    out = {
        "sets": sets,
        "cells": all_cells,
        "long_roads": all_long_roads,
        "roads": compat_roads,
        "set_count": len(sets),
        "cell_count": len(all_cells),
        "long_road_count": len(all_long_roads),
        "pitch_min_mm": min(pitch_values),
        "pitch_mean_mm": sum(pitch_values) / len(pitch_values),
        "pitch_max_mm": max(pitch_values),
        "front_normal_error_max": max(front_errors),
        "hidden_projector_clearance_min_mm": min(hidden_values) if hidden_values else float("inf"),
    }
    _U_PROFILE_CACHE[key] = out
    return out


def get_true_normal_wave_sets(piece):
    return generate_u_profile_wave_sets(piece)


def waveset_report(piece):
    w = generate_u_profile_wave_sets(piece)
    return {
        "build_order": WAVESET_BUILD_ORDER,
        "profile_model": WAVESET_PROFILE_MODEL,
        "set_count": w["set_count"],
        "cell_count": w["cell_count"],
        "road_count": w["long_road_count"],
        "peak_mm": WAVESET_TOTAL_PEAK_MM,
        "optical_rise_mm": WAVESET_OPTICAL_RISE_MM,
        "hidden_rise_mm": WAVESET_HIDDEN_RISE_MM,
        "print_feed_mm_s": WAVESET_PRINT_FEED_MM_S,
        "pitch_mm": {"min": w["pitch_min_mm"], "mean": w["pitch_mean_mm"], "max": w["pitch_max_mm"]},
        "front_normal_error_max": w["front_normal_error_max"],
        "hidden_projector_clearance_min_mm": w["hidden_projector_clearance_min_mm"],
        "reset_center_spacing_mm": WAVESET_RESET_CENTER_SPACING_MM,
        "minimum_center_spacing_mm": WAVESET_MIN_CENTER_SPACING_MM,
        "sets": [
            {
                "set_index": s["set_index"],
                "cell_count": len(s["cells"]),
                "road_count": s["road_count"],
                "end_reason": s["end_reason"],
                "pitch_start_mm": s["start_spacing"]["mean"],
                "pitch_start_min_mm": s["start_spacing"]["min"],
                "pitch_end_mm": s["end_spacing"]["mean"],
                "pitch_end_min_mm": s["end_spacing"]["min"],
                "clear_gap_start_min_mm": s["start_spacing"]["min"] - _rt().ROAD_WIDTH_MM,
                "clear_gap_end_min_mm": s["end_spacing"]["min"] - _rt().ROAD_WIDTH_MM,
            }
            for s in w["sets"]
        ],
    }


def audit_u_profile_orientation(piece=None):
    rt = _rt()
    if piece is None:
        piece = rt._current_piece()
    geo = generate_u_profile_wave_sets(piece)
    threshold = math.cos(math.radians(WAVESET_DIRECTION_TOL_DEG))
    tangent_limit = math.sin(math.radians(WAVESET_DIRECTION_TOL_DEG))
    role_counts = {"LEAD": 0, "OPTICAL_FRONT": 0, "HIDDEN_TOP": 0, "RETURN": 0}
    role_length = {k: 0.0 for k in role_counts}
    worst_abs_angle = 0.0
    worst_tangent = 0.0
    total_length = 0.0

    for road in geo["long_roads"]:
        for seg in road["segments"]:
            a = seg["p0"]
            b = seg["p1"]
            dx = b[0] - a[0]
            dz = b[1] - a[1]
            dh = b[2] - a[2]
            xy = math.hypot(dx, dz)
            if xy <= 1e-12:
                raise RuntimeError(f"v1.107 zero-XY wave segment: {seg}")
            mx = 0.5 * (a[0] + b[0])
            mz = 0.5 * (a[1] + b[1])
            frame = rt.mirror_frame_global(mx, mz)
            ux, uz = frame["b_unit"]
            ax, az = frame["a_unit"]
            vx, vz = dx / xy, dz / xy
            dot_u = vx * ux + vz * uz
            dot_a = vx * ax + vz * az
            role = seg["role"]
            if role == "OPTICAL_FRONT":
                if dot_u > -threshold or dh <= 1e-10:
                    raise RuntimeError(
                        f"v1.107 optical front is not local -u,+Z: dot_u={dot_u:.8f} dZ={dh:.8f} seg={seg}"
                    )
            elif role == "LEAD":
                if dot_u < threshold or abs(dh) > 1e-10:
                    raise RuntimeError(f"v1.107 lead is not local +u,flat: dot_u={dot_u:.8f} dZ={dh:.8f}")
            elif role == "HIDDEN_TOP":
                if dot_u < threshold or dh <= 1e-10:
                    raise RuntimeError(f"v1.107 hidden top is not local +u,+Z: dot_u={dot_u:.8f} dZ={dh:.8f}")
            elif role == "RETURN":
                if dot_u < threshold or dh >= -1e-10:
                    raise RuntimeError(f"v1.107 return is not local +u,-Z: dot_u={dot_u:.8f} dZ={dh:.8f}")
            else:
                raise RuntimeError(f"v1.107 unknown wave role {role!r}")
            if abs(dot_a) > tangent_limit + 1e-9:
                raise RuntimeError(f"v1.107 wave segment is tangentially dominated: role={role} dot_a={dot_a:.8f}")
            l3 = math.sqrt(dx * dx + dz * dz + dh * dh)
            role_counts[role] += 1
            role_length[role] += l3
            total_length += l3
            angle = math.degrees(math.acos(max(-1.0, min(1.0, abs(dot_u)))))
            worst_abs_angle = max(worst_abs_angle, angle)
            worst_tangent = max(worst_tangent, abs(dot_a))

    if not all(role_counts.values()):
        raise RuntimeError(f"v1.107 missing wave roles: {role_counts}")
    return {
        "result": "PASS",
        "direction_tolerance_deg": WAVESET_DIRECTION_TOL_DEG,
        "role_segment_counts": role_counts,
        "role_length_mm": role_length,
        "total_wave_length_mm": total_length,
        "max_angle_to_local_u_axis_deg": worst_abs_angle,
        "max_abs_tangent_dot": worst_tangent,
        "front_normal_error_max": geo["front_normal_error_max"],
    }


def _clip_long_road_paths(road, piece):
    rt = _rt()
    inset = rt.ROAD_WIDTH_MM / 2.0
    xmin, xmax = piece.global_x0_mm + inset, piece.global_x1_mm - inset
    zmin, zmax = piece.global_z0_mm + inset, piece.global_z1_mm - inset
    paths = []
    cur = []
    for seg in road["segments"]:
        cl = rt._clip_segment_rect3(seg["p0"], seg["p1"], xmin, xmax, zmin, zmax)
        if cl is None:
            if cur:
                paths.append(cur)
                cur = []
            continue
        p0, p1 = cl
        rec = dict(seg)
        rec["p0"] = p0
        rec["p1"] = p1
        if cur and math.dist(cur[-1]["p1"], p0) > 1e-6:
            paths.append(cur)
            cur = []
        cur.append(rec)
    if cur:
        paths.append(cur)
    return [p for p in paths if p]


def _segment_l3(seg):
    a, b = seg["p0"], seg["p1"]
    return math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 + (b[2] - a[2]) ** 2)


def _split_path_for_dry_tail(path, dry_tail_mm):
    total = sum(_segment_l3(s) for s in path)
    dry = min(float(dry_tail_mm), max(0.0, total * 0.45))
    cutoff = max(0.0, total - dry)
    draw, coast = [], []
    acc = 0.0
    for seg in path:
        length = _segment_l3(seg)
        if length <= 1e-12:
            continue
        if acc + length <= cutoff + 1e-12:
            draw.append(seg)
        elif acc >= cutoff - 1e-12:
            coast.append(seg)
        else:
            use = cutoff - acc
            t = max(0.0, min(1.0, use / length))
            a, b = seg["p0"], seg["p1"]
            q = tuple(a[i] + t * (b[i] - a[i]) for i in range(3))
            if use > 1e-12:
                left = dict(seg); left["p1"] = q; draw.append(left)
            if length - use > 1e-12:
                right = dict(seg); right["p0"] = q; coast.append(right)
        acc += length
    return draw, coast, dry


def _printer_point(p, piece, x_origin, y_origin, base_z):
    return (
        round(float(x_origin) + (p[0] - piece.global_x0_mm), 4),
        round(float(y_origin) + (p[1] - piece.global_z0_mm), 4),
        round(float(base_z) + p[2], 4),
    )


def _explicit_mirror_wave_layer_gcode(piece, x_origin: float, y_origin: float):
    """Emit v1.107 long local-u wave roads using real coordinated XYZ motion."""
    rt = _rt()
    geo = generate_u_profile_wave_sets(piece)
    audit_u_profile_orientation(piece)
    xo, yo = float(x_origin), float(y_origin)
    base_z = float(rt.WAVESET_COMMAND_Z_MM)
    travel_z = max(float(rt.NOMINAL_TOP_Z_MM), base_z + WAVESET_TOTAL_PEAK_MM) + float(rt.B_TRAVEL_CLEARANCE_MM)
    rows = [
        f"; FC3D_V1107_WAVESETS_START sets={geo['set_count']} cells={geo['cell_count']} "
        f"long_roads={geo['long_road_count']} topology=continuous_local_u_direct_xyz"
    ]
    emitted_paths = 0
    emitted_segments = 0

    for s in geo["sets"]:
        rows.append(
            f"; FC3D_V1107_WAVESET_START set={s['set_index']} roads={s['road_count']} "
            f"cells={len(s['cells'])} start_min={s['start_spacing']['min']:.6f} "
            f"end_min={s['end_spacing']['min']:.6f} end_reason={s['end_reason']}"
        )
        for road in s["roads"]:
            paths = _clip_long_road_paths(road, piece)
            for path_index, path in enumerate(paths, start=1):
                draw, coast, dry_len = _split_path_for_dry_tail(path, rt.A_ENDPOINT_DRY_TAIL_MM)
                if not draw:
                    continue
                emitted_paths += 1
                start = _printer_point(draw[0]["p0"], piece, xo, yo, base_z)
                rows.append(
                    f"; FC3D_V1107_U_PROFILE_ROAD_START set={s['set_index']} road={road['road_index']} "
                    f"path={path_index} cells={road['cell_count']}"
                )
                rows.append(f"G0 Z{travel_z:.4f} F900 ; FC3D_V1107_U_PROFILE_TRAVEL_Z")
                rows.append(f"G0 X{start[0]:.4f} Y{start[1]:.4f} F18000 ; FC3D_V1107_U_PROFILE_MOVE_TO_START")
                rows.append(f"G0 Z{start[2]:.4f} F900 ; FC3D_V1107_U_PROFILE_START_Z")
                rows.append(f"G1 E{rt.A_REPRIME_MM:.3f} F1800 ; FC3D_V1107_U_PROFILE_REPRIME")

                current_cmd = start
                for seg_no, seg in enumerate(draw, start=1):
                    end = _printer_point(seg["p1"], piece, xo, yo, base_z)
                    dx, dy, dz = end[0] - current_cmd[0], end[1] - current_cmd[1], end[2] - current_cmd[2]
                    l3 = math.sqrt(dx * dx + dy * dy + dz * dz)
                    if l3 <= 1e-12:
                        current_cmd = end
                        continue
                    e = l3 * float(rt.A_MAIN_E_PER_MM)
                    if float(f"{e:.5f}") <= 0.0:
                        current_cmd = end
                        continue
                    h0 = current_cmd[2] - base_z
                    h1 = end[2] - base_z
                    rows.append(
                        f"G1 X{end[0]:.4f} Y{end[1]:.4f} Z{end[2]:.4f} E{e:.5f} F{WAVESET_PRINT_FEED_MM_S*60:.0f} "
                        f"; FC3D_V1107_U_PROFILE_SEG set={s['set_index']} road={road['road_index']} "
                        f"cell={seg['cell_index']} role={seg['role']} seg={seg_no} h0={h0:.6f} h1={h1:.6f} L3={l3:.6f}"
                    )
                    emitted_segments += 1
                    current_cmd = end

                rows.append(f"G1 E-{rt.A_RETRACT_MM:.3f} F1800 ; FC3D_V1107_U_PROFILE_RETRACT")
                for seg in coast:
                    end = _printer_point(seg["p1"], piece, xo, yo, base_z)
                    rows.append(
                        f"G1 X{end[0]:.4f} Y{end[1]:.4f} Z{end[2]:.4f} F15000 "
                        f"; FC3D_V1107_U_PROFILE_DRY_TAIL role={seg['role']} cell={seg['cell_index']}"
                    )
                    current_cmd = end
                rows.append(f"; FC3D_V1107_U_PROFILE_ROAD_END dry_tail_mm={dry_len:.6f}")
                rows.append(f"G0 Z{travel_z:.4f} F900 ; FC3D_V1107_U_PROFILE_SAFE_LIFT")
        rows.append(f"; FC3D_V1107_WAVESET_END set={s['set_index']}")

    rows.append(f"G0 Z{travel_z:.4f} F900 ; FC3D_V1107_OPTICAL_SAFE_END_Z")
    rows.append(
        f"; FC3D_V1107_WAVESETS_END emitted_paths={emitted_paths} emitted_segments={emitted_segments} "
        f"B_EMITTED=0 INNER_EMITTED=0"
    )
    return rows


def audit_final_mirror_wave_paths(output, *unused):
    rt = _rt()
    output = Path(output)
    with zipfile.ZipFile(output, "r") as z:
        lines = z.read("Metadata/plate_1.gcode").decode("utf-8", errors="replace").splitlines()
    text = "\n".join(lines)
    if text.count("FC3D_V1107_WAVESETS_START") != 1 or text.count("FC3D_V1107_WAVESETS_END") != 1:
        raise RuntimeError("FINAL V1.107 AUDIT: wave-set boundaries missing")
    if "FC3D_V1106_WAVE_ARC" in text or "FC3D_V1107_WAVE_ARC" in text:
        raise RuntimeError("FINAL V1.107 AUDIT: rejected full-contour WAVE_ARC topology leaked")

    start_i = next(i for i, l in enumerate(lines) if "FC3D_V1107_WAVESETS_START" in l)
    end_i = next(i for i, l in enumerate(lines[start_i + 1:], start_i + 1) if "FC3D_V1107_WAVESETS_END" in l)
    wave_block = lines[start_i:end_i + 1]
    if any(re.match(r"^\s*G29\.1\b", l) for l in wave_block):
        raise RuntimeError("FINAL V1.107 AUDIT: G29.1 height stair-stepping found inside direct-XYZ wave")

    wave_lines = [l for l in wave_block if "FC3D_V1107_U_PROFILE_SEG" in l]
    if not wave_lines:
        raise RuntimeError("FINAL V1.107 AUDIT: no u-profile extrusion segments")
    epm = []
    role_counts = {"LEAD": 0, "OPTICAL_FRONT": 0, "HIDDEN_TOP": 0, "RETURN": 0}
    for line in wave_lines:
        for field in ("X", "Y", "Z", "E"):
            if not re.search(rf"\b{field}[-+0-9.]", line):
                raise RuntimeError(f"FINAL V1.107 AUDIT: direct XYZ/E field {field} missing: {line}")
        if f"F{WAVESET_PRINT_FEED_MM_S*60:.0f}" not in line:
            raise RuntimeError(f"FINAL V1.107 AUDIT: wrong wave feed: {line}")
        rm = re.search(r"\brole=([A-Z_]+)", line)
        hm0 = re.search(r"\bh0=([-+0-9.]+)", line)
        hm1 = re.search(r"\bh1=([-+0-9.]+)", line)
        lm = re.search(r"\bL3=([-+0-9.]+)", line)
        em = re.search(r"\bE([-+0-9.]+)", line)
        if not (rm and hm0 and hm1 and lm and em):
            raise RuntimeError(f"FINAL V1.107 AUDIT: malformed u-profile marker: {line}")
        role = rm.group(1)
        if role not in role_counts:
            raise RuntimeError(f"FINAL V1.107 AUDIT: unknown role {role}")
        h0, h1 = float(hm0.group(1)), float(hm1.group(1))
        if role == "LEAD" and abs(h1 - h0) > 1.1e-4:
            raise RuntimeError(f"FINAL V1.107 AUDIT: lead Z changed: {line}")
        if role in ("OPTICAL_FRONT", "HIDDEN_TOP") and h1 <= h0 + 1e-5:
            raise RuntimeError(f"FINAL V1.107 AUDIT: rising segment did not rise: {line}")
        if role == "RETURN" and h1 >= h0 - 1e-5:
            raise RuntimeError(f"FINAL V1.107 AUDIT: return did not descend: {line}")
        L = float(lm.group(1)); E = float(em.group(1))
        if L > 1e-9:
            epm.append(E / L)
        role_counts[role] += 1
    if not all(role_counts.values()):
        raise RuntimeError(f"FINAL V1.107 AUDIT: incomplete role coverage {role_counts}")
    if not epm or abs(sum(epm) / len(epm) - float(rt.A_MAIN_E_PER_MM)) > 8e-5:
        raise RuntimeError(f"FINAL V1.107 AUDIT: 3D E/mm mismatch mean={sum(epm)/len(epm) if epm else None}")

    roads = sum("FC3D_V1107_U_PROFILE_ROAD_START" in l for l in wave_block)
    reprimes = sum("FC3D_V1107_U_PROFILE_REPRIME" in l for l in wave_block)
    retracts = sum("FC3D_V1107_U_PROFILE_RETRACT" in l for l in wave_block)
    ends = sum("FC3D_V1107_U_PROFILE_ROAD_END" in l for l in wave_block)
    if not (roads == reprimes == retracts == ends and roads > 0):
        raise RuntimeError(
            f"FINAL V1.107 AUDIT: pressure-cycle counts road/reprime/retract/end={roads}/{reprimes}/{retracts}/{ends}"
        )
    orientation = audit_u_profile_orientation(rt._current_piece())
    return {
        "u_profile_paths": roads,
        "u_profile_segments": len(wave_lines),
        "role_counts": role_counts,
        "direct_xyz_wave": True,
        "wave_g29_steps": 0,
        "mean_e_per_mm_3d": sum(epm) / len(epm),
        "orientation": orientation,
    }


def _install_v107(runtime):
    global _RUNTIME
    _RUNTIME = runtime
    runtime.REAR_VERSION_TEXT = REAR_VERSION_TEXT
    runtime.WAVESET_BUILD_ORDER = WAVESET_BUILD_ORDER
    runtime.WAVESET_TOTAL_PEAK_MM = WAVESET_TOTAL_PEAK_MM
    runtime.WAVESET_HIDDEN_RISE_MM = WAVESET_HIDDEN_RISE_MM
    runtime.WAVESET_OPTICAL_RISE_MM = WAVESET_OPTICAL_RISE_MM
    runtime.WAVESET_BASE_LEAD_MM = WAVESET_BASE_LEAD_MM
    runtime.WAVESET_HIDDEN_RUN_MM = WAVESET_HIDDEN_RUN_MM
    runtime.WAVESET_RETURN_ANGLE_DEG = WAVESET_RETURN_ANGLE_DEG
    runtime.WAVESET_RETURN_RUN_MM = WAVESET_RETURN_RUN_MM
    runtime.WAVESET_PRINT_FEED_MM_S = WAVESET_PRINT_FEED_MM_S
    runtime.WAVESET_RESET_CENTER_SPACING_MM = WAVESET_RESET_CENTER_SPACING_MM
    runtime.WAVESET_MIN_CENTER_SPACING_MM = WAVESET_MIN_CENTER_SPACING_MM
    runtime.WAVESET_PITCH_TOL_MM = WAVESET_PITCH_TOL_MM
    runtime.WAVESET_PROFILE_MODEL = WAVESET_PROFILE_MODEL

    runtime.generate_u_profile_wave_sets = generate_u_profile_wave_sets
    runtime.generate_true_normal_wave_sets = generate_u_profile_wave_sets
    runtime.get_true_normal_wave_sets = get_true_normal_wave_sets
    runtime.waveset_report = waveset_report
    runtime.audit_u_profile_orientation = audit_u_profile_orientation
    runtime._explicit_mirror_wave_layer_gcode = _explicit_mirror_wave_layer_gcode
    runtime.audit_final_mirror_wave_paths = audit_final_mirror_wave_paths
    runtime._mirror_wave_peak_z_mm = lambda: max(
        float(runtime.NOMINAL_TOP_Z_MM), float(runtime.WAVESET_COMMAND_Z_MM) + WAVESET_TOTAL_PEAK_MM
    )

    inherited_dry = runtime.__dict__.get("dry_validate_v1107")
    if callable(inherited_dry):
        def dry_validate_v1107(dp):
            inherited_dry(dp)
            orient = audit_u_profile_orientation(runtime._current_piece())
            rep = waveset_report(runtime._current_piece())
            print("  v1.107 u-profile orientation  : PASS")
            print(f"  max angle to local u axis     : {orient['max_angle_to_local_u_axis_deg']:.5f} deg")
            print(f"  long u roads                  : {rep['road_count']}")
            for s in rep["sets"]:
                print(
                    f"  set {s['set_index']:2d}: roads={s['road_count']:3d} cells={s['cell_count']:3d} "
                    f"spacing {s['pitch_start_min_mm']:.4f}->{s['pitch_end_min_mm']:.4f} mm "
                    f"reason={s['end_reason']}"
                )
        runtime.dry_validate_v1107 = dry_validate_v1107


def _execute_v107():
    runtime = _load_runtime()
    _install_v107(runtime)
    main = runtime.__dict__.get("main")
    if not callable(main):
        raise RuntimeError(f"{SCRIPT_VERSION}: transformed predecessor has no main()")
    try:
        main()
    finally:
        sys.modules.pop(runtime.__name__, None)


if __name__ == "__main__":
    _execute_v107()
