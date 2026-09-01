#!/usr/bin/env python3
"""Diagnostic only: find the outermost full-span transverse contour for v1.107."""
from __future__ import annotations
import importlib.util
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location("v107probe", HERE/"3dprint_black_mirror_wave_grid_v1.107.py")
mod=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(mod)
rt=mod._load_runtime(); mod._RUNTIME=rt
piece=rt.PieceSpec.for_name("1-2")
lat=rt.get_mirror_wave_lattice(piece)


def plen(pts):
    return sum(math.hypot(b[0]-a[0],b[1]-a[1]) for a,b in zip(pts,pts[1:]))

recs=[]
for rec in lat["main_a_curves"]:
    clips=rt._clip_polyline2_to_piece(rec["points"],piece)
    if len(clips)!=1: continue
    pts=clips[0]; L=plen(pts)
    if L<=1e-9: continue
    rr=sum(math.hypot(x-rt.MASTER_FAN.projector_x_mm,z-rt.MASTER_FAN.projector_z_mm) for x,z in pts)/len(pts)
    recs.append((L,rr,pts,rec["wave"],rec["family"]))
print("candidate_count",len(recs))
mx=max(x[0] for x in recs)
print("max_clipped_length",mx)


def point_at(pts,target):
    acc=0.0
    for a,b in zip(pts,pts[1:]):
        ds=math.hypot(b[0]-a[0],b[1]-a[1])
        if acc+ds>=target-1e-12:
            t=0.0 if ds<=1e-12 else max(0.0,min(1.0,(target-acc)/ds))
            return (a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1]))
        acc+=ds
    return pts[-1]


def fixed_pitch(pts,pitch=0.600):
    L=plen(pts); intervals=int(math.floor(L/pitch));
    if intervals<1:return []
    used=intervals*pitch; off=0.5*(L-used)
    return [point_at(pts,off+i*pitch) for i in range(intervals+1)]


def spacing(pts):
    v=[math.hypot(b[0]-a[0],b[1]-a[1]) for a,b in zip(pts,pts[1:])]
    return min(v),sum(v)/len(v),max(v)

for frac in (0.90,0.95,0.98,0.99,0.995):
    pool=[r for r in recs if r[0]>=mx*frac]
    sel=max(pool,key=lambda x:x[1])
    pts=fixed_pitch(sel[2])
    print("SELECT",frac,"wave",sel[3],"family",sel[4],"L",sel[0],"radius",sel[1],"roads",len(pts),"start_spacing",spacing(pts))
    cur=pts
    for cell_i in range(1,401):
        nxt=[]
        for p in cur:
            c=mod._build_u_wave_cell(p,cell_i)
            nxt.append((c["end"][0],c["end"][1]))
        cur=nxt
        sp=spacing(cur)
        if cell_i in (1,10,25,50,100,150,200,250,300,350,400) or sp[0]<=0.402:
            print(" STEP",frac,cell_i,"minmeanmax",sp)
        if sp[0]<=0.402:
            print(" ZERO_GAP",frac,"cell",cell_i,"roads",len(cur)); break
        if not mod._curve_still_intersects_piece(cur,piece):
            print(" BOUNDARY",frac,"cell",cell_i,"spacing",sp); break
