#!/usr/bin/env python3
"""FC3D v1.113: version-clean release wrapper over validated v1.110 geometry.

v1.110 contains the validated sparse-global 0.600 -> 0.400 -> reset packing and
exact local-u direct-XYZ wave geometry. v1.111/v1.112 changed only release/dry
plumbing and are retained as failed diagnostics. v1.113 is rebuilt directly from
v1.110, keeps its geometry byte-for-behaviour identical, patches only the stale
active `DRY V1.106 VALIDATION` label at the deepest v1.106 transform boundary,
and wraps the single revision-specific `dry_validate_v*` callable. The generic
`dry_validate` helper is deliberately ignored.
"""
from __future__ import annotations

import hashlib
import sys
import types
from pathlib import Path

SCRIPT_VERSION = "3dprint_black_mirror_wave_grid_v1.113"
REAR_VERSION_TEXT = "113"
BASE_SCRIPT_VERSION = "3dprint_black_mirror_wave_grid_v1.110"
EXPECTED_V110_GIT_BLOB_SHA1 = "aabbe19bb39855f0bf32eb60d3fac3c6d9997edb"
ACTIVE_VERSION_LABEL_PATCH = ("DRY V1.106 VALIDATION", "DRY V1.113 VALIDATION")
EXPECTED_SET1_ROADS = 17521
EXPECTED_SET2_ROADS = 12009
EXPECTED_SET1_CELLS = 917
EXPECTED_SET2_CELLS = 526
EXPECTED_LOCAL_ROADS = 332
EXPECTED_SET1_END_MAX_MM = 0.402
EXPECTED_SET2_START_MM = 0.600
SEGMENT_MARKER = "FC3D_V1113_U_PROFILE_SEG"
DIRECT_Z_MODEL = "direct_xyz"

_MOD = None


def _git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _load_transformed_v110():
    here = Path(__file__).resolve()
    base = here.with_name(here.name.replace("v1.113", "v1.110", 1))
    if not base.exists():
        raise FileNotFoundError(f"{SCRIPT_VERSION}: predecessor {base.name} missing")
    data = base.read_bytes()
    got = _git_blob_sha1(data)
    if got != EXPECTED_V110_GIT_BLOB_SHA1:
        raise RuntimeError(
            f"{SCRIPT_VERSION}: v1.110 git-blob SHA drift {got} != {EXPECTED_V110_GIT_BLOB_SHA1}"
        )
    src = data.decode("utf-8")
    for old, new in (
        ("v1.110", "v1.113"),
        ("V1110", "V1113"),
        ("v1110", "v1113"),
        ("v110", "v113"),
    ):
        src = src.replace(old, new)
    name = "__fc3d_alr_v1113_release__"
    mod = types.ModuleType(name)
    mod.__file__ = str(here)
    mod.__package__ = None
    sys.modules[name] = mod
    try:
        exec(compile(src, str(here), "exec"), mod.__dict__)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return mod


def discover_revision_dry_validator(runtime):
    """Return the one revision-specific dry validator; ignore generic helper."""
    candidates = [
        (name, fn)
        for name, fn in runtime.__dict__.items()
        if name.startswith("dry_validate_v") and callable(fn)
    ]
    if len(candidates) != 1:
        raise RuntimeError(
            f"{SCRIPT_VERSION}: expected exactly one revision-specific dry validator, "
            f"found {[name for name, _ in candidates]}"
        )
    return candidates[0]


def _patch_release(mod):
    old_install_sparse = mod._install_sparse

    def install_sparse(inner):
        old_install_sparse(inner)

        # Patch only the active stale label at the deepest v1.106 source transform.
        old_load = inner._load_v107_template

        def load_template():
            template = old_load()
            old_transform = template._transform_predecessor_source

            def transform_predecessor(source: str):
                out = old_transform(source)
                old, new = ACTIVE_VERSION_LABEL_PATCH
                if old not in out:
                    raise RuntimeError(
                        f"{SCRIPT_VERSION}: stale active dry label not found at v1.106 transform boundary"
                    )
                return out.replace(old, new)

            template._transform_predecessor_source = transform_predecessor
            return template

        inner._load_v107_template = load_template

        # v1.110's _install_global_v110 becomes _install_global_v113 after the
        # outer source transform. Preserve it, then wrap only its active dry check.
        old_install_global = inner._install_global_v113

        def install_global(runtime):
            old_install_global(runtime)
            key, inherited = discover_revision_dry_validator(runtime)

            def dry_release(dp):
                inherited(dp)
                rep = inner.waveset_report(runtime._current_piece())
                sets = rep["sets"]
                if len(sets) < 2:
                    raise RuntimeError(
                        f"{SCRIPT_VERSION}: geometry fingerprint needs >=2 sets, got {sets}"
                    )
                s1, s2 = sets[0], sets[1]
                got = (
                    s1["road_count"],
                    s2["road_count"],
                    s1["cell_count"],
                    s2["cell_count"],
                    rep["road_count"],
                )
                expected = (
                    EXPECTED_SET1_ROADS,
                    EXPECTED_SET2_ROADS,
                    EXPECTED_SET1_CELLS,
                    EXPECTED_SET2_CELLS,
                    EXPECTED_LOCAL_ROADS,
                )
                if got != expected:
                    raise RuntimeError(
                        f"{SCRIPT_VERSION}: v1.110 geometry fingerprint drift {got} != {expected}"
                    )
                if s1["pitch_end_min_mm"] > EXPECTED_SET1_END_MAX_MM:
                    raise RuntimeError(
                        f"{SCRIPT_VERSION}: set1 no longer reaches zero-gap threshold: {s1}"
                    )
                if abs(s2["pitch_start_min_mm"] - EXPECTED_SET2_START_MM) > 0.0005:
                    raise RuntimeError(
                        f"{SCRIPT_VERSION}: set2 no longer restarts at 0.600 mm: {s2}"
                    )
                print("  v1.113 geometry fingerprint  : PASS (identical v1.110 schedule)")

            runtime.__dict__[key] = dry_release
            print(f"  v1.113 active dry validator   : {key}")

        inner._install_global_v113 = install_global

    mod._install_sparse = install_sparse


def _execute():
    global _MOD
    _MOD = _load_transformed_v110()
    _patch_release(_MOD)
    try:
        _MOD._execute()
    finally:
        sys.modules.pop(_MOD.__name__, None)


if __name__ == "__main__":
    _execute()
