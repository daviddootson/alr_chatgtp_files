#!/usr/bin/env python3
"""FC3D v1.157 — v1.156 mapped K/W pyramids with an adjustable thin top-K cap.

Compatibility wrapper around the established v1.156 converter.  Every non-cap
optical tier retains v1.156 geometry, material dose and XY placement.  The new
``--cap-height-mm`` option changes only the final/top K tier's material-dose
height; its physical bead height is still multiplied by ``--physical-height-scale``.
The cap's base/XY registration therefore stays where v1.156 places the final
K tier, while its own blocker height, draw extrusion, top Z and tower schedule
use the cap value.

Requirements beside this file:
  * 3dprint_black_mirror_wave_grid_v1.156.py
  * canonical 3dprintv1.179.py selected with --source as usual
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import sys
import zipfile
from pathlib import Path
from typing import Iterable

SCRIPT_VERSION = "3dprint_black_mirror_wave_grid_v1.157"
REVISION = 157
REAR_VERSION_TEXT = "157"
DEFAULT_V156 = Path(__file__).with_name("3dprint_black_mirror_wave_grid_v1.156.py")
CAP_MAX_MM = 0.28


class ThinCapError(ValueError):
    pass


def _load_v156(path: Path):
    path = Path(path)
    if not path.is_file():
        raise ThinCapError(f"v1.156 converter not found: {path}")
    spec = importlib.util.spec_from_file_location("fc3d_v156_for_v157", path)
    if spec is None or spec.loader is None:
        raise ThinCapError(f"cannot load v1.156 converter: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    if getattr(mod, "REVISION", None) != 156:
        raise ThinCapError(f"expected v1.156 converter, found revision {getattr(mod, 'REVISION', None)!r}")
    return mod


def _split_wrapper_args(argv: list[str]):
    p = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    p.add_argument("--cap-height-mm", type=float)
    p.add_argument("--v156-script", type=Path, default=DEFAULT_V156)
    return p.parse_known_args(argv)


def _scan_option(args: Iterable[str], name: str):
    args = list(args)
    prefix = name + "="
    for i, token in enumerate(args):
        if token.startswith(prefix):
            return token[len(prefix):]
        if token == name and i + 1 < len(args):
            return args[i + 1]
    return None


def _validate_cap(mapping: str, layer_height_mm: float, cap_height_mm: float | None) -> float:
    mapping = str(mapping).upper()
    layer_height_mm = float(layer_height_mm)
    cap = layer_height_mm if cap_height_mm is None else float(cap_height_mm)
    if not math.isfinite(cap) or not 0.0 < cap <= CAP_MAX_MM:
        raise ThinCapError(f"cap height must be greater than zero and at most {CAP_MAX_MM:.2f} mm")
    if cap_height_mm is not None and (not mapping or mapping[-1] != "K"):
        raise ThinCapError("--cap-height-mm requires the final/top layer-map tier to be K")
    return cap


def _tier_physical_heights(rt, cap_height_mm: float):
    n = len(rt.LAYER_MAP)
    common = float(rt.PHYSICAL_LAYER_HEIGHT_MM)
    cap = float(cap_height_mm) * float(rt.PHYSICAL_HEIGHT_SCALE)
    return tuple([common] * max(0, n - 1) + [cap])


def _tier_top_zs(rt, cap_height_mm: float):
    z = float(rt.BASE_TOP_Z_MM)
    out = []
    for h in _tier_physical_heights(rt, cap_height_mm):
        z += h
        out.append(z)
    return tuple(out)


def _cap_ratio(rt, cap_height_mm: float) -> float:
    return float(cap_height_mm) / float(rt.LAYER_HEIGHT_MM)


def _replace_e(line: str, factor: float) -> str:
    m = re.search(r"\bE([-+0-9.]+)", line)
    if not m:
        return line
    value = float(m.group(1)) * float(factor)
    text = f"{value:.8f}".rstrip("0").rstrip(".")
    return line[:m.start(1)] + text + line[m.end(1):]


def _patch_emitted_rows(rows: Iterable[str], rt, cap_height_mm: float):
    """Modify only final-K Z/draw E after v1.156 has solved the XY road paths."""
    rows = list(rows)
    if not rows:
        return rows
    cap_tier = len(rt.LAYER_MAP)
    cap_z = _tier_top_zs(rt, cap_height_mm)[-1]
    travel_z = cap_z + 0.160
    ratio = _cap_ratio(rt, cap_height_mm)
    active_cap = False
    out = []
    for line in rows:
        if "FC3D_V1156_OPTICAL_START" in line and "cap_dose_height=" not in line:
            line += (f" cap_dose_height={cap_height_mm:.3f}"
                     f" cap_physical_height={cap_height_mm*rt.PHYSICAL_HEIGHT_SCALE:.3f}")
        if "FC3D_V1156_SUPPORT_ROAD_START" in line:
            mt = re.search(r"\btier=(\d+)", line)
            active_cap = bool(mt and int(mt.group(1)) == cap_tier)
            if active_cap:
                line = re.sub(r"\bz=[-+0-9.]+", f"z={cap_z:.3f}", line)
        if "FC3D_V1156_SUPPORT_TRAVEL_Z" in line:
            line = re.sub(r"G0 Z[-+0-9.]+", f"G0 Z{travel_z:.3f}", line, count=1)
        if active_cap and "FC3D_V1156_SUPPORT_HEIGHT" in line:
            line = re.sub(r"G0 Z[-+0-9.]+", f"G0 Z{cap_z:.3f}", line, count=1)
        if active_cap and "SUPPORT_SEG" in line:
            line = _replace_e(line, ratio)
        out.append(line)
        if "FC3D_V1156_SUPPORT_ROAD_END" in line:
            active_cap = False
    return out


def _normalise_cap_e_for_v156_audit(block: str, rt, cap_height_mm: float) -> str:
    ratio = _cap_ratio(rt, cap_height_mm)
    if abs(ratio - 1.0) <= 1.0e-12:
        return block
    cap_tier = len(rt.LAYER_MAP)
    active = False
    out = []
    for line in block.splitlines():
        if "FC3D_V1156_SUPPORT_ROAD_START" in line:
            mt = re.search(r"\btier=(\d+)", line)
            active = bool(mt and int(mt.group(1)) == cap_tier)
        if active and "SUPPORT_SEG" in line:
            line = _replace_e(line, 1.0 / ratio)
        out.append(line)
        if "FC3D_V1156_SUPPORT_ROAD_END" in line:
            active = False
    return "\n".join(out)


def _install_runtime_thin_cap(rt, cap_requested: float | None):
    cap = _validate_cap(rt.LAYER_MAP, rt.LAYER_HEIGHT_MM, cap_requested)
    rt.CAP_HEIGHT_MM = cap
    rt.CAP_PHYSICAL_HEIGHT_MM = cap * float(rt.PHYSICAL_HEIGHT_SCALE)
    rt.TIER_PHYSICAL_HEIGHTS_MM = _tier_physical_heights(rt, cap)
    rt.TIER_TOP_Z_MM = _tier_top_zs(rt, cap)
    rt.NOMINAL_TOP_Z_MM = rt.TIER_TOP_Z_MM[-1]

    rt.LABEL_GLYPHS.setdefault("C", ("01111","10000","10000","10000","10000","10000","01111"))
    lines = list(rt.REAR_TEXT_LINES)
    if lines:
        lines[0] = f"{rt.CURRENT_PIECE.name}  157"
        lines[-1] = lines[-1] + f" C{int(round(cap*100)):02d}"
        rt.REAR_TEXT_LINES = tuple(lines)
        rt.REAR_PARAMETER_TEXT = " | ".join(lines)

    import numpy as np
    blocker_cache = {}

    def white_ray_mask(points, normals, center, target):
        key = (tuple(center), rt.LAYER_MAP, rt.LAYER_HEIGHT_MM,
               rt.PHYSICAL_HEIGHT_SCALE, cap)
        if key not in blocker_cache:
            cx, cz = map(float, center)
            frame = rt.mirror_frame_global(cx, cz)
            profile = rt._stack_cross_section_profile(frame["facet_tilt_deg"])
            roads = []
            for ti, tier in enumerate(profile["tiers"]):
                hh = rt.TIER_PHYSICAL_HEIGHTS_MM[ti]
                for uc in tier["centres_u_mm"]:
                    roads.append((uc, tier["base_height_mm"], hh))
            blocker_cache[key] = (np.asarray(frame["b_unit"], float), np.asarray(roads, float))
        b, roads = blocker_cache[key]
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
        a = float(rt.ARC_PROFILE_WIDTH_MM) / 2.0
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

    rt._white_ray_mask = white_ray_mask
    rt._BLOCKER_ARRAY_CACHE = {}
    rt._OPTICAL_LATTICE_CACHE = {}

    original_emit = rt._explicit_mirror_wave_layer_gcode
    def emit(*args, **kwargs):
        return _patch_emitted_rows(original_emit(*args, **kwargs), rt, cap)
    rt._explicit_mirror_wave_layer_gcode = emit

    original_report = rt.optical_spacing_report
    def report(piece):
        result = dict(original_report(piece))
        support_h = sum(rt.TIER_PHYSICAL_HEIGHTS_MM)
        result.update(
            revision=157,
            cap_height_mm=cap,
            cap_physical_height_mm=rt.CAP_PHYSICAL_HEIGHT_MM,
            tier_physical_heights_mm=list(rt.TIER_PHYSICAL_HEIGHTS_MM),
            support_height_mm=support_h,
            model_top_z_mm=rt.BASE_TOP_Z_MM + support_h,
            thin_cap_definition="final/top K tier only; W tiers retain v1.156 geometry and dose",
        )
        return result
    rt.optical_spacing_report = report
    return cap


def _make_tower_schedule(base_mod, inherited):
    def schedule(rt):
        if not hasattr(rt, "TIER_TOP_Z_MM"):
            return inherited(rt)
        tiers = [round(z, 3) for z in rt.TIER_TOP_Z_MM]
        base = float(rt.BASE_TOP_Z_MM)
        if any(b <= a for a, b in zip([base] + tiers, tiers)):
            raise ValueError("tier spacing is below G-code Z resolution")
        if tiers[-1] > 150:
            raise ValueError("optical stack exceeds the A1 mini build height allowance")
        changes = [g for g in base_mod._colour_groups(rt) if g["change"] is not None]
        if not changes:
            return dict(tiers=tiers, batches=[], changes=[], max_deposited_z=tiers[-1], safe_z=max(4.0, tiers[-1]+1.0))
        batches = [[.2], [.3], [.4]]
        last = 4
        scheduled = []
        for group in changes:
            end = max(last+1, int(math.ceil(tiers[group["tier"]-1]*10 - 1e-8)))
            heights = [round(i/10, 1) for i in range(last+1, end+1)]
            last = end
            batches.append(heights)
            scheduled.append(dict(tier=group["tier"], road=group["roads"][0], tool=group["tool"], heights=heights))
        maximum = max(tiers[-1], last/10)
        return dict(tiers=tiers, batches=batches, changes=scheduled,
                    max_deposited_z=maximum, safe_z=max(4.0, maximum+1.0))
    return schedule


def _make_output_namer(inherited, state):
    def namer(rt):
        old = Path(inherited(rt))
        cap = float(rt.CAP_HEIGHT_MM)
        slug = format(cap, ".8g").replace(".", "p")
        name = old.name.replace("_v156.gcode.3mf", f"_C{slug}_v157.gcode.3mf")
        if name == old.name:
            name = old.stem + f"_C{slug}_v157.gcode.3mf"
        if len(name.encode("utf-8")) > 96:
            digest = hashlib.sha256(name.encode()).hexdigest()[:16]
            name = f"ALR_{rt.LAYER_MAP}_{rt.CURRENT_PIECE.name}_C{slug}_{digest}_v157.gcode.3mf"
        state["default_output"] = Path(name)
        return Path(name)
    return namer


def _postprocess_revision(output: Path):
    output = Path(output)
    if not output.is_file():
        raise ThinCapError(f"expected generated package not found: {output}")
    with zipfile.ZipFile(output, "r") as zin:
        names = zin.namelist()
        data = {name: zin.read(name) for name in names}
    gname = "Metadata/plate_1.gcode"
    if gname not in data:
        raise ThinCapError("generated package has no Metadata/plate_1.gcode")
    g = data[gname].decode("utf-8")
    g = g.replace("FC3D_V1156", "FC3D_V1157").replace("FC3D v1.156", "FC3D v1.157")
    gb = g.encode("utf-8")
    data[gname] = gb
    md5name = "Metadata/plate_1.gcode.md5"
    if md5name in data:
        data[md5name] = (hashlib.md5(gb).hexdigest() + "\n").encode()
    for name in ("Metadata/fc3d_selective_white_audit.json", "Metadata/fc3d_mapped_pyramid_audit.json"):
        if name in data:
            try:
                obj = json.loads(data[name])
                obj["revision"] = 157
                obj["script_version"] = SCRIPT_VERSION
                data[name] = json.dumps(obj, indent=2).encode()
            except Exception:
                pass
    tmp = output.with_name(output.name + ".v157rewrite")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for name in names:
            zout.writestr(name, data[name])
    tmp.replace(output)
    with zipfile.ZipFile(output, "r") as zin:
        g2 = zin.read(gname)
        if b"FC3D_V1156" in g2 or b"FC3D_V1157" not in g2:
            raise ThinCapError("revision marker postprocess failed")
        if md5name in zin.namelist():
            if zin.read(md5name).decode().strip() != hashlib.md5(g2).hexdigest():
                raise ThinCapError("plate_1.gcode MD5 mismatch after v1.157 postprocess")


def _infer_explicit_output(args: list[str]):
    value = _scan_option(args, "--output")
    return Path(value) if value else None


def main(argv: list[str] | None = None):
    argv = list(sys.argv[1:] if argv is None else argv)
    wrapper, base_args = _split_wrapper_args(argv)
    base = _load_v156(wrapper.v156_script)

    mapping = (_scan_option(base_args, "--layer-map") or "kkkwwk").upper()
    layer_height = float(_scan_option(base_args, "--layer-height-mm") or .24)
    cap = _validate_cap(mapping, layer_height, wrapper.cap_height_mm)

    base.SCRIPT_VERSION = SCRIPT_VERSION
    base.REVISION = REVISION
    base.REAR_VERSION_TEXT = REAR_VERSION_TEXT

    inherited_configure = base._configure_map
    def configure_map(rt, mapping, visibility, piece, minimum_pitch=0.0):
        value = inherited_configure(rt, mapping, visibility, piece, minimum_pitch)
        _install_runtime_thin_cap(rt, wrapper.cap_height_mm)
        return value
    base._configure_map = configure_map

    base._tower_schedule = _make_tower_schedule(base, base._tower_schedule)
    state = {}
    base._mapped_output_name = _make_output_namer(base._mapped_output_name, state)

    inherited_audit_block = base._audit_optical_block
    def audit_block(block, rt):
        normal = _normalise_cap_e_for_v156_audit(block, rt, float(rt.CAP_HEIGHT_MM))
        result = dict(inherited_audit_block(normal, rt))
        result.update(cap_height_mm=float(rt.CAP_HEIGHT_MM),
                      cap_physical_height_mm=float(rt.CAP_PHYSICAL_HEIGHT_MM),
                      cap_draw_e_per_mm=float(rt.A_MAIN_E_PER_MM)*_cap_ratio(rt, float(rt.CAP_HEIGHT_MM)))
        return result
    base._audit_optical_block = audit_block

    inherited_audit_package = base._audit_package
    def audit_package(output, rt, piece_name):
        result = dict(inherited_audit_package(output, rt, piece_name))
        result.update(revision=157, script_version=SCRIPT_VERSION,
                      cap_height_mm=float(rt.CAP_HEIGHT_MM),
                      cap_physical_height_mm=float(rt.CAP_PHYSICAL_HEIGHT_MM),
                      tier_physical_heights_mm=list(rt.TIER_PHYSICAL_HEIGHTS_MM))
        return result
    base._audit_package = audit_package

    inherited_audit_contrast = base._audit_contrast
    def audit_contrast(output, rt):
        result = dict(inherited_audit_contrast(output, rt))
        result.update(revision=157, cap_height_mm=float(rt.CAP_HEIGHT_MM),
                      cap_physical_height_mm=float(rt.CAP_PHYSICAL_HEIGHT_MM))
        base._replace_zip(output, {"Metadata/fc3d_selective_white_audit.json": json.dumps(result, indent=2).encode()})
        return result
    base._audit_contrast = audit_contrast

    explicit = _infer_explicit_output(base_args)
    old_argv = sys.argv
    try:
        sys.argv = [str(wrapper.v156_script)] + base_args
        base.main()
    finally:
        sys.argv = old_argv

    if "--dry-validate" in base_args:
        return
    output = explicit or state.get("default_output")
    if output is None:
        raise ThinCapError("could not determine generated output path")
    _postprocess_revision(output)
    print(f"v1.157 thin-cap audit: PASS (cap dose {cap:.3f} mm)", flush=True)
    print("Saved: " + str(output), flush=True)


if __name__ == "__main__":
    try:
        main()
    except ThinCapError as exc:
        raise SystemExit(f"{SCRIPT_VERSION}: {exc}")
