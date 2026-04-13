# C++ Truncated Column Generation Solver

This directory contains a C++ truncated column generation solver for the current urban rail scheduler repository.

## Why the implementation is hybrid

The existing Python project already contains the business-critical logic for:

- XML parsing
- route/trip generation
- mixed large/small route turnback semantics
- same-turnback detection
- mixed-route arrival adjustment
- schedule-specific minimum/default/maximum turnback times

Reimplementing that entire stack in one pass would be high-risk and easy to diverge from the current 6-phase Python behavior. The implementation here therefore uses:

- `tools/export_cg_instance.py` to export a compact CG instance from the current Python code
- `cpp_cg/src/main.cpp` to solve that instance with truncated column generation in C++

This keeps the input semantics aligned with the existing Python project while moving the column generation core into C++.

## Trip discretization

The exporter keeps the legacy Python semantics and only discretizes the already-generated trip plan into a compact CG instance:

1. `phase0` and `phase1` produce the directional whole-day trip list.
2. Each exported trip becomes one `slot` with its nominal departure/arrival, direction, route, `xroad`, and headway metadata.
3. Each slot is shifted on its allowed departure grid to create `options`.
4. Feasible option-to-option turnbacks become `arcs`.
5. Adjacent slots in the same direction become `headways`.
6. Same-platform spacing violations between options become `option_conflicts`.
7. Turnback occupancy overlaps between arc events become `arc_conflicts`.
8. Legacy connected chains are optionally mapped back onto the same slot universe as initial `seed_columns`.

So the C++ solver does not re-decide the legacy route-pattern semantics. It solves the duty-selection core over the exported `slot / option / arc / conflict` instance.

## Modeling choices

- Headway is modeled explicitly in the master problem.
- Headway uses Python-aligned dispatch time, while turnback feasibility keeps physical departure/arrival time.
- Turnback resource is modeled implicitly through event-conflict rows.
- Only mixed-route and same-turnback cases generate turnback conflict rows.
- Turnback min/default/max times are taken from XML `TurnbackMode`.
- Same-turnback semantics follow the current Python `Engineering.judgeSameTurnback`.
- Mixed-route different-turnback effective arrival uses the current Python `RailInfo.computeNewArrival`.
- The initial restricted master includes singleton columns plus zero-shift path-cover duty seeds.
- Pricing supports a basis-neighborhood tabu heuristic.
- Pricing also injects basis-derived path-cover duty columns before exact reduced-cost DP columns.
- Pricing can switch between forward DP and bi-direction label search.
- Vehicle count uses an explicit master cap row with feasibility slack.
- First-car uses an explicit master row on top of the exported non-early option filter.
- Headway uniformity includes explicit target-gap deviation rows in the master.
- Legacy connected chains can be exported as initial seed columns; the current default is `phase5`.
- This is truncated CG only. There is no branch-and-price layer.

## Build

```powershell
cmake -S cpp_cg -B cpp_cg/build
cmake --build cpp_cg/build --config Release
```

The produced executable is `urban_rail_cg`.

If you build with the MSYS2 `mingw64` toolchain on Windows, ensure `C:\msys64\mingw64\bin` is on `PATH` during both build and run so GCC/CBC DLLs can be found.

## CLI

The executable keeps the current Python-style inputs where practical:

```powershell
urban_rail_cg `
  -r data/input_data_new/RailwayInfo/Schedule-cs2.xml `
  -u data/input_data_new/UserSettingInfoNew/cs2_同折返轨.xml `
  -o data/output_data/cpp_cg_cs2 `
  -m 1
```

Additional CG-specific options:

```powershell
urban_rail_cg `
  --instance-dir data/output_data/cpp_cg_cs2/cg_instance `
  --reuse-instance `
  --solver CBC `
  --cbc "C:\path\to\cbc.exe" `
  --max-iterations 40 `
  --min-iterations 40 `
  --master-time-limit 600 `
  --final-mip-time-limit 600 `
  --orthodox-tcg 1 `
  --tcg-fix-columns 5 `
  --tcg-fix-min-value 0.8 `
  --tcg-fix-force-value 0.9 `
  --tcg-incumbent-time-limit 60 `
  --mip-gap 0.005 `
  --seed-phase 5 `
  --pricing-batch 8 `
  --tabu 1 `
  --bidirectional-pricing 1
```

`--master-time-limit` applies to LP master solves. `--final-mip-time-limit` applies to the final integer master. When orthodox TCG is enabled, `--tcg-incumbent-time-limit` caps the interim integer masters that run after each new fixing round.

## Orthodox TCG loop

The current solver now follows an orthodox fix-and-reprice loop instead of only doing one last final MIP after CG stops:

1. Solve the restricted master LP under the current fixed column set.
2. Run pricing until no more negative reduced-cost columns exist for that fixed set.
3. First try to fix every feasible LP column with value at least `--tcg-fix-force-value`.
4. If no force-threshold column survives the hard-row screening, fall back to the top `--tcg-fix-columns` feasible columns whose LP values are at least `--tcg-fix-min-value`.
5. If that base-threshold bucket is still empty, use the top `--tcg-fix-columns` positive LP columns as a last-resort backstop so the fixing round does not stall.
6. Re-run LP pricing on the same accumulated column pool under the stronger bounds.
7. After each new fixing round, run a time-limited integer master and cache the best incumbent.
8. Run the final LP and final MIP, but export whichever integer incumbent is best across all interim and final integer solves.

While orthodox TCG fixing is active, column-pool pruning is disabled so the full priced pool stays available across fixing rounds.

## Output layout

The output directory contains two subdirectories:

- `cg_instance/`: exported compact CG instance from Python
- `cg_solution/`: C++ solution artifacts

Key solution files:

- `iterations.csv`
- `generated_columns.csv`
- `selected_duties.csv`
- `selected_trips.csv`
- `selected_turnbacks.csv`
- `selected_timetable.csv`
- `summary.json`
- `run_report.md`
- `result.xlsx` / `result.xls`
- `comparison_report.md`

Timing fields are exported in two places:

- `iterations.csv`: per-iteration `master_solve_sec`, `pricing_sec`, `tcg_round`, `fixed_columns_total`, `fixed_columns_added`, `incumbent_available`, `best_integer_objective`
- `summary.json`: aggregate `timing_master_sec`, `timing_pricing_sec`, `timing_other_sec`, `timing_total_sec`, `timing_tcg_incumbent_sec`, `timing_final_lp_sec`, `timing_final_mip_sec`
- `summary.json` / `run_report.md`: `selected_solution_source`, `fixed_column_count`, `fixing_round_count`, `root_pricing_exhausted`, `final_round_pricing_exhausted`

Detailed implementation notes are in `docs/CG_CPP_IMPLEMENTATION_NOTES.md`.

## Solver status on this machine

- Solver selection is explicit: `--solver CBC`, `--solver GUROBI`, or `--solver AUTO`.
- `GUROBI` first tries the Python bridge in `tools/solve_master_with_gurobi.py` via `gurobipy`; if that fails, the C++ driver falls back to `CBC`.
- `AUTO` now probes `gurobipy` first and otherwise falls back to `CBC`.
- On this machine, `gurobipy` is available, but the current license is size-limited. Small smoke models solve with Gurobi; large `cs4` master LP/MIP files can still fail with `Model too large for size-limited license`, then fall back to `CBC`.
- For large reproducible local runs, `--solver CBC` is still the practical choice unless an unrestricted Gurobi license is configured.

## Current scope and limitations

- The solver reuses Python for instance generation instead of reimplementing the full XML/domain layer in C++.
- Final outputs include a Python-side Excel bridge so the solver emits `result.xlsx` / `result.xls` in the solution directory.
- Depot in/out and full 6-phase repair/reoptimization are not rebuilt as a native C++ pipeline here.
- The CG master uses explicit headway rows and implicit turnback-conflict rows with slack penalties for robustness.
- `max_vehicle_count` is exported from `max(peak.train_num)`, then tightened by `depot_usable_trains` when depot data is available; if this still differs from whole-day vehicle-block semantics on a line, the summary exposes that via `vehicle_cap_slack`.
- On `cs4`, legacy `phase5` chains align with exported `phase1` slots better than legacy `phase6`, so seed export defaults to `--seed-phase 5`.
- On `cs4`, singleton collapse is currently driven mainly by exported hard conflict rows, especially `option_conflicts.csv`; this is documented in `docs/CG_CPP_IMPLEMENTATION_NOTES.md` with diagnostic runs.
