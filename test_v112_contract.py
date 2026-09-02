#!/usr/bin/env python3
from pathlib import Path
V112=Path('3dprint_black_mirror_wave_grid_v1.112.py')
def must(v,msg):
    if not v: raise AssertionError(msg)
def main():
    must(V112.exists(),'v1.112 release wrapper missing (expected RED before implementation)')
    s=V112.read_text(encoding='utf-8')
    for token in ('3dprint_black_mirror_wave_grid_v1.112','REAR_VERSION_TEXT = "112"',
                  'ACTIVE_VERSION_LABEL_PATCH','DRY V1.106 VALIDATION','DRY V1.112 VALIDATION',
                  'discover_dry_validator','EXPECTED_SET1_ROADS = 17521','EXPECTED_SET2_ROADS = 12009',
                  'EXPECTED_LOCAL_ROADS = 332','FC3D_V1112_U_PROFILE_SEG','direct_xyz'):
        must(token in s,f'missing v1.112 release token: {token}')
    print('PASS: v1.112 robust version-clean source contract present')
if __name__=='__main__': main()
