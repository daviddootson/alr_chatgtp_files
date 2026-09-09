#!/usr/bin/env python3
"""FC3D v1.109: closed global wave-set launch.

v1.108 used only the upper part of the global equal-optical-path contour. That
omitted true local-u streamlines which enter the screen later through its side
edges. v1.109 keeps the v1.108 global 0.600 -> 0.400 reset logic and the v1.107
correct direct-XYZ local-u wave, but launches every set from a CLOSED equal-path
contour enclosing the complete screen. The coupon is still only a clip window.
"""
from __future__ import annotations

import hashlib
import math
import sys
import types
from pathlib import Path

import numpy as np

SCRIPT_VERSION = "3dprint_black_mirror_wave_grid_v1.109"
REAR_VERSION_TEXT = "109"
BASE_SCRIPT_VERSION = "3dprint_black_mirror_wave_grid_v1.108"
EXPECTED_V108_GIT_BLOB_SHA1 = "6cb737613c17668240734efbbf3f6c3a547af9e7"
CLOSED_GLOBAL_WAVESET = True
CLOSED_GLOBAL_WAVESET_MODEL = "closed_equal_optical_path_contour"
GLOBAL_WAVESET_START_MM = 0.600
GLOBAL_WAVESET_ZERO_GAP_MM = 0.400
SEGMENT_MARKER = "FC3D_V1109_U_PROFILE_SEG"
DIRECT_Z_MODEL = "direct_xyz"
CLOSED_CONTOUR_SAMPLES = 16384

_MOD = None


def _git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _load_transformed_v108():
    here=Path(__file__).resolve()
    base=here.with_name(here.name.replace("v1.109","v1.108",1))
    if not base.exists(): raise FileNotFoundError(f"{SCRIPT_VERSION}: predecessor {base.name} missing")
    data=base.read_bytes(); got=_git_blob_sha1(data)
    if got!=EXPECTED_V108_GIT_BLOB_SHA1:
        raise RuntimeError(f"{SCRIPT_VERSION}: v1.108 git-blob SHA drift {got} != {EXPECTED_V108_GIT_BLOB_SHA1}")
    src=data.decode("utf-8")
    for old,new in (("v1.108","v1.109"),("V1108","V1109"),("v1108","v1109"),("v108","v109")):
        src=src.replace(old,new)
    name="__fc3d_alr_v1109_closed_global__"
    mod=types.ModuleType(name); mod.__file__=str(here); mod.__package__=None
    sys.modules[name]=mod
    try: exec(compile(src,str(here),"exec"),mod.__dict__)
    except Exception:
        sys.modules.pop(name,None); raise
    return mod


def _outer_closed_equal_path_contour():
    m=_MOD
    rt=m._rt(); f=rt.MASTER_FAN
    W=float(f.screen_width_mm); H=float(f.screen_height_mm)
    corners=np.array([[0.0,0.0],[W,0.0],[0.0,H],[W,H]],dtype=float)
    target=float(np.max(m._optical_path_vec(corners[:,0],corners[:,1])))
    theta=np.linspace(0.0,2.0*math.pi,CLOSED_CONTOUR_SAMPLES,endpoint=False)
    ct=np.cos(theta); st=np.sin(theta)
    cx=float(f.projector_x_mm); cz=0.0
    lo=np.zeros_like(theta)
    hi=np.full_like(theta,W+H+3000.0)
    for _ in range(8):
        val=m._optical_path_vec(cx+hi*ct,cz+hi*st)
        bad=val<=target
        if not np.any(bad): break
        hi=np.where(bad,hi*2.0,hi)
    else:
        raise RuntimeError("v1.109 could not bracket closed equal-path contour")
    for _ in range(60):
        mid=0.5*(lo+hi)
        inside=m._optical_path_vec(cx+mid*ct,cz+mid*st)<target
        lo=np.where(inside,mid,lo); hi=np.where(inside,hi,mid)
    r=0.5*(lo+hi)
    pts=np.column_stack([cx+r*ct,cz+r*st])
    if len(pts)<100: raise RuntimeError("v1.109 closed contour degenerate")
    return pts


def _sample_closed_pitch(points,pitch=GLOBAL_WAVESET_START_MM):
    p=np.asarray(points,dtype=float)
    if len(p)<3: return np.empty((0,2),dtype=float)
    q=np.vstack([p,p[0]])
    d=np.hypot(np.diff(q[:,0]),np.diff(q[:,1])); cum=np.concatenate(([0.0],np.cumsum(d)))
    total=float(cum[-1]); n=max(3,int(round(total/float(pitch))))
    actual=total/n; targets=np.arange(n,dtype=float)*actual
    return np.column_stack([np.interp(targets,cum,q[:,0]),np.interp(targets,cum,q[:,1])])


def _spacing_closed(points):
    p=np.asarray(points,dtype=float)
    if len(p)<2: return None
    q=np.vstack([p,p[0]])
    d=np.hypot(np.diff(q[:,0]),np.diff(q[:,1]))
    return {"min":float(np.min(d)),"mean":float(np.mean(d)),"max":float(np.max(d)),"samples":int(len(d))}


def _patch_closed_global(mod):
    mod.CLOSED_GLOBAL_WAVESET=True
    mod.CLOSED_GLOBAL_WAVESET_MODEL=CLOSED_GLOBAL_WAVESET_MODEL
    mod.GLOBAL_WAVESET_MODEL="closed_equal_optical_path_contour_then_local_u_flow"
    mod._outer_global_contour=_outer_closed_equal_path_contour
    mod._sample_polyline_pitch=_sample_closed_pitch
    mod._spacing_np=_spacing_closed


def _execute():
    global _MOD
    _MOD=_load_transformed_v108()
    _patch_closed_global(_MOD)
    try:
        _MOD._execute()
    finally:
        sys.modules.pop(_MOD.__name__,None)


if __name__=="__main__":
    _execute()
