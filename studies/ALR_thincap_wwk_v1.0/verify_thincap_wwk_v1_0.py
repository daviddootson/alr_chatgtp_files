#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,sys,csv,json,time
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('study',HERE/'ALR_thincap_wwk_v1_0.py')
study=importlib.util.module_from_spec(spec);sys.modules[spec.name]=study;spec.loader.exec_module(study)
CASES=[
 ('full_wwk',.24,.24,60,0.),
 ('thin24_k08_v50',.24,.08,50,0.),('thin24_k10_v40',.24,.10,40,0.),('thin24_k10_v45',.24,.10,45,0.),
 ('thin24_k10_v50',.24,.10,50,0.),('thin24_k10_v55',.24,.10,55,0.),('thin24_k10_v60',.24,.10,60,0.),
 ('thin24_k12_v50',.24,.12,50,0.),('thin22_k10_v50',.22,.10,50,0.),
 ('thin22_k10_v50_p05',.22,.10,50,.05),('thin24_k10_v40_p10',.24,.10,40,.10),('thin24_k10_v45_p05',.24,.10,45,.05),
]
def ix(v,r):return 100*v[0]/r[0],100*v[1]/r[1],100*(v[0]/v[1])/(r[0]/r[1])
def run():
 out=HERE/'verification';out.mkdir(exist_ok=True);res=(1536,128,768);ref,_=study.score_reference(*res,grid=3);rows=[];st=time.time()
 for name,w,k,V,po in CASES:
  r=study.score_case(w,k,V,po,rays=res[0],segments=res[1],ambient=res[2],grid=3)
  B,A,C=ix(r['response'],ref);centre=[x for x in r['records'] if x['offset_mm']==0]
  rows.append(dict(case=name,w_dose=w,k_cap_dose=k,V=V,pitch_offset_mm=po,pitch_mean_mm=float(np.mean([x['pitch_mm'] for x in centre])),
    dark_band_mean_mm=float(np.mean([x['dark_band_mm'] for x in centre])),dark_band_max_mm=float(np.max([x['dark_band_mm'] for x in centre])),
    actual_white_fraction_mean=float(np.mean([x['actual_target_white_fraction'] for x in centre])),target_met_all=r['target_met_all'],B_index=B,A_index=A,C_index=C))
  print(name,rows[-1],flush=True)
 with (out/'highres_selected_v1.0.csv').open('w',newline='') as f:wri=csv.DictWriter(f,fieldnames=list(rows[0]));wri.writeheader();wri.writerows(rows)
 (out/'highres_metadata_v1.0.json').write_text(json.dumps(dict(resolution=res,rows=len(rows),seconds=time.time()-st),indent=2)+'\n')
if __name__=='__main__':run()
