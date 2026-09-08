#!/usr/bin/env python3
"""
FC3D v1.142 delta converter.

Adds and fully corrects:
    --print-mode pyramid-2-1

Discrete two-tier pyramid with tier counts (2, 1), using the same support-stack
geometry as smooth2 but with smooth=False, so no smoothing/top pass is emitted.

Required beside this file:
    3dprint_black_mirror_wave_grid_v1.140.py
    3dprintv1.179.py
"""
from __future__ import annotations

import re
from pathlib import Path

SCRIPT_VERSION = "3dprint_black_mirror_wave_grid_v1.142"
REVISION = 142
BASE_CONVERTER = "3dprint_black_mirror_wave_grid_v1.140.py"


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(
            f"{SCRIPT_VERSION}: fail closed: expected exactly one {label} target, found {n}"
        )
    return text.replace(old, new, 1)


def _patch_v140_source(src: str) -> str:
    if 'SCRIPT_VERSION="3dprint_black_mirror_wave_grid_v1.140"' not in src:
        raise RuntimeError(
            f"{SCRIPT_VERSION}: {BASE_CONVERTER} is not the canonical v1.140 source"
        )

    # Add the non-smooth discrete 2-1 profile.
    src = _replace_once(
        src,
        '    "pyramid-3-2-1": {"tier_counts": (3, 2, 1), "smooth": False, "placement": "outer_to_inner"},\n'
        '    "smooth1": {"tier_counts": (1,), "smooth": True, "placement": "outer_to_inner"},',
        '    "pyramid-3-2-1": {"tier_counts": (3, 2, 1), "smooth": False, "placement": "outer_to_inner"},\n'
        '    "pyramid-2-1": {"tier_counts": (2, 1), "smooth": False, "placement": "outer_to_inner"},\n'
        '    "smooth1": {"tier_counts": (1,), "smooth": True, "placement": "outer_to_inner"},',
        "MODE_PROFILES",
    )

    src = _replace_once(
        src,
        'OPTICAL_MODES = ("single-arc", "pyramid-3-2-1")',
        'OPTICAL_MODES = ("single-arc", "pyramid-3-2-1", "pyramid-2-1")',
        "base OPTICAL_MODES",
    )

    src = _replace_once(
        src,
        'choices=("single-arc","pyramid-3-2-1","smooth1","smooth2","smooth3")',
        'choices=("single-arc","pyramid-3-2-1","pyramid-2-1","smooth1","smooth2","smooth3")',
        "CLI print-mode choices",
    )

    src = _replace_once(
        src,
        "if mode not in ('single-arc','pyramid-3-2-1','smooth1','smooth2','smooth3'):",
        "if mode not in ('single-arc','pyramid-3-2-1','pyramid-2-1','smooth1','smooth2','smooth3'):",
        "mode validation",
    )

    src = _replace_once(
        src,
        '{"single-arc":"A", "pyramid-3-2-1":"P", "smooth1":"S1", "smooth2":"S2", "smooth3":"S3"}',
        '{"single-arc":"A", "pyramid-3-2-1":"P", "pyramid-2-1":"P2", "smooth1":"S1", "smooth2":"S2", "smooth3":"S3"}',
        "rear mode code",
    )

    # Shadow/profile model must use the actual support tier profile.
    src = _replace_once(
        src,
        '    counts=(1,) if OPTICAL_MODE == "single-arc" else (3,2,1)\n'
        '    tiers=[]\n'
        '    for tier,count in enumerate(counts):',
        '    counts=_mode_profile()["tier_counts"]\n'
        '    tiers=[]\n'
        '    for tier,count in enumerate(counts):',
        "shadow cross-section tier counts",
    )

    # Clipped road set must match the actual support profile.
    src = _replace_once(
        src,
        'def _clip_roads(curve, piece):\n'
        '    counts=(1,) if OPTICAL_MODE == "single-arc" else (3,2,1)\n'
        '    roads={}',
        'def _clip_roads(curve, piece):\n'
        '    counts=_mode_profile()["tier_counts"]\n'
        '    roads={}',
        "clipped support tier counts",
    )

    # Emitted support roads + safe travel height must also match.
    src = _replace_once(
        src,
        '    counts=(1,) if OPTICAL_MODE=="single-arc" else (3,2,1)\n'
        '    travel_z=BASE_TOP_Z_MM+len(counts)*PHYSICAL_LAYER_HEIGHT_MM+0.160',
        '    counts=_mode_profile()["tier_counts"]\n'
        '    travel_z=BASE_TOP_Z_MM+len(counts)*PHYSICAL_LAYER_HEIGHT_MM+0.160',
        "emitted support tier counts",
    )

    # Physical no-overlap envelope: calculate one gap term per real tier.
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
    src = _replace_once(src, old_gap, new_gap, "physical-envelope tier calculation")

    src = _replace_once(
        src,
        '    halo=ARC_PROFILE_WIDTH_MM*(3.0 if OPTICAL_MODE=="pyramid-3-2-1" else 1.0)',
        '    halo=ARC_PROFILE_WIDTH_MM*float(max(_mode_profile()["tier_counts"]))',
        "finite-envelope halo",
    )

    # Both discrete pyramid modes use the inward-wave midpoint logic.
    src = src.replace(
        'OPTICAL_MODE=="pyramid-3-2-1"',
        'OPTICAL_MODE in ("pyramid-3-2-1","pyramid-2-1")',
    )
    src = src.replace(
        'OPTICAL_MODE == "pyramid-3-2-1"',
        'OPTICAL_MODE in ("pyramid-3-2-1","pyramid-2-1")',
    )

    # Core top-Z declaration: two support tiers for P2.
    src = _replace_once(
        src,
        'NOMINAL_TOP_Z_MM = BASE_TOP_Z_MM + '
        '(PHYSICAL_LAYER_HEIGHT_MM if OPTICAL_MODE == "single-arc" else 3.0 * PHYSICAL_LAYER_HEIGHT_MM)',
        'NOMINAL_TOP_Z_MM = BASE_TOP_Z_MM + '
        '(PHYSICAL_LAYER_HEIGHT_MM if OPTICAL_MODE == "single-arc" else '
        '(2.0 * PHYSICAL_LAYER_HEIGHT_MM if OPTICAL_MODE == "pyramid-2-1" '
        'else 3.0 * PHYSICAL_LAYER_HEIGHT_MM))',
        "NOMINAL_TOP_Z_MM",
    )

    # Audits must expect exactly the active support tiers.
    src = _replace_once(
        src,
        'expected_z=[rt.BASE_TOP_Z_MM+(i+1)*rt.PHYSICAL_LAYER_HEIGHT_MM for i in range(1 if rt.OPTICAL_MODE=="single-arc" else 3)]',
        'expected_z=[rt.BASE_TOP_Z_MM+(i+1)*rt.PHYSICAL_LAYER_HEIGHT_MM for i in range(len(rt._mode_profile()["tier_counts"]))]',
        "tier-height audit",
    )

    src = _replace_once(
        src,
        'expected_tiers={1} if rt.OPTICAL_MODE=="single-arc" else {1,2,3}',
        'expected_tiers=set(range(1,len(rt._mode_profile()["tier_counts"])+1))',
        "tier-ID audit",
    )

    # Revision all visible IDs.
    src = src.replace("FC3D_V1140", "FC3D_V1142")
    src = src.replace(
        "3dprint_black_mirror_wave_grid_v1.140",
        "3dprint_black_mirror_wave_grid_v1.142",
    )
    src = src.replace("V1.140", "V1.142")
    src = src.replace("v1.140", "v1.142")
    src = src.replace("v140", "v142")
    src = re.sub(r'REVISION=140\b', 'REVISION=142', src)
    src = re.sub(r'REAR_VERSION_TEXT="140"', 'REAR_VERSION_TEXT="142"', src)
    src = src.replace("revision=140", "revision=142")

    # Fail closed if any known geometry-bearing 3-tier assumptions remain.
    forbidden = (
        'counts=(1,) if OPTICAL_MODE == "single-arc" else (3,2,1)',
        'counts=(1,) if OPTICAL_MODE=="single-arc" else (3,2,1)',
        'expected_tiers={1} if rt.OPTICAL_MODE=="single-arc" else {1,2,3}',
    )
    leftovers = [x for x in forbidden if x in src]
    if leftovers:
        raise RuntimeError(
            f"{SCRIPT_VERSION}: hard-coded tier assumptions remain: {leftovers}"
        )

    required = (
        '"pyramid-2-1": {"tier_counts": (2, 1), "smooth": False',
        '"pyramid-2-1":"P2"',
        'counts=_mode_profile()["tier_counts"]',
        'len(rt._mode_profile()["tier_counts"])',
        'max(_mode_profile()["tier_counts"])',
        'SCRIPT_VERSION="3dprint_black_mirror_wave_grid_v1.142"',
        'FC3D_V1142',
    )
    missing = [x for x in required if x not in src]
    if missing:
        raise RuntimeError(
            f"{SCRIPT_VERSION}: patched source sanity failure; missing {missing}"
        )

    return src


def main() -> None:
    base = Path(__file__).resolve().with_name(BASE_CONVERTER)
    if not base.exists():
        raise FileNotFoundError(
            f"{SCRIPT_VERSION}: cannot find {BASE_CONVERTER}. "
            "Put v1.142 beside the existing v1.140 converter."
        )

    src = base.read_text(encoding="utf-8")
    patched = _patch_v140_source(src)

    ns = {
        "__name__": "__main__",
        "__file__": str(Path(__file__).resolve()),
        "__package__": None,
    }
    exec(compile(patched, str(Path(__file__).resolve()), "exec"), ns, ns)


if __name__ == "__main__":
    main()
