import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve()
TARGET = HERE.parent.parent / '3dprint_black_mirror_wave_grid_v1.157.py' if HERE.parent.name == 'tests' else HERE.parent / '3dprint_black_mirror_wave_grid_v1.157.py'


def load_target():
    if not TARGET.exists():
        return None
    spec = importlib.util.spec_from_file_location('v157_under_test', TARGET)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fake_rt(layer_map='WWK', layer_height=.22, scale=1.2):
    return SimpleNamespace(
        LAYER_MAP=layer_map,
        LAYER_HEIGHT_MM=layer_height,
        PHYSICAL_HEIGHT_SCALE=scale,
        PHYSICAL_LAYER_HEIGHT_MM=layer_height*scale,
        BASE_TOP_Z_MM=.4,
    )


def test_module_exists_and_is_revision_157():
    m = load_target()
    assert m is not None, 'v1.157 script does not exist yet'
    assert m.REVISION == 157
    assert m.SCRIPT_VERSION.endswith('v1.157')


def test_target_tier_heights_w022_k010_s12():
    m = load_target(); assert m is not None
    rt = fake_rt()
    heights = m._tier_physical_heights(rt, .10)
    assert heights == (0.264, 0.264, 0.12)
    tops = m._tier_top_zs(rt, .10)
    assert all(abs(a-b) < 1e-12 for a,b in zip(tops, (.664, .928, 1.048)))


def test_cap_default_reproduces_common_height():
    m = load_target(); assert m is not None
    rt = fake_rt()
    heights = m._tier_physical_heights(rt, .22)
    assert heights == (0.264, 0.264, 0.264)


def test_cap_requires_top_k_if_explicit():
    m = load_target(); assert m is not None
    try:
        m._validate_cap('WWW', .22, .10)
    except Exception as exc:
        assert 'top' in str(exc).lower() and 'k' in str(exc).lower()
    else:
        raise AssertionError('explicit thin cap on top W must fail')


def test_emitted_cap_z_and_draw_e_change_only_on_top_k():
    m = load_target(); assert m is not None
    rt = fake_rt()
    rows = [
        '; FC3D_V1156_OPTICAL_START mode=mapped-pyramid',
        '; FC3D_V1156_SUPPORT_ROAD_START road=1 stack=1 tier=2 tier_road=1 z=0.928',
        'G0 Z1.192 F900 ; FC3D_V1156_SUPPORT_TRAVEL_Z',
        'G0 Z0.928 F900 ; FC3D_V1156_SUPPORT_HEIGHT',
        'G1 X1.000 Y2.000 E0.034474 F15000 ; FC3D_V1156_SUPPORT_SEG',
        '; FC3D_V1156_SUPPORT_ROAD_END road=1',
        '; FC3D_V1156_SUPPORT_ROAD_START road=2 stack=1 tier=3 tier_road=1 z=1.192',
        'G0 Z1.192 F900 ; FC3D_V1156_SUPPORT_TRAVEL_Z',
        'G0 Z1.192 F900 ; FC3D_V1156_SUPPORT_HEIGHT',
        'G1 X1.000 Y2.000 E0.034474 F15000 ; FC3D_V1156_SUPPORT_SEG',
        '; FC3D_V1156_SUPPORT_ROAD_END road=2',
    ]
    out = m._patch_emitted_rows(rows, rt, .10)
    text='\n'.join(out)
    assert 'tier=3 tier_road=1 z=1.048' in text
    assert 'G0 Z1.048 F900 ; FC3D_V1156_SUPPORT_HEIGHT' in text
    assert 'G0 Z1.208 F900 ; FC3D_V1156_SUPPORT_TRAVEL_Z' in text
    blocks = text.split('FC3D_V1156_SUPPORT_ROAD_START')
    tier2 = next(b for b in blocks if 'tier=2 ' in b)
    tier3 = next(b for b in blocks if 'tier=3 ' in b)
    e2=float(re.search(r'SUPPORT_HEIGHT.*?\n.*?E([0-9.]+).*?SUPPORT_SEG', tier2, re.S).group(1))
    e3=float(re.search(r'SUPPORT_HEIGHT.*?\n.*?E([0-9.]+).*?SUPPORT_SEG', tier3, re.S).group(1))
    assert abs(e2-.034474) < 1e-9
    assert abs(e3/e2-(.10/.22)) < 2e-6


def test_audit_normalisation_restores_cap_e():
    m=load_target(); assert m is not None
    rt=fake_rt()
    original='\n'.join([
        '; FC3D_V1156_SUPPORT_ROAD_START road=1 stack=1 tier=3 tier_road=1 z=1.048',
        'G1 X1 Y2 E0.01567 F15000 ; FC3D_V1156_SUPPORT_SEG',
        '; FC3D_V1156_SUPPORT_ROAD_END road=1',
    ])
    norm=m._normalise_cap_e_for_v156_audit(original,rt,.10)
    e=float(re.search(r'E([0-9.]+).*SUPPORT_SEG',norm).group(1))
    assert abs(e-.034474) < 1e-6


def test_wrapper_arg_is_removed_but_v156_args_preserved():
    m=load_target(); assert m is not None
    known, rest=m._split_wrapper_args(['--piece','1-2','--cap-height-mm','0.10','--visibility-percent','50'])
    assert abs(known.cap_height_mm-.10)<1e-12
    assert rest==['--piece','1-2','--visibility-percent','50']


def test_runtime_patch_preserves_w_tiers_and_reports_true_total_height():
    m=load_target(); assert m is not None
    class Piece: name='1-2'
    def frame(x,z): return {'facet_tilt_deg':45.0,'b_unit':(1.0,0.0)}
    def profile(angle):
        return {'tiers':[
            {'tier':1,'base_height_mm':0.0,'centres_u_mm':[.2,.6,1.0]},
            {'tier':2,'base_height_mm':.264,'centres_u_mm':[.464,.864]},
            {'tier':3,'base_height_mm':.528,'centres_u_mm':[.728]},
        ]}
    rt=SimpleNamespace(
        LAYER_MAP='WWK',LAYER_HEIGHT_MM=.22,PHYSICAL_HEIGHT_SCALE=1.2,
        PHYSICAL_LAYER_HEIGHT_MM=.264,BASE_TOP_Z_MM=.4,NOMINAL_TOP_Z_MM=1.192,
        CURRENT_PIECE=Piece(),LABEL_GLYPHS={},REAR_TEXT_LINES=('1-2  156','WWK','V50 L0.22','S1.2'),
        REAR_PARAMETER_TEXT='',mirror_frame_global=frame,_stack_cross_section_profile=profile,
        ARC_PROFILE_WIDTH_MM=.4,_BLOCKER_ARRAY_CACHE={},_OPTICAL_LATTICE_CACHE={},
        _explicit_mirror_wave_layer_gcode=lambda *a,**k: ['; FC3D_V1156_OPTICAL_START mode=mapped-pyramid'],
        optical_spacing_report=lambda piece:{'support_height_mm':.792,'model_top_z_mm':1.192},
    )
    m._install_runtime_thin_cap(rt,.10)
    assert rt.TIER_PHYSICAL_HEIGHTS_MM == (.264,.264,.12)
    assert abs(rt.NOMINAL_TOP_Z_MM-1.048)<1e-12
    p=rt._stack_cross_section_profile(45.0)
    assert [t['base_height_mm'] for t in p['tiers']] == [0.0,.264,.528]
    assert [t['centres_u_mm'] for t in p['tiers']] == [[.2,.6,1.0],[.464,.864],[.728]]
    report=rt.optical_spacing_report(Piece())
    assert abs(report['support_height_mm']-.648)<1e-12
    assert abs(report['model_top_z_mm']-1.048)<1e-12
    assert report['cap_height_mm']==.10
