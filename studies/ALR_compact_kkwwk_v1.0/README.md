# ALR compact KKWWK 3-3-3-2-1 study v1.0

Finished local numerical study, 8 September 2026. Read `ALR_compact_kkwwk_report_v1.0.html` or the Markdown report first.

This study keeps PETG, H0 and S1.2 as the main design assumptions and extends the previous local v156 mapped-white reconstruction with a compact KKWWK cross-section. The upper WWK head retains normal tilt-derived 3-2-1 offsets. The two lower K tiers use three roads each and are vertically registered under the three-road W tier, giving road counts 3-3-3-2-1.

The common reference is PETG KWK / L0.20 / S1.2 / V70 / H0 / piece 1-2 under the v156 local spacing law. All indices are relative predictions, not physical measurements.

Reproduce tests:

```sh
python -m pytest -q test_compact_kkwwk_v1_0.py test_results_v1_0.py
```

The main sweep was run at 768 rays / 80 segments / 384 ambient directions. Selected cases were independently recomputed at 2048 / 160 / 1024. Inputs are preserved in `inputs/`; results and convergence evidence are under `results/` and `verification/`.

This is analysis-only software and does not emit G-code or 3MF. The previous material-study checkpoint is preserved separately in the originating conversation; the source dependency used by this study is included here.
