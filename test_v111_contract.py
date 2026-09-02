#!/usr/bin/env python3
from pathlib import Path

V110=Path('3dprint_black_mirror_wave_grid_v1.110.py')
V111=Path('3dprint_black_mirror_wave_grid_v1.111.py')

def must(v,msg):
    if not v: raise AssertionError(msg)

def main():
    must(V110.exists(),'v1.110 geometry-proving predecessor missing')
    must(V111.exists(),'v1.111 release wrapper missing (expected RED before implementation)')
    s=V111.read_text(encoding='utf-8')
    for token in ('3dprint_black_mirror_wave_grid_v1.111','REAR_VERSION_TEXT = "111"',
                  'ACTIVE_VERSION_LABEL_PATCH','DRY V1.106 VALIDATION','DRY V1.111 VALIDATION',
                  'EXPECTED_SET1_ROADS = 17521','EXPECTED_SET2_ROADS = 12009',
                  'EXPECTED_LOCAL_ROADS = 332','FC3D_V1111_U_PROFILE_SEG','direct_xyz'):
        must(token in s,f'missing v1.111 release token: {token}')
    print('PASS: v1.111 version-clean release source contract present')

if __name__=='__main__': main()
