#!/usr/bin/env python3
"""FC3D v1.111: version-clean release wrapper over v1.110 geometry.

Geometry is intentionally unchanged from dry-validated v1.110.  This revision
exists because the deeply inherited predecessor dry logger still printed the
active label `DRY V1.106 VALIDATION`.  v1.111 patches that exact active label at
the v1.106 source-transform boundary and asserts the proven v1.110 geometry
fingerprint before accepting dry validation.
"""
from __future__ import annotations

import hashlib
import sys
import types
from pathlib import Path

SCRIPT_VERSION = "3dprint_black_mirror_wave_grid_v1.111"
REAR_VERSION_TEXT = "111"
BASE_SCRIPT_VERSION = "3dprint_black_mirror_wave_grid_v1.110"
EXPECTED_V110_GIT_BLOB_SHA1 = "aabbe19bb39855f0bf32eb60d3fac3c6d9997edb"
ACTIVE_VERSION_LABEL_PATCH = ("DRY V1.106 VALIDATION", "DRY V1.111 VALIDATION")
EXPECTED_SET1_ROADS = 17521
EXPECTED_SET2_ROADS = 12009
EXPECTED_SET1_CELLS = 917
EXPECTED_SET2_CELLS = 526
EXPECTED_LOCAL_ROADS = 332
EXPECTED_SET1_END_MAX_MM = 0.402
EXPECTED_SET2_START_MM = 0.600
SEGMENT_MARKER = "FC3D_V1111_U_PROFILE_SEG"
DIRECT_Z_MODEL = "direct_xyz"

_MOD = None


def _git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _load_transformed_v110():
    here=Path(__file__).resolve()
    base=here.with_name(here.name.replace("v1.111","v1.110",1))
    if not base.exists(): raise FileNotFoundError(f"{SCRIPT_VERSION}: predecessor {base.name} missing")
    data=base.read_bytes(); got=_git_blob_sha1(data)
    if got!=EXPECTED_V110_GIT_BLOB_SHA1:
        raise RuntimeError(f"{SCRIPT_VERSION}: v1.110 git-blob SHA drift {got} != {EXPECTED_V110_GIT_BLOB_SHA1}")
    src=data.decode("utf-8")
    for old,new in (("v1.110","v1.111"),("V1110","V1111"),("v1110","v1111"),("v110","v111")):
        src=src.replace(old,new)
    name="__fc3d_alr_v1111_release__"
    mod=types.ModuleType(name); mod.__file__=str(here); mod.__package__=None
    sys.modules[name]=mod
    try: exec(compile(src,str(here),"exec"),mod.__dict__)
    except Exception:
        sys.modules.pop(name,None); raise
    return mod


def _patch_active_version_label_and_fingerprint(mod):
    """Patch only the stale active dry label; do not rewrite historical references."""
    old_install_sparse=mod._install_sparse

    def install_sparse(inner):
        old_install_sparse(inner)
        old_load=inner._load_v107_template

        def load_template():
            template=old_load()
            old_transform=template._transform_predecessor_source

            def transform_predecessor(source: str):
                out=old_transform(source)
                old,new=ACTIVE_VERSION_LABEL_PATCH
                if old not in out:
                    raise RuntimeError(f"{SCRIPT_VERSION}: expected stale active dry label was not present to patch")
                out=out.replace(old,new)
                return out

            template._transform_predecessor_source=transform_predecessor
            return template

        inner._load_v107_template=load_template

        # Keep the v1.110 global geometry acceptance and add an exact release
        # fingerprint after the inherited dry validator is installed.
        old_install_global=inner._install_global_v111

        def install_global(runtime):
            old_install_global(runtime)
            inherited=runtime.__dict__.get("dry_validate_v1111")
            if inherited is None:
                inherited=runtime.__dict__.get("dry_validate_v111")
            if not callable(inherited):
                raise RuntimeError(f"{SCRIPT_VERSION}: transformed runtime dry validator missing")

            def dry_release(dp):
                inherited(dp)
                rep=inner.waveset_report(runtime._current_piece())
                sets=rep["sets"]
                if len(sets)<2:
                    raise RuntimeError(f"{SCRIPT_VERSION}: geometry fingerprint needs two sets, got {sets}")
                s1,s2=sets[0],sets[1]
                got=(s1["road_count"],s2["road_count"],s1["cell_count"],s2["cell_count"],rep["road_count"])
                exp=(EXPECTED_SET1_ROADS,EXPECTED_SET2_ROADS,EXPECTED_SET1_CELLS,EXPECTED_SET2_CELLS,EXPECTED_LOCAL_ROADS)
                if got!=exp:
                    raise RuntimeError(f"{SCRIPT_VERSION}: v1.110 geometry fingerprint drift {got} != {exp}")
                if s1["pitch_end_min_mm"]>EXPECTED_SET1_END_MAX_MM:
                    raise RuntimeError(f"{SCRIPT_VERSION}: set1 no longer reaches zero gap: {s1}")
                if abs(s2["pitch_start_min_mm"]-EXPECTED_SET2_START_MM)>0.0005:
                    raise RuntimeError(f"{SCRIPT_VERSION}: set2 no longer restarts at 0.600: {s2}")
                print("  v1.111 geometry fingerprint  : PASS (identical v1.110 schedule)")

            # The transformed predecessor normally exposes dry_validate_v111.
            runtime.__dict__["dry_validate_v111"] = dry_release
            runtime.__dict__["dry_validate_v1111"] = dry_release

        inner._install_global_v111=install_global

    mod._install_sparse=install_sparse


def _execute():
    global _MOD
    _MOD=_load_transformed_v110()
    _patch_active_version_label_and_fingerprint(_MOD)
    try:
        _MOD._execute()
    finally:
        sys.modules.pop(_MOD.__name__,None)


if __name__=="__main__":
    _execute()
