#!/usr/bin/env python3
from pathlib import Path

V110=Path('3dprint_black_mirror_wave_grid_v1.110.py')
V113=Path('3dprint_black_mirror_wave_grid_v1.113.py')

def must(v,msg):
    if not v: raise AssertionError(msg)

def main():
    must(V110.exists(),'v1.110 validated geometry predecessor missing')
    must(V113.exists(),'v1.113 release wrapper missing (expected RED before implementation)')
    s=V113.read_text(encoding='utf-8')
    for token in (
        '3dprint_black_mirror_wave_grid_v1.113',
        'REAR_VERSION_TEXT = "113"',
        'EXPECTED_V110_GIT_BLOB_SHA1 = "aabbe19bb39855f0bf32eb60d3fac3c6d9997edb"',
        'ACTIVE_VERSION_LABEL_PATCH',
        'DRY V1.106 VALIDATION',
        'DRY V1.113 VALIDATION',
        'discover_revision_dry_validator',
        'EXPECTED_SET1_ROADS = 17521',
        'EXPECTED_SET2_ROADS = 12009',
        'EXPECTED_LOCAL_ROADS = 332',
        'FC3D_V1113_U_PROFILE_SEG',
        'direct_xyz',
    ):
        must(token in s,f'missing v1.113 release token: {token}')
    print('PASS: v1.113 revision-specific dry-validator source contract present')

if __name__=='__main__': main()
