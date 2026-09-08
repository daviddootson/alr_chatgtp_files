#!/usr/bin/env python3
"""FC3D v1.143: discrete pyramid-2-1 mode over canonical v1.140."""
from __future__ import annotations
import re
from pathlib import Path

SCRIPT_VERSION = "3dprint_black_mirror_wave_grid_v1.143"
BASE_CONVERTER = "3dprint_black_mirror_wave_grid_v1.140.py"


def _one(src: str, old: str, new: str, label: str) -> str:
    n = src.count(old)
    if n != 1:
        raise RuntimeError(f"{SCRIPT_VERSION}: expected exactly one {label} anchor, found {n}")
    return src.replace(old, new, 1)


def _patch(src: str) -> str:
    if 'SCRIPT_VERSION="3dprint_black_mirror_wave_grid_v1.140"' not in src:
        raise RuntimeError(f"{SCRIPT_VERSION}: base is not canonical v1.140")

    # Add P2 profile beside P321 using the actual v1.140 line.
    p321 = '    "pyramid-3-2-1": {"tier_counts": (3, 2, 1), "smooth": False, "placement": "outer_to_inner"},'
    src = _one(
        src, p321,
        p321 + '\n    "pyramid-2-1": {"tier_counts": (2, 1), "smooth": False, "placement": "outer_to_inner"},',
        "MODE_PROFILES pyramid line")

    # CLI choice.
    src = _one(
        src,
        'ap.add_argument("--print-mode",choices=("single-arc","pyramid-3-2-1","smooth1","smooth2","smooth3"),required=True)',
        'ap.add_argument("--print-mode",choices=("single-arc","pyramid-3-2-1","pyramid-2-1","smooth1","smooth2","smooth3"),required=True)',
        "CLI print-mode")

    # Validation tuple: canonical v1.140 uses single quotes here.
    oldv = "if mode not in ('single-arc','pyramid-3-2-1','smooth1','smooth2','smooth3'):"
    if oldv in src:
        src = _one(src, oldv,
                   "if mode not in ('single-arc','pyramid-3-2-1','pyramid-2-1','smooth1','smooth2','smooth3'):",
                   "mode validation")
    else:
        oldv = 'if mode not in ("single-arc","pyramid-3-2-1","smooth1","smooth2","smooth3"):'
        src = _one(src, oldv,
                   'if mode not in ("single-arc","pyramid-3-2-1","pyramid-2-1","smooth1","smooth2","smooth3"):',
                   "mode validation")

    # Rear code.
    src = _one(
        src,
        'return {"single-arc":"A", "pyramid-3-2-1":"P", "smooth1":"S1", "smooth2":"S2", "smooth3":"S3"}[mode]',
        'return {"single-arc":"A", "pyramid-3-2-1":"P", "pyramid-2-1":"P2", "smooth1":"S1", "smooth2":"S2", "smooth3":"S3"}[mode]',
        "rear mode code")

    # P2 is a discrete pyramid: use the P-style outer reference branch.
    src = src.replace('if OPTICAL_MODE == "pyramid-3-2-1":',
                      'if OPTICAL_MODE in ("pyramid-3-2-1","pyramid-2-1"):')
    src = src.replace('if OPTICAL_MODE=="pyramid-3-2-1":',
                      'if OPTICAL_MODE in ("pyramid-3-2-1","pyramid-2-1"):')

    # Generalise the physical envelope from hard-coded 3/2/1 to active profile.
    old_gap = """    gaps=[]
    for c,p,d in zip(current,previous,distances):
        dc=_du_for_frame(mirror_frame_global(c[0],c[1]))
        dp=_du_for_frame(mirror_frame_global(p[0],p[1]))
        gaps.extend((d-3.0*ARC_PROFILE_WIDTH_MM,
                     d+dc-dp-2.0*ARC_PROFILE_WIDTH_MM,
                     d+2.0*dc-2.0*dp-ARC_PROFILE_WIDTH_MM))
    return min(gaps)"""
    new_gap = """    gaps=[]
    counts=_mode_profile()["tier_counts"]
    for c,p,d in zip(current,previous,distances):
        dc=_du_for_frame(mirror_frame_global(c[0],c[1]))
        dp=_du_for_frame(mirror_frame_global(p[0],p[1]))
        for tier,count in enumerate(counts):
            gaps.append(d+tier*dc-tier*dp-float(count)*ARC_PROFILE_WIDTH_MM)
    return min(gaps)"""
    n = src.count(old_gap)
    if n < 1:
        raise RuntimeError(f"{SCRIPT_VERSION}: physical-envelope block not found")
    src = src.replace(old_gap, new_gap)

    old_halo = 'halo=ARC_PROFILE_WIDTH_MM*(3.0 if OPTICAL_MODE=="pyramid-3-2-1" else 1.0)'
    n = src.count(old_halo)
    if n < 1:
        raise RuntimeError(f"{SCRIPT_VERSION}: finite-envelope halo not found")
    src = src.replace(old_halo,
                      'halo=ARC_PROFILE_WIDTH_MM*float(max(_mode_profile()["tier_counts"]))')

    # Older definitions inside the consolidated engine still contain this old
    # fallback. Make them profile-driven too. Later v1.140 definitions already are.
    src = src.replace('counts=(1,) if OPTICAL_MODE == "single-arc" else (3,2,1)',
                      'counts=_mode_profile()["tier_counts"]')
    src = src.replace('counts=(1,) if OPTICAL_MODE=="single-arc" else (3,2,1)',
                      'counts=_mode_profile()["tier_counts"]')

    # These are the key v1.140 invariants proving P2 shadow/emission height is 2 tiers.
    if '"height_mm": len(counts) * PHYSICAL_LAYER_HEIGHT_MM' not in src:
        raise RuntimeError(f"{SCRIPT_VERSION}: profile-driven shadow-height code missing")
    if 'counts = _mode_profile()["tier_counts"]' not in src:
        raise RuntimeError(f"{SCRIPT_VERSION}: profile-driven final support emitter missing")

    # Revision identifiers last.
    src = src.replace("FC3D_V1140", "FC3D_V1143")
    src = src.replace("3dprint_black_mirror_wave_grid_v1.140", "3dprint_black_mirror_wave_grid_v1.143")
    src = src.replace("V1.140", "V1.143").replace("v1.140", "v1.143").replace("v140", "v143")
    src = re.sub(r'\bREVISION=140\b', 'REVISION=143', src)
    src = re.sub(r'\bREAR_VERSION_TEXT="140"', 'REAR_VERSION_TEXT="143"', src)
    src = src.replace('line1=f"{piece}  140"', 'line1=f"{piece}  143"')

    required = [
        '"pyramid-2-1": {"tier_counts": (2, 1), "smooth": False',
        '"pyramid-2-1":"P2"',
        '"height_mm": len(counts) * PHYSICAL_LAYER_HEIGHT_MM',
        'counts = _mode_profile()["tier_counts"]',
        'max(_mode_profile()["tier_counts"])',
        'SCRIPT_VERSION="3dprint_black_mirror_wave_grid_v1.143"',
    ]
    missing = [x for x in required if x not in src]
    if missing:
        raise RuntimeError(f"{SCRIPT_VERSION}: patched-source invariant failure: {missing}")
    return src


def main() -> None:
    base = Path(__file__).resolve().with_name(BASE_CONVERTER)
    if not base.exists():
        raise FileNotFoundError(f"{SCRIPT_VERSION}: {BASE_CONVERTER} not found beside this script")
    patched = _patch(base.read_text(encoding="utf-8"))
    ns = {"__name__": "__main__", "__file__": str(Path(__file__).resolve()), "__package__": None}
    exec(compile(patched, str(Path(__file__).resolve()), "exec"), ns, ns)


if __name__ == "__main__":
    main()
