# FC3D ChatGPT workspace inventory — 2026-09-01

This inventory records the FC3D files currently present in the ChatGPT execution workspace but not necessarily present in the GitHub repository. It exists because the connected GitHub write API in this session does not expose a local-file upload parameter; existing sandbox file bytes cannot be streamed directly into GitHub through the connector.

## Canonical repository baseline already present

- `3dprint_black_mirror_wave_grid_v1.91.py`
- `3dprint_black_mirror_wave_grid_v1.98.py`
- `3dprintv1.179.py`
- `3mm_cube_for_0p3mm_slice_PETG_12m6s.gcode.3mf`

## Wrapper/source files currently in the ChatGPT workspace

| File | Bytes | SHA-256 |
|---|---:|---|
| `3dprint_black_mirror_wave_grid_v1.92.py` | 27365 | `6b4fd20b5f8636b12b8dc8fd8f337aa1694c86b4b882a03ce3383a461c2e99c8` |
| `3dprint_black_mirror_wave_grid_v1.93.py` | 42283 | `a69663b4024586aab1edc8acfcc1d7c945bcc10af310bd494916c35b5916a591` |
| `3dprint_black_mirror_wave_grid_v1.94.py` | 45893 | `32e42bbac5f21ba3c87f85d9797df76f12b6afeeb6fb0d6977fe07bda32ef491` |
| `3dprint_black_mirror_wave_grid_v1.95.py` | 56324 | `37837eaa9d8c56e56c2a4f5dda0a9cad138cc0f101884160d7eff498539298fc` |
| `3dprint_black_mirror_wave_grid_v1.96.py` | 59078 | `74ada4e783e0c79e42a51c4fb7525da5eb1738fcb550e4cef0ea23f7bed73859` |
| `3dprint_black_mirror_wave_grid_v1.97.py` | 65813 | `548a9609b935c6b58b04a7cb9fd87d41ee560fe4b39499fc4863fbc142540ef8` |
| `3dprint_black_mirror_wave_grid_v1.98.py` | 118748 | `eadafc2727459ff7ded844b12817ac2502462b5cd7455cf95eb8eb631689772e` |
| `3dprint_black_mirror_wave_grid_v1.99.py` | 129563 | `6f51661ca0e5d94042159ee26a57b4c636e39a8942ba4bdceb2f1197e49a7067` |
| `3dprint_black_mirror_wave_grid_v1.100.py` | 142711 | `da1290f2b9329c793ff4aee4e1646bc414b550802ad7e1d2ec31cb52eb5077d2` |
| `3dprint_black_mirror_wave_grid_v1.101.py` | 158191 | `6728d306e2a2715e872c3fb77e3ee81a1b93c06b2179fb7e4d510e17536910a7` |
| `3dprint_black_mirror_wave_grid_v1.102.py` | 145394 | `41cd6163f685db40458a74a782aa16bccc8d81d68dc1cd37a08e197bb683c73c` |
| `3dprint_black_mirror_wave_grid_v1.105.py` | 179197 | `4dce2b1d49dc580b72bea2867ebdb4798263df6e77b2dd3a9faf9d66e8c62375` |
| `3dprint_black_mirror_wave_grid_v1.106.py` | 344893 | `a7e14bf818033aff390f69fd0e27368a8917a8a60dbb9c29c5d1a5c308814e80` |

`v1.106` is a **work-in-progress/rejected geometry attempt**: the layer-4 wave geometry was reported physically/visually wrong because the wave roads were not running inward toward the projector along the tangent implied by the bisecting normal. Do not treat v1.106 as canonical.

## Generated G-code packages currently in the ChatGPT workspace

| File | Bytes | SHA-256 |
|---|---:|---|
| `black_a_only_bonding_1_2_v1.98.gcode.3mf` | 1236988 | `17d15e6ae9dc6da629e683cb5f34a41075523017abb012ea316a7dcde6d58fbc` |
| `black_a_only_bonding_1_2_v1.99.gcode.3mf` | 1262415 | `33ff7d7df1d47e1bfea6e0f8d856c3274c439af176d15cd83a8bb444f9bd03e9` |
| `black_a_only_bonding_1_2_v1.99_studio.gcode.3mf` | 1262377 | `5208945eb114f6b1dce37917c455ff5b741254a02c5e69ef92bf9ebe83ba5191` |
| `black_a_only_single_0p14_1_2_v1.100.gcode.3mf` | 679564 | `1bee70b7e81d4e3c421b3820067153635e10655087c56545b2d6d1d374b0aa51` |
| `black_a_only_single_0p14_1_2_v1.100_studio.gcode.3mf` | 679535 | `c6924551d7d43415c01aff5880f14b57be645c4b3b76506a20497c3213671f83` |
| `black_a_only_single_0p14_valleyfill40_1_2_v1.101.gcode.3mf` | 686328 | `d4f878299478383bc018211c305396a4fa2f9670c236aee32882b2b03b21a82e` |
| `black_a_only_single_0p14_valleyfill40_1_2_v1.101_studio.gcode.3mf` | 686300 | `6a700464bf9dbf46eb8fd0e694b65e6dc2292c2b6ba8aa4cf31b53d37ba5796b` |
| `black_a_only_paired_0p08_0p14_valleyfill50_1_2_v1.102.gcode.3mf` | 1248592 | `af485378e498fcad64e54fb69b555cc601bc8337e5e715e8f58dd00e9eb40e3d` |
| `black_a_only_paired_0p08_0p14_valleyfill50_1_2_v1.102_studio.gcode.3mf` | 1248557 | `1c644db597b028263db6b3fa7c71d411ca0c0334dc457b9718d55f99bfddd55f` |
| `black_a_only_single_0p14_shadowclear_valleyfill25_1_2_v1.105.gcode.3mf` | 1966806 | `618047dff59e7c3c62badb0a3d610c3fc6ea95daf9d3db4f9fe23a951b4759a3` |
| `black_a_only_single_0p14_shadowclear_valleyfill25_1_2_v1.105_studio.gcode.3mf` | 1966785 | `8dbcb2733577f09f48eb65ca1f0c0dc4543aa70b07235e8fb478dfd245b7ad6c` |
| `black_a_only_wave_sets_true_normal_valleyfill25_1_2_v1.106.gcode.3mf` | 696066 | `f920d4153a444b417340dd6d551f65e499d494f535c4008c6edf53045f2936da` |
| `black_a_only_wave_sets_true_normal_valleyfill25_1_2_v1.106_studio.gcode.3mf` | 696041 | `9f31b405e27ca74185629a0ffe2a16e87f887e9dde1a2550f26855b379bbaacf` |

## Handoff and development-support files

| File | Bytes | SHA-256 |
|---|---:|---|
| `FC3D_ALR_wave_test_handoff_2026-09-01.md` | 32003 | `16fc4982ffaefed1c0811e3443e3e740d87aa9c8086c7383a709b33c294e3539` |
| `FC3D_ALR_wave_test_handoff_2026-09-01.docx` | 50683 | `2c4b64aabbfe91b72e119bce040035aab86efd5da9b40a4272e4f31c9990c64b` |
| `fc3d_handoff_render/FC3D_ALR_wave_test_handoff_2026-09-01.pdf` | 262891 | `e50e169151763b4bce06a3535bc04c2282cb2dc7e2629248865a2a98e28ecf67` |
| `create_fc3d_handoff.py` | 40142 | `4387c987b92948e747eb1c24ee1228110b3d3e53e7b5a7d4f0fea612b18de4df` |
| `fc3d_v106_work/build_v106.py` | 29381 | `97e5089e1ed2b66a81e75af5bc393148e467ac9be589854673c498ce88e6c3d2` |
| `fc3d_v106_work/test_v106_contract.py` | 1384 | `2f45199c5bc00df5ba3ffdfe2dba751fff084700956148c425733f62bcfaf1fd` |
| `fc3d_v106_work/independent_v106_audit.py` | 5594 | `ace3cb4112396c57dac9912686bd0d631504d59d9afb033d91e7d1c557192304` |

## Additional workspace material

The execution workspace also contains the generated audit JSON files, layer/mirror summary CSVs, v1.101→v1.105 arc-position comparison, v1.103/v1.104 profile-comparison CSVs, v1.105→v1.106 comparison CSV, v1.106 time-estimate JSON, handoff render PNGs, and conversation-upload PNGs. A full local manifest was generated as `fc3d_workspace_snapshot_2026-09-01_manifest.json` and `.csv`.

## Status / next geometry work

- v1.101 remains the good single-road physical baseline with 40% valley fill.
- v1.105 is the active dense single-road shadow-clear test with 25% valley fill.
- Twin-road v1.102/v1.103/v1.104 work is benched/voided as an active optical architecture.
- v1.106 is not accepted: layer-4 wave lines need to run inward toward the projector along the local tangent dictated by the bisecting-normal wave surface; current v1.106 geometry is missing/incorrect in that respect.
