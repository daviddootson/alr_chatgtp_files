# Physical best + 0.2 mm scaling checkpoint v1.4

Current physically successful working best reported by the user: **WWK / V75 / W0.24 / S1.2 / K0.165 / H0**, 0.4-mm road architecture. Physical observation: great black, good colour response, fairly bright, and substantially better than the user's commercial ALR screen. Main remaining issue: feature size.

The 0.2-mm scaling study found this case is unusually suitable for exact 2:1 miniaturisation because half the cap dose is **0.0825 mm**, just above the user's 0.08-mm minimum. Exact scaled target: **road width 0.20 / W0.12 / K0.0825 / S1.2 / V75 / H0**.

Highest-resolution reconstructed optical model: 0.4 case B/A/C **115.543 / 104.182 / 110.905**, pitch **2.128650 mm**, mean dark band **1.591531 mm**; 0.2 half-scale case B/A/C **115.576 / 104.192 / 110.926**, pitch **1.064990 mm**, mean dark band **0.796192 mm**. Total optical height halves **0.774 -> 0.387 mm**.

These are model predictions, not physical measurements. Current v1.158 is still a 0.4-mm-road converter; a future 0.2-mm printer revision must scale road width, blocker geometry, physical-clearance floors, spacing, extrusion calibration, metadata and audits rather than only changing slicer nozzle diameter.
