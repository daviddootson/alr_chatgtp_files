#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,sys,csv,json,time
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('study',HERE/'ALR_thincap_wwk_v1_0.py')
study=importlib.util.module_from_spec(spec);sys.modules[spec.name]=study;spec.loader.exec_module(study)

def indices(v,ref):return 100*v[0]/ref[0],100*v[1]/ref[1],100*(v[0]/v[1])/(ref[0]/ref[1])
def run_one(wd,kd,V,po,ref,res):
 r=study.score_case(wd,kd,V,po,rays=res[0],segments=res[1],ambient=res[2],grid=3)
 if not r:return None
 B,A,C=indices(r['response'],ref);centre=[x for x in r['records'] if x['offset_mm']==0]
 p=[x['pitch_mm'] for x in centre];ap=[x['auto_pitch_mm'] for x in centre]
 # Per-view projector response isn't directly retained; geometry uniformity is represented by lit fraction/dark band only.
 return dict(w_dose=wd,k_cap_dose=kd,V=V,pitch_offset_mm=po,pitch_mean_mm=float(np.mean(p)),pitch_min_mm=float(np.min(p)),pitch_max_mm=float(np.max(p)),auto_pitch_mean_mm=float(np.mean(ap)),
   total_height_mm=study.total_height(wd,kd,1.2),dark_band_mean_mm=float(np.mean([x['dark_band_mm'] for x in centre])),dark_band_max_mm=float(np.max([x['dark_band_mm'] for x in centre])),
   actual_white_fraction_mean=float(np.mean([x['actual_target_white_fraction'] for x in centre])),target_met_all=bool(r['target_met_all']),physical_all=bool(r['physical_all']),B_index=B,A_index=A,C_index=C)
def selected():
 s=set()
 def add(w,k,V,offs=(0.,)):
  for o in offs:s.add((w,k,V,o))
 add(.24,.24,60)
 for V in range(35,81,5):add(.24,.10,V)
 for V in (40,45,50,55,60,65):add(.22,.10,V)
 for k in (.06,.08,.10,.12,.14,.16,.18):add(.24,k,50)
 add(.24,.10,40,(-.025,.025,.05,.10))
 add(.24,.10,45,(-.05,-.025,.025,.05,.10))
 add(.24,.10,50,(-.05,-.025,.025,.05,.10))
 add(.24,.10,55,(-.05,.025,.05,.10))
 add(.22,.10,45,(-.025,.025,.05,.10))
 add(.22,.10,50,(-.05,-.025,.025,.05,.10))
 return sorted(s)
def write(path,rows):
 with path.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main():
 out=HERE/'results'/'fine';out.mkdir(parents=True,exist_ok=True);res=(640,72,320);ref,rr=study.score_reference(*res,grid=3)
 rows=[];start=time.time()
 for i,c in enumerate(selected(),1):
  r=run_one(*c,ref,res)
  if r:rows.append(r)
  if rows: write(out/'fine_selected_v1.0.csv',rows)
  print(i,'/',len(selected()),c,'ok' if r else 'invalid',flush=True)
 write(out/'fine_selected_v1.0.csv',rows)
 meta=dict(version='1.0',reference='PETG KWK L0.20 S1.2 V70 H0 v156',resolution=dict(rays=res[0],segments=res[1],ambient=res[2],grid=3),rows=len(rows),seconds=time.time()-start)
 (out/'fine_metadata_v1.0.json').write_text(json.dumps(meta,indent=2)+'\n')
 for name,key,rev in [('contrast','C_index',True),('dark','dark_band_mean_mm',False)]:
  (out/f'top_{name}_fine_v1.0.json').write_text(json.dumps(sorted(rows,key=lambda x:x[key],reverse=rev)[:25],indent=2)+'\n')
 print('done',len(rows),'seconds',meta['seconds'])
if __name__=='__main__':main()
