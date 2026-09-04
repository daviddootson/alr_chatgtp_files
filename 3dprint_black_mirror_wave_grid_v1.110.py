#!/usr/bin/env python3
"""FC3D v1.110: sparse global metric, exact local-u direct-XYZ roads.

v1.109 established the correct CLOSED equal-optical-path global launch but its
literal global simulation advanced every nominal 0.600-mm road and was too
expensive. v1.110 preserves that exact topology while separating two concerns:

* global set phase is measured on 4096 persistent streamline samples; their
  deformation is scaled by the exact integer global road count, so the complete
  0.600 -> 0.400 -> reset rule is evaluated globally without instantiating every
  road;
* only the discrete global roads whose streamline neighbourhood can reach the
  selected coupon are reconstructed, and those use the same scalar local-u
  direct-XYZ cell builder and emitter proven by v1.107.

No coupon-local reseeding is permitted. Wave height remains real coordinated Z.
"""
from __future__ import annotations

import hashlib
import math
import sys
import types
from pathlib import Path

import numpy as np

SCRIPT_VERSION = "3dprint_black_mirror_wave_grid_v1.110"
REAR_VERSION_TEXT = "110"
BASE_SCRIPT_VERSION = "3dprint_black_mirror_wave_grid_v1.109"
EXPECTED_V109_GIT_BLOB_SHA1 = "3d5f37bb5a6e3ec921a123a860107ef181ecf82c"
SPARSE_GLOBAL_METRIC = True
SPARSE_METRIC_SAMPLES = 4096
SPARSE_TOUCH_EXPAND_SAMPLES = 3
GLOBAL_WAVESET_START_MM = 0.600
GLOBAL_WAVESET_ZERO_GAP_MM = 0.400
GLOBAL_WAVESET_RESET_TOL_MM = 0.002
GLOBAL_MAX_SETS = 16
GLOBAL_MAX_CELLS_PER_SET = 1200
GLOBAL_EXIT_GUARD_CELLS = 20
SEGMENT_MARKER = "FC3D_V1110_U_PROFILE_SEG"
DIRECT_Z_MODEL = "direct_xyz"

_OUTER = None
_INNER = None
_SCHEDULE_CACHE = {}
_GEOMETRY_CACHE = {}


def _git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _load_transformed_v109():
    here=Path(__file__).resolve()
    base=here.with_name(here.name.replace("v1.110","v1.109",1))
    if not base.exists(): raise FileNotFoundError(f"{SCRIPT_VERSION}: predecessor {base.name} missing")
    data=base.read_bytes(); got=_git_blob_sha1(data)
    if got!=EXPECTED_V109_GIT_BLOB_SHA1:
        raise RuntimeError(f"{SCRIPT_VERSION}: v1.109 git-blob SHA drift {got} != {EXPECTED_V109_GIT_BLOB_SHA1}")
    src=data.decode("utf-8")
    for old,new in (("v1.109","v1.110"),("V1109","V1110"),("v1109","v1110"),("v109","v110")):
        src=src.replace(old,new)
    name="__fc3d_alr_v1110_sparse_global__"
    mod=types.ModuleType(name); mod.__file__=str(here); mod.__package__=None
    sys.modules[name]=mod
    try: exec(compile(src,str(here),"exec"),mod.__dict__)
    except Exception:
        sys.modules.pop(name,None); raise
    return mod


def _closed_length(points):
    p=np.asarray(points,dtype=float)
    q=np.vstack([p,p[0]])
    return float(np.sum(np.hypot(np.diff(q[:,0]),np.diff(q[:,1]))))


def _closed_resample_count(points,count):
    p=np.asarray(points,dtype=float); n=int(count)
    if len(p)<3 or n<3: raise RuntimeError("v1.110 closed resample requires >=3 points")
    q=np.vstack([p,p[0]])
    d=np.hypot(np.diff(q[:,0]),np.diff(q[:,1])); cum=np.concatenate(([0.0],np.cumsum(d)))
    total=float(cum[-1]); targets=np.arange(n,dtype=float)*(total/n)
    return np.column_stack([np.interp(targets,cum,q[:,0]),np.interp(targets,cum,q[:,1])])


def _closed_points_at_fractions(points,fractions):
    p=np.asarray(points,dtype=float); f=np.mod(np.asarray(fractions,dtype=float),1.0)
    q=np.vstack([p,p[0]])
    d=np.hypot(np.diff(q[:,0]),np.diff(q[:,1])); cum=np.concatenate(([0.0],np.cumsum(d)))
    total=float(cum[-1]); t=f*total
    return np.column_stack([np.interp(t,cum,q[:,0]),np.interp(t,cum,q[:,1])])


def scaled_sparse_spacing(metric_points,global_road_count):
    """Estimate actual adjacent-road spacing from persistent sparse streamlines.

    Each sparse interval represents global_road_count/SPARSE_METRIC_SAMPLES
    true road intervals. Scaling its current chord by the inverse of that count
    preserves the material-road spacing metric while avoiding all-road storage.
    """
    p=np.asarray(metric_points,dtype=float); n=int(global_road_count); m=len(p)
    q=np.vstack([p,p[0]])
    d=np.hypot(np.diff(q[:,0]),np.diff(q[:,1]))
    vals=d*(m/float(n))
    return {"min":float(np.min(vals)),"mean":float(np.mean(vals)),"max":float(np.max(vals)),"samples":int(n)}


def _nominal_global_count(points):
    L=_closed_length(points)
    return max(3,int(round(L/GLOBAL_WAVESET_START_MM)))


def _nominal_start_spacing(points,count):
    v=_closed_length(points)/float(count)
    return {"min":v,"mean":v,"max":v,"samples":int(count)}


def _expand_circular_mask(mask,n=SPARSE_TOUCH_EXPAND_SAMPLES):
    x=np.asarray(mask,dtype=bool).copy()
    out=x.copy()
    for k in range(1,int(n)+1): out |= np.roll(x,k)|np.roll(x,-k)
    return out


def _piece_touch_mask(a,b,piece):
    h=float(_INNER.GLOBAL_WAVESET_PIECE_HALO_MM)
    xmin=piece.global_x0_mm-h; xmax=piece.global_x1_mm+h
    zmin=piece.global_z0_mm-h; zmax=piece.global_z1_mm+h
    lo_x=np.minimum(a[:,0],b[:,0]); hi_x=np.maximum(a[:,0],b[:,0])
    lo_z=np.minimum(a[:,1],b[:,1]); hi_z=np.maximum(a[:,1],b[:,1])
    return (hi_x>=xmin)&(lo_x<=xmax)&(hi_z>=zmin)&(lo_z<=zmax)


def sparse_global_wave_set_schedule(piece):
    key=(piece.name,round(piece.global_x0_mm,6),round(piece.global_z0_mm,6))
    if key in _SCHEDULE_CACHE: return _SCHEDULE_CACHE[key]

    launch=np.asarray(_INNER._outer_global_contour(),dtype=float)
    metric=_closed_resample_count(launch,SPARSE_METRIC_SAMPLES)
    sets=[]; global_cell_base=0; seen_piece=False; piece_done=False

    for set_idx in range(1,GLOBAL_MAX_SETS+1):
        metric=_closed_resample_count(metric,SPARSE_METRIC_SAMPLES)
        nroads=_nominal_global_count(metric)
        start_metric=metric.copy(); start_sp=_nominal_start_spacing(metric,nroads)
        touch_ever=np.zeros(SPARSE_METRIC_SAMPLES,dtype=bool)
        touch_first=np.full(SPARSE_METRIC_SAMPLES,-1,dtype=int)
        touch_last=np.full(SPARSE_METRIC_SAMPLES,-1,dtype=int)
        pitch_hist=[]; no_touch_after=0; end_reason=None

        for lc in range(1,GLOBAL_MAX_CELLS_PER_SET+1):
            nxt=_INNER._advance_wave_vec(metric)
            sp=scaled_sparse_spacing(nxt,nroads); pitch_hist.append(sp)
            touch=_piece_touch_mask(metric,nxt,piece)
            new=touch&(touch_first<0); touch_first[new]=lc; touch_last[touch]=lc; touch_ever|=touch
            if np.any(touch):
                seen_piece=True; no_touch_after=0
            elif seen_piece:
                no_touch_after+=1
            metric=nxt
            if sp["min"] <= GLOBAL_WAVESET_ZERO_GAP_MM+GLOBAL_WAVESET_RESET_TOL_MM:
                end_reason="zero_gap"; break
            if seen_piece and no_touch_after>=GLOBAL_EXIT_GUARD_CELLS:
                end_reason="piece_complete"; piece_done=True; break
        if end_reason is None:
            raise RuntimeError(f"v1.110 set {set_idx} exceeded sparse cell guard")

        sets.append({
            "set_index":set_idx,"start_metric":start_metric,"end_metric":metric.copy(),
            "global_road_count":nroads,"start_spacing":start_sp,"end_spacing":pitch_hist[-1],
            "pitch_hist":pitch_hist,"cell_count":len(pitch_hist),"end_reason":end_reason,
            "touch_ever":_expand_circular_mask(touch_ever),"touch_first":touch_first,"touch_last":touch_last,
            "global_cell_base":global_cell_base,
        })
        global_cell_base += len(pitch_hist)
        if piece_done: break
        if end_reason!="zero_gap": break

        reset_metric=_closed_resample_count(metric,SPARSE_METRIC_SAMPLES)
        new_count=_nominal_global_count(reset_metric)
        if new_count>=nroads:
            raise RuntimeError(f"v1.110 reset failed to reduce road count {new_count} >= {nroads}")
        reset_start=_nominal_start_spacing(reset_metric,new_count)
        if abs(reset_start["mean"]-GLOBAL_WAVESET_START_MM)>0.003:
            raise RuntimeError(f"v1.110 reset did not return near 0.600 mm: {reset_start}")
        metric=reset_metric

    if not seen_piece:
        raise RuntimeError(f"v1.110 sparse global streamlines never reached piece {piece.name}")
    resets=[s for s in sets if s["end_reason"]=="zero_gap"]
    if not resets:
        raise RuntimeError("v1.110 global schedule produced no complete 0.600->0.400 reset")
    for a,b in zip(sets,sets[1:]):
        if a["end_reason"]=="zero_gap":
            if a["end_spacing"]["min"]>GLOBAL_WAVESET_ZERO_GAP_MM+GLOBAL_WAVESET_RESET_TOL_MM:
                raise RuntimeError(f"v1.110 reset before zero gap: {a['end_spacing']}")
            if b["global_road_count"]>=a["global_road_count"]:
                raise RuntimeError("v1.110 reset did not use fewer roads")
    out={"sets":sets,"global_cell_count":global_cell_base}
    _SCHEDULE_CACHE[key]=out
    return out


def _actual_indices_from_sparse_touch(set_rec):
    mask=np.asarray(set_rec["touch_ever"],dtype=bool); m=len(mask); n=int(set_rec["global_road_count"])
    touched=np.where(mask)[0]
    if len(touched)==0: return np.array([],dtype=int)
    # Map every touched sparse Voronoi interval to the exact discrete global road indices.
    keep=set()
    half=0.55/m
    for i in touched:
        f=i/m
        k0=int(math.floor((f-half)*n)); k1=int(math.ceil((f+half)*n))
        for k in range(k0,k1+1): keep.add(k%n)
    return np.array(sorted(keep),dtype=int)


def _reconstruct_set_local_roads(set_rec,piece):
    idx=_actual_indices_from_sparse_touch(set_rec)
    if len(idx)==0: return [],{},0.0,[]
    n=int(set_rec["global_road_count"])
    start=_closed_points_at_fractions(set_rec["start_metric"],idx.astype(float)/n)
    current=start.copy(); road_segments=[[] for _ in range(len(idx))]
    crest_by_cell={}; hidden_by_cell={}; front_err=0.0
    detailed_cells=0
    for lc in range(1,int(set_rec["cell_count"])+1):
        nxt=_INNER._advance_wave_vec(current)
        touch=_piece_touch_mask(current,nxt,piece)
        if np.any(touch):
            gc=int(set_rec["global_cell_base"]+lc)
            for j in np.where(touch)[0]:
                cell=_INNER._TEMPLATE._build_u_wave_cell(tuple(current[j]),gc)
                road_segments[j].extend(cell["segments"]); detailed_cells+=1
                front_err=max(front_err,float(cell["front_normal_error"]))
                crest_by_cell.setdefault(gc,[]).append((cell["crest"][0],cell["crest"][1]))
                hidden_by_cell.setdefault(gc,[]).append((cell["hidden_end"][0],cell["hidden_end"][1]))
                nxt[j,0]=cell["end"][0]; nxt[j,1]=cell["end"][1]
        current=nxt
    roads=[]
    for j,segs in enumerate(road_segments):
        if not segs: continue
        roads.append({"set_index":set_rec["set_index"],"road_index":int(idx[j])+1,
                      "segments":segs,"start_global":segs[0]["p0"],"end_global":segs[-1]["p1"],
                      "cell_count":len({s["cell_index"] for s in segs}),"global_road_count":n})
    hidden_vals=[]
    rt=_INNER._rt()
    for gc,crests in crest_by_cell.items():
        hiddens=hidden_by_cell[gc]
        if len(crests)>=2:
            hc=rt._waveset_hidden_surface_clearance(crests,hiddens,piece)
            if hc["samples"]: hidden_vals.append(hc["endpoint_clearance_min_mm"])
    return roads,crest_by_cell,front_err,hidden_vals


def sparse_generate_u_profile_wave_sets(piece):
    key=(piece.name,round(piece.global_x0_mm,6),round(piece.global_z0_mm,6))
    if key in _GEOMETRY_CACHE: return _GEOMETRY_CACHE[key]
    sched=sparse_global_wave_set_schedule(piece)
    emit_sets=[]; all_roads=[]; compat=[]; front_err=0.0; hidden_vals=[]
    for s in sched["sets"]:
        roads,crests,err,hvals=_reconstruct_set_local_roads(s,piece)
        front_err=max(front_err,err); hidden_vals.extend(hvals)
        if roads:
            emit_sets.append({"set_index":s["set_index"],"roads":roads,"cells":[None]*s["cell_count"],
                              "road_count":s["global_road_count"],"local_road_count":len(roads),
                              "start_spacing":s["start_spacing"],"end_spacing":s["end_spacing"],
                              "end_reason":s["end_reason"]})
            all_roads.extend(roads)
        for gc,pts in crests.items():
            if len(pts)>=2: compat.append({"role":"OPTICAL_CREST","set_index":s["set_index"],"cell_index":gc,"points_global":pts})
    if not all_roads or len(compat)<2:
        raise RuntimeError(f"v1.110 insufficient exact clipped geometry for {piece.name}")
    p=[q for s in sched["sets"] for q in s["pitch_hist"]]
    out={"sets":emit_sets,"global_sets":sched["sets"],"long_roads":all_roads,"roads":compat,
         "set_count":len(sched["sets"]),"cell_count":len(p),"long_road_count":len(all_roads),
         "pitch_min_mm":min(q["min"] for q in p),"pitch_mean_mm":sum(q["mean"] for q in p)/len(p),
         "pitch_max_mm":max(q["max"] for q in p),"front_normal_error_max":front_err,
         "hidden_projector_clearance_min_mm":min(hidden_vals) if hidden_vals else float("inf")}
    _GEOMETRY_CACHE[key]=out
    return out


def sparse_waveset_report(piece):
    w=sparse_generate_u_profile_wave_sets(piece); sets=[]
    for s in w["global_sets"]:
        sets.append({"set_index":s["set_index"],"cell_count":s["cell_count"],"road_count":s["global_road_count"],
                     "end_reason":s["end_reason"],"pitch_start_mm":s["start_spacing"]["mean"],
                     "pitch_start_min_mm":s["start_spacing"]["min"],"pitch_end_mm":s["end_spacing"]["mean"],
                     "pitch_end_min_mm":s["end_spacing"]["min"],
                     "clear_gap_start_min_mm":s["start_spacing"]["min"]-_INNER._rt().ROAD_WIDTH_MM,
                     "clear_gap_end_min_mm":s["end_spacing"]["min"]-_INNER._rt().ROAD_WIDTH_MM})
    return {"build_order":"outer_to_inner","profile_model":"SPARSE_GLOBAL_METRIC closed_equal_path direct_xyz local_u",
            "sparse_global_metric":True,"metric_samples":SPARSE_METRIC_SAMPLES,
            "set_count":w["set_count"],"cell_count":w["cell_count"],"road_count":w["long_road_count"],
            "global_road_count_first_set":w["global_sets"][0]["global_road_count"],
            "peak_mm":_INNER._TEMPLATE.WAVESET_TOTAL_PEAK_MM,"optical_rise_mm":_INNER._TEMPLATE.WAVESET_OPTICAL_RISE_MM,
            "hidden_rise_mm":_INNER._TEMPLATE.WAVESET_HIDDEN_RISE_MM,"print_feed_mm_s":_INNER._TEMPLATE.WAVESET_PRINT_FEED_MM_S,
            "pitch_mm":{"min":w["pitch_min_mm"],"mean":w["pitch_mean_mm"],"max":w["pitch_max_mm"]},
            "front_normal_error_max":w["front_normal_error_max"],
            "hidden_projector_clearance_min_mm":w["hidden_projector_clearance_min_mm"],
            "reset_center_spacing_mm":GLOBAL_WAVESET_START_MM,"minimum_center_spacing_mm":GLOBAL_WAVESET_ZERO_GAP_MM,
            "sets":sets}


def _install_sparse(inner):
    global _INNER
    _INNER=inner
    inner.SPARSE_GLOBAL_METRIC=True
    inner.SPARSE_METRIC_SAMPLES=SPARSE_METRIC_SAMPLES
    inner.global_wave_set_schedule=sparse_global_wave_set_schedule
    inner.generate_u_profile_wave_sets=sparse_generate_u_profile_wave_sets
    inner.generate_true_normal_wave_sets=sparse_generate_u_profile_wave_sets
    inner.get_true_normal_wave_sets=sparse_generate_u_profile_wave_sets
    inner.waveset_report=sparse_waveset_report


def _execute():
    global _OUTER
    _OUTER=_load_transformed_v109()
    old_patch=_OUTER._patch_closed_global
    def patched(inner):
        old_patch(inner)
        _install_sparse(inner)
    _OUTER._patch_closed_global=patched
    try:
        _OUTER._execute()
    finally:
        sys.modules.pop(_OUTER.__name__,None)


if __name__=="__main__":
    _execute()
