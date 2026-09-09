#!/usr/bin/env python3
import importlib.util,sys,numpy as np,json,time
from pathlib import Path
p=Path(__file__).resolve().parent/'wk_landscape_v1.py'
sp=importlib.util.spec_from_file_location('wk',p);wk=importlib.util.module_from_spec(sp);sys.modules['wk']=wk;sp.loader.exec_module(wk)
cap=wk.cap;mat=wk.prepare_material();offs=wk.VIEW_OFFSETS;weights=wk.VIEW_WEIGHTS
R=(1536,128,768)
cases=[
('WK_best_contrast',.225,.140,1.30,78),
('WK_compact_bal',.225,.130,1.30,72),
('WK_bright_compact',.220,.120,1.30,78),
('WK_low_ambient',.225,.160,1.30,76),
('WK_refined_best',.225,.145,1.30,78),
('WK_mid_cap',.225,.150,1.30,78),
]
cap.W_DOSE=.24;cap.K_DOSE=.16;cap.SCALE=1.3;cap.V=77.
ref=cap.score_layout('single',0,*R,grid=3,view_offsets=offs,white_samples_n=384,material=mat);rm=cap.weighted_metrics(ref)
out={'reference':{'pitch':ref['pitch_mean_mm'],'dark':rm['dark_band_mm'],'B_views':rm['B_views'].tolist(),'A_views':rm['A_views'].tolist(),'C_views':rm['C_views'].tolist()},'cases':[]}
print('REF pitch',ref['pitch_mean_mm'],'dark',rm['dark_band_mm'],flush=True);t=time.time()
for name,w,k,s,v in cases:
 sc=wk.score_case(w,k,s,v,*R,grid=3,view_offsets=offs,white_samples_n=384,material=mat)
 if sc is None: print(name,'INFEAS');continue
 m=wk.metrics(sc,weights,offs);ii=wk.idx(m,rm)
 rec={'name':name,'W':w,'K':k,'S':s,'V':v,'pitch':sc['pitch_mean_mm'],'pitch_change_pct':100*(sc['pitch_mean_mm']/ref['pitch_mean_mm']-1),'dark':m['dark_band_mm'],'dark_change_pct':100*(m['dark_band_mm']/rm['dark_band_mm']-1),'height':sc['total_height_mm'],'B':ii['B'],'A':ii['A'],'C':ii['C'],'B_views_index':(100*m['B_views']/rm['B_views']).tolist(),'A_views_index':(100*m['A_views']/rm['A_views']).tolist(),'C_views_index':(100*m['C_views']/rm['C_views']).tolist(),'dark_views':m['dark_views'].tolist(),'white':sc['actual_white_fraction_mean']}
 out['cases'].append(rec);print(json.dumps(rec),flush=True)
(Path(__file__).resolve().parent/'final_highres.json').write_text(json.dumps(out,indent=2)+'\n')
print('SEC',time.time()-t)
