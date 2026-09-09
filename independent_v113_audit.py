#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, re, zipfile
from pathlib import Path

START='FC3D_V1113_WAVESETS_START'
END='FC3D_V1113_WAVESETS_END'
SEG='FC3D_V1113_U_PROFILE_SEG'
ROLE={'LEAD':0,'OPTICAL_FRONT':0,'HIDDEN_TOP':0,'RETURN':0}


def fail(msg): raise RuntimeError('V1.113 INDEPENDENT AUDIT: '+msg)

def audit(path: Path):
    path=Path(path)
    if not path.exists(): fail(f'missing package {path}')
    with zipfile.ZipFile(path,'r') as z:
        bad=z.testzip()
        if bad: fail(f'ZIP CRC failure at {bad}')
        names=set(z.namelist())
        gname='Metadata/plate_1.gcode'; mname=gname+'.md5'
        if gname not in names or mname not in names: fail('gcode/md5 sidecar missing')
        gb=z.read(gname); g=gb.decode('utf-8',errors='replace')
        side=z.read(mname).decode('ascii',errors='ignore').strip().split()[0].lower()
        md5=hashlib.md5(gb).hexdigest()
        if side!=md5: fail(f'MD5 sidecar {side} != {md5}')
        project=json.loads(z.read('Metadata/project_settings.config').decode('utf-8')) if 'Metadata/project_settings.config' in names else {}
        slice_info=z.read('Metadata/slice_info.config').decode('utf-8',errors='replace') if 'Metadata/slice_info.config' in names else ''

    lines=g.splitlines()
    starts=[i for i,l in enumerate(lines) if START in l]; ends=[i for i,l in enumerate(lines) if END in l]
    if len(starts)!=1 or len(ends)!=1 or ends[0]<=starts[0]: fail(f'wave boundaries {len(starts)}/{len(ends)}')
    block=lines[starts[0]:ends[0]+1]
    for token in ('FC3D_V1106_WAVE_ARC','FC3D_V1107_WAVE_ARC','FC3D_V1108_WAVE_ARC','FC3D_V1109_WAVE_ARC','FC3D_V1110_WAVE_ARC'):
        if token in g: fail(f'rejected contour marker survived: {token}')
    if any(re.match(r'^\s*G29\.1\b',l) for l in block): fail('G29.1 stair-step found inside direct-XYZ wave')

    segs=[l for l in block if SEG in l]
    if not segs: fail('no v1.113 u-profile extrusion segments')
    roles=dict(ROLE); total_l=0.0; total_e=0.0; hmin=1e9; hmax=-1e9; zvals=[]
    for l in segs:
        if not re.match(r'^\s*G1\b',l): fail(f'wave segment is not G1: {l}')
        for fld in ('X','Y','Z','E'):
            if not re.search(rf'\b{fld}[-+0-9.]',l): fail(f'{fld} missing from moving-XYZ extrusion: {l}')
        if 'F3000' not in l: fail(f'wave segment not F3000: {l}')
        rm=re.search(r'\brole=([A-Z_]+)',l); h0m=re.search(r'\bh0=([-+0-9.]+)',l); h1m=re.search(r'\bh1=([-+0-9.]+)',l)
        lm=re.search(r'\bL3=([-+0-9.]+)',l); em=re.search(r'\bE([-+0-9.]+)',l); zm=re.search(r'\bZ([-+0-9.]+)',l)
        if not all((rm,h0m,h1m,lm,em,zm)): fail(f'malformed segment marker: {l}')
        role=rm.group(1)
        if role not in roles: fail(f'unknown role {role}')
        h0=float(h0m.group(1)); h1=float(h1m.group(1)); L=float(lm.group(1)); E=float(em.group(1)); Z=float(zm.group(1))
        if role=='LEAD' and abs(h1-h0)>1.1e-4: fail('lead changed Z')
        if role in ('OPTICAL_FRONT','HIDDEN_TOP') and h1<=h0+1e-5: fail(f'{role} did not rise')
        if role=='RETURN' and h1>=h0-1e-5: fail('return did not descend')
        if L<=0 or E<=0: fail(f'non-positive L3/E: {l}')
        roles[role]+=1; total_l+=L; total_e+=E; hmin=min(hmin,h0,h1); hmax=max(hmax,h0,h1); zvals.append(Z)
    if not all(roles.values()): fail(f'incomplete roles {roles}')
    if hmax-hmin < 0.299: fail(f'wave physical relief only {hmax-hmin:.6f} mm')
    if max(zvals)-min(zvals) < 0.299: fail(f'executable moving-Z span only {max(zvals)-min(zvals):.6f} mm')
    epm=total_e/total_l
    if not (0.020 <= epm <= 0.024): fail(f'aggregate 3D E/mm implausible {epm:.9f}')

    road_starts=sum('FC3D_V1113_U_PROFILE_ROAD_START' in l for l in block)
    reprimes=sum('FC3D_V1113_U_PROFILE_REPRIME' in l for l in block)
    retracts=sum('FC3D_V1113_U_PROFILE_RETRACT' in l for l in block)
    road_ends=sum('FC3D_V1113_U_PROFILE_ROAD_END' in l for l in block)
    if not (road_starts==reprimes==retracts==road_ends and road_starts>20):
        fail(f'pressure-cycle counts road/reprime/retract/end={road_starts}/{reprimes}/{retracts}/{road_ends}')

    direct_layers=sorted({int(m.group(1)) for l in lines for m in [re.search(r'DIRECT_LAYER\s+V4\s+physical=(\d+)',l)] if m})
    if direct_layers[:4] != [0,1,2,3]: fail(f'expected base/base/base/wave physical layers, got {direct_layers[:8]}')
    for forbidden in ('WIPE_TOWER_START DIRECT_SOLID','FC3D_PPSPV43_FULL_H2C_SWAP_START','Vortek'):
        if forbidden in g: fail(f'forbidden executable lifecycle survived: {forbidden}')
    if 'A1 mini' not in (json.dumps(project)+slice_info+g): fail('A1 mini identity not found')

    report={'result':'PASS','package':path.name,'md5':md5,'u_profile_segments':len(segs),'u_profile_paths':road_starts,
            'role_counts':roles,'moving_z_span_mm':max(zvals)-min(zvals),'physical_h_span_mm':hmax-hmin,
            'aggregate_e_per_3d_mm':epm,'direct_layers':direct_layers[:8],'g29_inside_wave':0}
    print(json.dumps(report,indent=2,sort_keys=True)); return report

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('package',type=Path); ns=ap.parse_args()
    audit(ns.package)
