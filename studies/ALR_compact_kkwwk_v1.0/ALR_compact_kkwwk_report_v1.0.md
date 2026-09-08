# ALR compact KKWWK 3-3-3-2-1 study v1.0

Completed 8 September 2026. Analysis only; no printer G-code or 3MF is generated.

## Question

Test whether replacing the conventional KKWWK 5-4-3-2-1 lower pyramid skirt with a compact 3-3-3-2-1 pedestal allows materially tighter packing while retaining the upper WWK optical head, PETG material, v156 mapped-white spacing maths, S1.2 and H0. The lower K tiers are placed directly under the three-road W tier; the upper 3-2-1 WWK offsets remain the normal v156 tilt-derived offsets.

All brightness, ambient and contrast indices use the current common baseline: PETG KWK, dose 0.20 mm, S1.2, V70, H0, piece 1-2, interpreted by the v156 local reconstructed spacing law. Baseline = 100/100/100. Lower ambient is better. Contrast index is useful projector response divided by ambient response, relative to the baseline.

## Main result

The compact pedestal **does achieve essentially WWK pitch**. For the representative compact cases checked independently, the mean compact-minus-WWK pitch difference is only about 0.06–0.12 micrometres, with a worst sampled difference below 0.32 micrometres. So the extra two K tiers can be hidden underneath the WWK head without materially increasing the v156 pitch requirement.

However, that does **not** deliver the hoped-for all-worlds result. The five-tier height still produces a much larger viewer dark band than the current baseline. The best compact cases that keep contrast at or above the historical ~102.3 target remain around 1.38–1.45 mm dark band, versus 1.044 mm for the current baseline and about 1.176 mm for the historical 102.3 v154 prediction.

This means the wide 5-4 black skirt was **not the main cause of the viewer shadow**. It becomes a pitch limiter only at low visibility, but the tall five-tier silhouette is the dominant remaining viewer-shadow cost.

## Fine-resolution key results

| Case | Profile | Dose mm | V % | Mean pitch mm | Dark band mm | Brightness | Ambient | Contrast |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| R0 | standard54321 | 0.200 | 70 | 1.326 | 1.044 | 100.0 | 100.0 | 100.0 |
| A1 | standard54321 | 0.220 | 70 | 2.148 | 1.614 | 119.4 | 102.7 | 116.4 |
| B1 | compact33321 | 0.220 | 70 | 2.148 | 1.614 | 119.4 | 104.3 | 114.5 |
| A4 | standard54321 | 0.220 | 40 | 2.000 | 1.512 | 117.9 | 106.1 | 111.2 |
| B8 | compact33321 | 0.220 | 40 | 1.879 | 1.432 | 114.8 | 109.8 | 104.5 |
| B9 | compact33321 | 0.220 | 35 | 1.833 | 1.404 | 112.5 | 110.9 | 101.5 |
| H04 | compact33321 | 0.195 | 60 | 1.898 | 1.372 | 131.5 | 129.8 | 101.3 |
| H01 | compact33321 | 0.200 | 55 | 1.889 | 1.380 | 128.6 | 125.9 | 102.2 |
| D11 | compact33321 | 0.205 | 50 | 1.878 | 1.387 | 125.4 | 122.1 | 102.7 |
| H02 | compact33321 | 0.200 | 60 | 1.932 | 1.409 | 129.4 | 124.6 | 103.8 |
| G01 | compact33321 | 0.205 | 50 | 1.928 | 1.420 | 126.5 | 120.7 | 104.9 |
| G02 | compact33321 | 0.205 | 50 | 1.978 | 1.453 | 127.2 | 119.3 | 106.6 |

### What the controls tell us

At the **same pitch** (A1 versus B1, both 2.148 mm), removing the outer K skirt leaves useful projector brightness unchanged (119.4 → 119.4), but ambient pickup rises (102.7 → 104.3) and contrast falls (116.4 → 114.5). So the KKKKK/KKKK skirt is not creating the brightness advantage, but it does provide a modest amount of ambient shielding/rejection.

At V40, the conventional 5-4-3-2-1 structure hits its 2.000 mm physical-width floor. The compact structure continues to 1.879 mm: **6.1% tighter pitch** and **5.3% smaller dark band**. The cost is contrast 111.2 → 104.5 and slightly lower brightness.

At V35 the compact version tightens further to 1.833 mm pitch and 1.404 mm dark band while still giving 112.5 brightness and 101.5 contrast. The conventional pyramid remains stuck at its 2.000 mm floor below V40, so the compact pedestal is doing exactly what it was intended to do geometrically.

## Best compact trade-offs found

- **H04: Smallest fine-verified dark band while retaining both brightness and contrast above baseline.** L0.195, V60 → pitch 1.898 mm, dark band 1.372 mm, brightness 131.5, ambient 129.8, contrast 101.3.
- **H01: Near the historical 102.3 contrast target with very high brightness.** L0.200, V55 → pitch 1.889 mm, dark band 1.380 mm, brightness 128.6, ambient 125.9, contrast 102.2.
- **D11: Slightly more contrast than H01 at a similar dark band.** L0.205, V50 → pitch 1.878 mm, dark band 1.387 mm, brightness 125.4, ambient 122.1, contrast 102.7.
- **G01: Deliberately adds 0.05 mm pitch to D11 to recover contrast.** L0.205, V50 → pitch 1.928 mm, dark band 1.420 mm, brightness 126.5, ambient 120.7, contrast 104.9.
- **G02: Adds 0.10 mm pitch to D11 for still more contrast.** L0.205, V50 → pitch 1.978 mm, dark band 1.453 mm, brightness 127.2, ambient 119.3, contrast 106.6.

The strongest compact brightness/contrast compromise without deliberately widening pitch is therefore around **L0.20/V55 to L0.205/V50**. Both produce roughly 25–29% more brightness than the current baseline and about 2–3% better contrast, but their predicted viewer dark bands remain about 32–33% wider than the baseline.

The spacing trade-off is very clear. Starting from D11 (L0.205/V50), adding 0.05 mm pitch raises contrast from 102.7 to 104.9 but widens the dark band from 1.387 to 1.420 mm. Adding 0.10 mm raises contrast to 106.6 and the dark band to 1.453 mm. There is no free contrast recovery from spacing alone.

## Lower-dose / lower-V boundary

The coarse sweep deliberately pushed dose and visibility lower. At L0.18/V35 the compact profile reaches a 1.149 mm predicted dark band, which is close to the old ~1.176 mm v154 target band. But its contrast collapses to about 80 because ambient pickup rises to ~155.5. Therefore simply making the tall structure thinner and packing it harder does not retain ALR performance.

## Interpretation

1. **The compact pedestal concept is geometrically valid and useful.** It removes the 2.0 mm base-width floor and lets low-V KKWWK reach essentially normal WWK pitch.
2. **The outer K skirt is optically useful but not responsible for brightness.** At identical spacing it mainly lowers ambient pickup.
3. **The remaining large viewer shadow comes from height, not lateral footprint.** Once the lower K tiers are tucked under the WWK head, the five-tier silhouette still occupies the viewer line of sight.
4. **Lower V gives tighter pitch, but ambient rejection deteriorates faster than the dark band improves.** The useful compact operating region is not down at V25–40 if contrast is a priority.
5. **A small deliberate pitch increase buys contrast efficiently, but necessarily increases the dark band.**

So the experiment does not yet beat the current baseline on all three targets simultaneously. It does, however, isolate the next design problem very clearly: if we want tall-structure brightness with baseline-sized viewer shadows, the next change has to reduce how much of the lower pedestal is visible to the viewer, rather than merely narrowing its lateral road count.

## Numerical verification and limitations

The selected cases were recomputed at 2048 viewer rays, 160 bead segments and 1024 ambient directions. Across the fine-selected cases, the largest coarse-to-fine contrast change was <0.056 index points and the largest dark-band change was <0.001 mm. Ten automated tests pass, including standard-geometry equivalence, vertical-pedestal registration, same-pitch control, WWK pitch equivalence and convergence checks.

This is still the same local reconstructed v156 cross-section model used in the material study, not a full curved-road G-code regeneration or a physical measurement. PETG uses the central v1.2 material assumptions. Bead deformation, multiple reflections, anisotropic printed texture and full-card curved-lattice effects remain uncalibrated.

## Files

- `ALR_compact_kkwwk_v1_0.py` — compact geometry and scorer extension.
- `inputs/` — approved sweep, refinements and fine-selected manifests.
- `results/main/` — coarse full sweep.
- `results/fine/` — higher-resolution selected cases.
- `results/summary/` — summaries and key CSV.
- `verification/` — tests, convergence and WWK-pitch checks.
