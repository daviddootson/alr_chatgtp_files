#!/usr/bin/env python3
"""FC3D v1.158 — audited thin-cap fix for v1.157.

v1.157 introduced ``--cap-height-mm`` but direct audit of a generated WWK
package found that the tier-3 marker/descent moved to the thin-cap top while the
executable SUPPORT_SEG and SUPPORT_DRY_TAIL Z words remained at the old v1.156
top. v1.158 wraps v1.157, fixes those executable coordinates, adds a fail-closed
actual-G-code tier-Z/cap-dose audit, and normalises packaged revision markers.

Requirements beside this file:
  * 3dprint_black_mirror_wave_grid_v1.157.py
  * 3dprint_black_mirror_wave_grid_v1.156.py
  * canonical 3dprintv1.179.py selected with --source
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import re
import sys
import zipfile
from pathlib import Path

SCRIPT_VERSION = "3dprint_black_mirror_wave_grid_v1.158"
REVISION = 158
DEFAULT_V157 = Path(__file__).with_name("3dprint_black_mirror_wave_grid_v1.157.py")


def _load_v157(path: Path = DEFAULT_V157):
    path = Path(path)
    if not path.is_file():
        raise SystemExit(f"{SCRIPT_VERSION}: v1.157 converter not found: {path}")
    spec = importlib.util.spec_from_file_location("fc3d_v157_for_v158", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"{SCRIPT_VERSION}: cannot load v1.157 converter: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    if getattr(mod, "REVISION", None) != 157:
        raise SystemExit(f"{SCRIPT_VERSION}: expected v1.157, got revision {getattr(mod,'REVISION',None)!r}")
    return mod


def _audit_actual_cap_block(block: str, rt, cap_height_mm: float) -> dict:
    expected = tuple(float(z) for z in rt.TIER_TOP_Z_MM)
    cap_tier = len(rt.LAYER_MAP)
    expected_e = float(rt.A_MAIN_E_PER_MM) * float(cap_height_mm) / float(rt.LAYER_HEIGHT_MM)
    active = None
    pos = None
    ratios = []
    seen = {i: 0 for i in range(1, cap_tier + 1)}
    for line in block.splitlines():
        if "SUPPORT_ROAD_START" in line:
            mt=re.search(r"\btier=(\d+)",line); mz=re.search(r"\bz=([-+0-9.]+)",line)
            if not (mt and mz): raise RuntimeError(f"{SCRIPT_VERSION}: support marker lacks tier/Z")
            active=int(mt.group(1)); seen[active]+=1; pos=None
            if abs(float(mz.group(1))-expected[active-1])>5.1e-4:
                raise RuntimeError(f"{SCRIPT_VERSION}: tier {active} road marker Z mismatch")
            continue
        if active is None: continue
        if "SUPPORT_ROAD_END" in line:
            active=None; pos=None; continue
        if not re.match(r"G[01] ",line): continue
        vals={k:float(v) for k,v in re.findall(r"\b([XYZE])([-+0-9.]+)",line.split(';')[0])}
        if "SUPPORT_MOVE" in line:
            if "X" in vals and "Y" in vals: pos=(vals["X"],vals["Y"])
            continue
        if "SUPPORT_HEIGHT" in line:
            mz=re.search(r"\bZ([-+0-9.]+)",line)
            if not mz or abs(float(mz.group(1))-expected[active-1])>5.1e-4:
                raise RuntimeError(f"{SCRIPT_VERSION}: tier {active} descent Z mismatch")
            continue
        if "SUPPORT_SEG" in line or "SUPPORT_DRY_TAIL" in line:
            mz=re.search(r"\bZ([-+0-9.]+)",line)
            if not mz or abs(float(mz.group(1))-expected[active-1])>5.1e-4:
                raise RuntimeError(f"{SCRIPT_VERSION}: tier {active} executable segment Z mismatch")
            if "X" in vals and "Y" in vals:
                new=(vals["X"],vals["Y"])
                if active==cap_tier and "SUPPORT_SEG" in line and pos is not None and "E" in vals:
                    ds=math.hypot(new[0]-pos[0],new[1]-pos[1])
                    if ds>1e-9: ratios.append(vals["E"]/ds)
                pos=new
    if any(v==0 for v in seen.values()): raise RuntimeError(f"{SCRIPT_VERSION}: missing tier in executable audit {seen}")
    if not ratios: raise RuntimeError(f"{SCRIPT_VERSION}: no cap extrusion segments in executable audit")
    mean=sum(ratios)/len(ratios)
    if abs(mean-expected_e)>8e-5: raise RuntimeError(f"{SCRIPT_VERSION}: cap E/mm {mean:.8f} != {expected_e:.8f}")
    return {"status":"PASS","tier_top_z_mm":list(expected),"cap_draw_e_per_mm":mean,
            "cap_segment_count":len(ratios),"tier_road_counts":seen}


def _install(v157):
    v157.SCRIPT_VERSION=SCRIPT_VERSION
    v157.REVISION=REVISION
    v157.REAR_VERSION_TEXT="158"

    old_patch=v157._patch_emitted_rows
    def patch_rows(rows,rt,cap):
        rows=list(old_patch(rows,rt,cap)); cap_tier=len(rt.LAYER_MAP); cap_z=float(rt.TIER_TOP_Z_MM[-1]); active=False; out=[]
        for line in rows:
            if "SUPPORT_ROAD_START" in line:
                mt=re.search(r"\btier=(\d+)",line); active=bool(mt and int(mt.group(1))==cap_tier)
            if active and ("SUPPORT_SEG" in line or "SUPPORT_DRY_TAIL" in line):
                line=re.sub(r"\bZ[-+0-9.]+",f"Z{cap_z:.3f}",line,count=1)
            out.append(line)
            if "SUPPORT_ROAD_END" in line: active=False
        return out
    v157._patch_emitted_rows=patch_rows

    old_norm=v157._normalise_cap_e_for_v156_audit
    def normalise(block,rt,cap):
        actual=_audit_actual_cap_block(block,rt,cap)
        rt._V158_ACTUAL_CAP_GCODE_AUDIT=actual
        return old_norm(block,rt,cap)
    v157._normalise_cap_e_for_v156_audit=normalise

    old_install=v157._install_runtime_thin_cap
    def install_rt(rt,cap_requested):
        cap=old_install(rt,cap_requested)
        lines=list(rt.REAR_TEXT_LINES)
        if lines:
            lines[0]=f"{rt.CURRENT_PIECE.name}  158"; rt.REAR_TEXT_LINES=tuple(lines); rt.REAR_PARAMETER_TEXT=" | ".join(lines)
        old_report=rt.optical_spacing_report
        def report(piece):
            d=dict(old_report(piece)); d["revision"]=158; return d
        rt.optical_spacing_report=report
        return cap
    v157._install_runtime_thin_cap=install_rt

    old_factory=v157._make_output_namer
    def factory(inherited,state):
        old=old_factory(inherited,state)
        def namer(rt):
            p=Path(old(rt)); q=Path(p.name.replace("_v157.gcode.3mf","_v158.gcode.3mf")); state["default_output"]=q; return q
        return namer
    v157._make_output_namer=factory

    old_post=v157._postprocess_revision
    def postprocess(output):
        old_post(output)
        output=Path(output)
        with zipfile.ZipFile(output,"r") as zin:
            names=zin.namelist(); data={n:zin.read(n) for n in names}
        gname="Metadata/plate_1.gcode"; g=data[gname].decode().replace("FC3D_V1157","FC3D_V1158").replace("FC3D v1.157","FC3D v1.158")
        gb=g.encode(); data[gname]=gb
        psn="Metadata/project_settings.config"
        if psn in data:
            ps=data[psn].decode().replace("FC3D_V1156","FC3D_V1158").replace("FC3D_V1157","FC3D_V1158").replace("FC3D v1.156","FC3D v1.158").replace("FC3D v1.157","FC3D v1.158")
            data[psn]=ps.encode()
        md5n="Metadata/plate_1.gcode.md5"
        if md5n in data: data[md5n]=(hashlib.md5(gb).hexdigest()+"\n").encode()
        for n in ("Metadata/fc3d_selective_white_audit.json","Metadata/fc3d_mapped_pyramid_audit.json"):
            if n in data:
                obj=json.loads(data[n]); obj["revision"]=158; obj["script_version"]=SCRIPT_VERSION
                data[n]=json.dumps(obj,indent=2).encode()
        tmp=output.with_name(output.name+".v158rewrite")
        with zipfile.ZipFile(tmp,"w",compression=zipfile.ZIP_DEFLATED) as zout:
            for n in names: zout.writestr(n,data[n])
        tmp.replace(output)
        with zipfile.ZipFile(output) as z:
            g2=z.read(gname); assert b"V1157" not in g2 and b"V1158" in g2
            if psn in z.namelist(): assert b"V1156" not in z.read(psn) and b"V1158" in z.read(psn)
            if md5n in z.namelist(): assert z.read(md5n).decode().strip()==hashlib.md5(g2).hexdigest()
    v157._postprocess_revision=postprocess

    old_print=print
    def fixed_print(*args,**kwargs):
        args=tuple(a.replace("v1.157 thin-cap audit","v1.158 thin-cap audit") if isinstance(a,str) else a for a in args)
        return old_print(*args,**kwargs)
    v157.print=fixed_print
    return v157


def main(argv=None):
    v157=_install(_load_v157())
    return v157.main(argv)


if __name__=="__main__":
    main()
