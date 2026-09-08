#!/usr/bin/env python3
"""Compact KKWWK 3-3-3-2-1 local optical study v1.0.

Analysis only, not printer G-code. Uses the archived v1.2 material model and
local reconstructed v156 mapped-white spacing law. The compact geometry keeps
upper WWK tier offsets unchanged and places the two lower K tiers vertically
under the three-road W tier: road counts 3-3-3-2-1.
"""
from __future__ import annotations
import argparse, importlib.util, json, math, sys, time, hashlib
from pathlib import Path
import numpy as np

VERSION='1.0'
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('matv12',HERE/'material_model_v1_2.py')
mat=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mat;spec.loader.exec_module(mat)
geo=mat.geo

PROFILES={
    'standard54321': {'counts':[5,4,3,2,1],'shift_mult':[0,1,2,3,4]},
    'compact33321': {'counts':[3,3,3,2,1],'shift_mult':[2,2,2,3,4]},
}

def _profile(name,mapping):
    if name=='standard54321':
        n=len(mapping);return {'counts':list(range(n,0,-1)),'shift_mult':list(range(n))}
    if name!='compact33321' or mapping!='KKWWK':
        raise ValueError('compact33321 is defined only for KKWWK')
    return PROFILES[name]

def stack_profile(c,mapping,dose,scale,H,profile):
    if profile=='standard54321': return geo.stack(c,mapping,dose,scale,H)
    b,p,v,tilt=geo.frame(c,H);h=dose*scale;du=h/np.tan(tilt);cfg=_profile(profile,mapping)
    rows=[]
    for t,(count,mult) in enumerate(zip(cfg['counts'],cfg['shift_mult'])):
        for i in range(count): rows.append((mult*du+(i+.5)*.4,t*h,t,i))
    return b,np.array(rows,float),du

def white_samples_profile(c,mapping,dose,scale,H,profile,count=256):
    b,roads,du=stack_profile(c,mapping,dose,scale,H,profile);h=dose*scale;a=.2
    cfg=_profile(profile,mapping)
    phi=(np.arange(count)+.5)*np.pi/(2*count);co=np.cos(phi);si=np.sin(phi)
    w=np.hypot(a*si,h*co)*np.pi/(2*count);norm=np.hypot(h*co,a*si)
    points=[];normals=[];weights=[];ids=[]
    for t,char in enumerate(mapping):
        if char!='W':continue
        count_t=cfg['counts'][t]; mult=cfg['shift_mult'][t]
        u=mult*du+(count_t-.5)*.4+a*co
        points.append(np.column_stack([c[0]+b[0]*u,c[1]+b[1]*u,t*h+h*si]))
        normals.append(np.column_stack([b[0]*h*co/norm,b[1]*h*co/norm,a*si/norm]))
        weights.append(w);ids.extend([t]*count)
    if not points:raise ValueError('No white working road')
    return np.concatenate(points),np.concatenate(normals),np.concatenate(weights),np.array(ids)

def white_ray_mask_profile(points,normals,c,mapping,dose,scale,H,profile,target=geo.PROJECTOR):
    b,roads,_=stack_profile(c,mapping,dose,scale,H,profile)
    ray=target-points;dist=np.linalg.norm(ray,axis=1);ray/=dist[:,None]
    facing=np.sum(normals*ray,axis=1)>0
    q0=((points[:,:2]-c)@b)[:,None];dq=(ray[:,:2]@b)[:,None]
    rh=ray[:,2,None];h0=points[:,2,None];a=.2;h=dose*scale
    uc=roads[:,0][None,:];base=roads[:,1][None,:]
    lo=np.maximum(1e-5,(base-h0)/rh);hi=np.minimum(dist[:,None],(base+h-h0)/rh)
    v0=h0-base;aa=(dq/a)**2+(rh/h)**2
    bb=2*((q0-uc)*dq/a**2+v0*rh/h**2);cc=((q0-uc)/a)**2+(v0/h)**2-1
    t=np.maximum(lo,np.minimum(hi,-bb/(2*aa)))
    blocked=np.any((hi>lo)&((aa*t*t+bb*t+cc)<-1e-8),axis=1)
    return facing&~blocked

def pitch_valid(c,mapping,dose,scale,V,H,pitch,profile):
    samples=white_samples_profile(c,mapping,dose,scale,H,profile)
    own=white_ray_mask_profile(samples[0],samples[1],c,mapping,dose,scale,H,profile)
    if geo.white_fraction(samples,own)<V/100-1e-9:return False
    c1=geo.advance(c,pitch,H);du0=stack_profile(c,mapping,dose,scale,H,profile)[2];du1=stack_profile(c1,mapping,dose,scale,H,profile)[2]
    cfg=_profile(profile,mapping);d=np.linalg.norm(c1-c)
    physical=min(d+m*(du1-du0)-cnt*.4 for m,cnt in zip(cfg['shift_mult'],cfg['counts']))
    if physical < -1e-12:return False
    mask=own&white_ray_mask_profile(samples[0],samples[1],c1,mapping,dose,scale,H,profile)
    return geo.white_fraction(samples,mask)>=V/100-1e-9

def solve_pitch_profile(c,mapping,dose,scale,V,H,floor,profile):
    if profile=='standard54321':return geo.solve_pitch(c,mapping,dose,scale,V,H,floor,'white')
    cfg=_profile(profile,mapping);lo=max(floor,max(cfg['counts'])*.4)
    if pitch_valid(c,mapping,dose,scale,V,H,lo,profile):return lo
    hi=max(lo,.45)
    for _ in range(90):
        hi*=1.12
        if pitch_valid(c,mapping,dose,scale,V,H,hi,profile):break
        if hi>8:return np.nan
    for _ in range(32):
        mid=(lo+hi)/2
        if pitch_valid(c,mapping,dose,scale,V,H,mid,profile):hi=mid
        else:lo=mid
    return hi

def polygons_profile(c,mapping,dose,scale,H,profile,segments=64,bead='volume'):
    b,roads,_=stack_profile(c,mapping,dose,scale,H,profile);h=dose*scale
    power=geo.volume_power(scale) if bead=='volume' else 2.;a=.2
    theta=np.linspace(np.pi,0,segments+1)
    x=a*np.sign(np.cos(theta))*np.abs(np.cos(theta))**(2/power);z=h*np.sin(theta)**(2/power)
    cfg=_profile(profile,mapping);shapes=[];colours=[]
    for uc,base,t,i in roads:
        shapes.append(np.column_stack([uc+x,base+z]));t=int(t);i=int(i)
        colours.append(1. if mapping[t]=='W' and i==cfg['counts'][t]-1 else .025)
    return np.array(shapes),np.array(colours)

def geometry_kernel_profile(c,case,pitch,offset,nrays,segments,nambient):
    mapping=case['layer_map'];dose=case['layer_height_mm'];scale=case['physical_height_scale'];H=case['horizontal_percent'];profile=case['profile']
    b,p,_,_=geo.frame(c,H);a=np.array([-b[1],b[0]])
    polygons,colours=polygons_profile(c,mapping,dose,scale,H,profile,segments,'volume')
    sources=np.vstack([p,mat.source_directions(nambient)])
    lights=np.column_stack([sources[:,:2]@b,sources[:,:2]@a,sources[:,2]])
    target=geo.VIEWER+np.array([offset,0.,0.]);v=geo.unit(target-np.r_[c,0.]);local_v=np.array([v[:2]@b,v[:2]@a,v[2]])
    hits=geo.first_hits(polygons,colours,pitch,local_v[0]/local_v[2],nrays)
    normals,index=np.unique(np.round(np.column_stack([hits[2],hits[3]]),13),axis=0,return_inverse=True)
    kernel,lit=mat.collect_kernel(polygons,pitch,hits,lights,index,len(normals))
    gap=geo.longest_dark_fraction(lit)*pitch/np.sqrt(1+(local_v[0]/local_v[2])**2)
    return dict(kernel=kernel,normals=normals,lights=lights,viewer=local_v,lit_white_fraction=float(lit.mean()),dark_band_mm=gap)

def resolve_pitch(point,case):
    mode=case.get('spacing_mode','auto');mapping=case['layer_map'];dose=case['layer_height_mm'];scale=case['physical_height_scale'];V=case['visibility_percent'];H=case['horizontal_percent'];profile=case['profile']
    if mode=='auto':return solve_pitch_profile(point,mapping,dose,scale,V,H,case.get('minimum_pitch_mm',0.),profile),True
    if mode=='forced_standard_A1':
        p=geo.solve_pitch(point,'KKWWK',.22,1.2,70,0,0,'white')
        return p,pitch_valid(point,mapping,dose,scale,V,H,p,profile)
    if mode=='forced_wwk_same':
        p=geo.solve_pitch(point,'WWK',dose,scale,V,H,0,'white')
        return p,pitch_valid(point,mapping,dose,scale,V,H,p,profile)
    if mode=='auto_plus':
        base=solve_pitch_profile(point,mapping,dose,scale,V,H,case.get('minimum_pitch_mm',0.),profile)
        p=base+case['pitch_offset_mm'];return p,pitch_valid(point,mapping,dose,scale,V,H,p,profile)
    raise ValueError(mode)

def load_cases(path=None):return json.loads(Path(path or HERE/'inputs'/'cases_v1.0.json').read_text())['cases']

def prepare_petg_central():
    # Vectorised equivalent of material_model_v1_2._integrate_spec. Avoids a
    # large one-time JIT compile while retaining the same GGX/Fresnel equations.
    from scipy.special import roots_legendre
    eta=1.57;alpha=.22;a2=alpha*alpha
    x,w=roots_legendre(80);co=(x+1)/2;weights=w/2
    phis=(np.arange(256)+.5)*2*np.pi/256;cp=np.cos(phis)[None,:]
    so=np.sqrt(1-co*co)[:,None];co2=co[:,None]
    mus=np.linspace(0.,1.,129);vals=[]
    for mu0 in mus:
        mu=max(float(mu0),.0001);si=math.sqrt(max(0.,1.-mu*mu))
        hx=si+so*cp;hy=so*np.sin(phis)[None,:];hz=mu+co2
        ll=np.sqrt(hx*hx+hy*hy+hz*hz);nh=hz/ll;ih=(si*hx+mu*hz)/ll
        ct=np.sqrt(np.maximum(0.,1.-(1.-ih*ih)/(eta*eta)))
        rs=(ih-eta*ct)/(ih+eta*ct);rp=(eta*ih-ct)/(eta*ih+ct);F=.5*(rs*rs+rp*rp)
        den=nh*nh*(a2-1.)+1.;D=a2/(np.pi*den*den)
        li=.5*(math.sqrt(1.+a2*max(0.,1.-mu*mu)/(mu*mu))-1.)
        lo=.5*(np.sqrt(1.+a2*np.maximum(0.,1.-co2*co2)/(co2*co2))-1.)
        G=1./(1.+li+lo);spec=D*G*F/(4.*mu*co2)
        vals.append(float(np.sum(spec.mean(axis=1)*2*np.pi*co*weights)))
    table=np.array(vals);average=float(np.trapezoid(2*mus*table,mus))
    return np.array([eta]),np.array([alpha]),table[None,:],np.array([average])

def run(output_dir,case_file=None,rays=1024,segments=96,ambient=512,grid=3):
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True);material=prepare_petg_central();cases=load_cases(case_file)
    metadata=dict(version=VERSION,rays=rays,segments=segments,ambient=ambient,grid=grid,material_model='v1.2 central/surface coefficient basis',geometry='v156 local reconstruction with compact33321 extension')
    (out/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    for case in cases:
        target=out/(case['id']+'.json');start=time.time();records=[]
        points=geo.card_points(case['piece'],grid)
        for point in points:
            pitch,valid=resolve_pitch(point,case)
            if not np.isfinite(pitch) or not valid:
                records.append(dict(point_mm=point.tolist(),status='infeasible',pitch_mm=float(pitch) if np.isfinite(pitch) else None));continue
            for offset in (-1000.,0.,1000.):
                g=geometry_kernel_profile(point,case,pitch,offset,rays,segments,ambient)
                coeff=mat.compute_coefficients(g['kernel'],g['normals'],g['lights'],g['viewer'],*material,ambient)
                records.append(dict(point_mm=point.tolist(),offset_mm=offset,pitch_mm=float(pitch),lit_white_fraction=g['lit_white_fraction'],dark_band_mm=g['dark_band_mm'],coefficients=coeff.tolist()))
        target.write_text(json.dumps(dict(metadata=metadata,case=case,records=records,seconds=time.time()-start),separators=(',',':'),allow_nan=False)+'\n')
        print(case['id'],case['profile'],f"L{case['layer_height_mm']} V{case['visibility_percent']}",len(records),'records',flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--cases',type=Path,default=HERE/'inputs'/'cases_v1.0.json');p.add_argument('--rays',type=int,default=1024);p.add_argument('--segments',type=int,default=96);p.add_argument('--ambient',type=int,default=512);p.add_argument('--grid',type=int,default=3);a=p.parse_args();run(a.output_dir,a.cases,a.rays,a.segments,a.ambient,a.grid)
if __name__=='__main__':main()
