# SDDP Hydrothermal Dispatch Solver — Code Extracts

> **These are extracts from a production 108K+ LOC codebase**, not a toy project.
> Files are trimmed to their most representative sections; the full implementation
> is substantially larger.

## What This Is

A **Stochastic Dual Dynamic Programming (SDDP)** solver for long-term hydrothermal
dispatch planning, built to model the **Chilean national electricity grid (SEN)**.

The full system handles:

- **300+ generators**: hydro reservoirs, run-of-river, thermal (coal, gas, diesel), solar, wind, battery storage (BESS)
- **200+ transmission lines** with piecewise-linear loss modeling
- **30+ reservoirs** with full hydraulic cascade topology (turbine/spill routing, seepage, extraction)
- **10-block temporal resolution** per month across a **120-month planning horizon**
- **Irrigation agreements** (Convenio del Laja, Convenio del Maule) — legal water-sharing constraints unique to Chilean hydrology
- **Operational constraints**: Ralco minimum flow, reservoir spillway modeling, maintenance schedules

## Full Project Scope

| Component | Description |
|---|---|
| **SDDP Algorithm** | Forward/backward passes, Benders cut generation, Expected Value cuts (Philpott & Guan 2008), cut regularization, parallel multi-scenario execution |
| **Persistent Model** | Build-once/update-many pattern with Pyomo + CPLEX/Gurobi persistent solvers — **17x speedup** (5 hours to 18 minutes for full SEN case) |
| **Multi-Block Architecture** | Simultaneous optimization of all hourly blocks per stage, enabling optimal battery dispatch instead of greedy |
| **Benders Decomposition** | Optimality cuts with dual regularization, seed cuts from Fortran binary files, per-stage incremental cut management |
| **Legacy Fortran Interop** | Reads 40+ binary/text data formats from legacy Fortran solver, loads pre-converged Benders cuts from stage data files |
| **Transmission Losses** | O(n^2) piecewise-linear loss approximation (improved from O(n^3) in earlier versions) |
| **Unit Commitment** | Thermal startup costs, minimum up/down times, ramping constraints |
| **Battery Storage (BESS)** | Full state-of-charge balance, charge/discharge efficiency, multi-injector support |
| **Irrigation Agreements** | Laja and Maule river water-sharing protocols with seasonal state variables |
| **Regression Testing** | Python vs. Fortran comparison tests verifying generation, costs, and reservoir volumes match within tolerance |

## What These Extracts Show

### `algorithm/sddp.py` — Core SDDP Algorithm
The main solve loop, Benders cut data structures (`BendersCut`, `CutsManager`),
forward/backward pass orchestration, Expected Value cut generation with stratified
sampling over hydrological classes, dual regularization (Level Method), and parallel
backward pass execution.

### `core/persistent_model.py` — 17x Speedup Pattern
The `PersistentStageModel` class that builds a Pyomo LP model once and reuses it
across thousands of solve calls. Shows: mutable parameter design, deferred
`set_instance()`, incremental Benders cut addition via `add_constraint()`,
hydraulic cascade topology construction with recursive downstream search, and
the full power balance + water balance constraint formulation.

### `core/schemas.py` — Domain Model
Typed dataclass schemas for the complete hydrothermal system: temporal configuration
(stages, blocks), network topology (buses, transmission lines with loss coefficients),
generation centrals (hydro with cascade routing, thermal with UC parameters),
hydrology (inflow arrays, simulation indices, scenario trees), and battery storage.

### `tests/test_sddp.py` — Unit & Integration Tests
Unit tests for `BendersCut`, `CutsManager`, `SDDPEngine` initialization, forward pass,
convergence behavior, and parallel execution. Integration tests comparing Python solver
output against the legacy Fortran reference implementation (generation totals, reservoir
behavior, deficit detection).

## Tech Stack

- **Python 3.11+** with type hints throughout
- **Pyomo** for algebraic modeling (LP/MILP)
- **CPLEX / Gurobi** persistent solver APIs
- **NumPy** for hydrology arrays and stochastic sampling
- **Rich** for progress bars
- **pytest** with fixtures, markers, and parametrized tests
