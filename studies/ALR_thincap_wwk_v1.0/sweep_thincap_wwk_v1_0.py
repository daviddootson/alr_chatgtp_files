#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,sys,csv,json,time
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('study',HERE/'ALR_thincap_wwk_v1_0.py')
study=importlib.util.module_from_spec(spec);sys.modules[spec.name]=study;spec.loader.exec_module(study)

def indices(v,ref): return 100*v[0]/ref[0],100*v[1]/ref[1],100*(v[0]/v[1])/(ref[0]/ref[1])
def row_from(wd,kd,V,po,r,ref):
    B,A,C=indices(r['response'],ref);centre=[x for x in r['records'] if x['offset_mm']==0][0]
    return dict(w_dose=wd,k_cap_dose=kd,V=V,pitch_offset_mm=po,auto_pitch_mm=centre['auto_pitch_mm'],pitch_mm=centre['pitch_mm'],
        total_height_mm=study.total_height(wd,kd,1.2),dark_band_mm=centre['dark_band_mm'],actual_white_fraction=centre['actual_target_white_fraction'],
        target_met=bool(r['target_met_all']),physical_all=bool(r['physical_all']),B_index=B,A_index=A,C_index=C)
def write_csv(path,rows):
    with path.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def run():
    out=HERE/'results'/'coarse';out.mkdir(parents=True,exist_ok=True)
    rays,segments,ambient,grid=224,44,112,1
    ref,_=study.score_reference(rays,segments,ambient,grid)
    w_doses=[.20,.22,.24];caps=[.06,.08,.10,.12,.14,.16,.18,.20,.22,.24];vis=list(range(35,81,5))
    rows=[];start=time.time()
    for wd in w_doses:
      for kd in caps:
       if kd<=wd+1e-12:
        for V in vis:
          r=study.score_case(wd,kd,V,0,rays=rays,segments=segments,ambient=ambient,grid=grid)
          if r:rows.append(row_from(wd,kd,V,0,r,ref))
    write_csv(out/'auto_sweep_v1.0.csv',rows)
    # Pick broad candidate pool: high contrast, small dark band, high brightness, plus cap=0.10 cases.
    cand={}
    def add(seq):
      for r in seq:cand[(r['w_dose'],r['k_cap_dose'],r['V'])]=r
    add(sorted(rows,key=lambda r:r['C_index'],reverse=True)[:18])
    add(sorted(rows,key=lambda r:r['dark_band_mm'])[:18])
    add(sorted(rows,key=lambda r:r['B_index'],reverse=True)[:12])
    add([r for r in rows if abs(r['k_cap_dose']-.10)<1e-9 and r['V'] in (40,45,50,55,60,65,70)])
    # Local spacing probes around the auto solver. Negative offsets are retained only when physically valid.
    probes=[]
    for wd,kd,V in sorted(cand):
      for po in (-.05,-.025,.025,.05,.075,.10,.15):
        r=study.score_case(wd,kd,V,po,rays=rays,segments=segments,ambient=ambient,grid=grid)
        if r:probes.append(row_from(wd,kd,V,po,r,ref))
    write_csv(out/'pitch_probe_v1.0.csv',probes)
    meta=dict(version='1.0',reference='PETG KWK L0.20 S1.2 V70 H0 v156',resolution=dict(rays=rays,segments=segments,ambient=ambient,grid=grid),
              w_doses=w_doses,k_cap_doses=caps,visibility=vis,auto_rows=len(rows),probe_rows=len(probes),seconds=time.time()-start)
    (out/'coarse_metadata_v1.0.json').write_text(json.dumps(meta,indent=2)+'\n')
    print('auto',len(rows),'probes',len(probes),'seconds',meta['seconds'])
    # Write compact top tables for inspection.
    allrows=rows+probes
    for name,key,reverse in [('contrast','C_index',True),('brightness','B_index',True),('darkband','dark_band_mm',False)]:
      (out/f'top_{name}_v1.0.json').write_text(json.dumps(sorted(allrows,key=lambda r:r[key],reverse=reverse)[:40],indent=2)+'\n')
if __name__=='__main__':run()
