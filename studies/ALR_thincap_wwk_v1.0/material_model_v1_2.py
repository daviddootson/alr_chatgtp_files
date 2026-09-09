#!/usr/bin/env python3
"""ALR v1.2 material-aware local optical comparison; not printer G-code.

All spacing is reconstructed v156 mapped-white spacing, as in the archived
v1.1 local scorer. The unchanged v1.1 geometry source is shipped in vendor/.
An isotropic GGX dielectric surface is combined with an energy-budgeted diffuse
body. Effective body return and micro-roughness are stated priors, NOT filament
measurements. First-bounce, opaque/effective-loss, periodic local-ridge model.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, math, sys, time
from functools import lru_cache
from pathlib import Path
import numpy as np
from numba import njit
from scipy.special import roots_legendre

VERSION='1.2'
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('alr_geometry_v1_1',HERE/'vendor'/'ALR_shadow_comparison_v1.1.py')
geo=importlib.util.module_from_spec(spec);sys.modules[spec.name]=geo;spec.loader.exec_module(geo)
LIGHT_NAMES=['projector','uniform','overhead60','overhead80','front','left60','right60']
SURFACES=[('PETG_smooth',1.57,.12),('PETG_central',1.57,.22),('PETG_rough',1.57,.35),
          ('PLA_smooth',1.45,.20),('PLA_central',1.45,.35),('PLA_rough',1.45,.50),
          ('PLA_matt_smooth',1.45,.35),('PLA_matt_central',1.45,.50),('PLA_matt_rough',1.45,.65)]

@njit(cache=True)
def fresnel(cosine, eta):
    c=max(0.,min(1.,cosine))
    if abs(eta-1.)<1e-14:return 0.
    ct=math.sqrt(max(0.,1.-(1.-c*c)/(eta*eta)))
    rs=(c-eta*ct)/(c+eta*ct)
    rp=(eta*c-ct)/(eta*c+ct)
    return .5*(rs*rs+rp*rp)

@njit(cache=True)
def specular(ci,co,nh,ih,eta,alpha):
    if ci<=1e-10 or co<=1e-10 or nh<=0.:return 0.
    a2=alpha*alpha
    den=nh*nh*(a2-1.)+1.
    D=a2/(math.pi*den*den)
    li=.5*(math.sqrt(1.+a2*max(0.,1.-ci*ci)/(ci*ci))-1.)
    lo=.5*(math.sqrt(1.+a2*max(0.,1.-co*co)/(co*co))-1.)
    G=1./(1.+li+lo)
    return D*G*fresnel(ih,eta)/(4.*ci*co)

@njit(cache=True)
def interp_energy(mu,table):
    z=max(0.,min(1.,mu))*(len(table)-1)
    i=min(len(table)-2,int(z));t=z-i
    return table[i]*(1.-t)+table[i+1]*t

@njit(cache=True)
def brdf_components(ci,co,nh,ih,eta,alpha,table,average):
    if ci<=1e-10 or co<=1e-10:return 0.,0.
    s=specular(ci,co,nh,ih,eta,alpha)
    d=(1.-interp_energy(ci,table))*(1.-interp_energy(co,table))/(math.pi*(1.-average))
    return s,d

@njit(cache=True)
def brdf(wi,wo,rho,eta,alpha,table,average):
    hx=wi[0]+wo[0];hy=wi[1]+wo[1];hz=wi[2]+wo[2]
    norm=math.sqrt(hx*hx+hy*hy+hz*hz)
    if norm<1e-12:return 0.
    nh=hz/norm;ih=(wi[0]*hx+wi[1]*hy+wi[2]*hz)/norm
    s,d=brdf_components(wi[2],wo[2],nh,ih,eta,alpha,table,average)
    return s+rho*d

@njit(cache=True)
def _integrate_spec(mu,eta,alpha,cosines,weights,phis):
    si=math.sqrt(max(0.,1.-mu*mu));total=0.
    for i in range(len(cosines)):
        co=cosines[i];so=math.sqrt(max(0.,1.-co*co))
        subtotal=0.
        for p in phis:
            hx=si+so*math.cos(p);hy=so*math.sin(p);hz=mu+co
            l=math.sqrt(hx*hx+hy*hy+hz*hz)
            nh=hz/l;ih=(si*hx+mu*hz)/l
            subtotal+=specular(mu,co,nh,ih,eta,alpha)
        total+=subtotal/len(phis)*2*math.pi*co*weights[i]
    return total

@lru_cache(maxsize=32)
def energy_table(eta,alpha):
    if not 1<=eta<=2.5 or not .08<=alpha<=1.:raise ValueError('Optical prior out of supported numerical range')
    x,w=roots_legendre(160);cosines=(x+1)/2;weights=w/2
    phis=(np.arange(640)+.5)*2*np.pi/640
    mus=np.linspace(0.,1.,129)
    table=np.array([_integrate_spec(max(mu,.0001),eta,alpha,cosines,weights,phis) for mu in mus])
    if np.any(~np.isfinite(table)) or np.any(table<0) or np.any(table>=1):
        raise ValueError('Invalid surface-energy table')
    average=float(np.trapezoid(2*mus*table,mus))
    return table,average

def integrated_brdf(mu,rho,eta,alpha,table,average,ntheta=160,nphi=640):
    x,w=roots_legendre(ntheta);cosines=(x+1)/2;weights=w/2
    phis=(np.arange(nphi)+.5)*2*np.pi/nphi
    sp=_integrate_spec(mu,eta,alpha,cosines,weights,phis)
    de=float(np.sum(2*cosines*weights*(1.-np.interp(cosines,np.linspace(0,1,len(table)),table))))
    return sp+rho*(1.-np.interp(mu,np.linspace(0,1,len(table)),table))*de/(1.-average)

def load_cases():
    return json.loads((HERE/'inputs'/'candidates_v1.2.json').read_text())['cases']

@njit(cache=False)
def collect_kernel(polys,pitch,hits,lights,indices,nn):
    u,z,nu,nz,rho,owner,period=hits
    nr=len(u);nd=len(lights);k=np.zeros((nn*2,nd));lit=np.zeros(nr,np.bool_)
    slopes=lights[:,0]/lights[:,2]
    for i in range(nr):
        cosine=nu[i]*lights[:,0]+nz[i]*lights[:,2]
        eligible=cosine>1e-12
        clear=geo.directional_visibility(polys,pitch,u[i],z[i],owner[i],period[i],slopes,eligible)
        group=indices[i]+(nn if rho[i]>.5 else 0)
        if clear[0] and rho[i]>.5:lit[i]=True
        for j in range(nd):
            if clear[j]:k[group,j]+=cosine[j]/nr
    return k,lit

def source_directions(nambient):
    rad=np.pi/180
    direct=np.array([[0,np.sin(60*rad),np.cos(60*rad)],
                     [0,np.sin(80*rad),np.cos(80*rad)],
                     [0,0,1],[-np.sin(60*rad),0,np.cos(60*rad)],
                     [np.sin(60*rad),0,np.cos(60*rad)]])
    return np.vstack([geo.ambient_directions(nambient),direct])

def geometry_kernel(c,case,pitch,offset,nrays,segments,nambient):
    mapping=case['layer_map'];dose=case['layer_height_mm'];scale=case['physical_height_scale'];H=case['horizontal_percent']
    b,p,_,_=geo.frame(c,H);a=np.array([-b[1],b[0]])
    polygons,colours=geo.polygons(c,mapping,dose,scale,H,segments,'volume')
    sources=np.vstack([p,source_directions(nambient)])
    lights=np.column_stack([sources[:,:2]@b,sources[:,:2]@a,sources[:,2]])
    target=geo.VIEWER+np.array([offset,0.,0.]);v=geo.unit(target-np.r_[c,0.])
    local_v=np.array([v[:2]@b,v[:2]@a,v[2]])
    hits=geo.first_hits(polygons,colours,pitch,local_v[0]/local_v[2],nrays)
    normals,index=np.unique(np.round(np.column_stack([hits[2],hits[3]]),13),axis=0,return_inverse=True)
    kernel,lit=collect_kernel(polygons,pitch,hits,lights,index,len(normals))
    gap=geo.longest_dark_fraction(lit)*pitch/np.sqrt(1+(local_v[0]/local_v[2])**2)
    return dict(kernel=kernel,normals=normals,lights=lights,viewer=local_v,projector_depth_component=p[2],
                lit_white_fraction=float(lit.mean()),dark_band_mm=gap)

@njit(cache=True)
def compute_coefficients(kernel,normals,lights,viewer,etas,alphas,tables,averages,nambient):
    nn=len(normals);nd=len(lights);ns=len(etas)
    result=np.zeros((ns,2,7,2))
    hx=lights[:,0]+viewer[0];hy=lights[:,1]+viewer[1];hz=lights[:,2]+viewer[2]
    hn=np.sqrt(hx*hx+hy*hy+hz*hz)
    ih=(lights[:,0]*hx+lights[:,1]*hy+lights[:,2]*hz)/hn
    for k in range(nn):
        nu=normals[k,0];nz=normals[k,1];co=nu*viewer[0]+nz*viewer[2]
        if co<=1e-10:continue
        for j in range(nd):
            ci=nu*lights[j,0]+nz*lights[j,2]
            if ci<=1e-10:continue
            nh=(nu*hx[j]+nz*hz[j])/hn[j]
            label=0 if j==0 else (1 if j<=nambient else j-nambient+1)
            weight=2*math.pi/nambient if label==1 else math.pi/lights[j,2]
            for s in range(ns):
                sp,de=brdf_components(ci,co,nh,ih[j],etas[s],alphas[s],tables[s],averages[s])
                for colour in range(2):
                    kw=kernel[k+colour*nn,j]*weight
                    result[s,colour,label,0]+=kw*sp
                    result[s,colour,label,1]+=kw*de
    return result

def prepare_surfaces():
    values=[energy_table(eta,alpha) for name,eta,alpha in SURFACES]
    return (np.array([s[1] for s in SURFACES]),np.array([s[2] for s in SURFACES]),
            np.array([v[0] for v in values]),np.array([v[1] for v in values]))

def run(output_dir,rays=1024,segments=96,ambient=512,case_ids=None,grid=3):
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    if min(rays,segments,ambient)<16 or grid not in (1,3,5):raise ValueError('Invalid numerical resolution')
    material=prepare_surfaces()
    manifest=HERE/'inputs'/'candidates_v1.2.json'
    metadata=dict(version=VERSION,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),rays=rays,segments=segments,
                  ambient=ambient,grid=grid,view_offsets_mm=[-1000,0,1000],surface_names=[s[0] for s in SURFACES],
                  source_names=LIGHT_NAMES,geometry='v156 local mapped-white reconstruction; not full curved lattice',
                  scorer='first-bounce periodic ridge; GGX + energy-complement diffuse; effective opaque loss')
    (out/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    for case in load_cases():
        if case_ids and case['id'] not in case_ids:continue
        target=out/(case['id']+'.json')
        if target.exists():
            existing=json.loads(target.read_text())
            if existing['metadata']!=metadata:raise ValueError('Existing results use different settings or source')
            print(case['id'],'already calculated',flush=True);continue
        start=time.time();records=[]
        points=geo.card_points(case['piece'],grid) if grid!=1 else [geo.card_points(case['piece'],3)[4]]
        for point in points:
            pitch=geo.solve_pitch(point,case['layer_map'],case['layer_height_mm'],case['physical_height_scale'],
                 case['visibility_percent'],case['horizontal_percent'],case['minimum_pitch_mm'],'white')
            if not np.isfinite(pitch):
                records.append(dict(point_mm=point.tolist(),status='infeasible_white_visibility'))
                continue
            for offset in (-1000.,0.,1000.):
                g=geometry_kernel(point,case,pitch,offset,rays,segments,ambient)
                coeff=compute_coefficients(g['kernel'],g['normals'],g['lights'],g['viewer'],*material,ambient)
                records.append(dict(point_mm=point.tolist(),offset_mm=offset,pitch_mm=pitch,
                                    lit_white_fraction=g['lit_white_fraction'],dark_band_mm=g['dark_band_mm'],
                                    coefficients=coeff.tolist()))
        obj=dict(metadata=metadata,case=case,records=records,seconds=time.time()-start)
        target.write_text(json.dumps(obj,separators=(',',':'),allow_nan=False)+'\n')
        print(f"{case['id']} {case['layer_map']} L{case['layer_height_mm']} V{case['visibility_percent']} "
              f"{len(records)} records; {obj['seconds']:.1f} s",flush=True)
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,default=HERE/'results'/'main')
    p.add_argument('--rays',type=int,default=1024);p.add_argument('--segments',type=int,default=96)
    p.add_argument('--ambient',type=int,default=512);p.add_argument('--grid',type=int,default=3)
    p.add_argument('--cases',nargs='*')
    args=p.parse_args()
    try:run(args.output_dir,args.rays,args.segments,args.ambient,args.cases,args.grid)
    except (ValueError,OSError,KeyError) as exc:p.exit(2,f'ALR material study: {exc}\n')
if __name__=='__main__':main()
