#!/usr/bin/env python3
"""FC3D v1.108: global-screen wave-set packing with local-u direct XYZ roads.

v1.107 proved the corrected print-head direction but incorrectly seeded each set
from the clipped coupon.  v1.108 defines set phase globally across the 100-inch
screen.  A complete global set starts with neighbouring u-streamlines at 0.600
mm centres, advances complete wave cells inward until the global minimum spacing
reaches 0.400 mm, then resamples that complete contour at 0.600 mm with fewer
roads.  The selected coupon only clips the already-defined global roads.

The wave itself remains the v1.107 direct-XYZ topology: +u flat lead,
-u,+Z exact optical front, +u,+Z shallow hidden top, +u,-Z return.
"""
from __future__ import annotations

import hashlib
import math
import sys
import types
from pathlib import Path

import numpy as np

SCRIPT_VERSION = "3dprint_black_mirror_wave_grid_v1.108"
REAR_VERSION_TEXT = "108"
BASE_SCRIPT_VERSION = "3dprint_black_mirror_wave_grid_v1.107"
EXPECTED_V107_GIT_BLOB_SHA1 = "ddb421f4cedd90780c4921b0c81105d00ea45f4b"
GLOBAL_WAVESET_MODEL = "global_equal_optical_path_contour_then_local_u_flow"
GLOBAL_WAVESET_START_MM = 0.600
GLOBAL_WAVESET_ZERO_GAP_MM = 0.400
GLOBAL_WAVESET_RESET_TOL_MM = 0.002
GLOBAL_WAVESET_PIECE_HALO_MM = 3.0
GLOBAL_WAVESET_EXIT_GUARD_CELLS = 20
GLOBAL_WAVESET_MAX_SETS = 8
GLOBAL_WAVESET_MAX_CELLS_PER_SET = 1200
GLOBAL_OUTER_CONTOUR_X_STEP_MM = 0.50
SEGMENT_MARKER = "FC3D_V1108_U_PROFILE_SEG"
DIRECT_Z_MODEL = "direct_xyz"

_TEMPLATE = None
_GLOBAL_CACHE = {}


def _git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _load_v107_template():
    here = Path(__file__).resolve()
    base = here.with_name(here.name.replace("v1.108", "v1.107", 1))
    if not base.exists():
        raise FileNotFoundError(f"{SCRIPT_VERSION}: predecessor {base.name} not found")
    data = base.read_bytes()
    got = _git_blob_sha1(data)
    if got != EXPECTED_V107_GIT_BLOB_SHA1:
        raise RuntimeError(f"{SCRIPT_VERSION}: v1.107 git-blob SHA drift {got} != {EXPECTED_V107_GIT_BLOB_SHA1}")
    src = data.decode("utf-8")
    for old, new in (("v1.107", "v1.108"), ("V1107", "V1108"), ("v1107", "v1108"), ("v107", "v108")):
        src = src.replace(old, new)
    name = "__fc3d_alr_v1108_template__"
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


def _rt():
    if _TEMPLATE is None:
        raise RuntimeError(f"{SCRIPT_VERSION}: template not installed")
    return _TEMPLATE._rt()


def _optical_path_vec(x, z):
    rt = _rt()
    f = rt.MASTER_FAN
    x = np.asarray(x, dtype=float)
    z = np.asarray(z, dtype=float)
    rp = np.sqrt((x-f.projector_x_mm)**2 + (z-f.projector_z_mm)**2 + f.projector_distance_mm**2)
    rv = np.sqrt((x-f.viewer_x_mm)**2 + (z-f.viewer_z_mm)**2 + f.viewer_distance_mm**2)
    return rp + rv


def _b_and_tan_vec(x, z):
    rt = _rt(); f = rt.MASTER_FAN
    x = np.asarray(x, dtype=float); z = np.asarray(z, dtype=float)
    dxp=f.projector_x_mm-x; dzp=f.projector_z_mm-z
    dxv=f.viewer_x_mm-x; dzv=f.viewer_z_mm-z
    rp=np.sqrt(dxp*dxp+dzp*dzp+f.projector_distance_mm**2)
    rv=np.sqrt(dxv*dxv+dzv*dzv+f.viewer_distance_mm**2)
    nx=dxp/rp+dxv/rv; nz=dzp/rp+dzv/rv
    nh=f.projector_distance_mm/rp+f.viewer_distance_mm/rv
    m=np.hypot(nx,nz)
    if np.any(m <= 1e-12):
        raise RuntimeError("v1.108 degenerate projected bisecting-normal field")
    return nx/m, nz/m, m/np.maximum(nh,1e-12)


def _outer_global_contour():
    rt=_rt(); f=rt.MASTER_FAN
    W=float(f.screen_width_mm); H=float(f.screen_height_mm)
    corners=np.array([[0.0,0.0],[W,0.0],[0.0,H],[W,H]],dtype=float)
    target=float(np.max(_optical_path_vec(corners[:,0],corners[:,1])))
    n=max(3,int(math.ceil(W/GLOBAL_OUTER_CONTOUR_X_STEP_MM))+1)
    x=np.linspace(0.0,W,n)
    lo=np.full_like(x,H); hi=np.full_like(x,H+W+1000.0)
    for _ in range(60):
        mid=0.5*(lo+hi)
        low=_optical_path_vec(x,mid) < target
        lo=np.where(low,mid,lo); hi=np.where(low,hi,mid)
    z=0.5*(lo+hi)
    return np.column_stack([x,z])


def _sample_polyline_pitch(points, pitch=GLOBAL_WAVESET_START_MM):
    p=np.asarray(points,dtype=float)
    d=np.hypot(np.diff(p[:,0]),np.diff(p[:,1])); cum=np.concatenate(([0.0],np.cumsum(d)))
    total=float(cum[-1])
    if total < pitch:
        return np.empty((0,2),dtype=float)
    intervals=int(math.floor(total/pitch))
    residual=total-intervals*pitch
    targets=residual*0.5+np.arange(intervals+1,dtype=float)*pitch
    return np.column_stack([np.interp(targets,cum,p[:,0]),np.interp(targets,cum,p[:,1])])


def _spacing_np(points):
    p=np.asarray(points,dtype=float)
    d=np.hypot(np.diff(p[:,0]),np.diff(p[:,1]))
    if len(d)==0: return None
    return {"min":float(np.min(d)),"mean":float(np.mean(d)),"max":float(np.max(d)),"samples":int(len(d))}


def _advance_plus_u_vec(points, distance):
    p=np.asarray(points,dtype=float).copy(); rem=float(distance)
    while rem>1e-12:
        ds=min(float(_TEMPLATE.WAVESET_MAX_STEP_MM),rem)
        bx,bz,_=_b_and_tan_vec(p[:,0],p[:,1])
        mid=p+0.5*ds*np.column_stack([bx,bz])
        bx,bz,_=_b_and_tan_vec(mid[:,0],mid[:,1])
        p += ds*np.column_stack([bx,bz]); rem-=ds
    return p


def _advance_front_vec(points):
    p=np.asarray(points,dtype=float).copy(); h=np.zeros(len(p),dtype=float)
    target=float(_TEMPLATE.WAVESET_OPTICAL_RISE_MM); step=float(_TEMPLATE.WAVESET_MAX_STEP_MM)
    for _ in range(200):
        rem=target-h; active=rem>1e-11
        if not np.any(active): return p
        bx,bz,tan=_b_and_tan_vec(p[:,0],p[:,1])
        ds0=np.minimum(step,rem/np.maximum(tan,1e-12)); ds0=np.where(active,ds0,0.0)
        mid=p-0.5*ds0[:,None]*np.column_stack([bx,bz])
        bxm,bzm,tanm=_b_and_tan_vec(mid[:,0],mid[:,1])
        ds=np.minimum(step,rem/np.maximum(tanm,1e-12)); ds=np.where(active,ds,0.0)
        p -= ds[:,None]*np.column_stack([bxm,bzm])
        h=np.minimum(target,h+tanm*ds)
    raise RuntimeError("v1.108 vector optical-front integration guard tripped")


def _advance_wave_vec(points):
    p=_advance_plus_u_vec(points,_TEMPLATE.WAVESET_BASE_LEAD_MM)
    p=_advance_front_vec(p)
    p=_advance_plus_u_vec(p,_TEMPLATE.WAVESET_HIDDEN_RUN_MM)
    p=_advance_plus_u_vec(p,_TEMPLATE.WAVESET_RETURN_RUN_MM)
    return p


def _piece_touch_mask(a,b,piece):
    h=GLOBAL_WAVESET_PIECE_HALO_MM
    xmin=piece.global_x0_mm-h; xmax=piece.global_x1_mm+h
    zmin=piece.global_z0_mm-h; zmax=piece.global_z1_mm+h
    lo_x=np.minimum(a[:,0],b[:,0]); hi_x=np.maximum(a[:,0],b[:,0])
    lo_z=np.minimum(a[:,1],b[:,1]); hi_z=np.maximum(a[:,1],b[:,1])
    return (hi_x>=xmin)&(lo_x<=xmax)&(hi_z>=zmin)&(lo_z<=zmax)


def global_wave_set_schedule(piece):
    """Build global 0.600->0.400 set phase before coupon clipping."""
    key=(piece.name,round(piece.global_x0_mm,6),round(piece.global_z0_mm,6))
    if key in _GLOBAL_CACHE: return _GLOBAL_CACHE[key]
    current=_sample_polyline_pitch(_outer_global_contour())
    if len(current)<10: raise RuntimeError("v1.108 global outer contour produced too few roads")
    sets=[]; global_cell=0; piece_done=False
    for set_idx in range(1,GLOBAL_WAVESET_MAX_SETS+1):
        start=current.copy(); start_sp=_spacing_np(start); n=len(start)
        first=np.full(n,-1,dtype=int); last=np.full(n,-1,dtype=int); entry=np.full((n,2),np.nan)
        pitch_hist=[]; no_touch_after_seen=0; seen=False; base_global_cell=global_cell
        end_reason=None
        for local_cell in range(1,GLOBAL_WAVESET_MAX_CELLS_PER_SET+1):
            nxt=_advance_wave_vec(current); global_cell+=1
            sp=_spacing_np(nxt); pitch_hist.append(sp)
            touch=_piece_touch_mask(current,nxt,piece)
            new=touch&(first<0)
            if np.any(new): entry[new]=current[new]; first[new]=local_cell
            last[touch]=local_cell
            if np.any(touch):
                seen=True; no_touch_after_seen=0
            elif seen:
                no_touch_after_seen+=1
            current=nxt
            if sp["min"] <= GLOBAL_WAVESET_ZERO_GAP_MM+GLOBAL_WAVESET_RESET_TOL_MM:
                end_reason="zero_gap"; break
            if seen and no_touch_after_seen>=GLOBAL_WAVESET_EXIT_GUARD_CELLS:
                end_reason="piece_complete"; piece_done=True; break
        if end_reason is None: raise RuntimeError(f"v1.108 set {set_idx} exceeded cell guard")
        sets.append({
            "set_index":set_idx,"start_points":start,"end_points":current.copy(),
            "global_road_count":n,"start_spacing":start_sp,"end_spacing":pitch_hist[-1],
            "pitch_hist":pitch_hist,"cell_count":len(pitch_hist),"end_reason":end_reason,
            "first_touch":first,"last_touch":last,"entry_points":entry,"global_cell_base":base_global_cell,
        })
        if piece_done: break
        if end_reason!="zero_gap": break
        reset=_sample_polyline_pitch(current)
        if len(reset)>=n:
            raise RuntimeError(f"v1.108 reset failed to reduce road count {len(reset)} >= {n}")
        rsp=_spacing_np(reset)
        if rsp["min"] < GLOBAL_WAVESET_START_MM-GLOBAL_WAVESET_RESET_TOL_MM:
            raise RuntimeError(f"v1.108 reset start too tight {rsp}")
        current=reset
    if not any(np.any(s["first_touch"]>=0) for s in sets):
        raise RuntimeError(f"v1.108 global sets never intersected piece {piece.name}")
    for a,b in zip(sets,sets[1:]):
        if a["end_reason"]=="zero_gap":
            if a["end_spacing"]["min"]>GLOBAL_WAVESET_ZERO_GAP_MM+GLOBAL_WAVESET_RESET_TOL_MM:
                raise RuntimeError(f"v1.108 reset before zero gap: {a['end_spacing']}")
            if b["global_road_count"]>=a["global_road_count"]:
                raise RuntimeError("v1.108 global road count did not fall at reset")
            if abs(b["start_spacing"]["mean"]-GLOBAL_WAVESET_START_MM)>0.003:
                raise RuntimeError(f"v1.108 reset did not return to 0.600 mm: {b['start_spacing']}")
    _GLOBAL_CACHE[key]={"sets":sets,"global_cell_count":global_cell}
    return _GLOBAL_CACHE[key]


def generate_u_profile_wave_sets(piece):
    sched=global_wave_set_schedule(piece); rt=_rt()
    emit_sets=[]; long_roads=[]; compat_by_cell={}; front_err=0.0; hidden_vals=[]
    global_pitch=[]; local_cell_total=0
    for gs in sched["sets"]:
        global_pitch.extend(gs["pitch_hist"])
        ids=np.where(gs["first_touch"]>=0)[0]
        local=[]
        for idx in ids:
            first=int(gs["first_touch"][idx]); last=int(gs["last_touch"][idx])
            p=tuple(float(v) for v in gs["entry_points"][idx]); segs=[]
            for lc in range(first,last+1):
                gc=int(gs["global_cell_base"]+lc)
                cell=_TEMPLATE._build_u_wave_cell(p,gc)
                segs.extend(cell["segments"]); front_err=max(front_err,float(cell["front_normal_error"]))
                crest=(cell["crest"][0],cell["crest"][1]); hidden=(cell["hidden_end"][0],cell["hidden_end"][1])
                compat_by_cell.setdefault((gs["set_index"],gc),[]).append(crest)
                hc=rt._waveset_hidden_surface_clearance([crest],[hidden],piece)
                if hc["samples"]: hidden_vals.append(hc["endpoint_clearance_min_mm"])
                p=(cell["end"][0],cell["end"][1])
            if segs:
                rec={"set_index":gs["set_index"],"road_index":int(idx)+1,"segments":segs,
                     "start_global":segs[0]["p0"],"end_global":segs[-1]["p1"],"cell_count":last-first+1,
                     "global_road_count":gs["global_road_count"]}
                local.append(rec); long_roads.append(rec); local_cell_total+=last-first+1
        if local:
            emit_sets.append({"set_index":gs["set_index"],"roads":local,"cells":[None]*gs["cell_count"],
                              "road_count":gs["global_road_count"],"local_road_count":len(local),
                              "start_spacing":gs["start_spacing"],"end_spacing":gs["end_spacing"],
                              "end_reason":gs["end_reason"]})
    compat=[]
    for (si,ci),pts in sorted(compat_by_cell.items()):
        if len(pts)>=2: compat.append({"role":"OPTICAL_CREST","set_index":si,"cell_index":ci,"points_global":pts})
    if not long_roads or len(compat)<2: raise RuntimeError(f"v1.108 insufficient clipped global geometry for {piece.name}")
    mins=[p["min"] for p in global_pitch]; means=[p["mean"] for p in global_pitch]; maxs=[p["max"] for p in global_pitch]
    out={"sets":emit_sets,"global_sets":sched["sets"],"long_roads":long_roads,"roads":compat,
         "set_count":len(sched["sets"]),"cell_count":len(global_pitch),"long_road_count":len(long_roads),
         "pitch_min_mm":min(mins),"pitch_mean_mm":sum(means)/len(means),"pitch_max_mm":max(maxs),
         "front_normal_error_max":front_err,
         "hidden_projector_clearance_min_mm":min(hidden_vals) if hidden_vals else float("inf"),
         "local_detailed_cell_count":local_cell_total}
    return out


def get_true_normal_wave_sets(piece): return generate_u_profile_wave_sets(piece)


def waveset_report(piece):
    w=generate_u_profile_wave_sets(piece)
    sets=[]
    for s in w["global_sets"]:
        sets.append({"set_index":s["set_index"],"cell_count":s["cell_count"],"road_count":s["global_road_count"],
                     "end_reason":s["end_reason"],"pitch_start_mm":s["start_spacing"]["mean"],
                     "pitch_start_min_mm":s["start_spacing"]["min"],"pitch_end_mm":s["end_spacing"]["mean"],
                     "pitch_end_min_mm":s["end_spacing"]["min"],
                     "clear_gap_start_min_mm":s["start_spacing"]["min"]-_rt().ROAD_WIDTH_MM,
                     "clear_gap_end_min_mm":s["end_spacing"]["min"]-_rt().ROAD_WIDTH_MM})
    return {"build_order":"outer_to_inner","profile_model":"GLOBAL_WAVESET direct_xyz local_u",
            "global_wave_set_schedule":True,"set_count":w["set_count"],"cell_count":w["cell_count"],
            "road_count":w["long_road_count"],"global_road_count_first_set":w["global_sets"][0]["global_road_count"],
            "peak_mm":_TEMPLATE.WAVESET_TOTAL_PEAK_MM,"optical_rise_mm":_TEMPLATE.WAVESET_OPTICAL_RISE_MM,
            "hidden_rise_mm":_TEMPLATE.WAVESET_HIDDEN_RISE_MM,"print_feed_mm_s":_TEMPLATE.WAVESET_PRINT_FEED_MM_S,
            "pitch_mm":{"min":w["pitch_min_mm"],"mean":w["pitch_mean_mm"],"max":w["pitch_max_mm"]},
            "front_normal_error_max":w["front_normal_error_max"],
            "hidden_projector_clearance_min_mm":w["hidden_projector_clearance_min_mm"],
            "reset_center_spacing_mm":GLOBAL_WAVESET_START_MM,"minimum_center_spacing_mm":GLOBAL_WAVESET_ZERO_GAP_MM,
            "sets":sets}


def _install_global_v108(runtime):
    old_install=_TEMPLATE.__dict__.get("_v108_original_install")
    old_install(runtime)
    for ns in (_TEMPLATE.__dict__,runtime.__dict__):
        ns["generate_u_profile_wave_sets"]=generate_u_profile_wave_sets
        ns["generate_true_normal_wave_sets"]=generate_u_profile_wave_sets
        ns["get_true_normal_wave_sets"]=get_true_normal_wave_sets
        ns["waveset_report"]=waveset_report
        ns["GLOBAL_WAVESET_MODEL"]=GLOBAL_WAVESET_MODEL
        ns["GLOBAL_WAVESET_START_MM"]=GLOBAL_WAVESET_START_MM
        ns["GLOBAL_WAVESET_ZERO_GAP_MM"]=GLOBAL_WAVESET_ZERO_GAP_MM
    inherited=runtime.__dict__.get("dry_validate_v1108")
    if callable(inherited):
        def dry_validate_v1108(dp):
            inherited(dp); rep=waveset_report(runtime._current_piece())
            first=rep["sets"][0]
            if abs(first["pitch_start_mm"]-0.600)>0.003:
                raise RuntimeError(f"v1.108 first global set does not start at 0.600: {first}")
            resets=[s for s in rep["sets"] if s["end_reason"]=="zero_gap"]
            if not resets:
                raise RuntimeError(f"v1.108 no complete 0.600->0.400 global reset before piece: {rep}")
            for s in resets:
                if s["pitch_end_min_mm"]>0.402:
                    raise RuntimeError(f"v1.108 zero-gap set ended too wide: {s}")
            print("  v1.108 global spacing audit  : PASS")
            print(f"  global first-set roads        : {rep['global_road_count_first_set']}")
            for s in rep["sets"]:
                print(f"  GLOBAL set {s['set_index']:2d}: roads={s['road_count']:4d} cells={s['cell_count']:4d} spacing {s['pitch_start_min_mm']:.4f}->{s['pitch_end_min_mm']:.4f} reason={s['end_reason']}")
        runtime.__dict__["dry_validate_v1108"]=dry_validate_v1108


def _execute():
    global _TEMPLATE
    _TEMPLATE=_load_v107_template()
    original=_TEMPLATE.__dict__.get("_install_v108")
    if not callable(original): raise RuntimeError("v1.108 transformed template lacks _install_v108")
    _TEMPLATE.__dict__["_v108_original_install"]=original
    _TEMPLATE.__dict__["_install_v108"]=_install_global_v108
    try:
        _TEMPLATE._execute_v108()
    finally:
        sys.modules.pop(_TEMPLATE.__name__,None)


if __name__ == "__main__":
    _execute()
