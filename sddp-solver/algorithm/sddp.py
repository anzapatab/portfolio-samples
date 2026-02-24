# Extract from production SDDP solver (108K+ LOC)
# Extract from full implementation (~1500 lines). Shows core SDDP loop,
# Benders cut management, forward/backward passes, and convergence logic.
"""
Stochastic Dual Dynamic Programming (SDDP) algorithm implementation.

This module implements the SDDP algorithm for long-term hydrothermal
dispatch planning, with support for parallel execution, Expected Value
cuts, and Benders cut regularization.

Production solver for the Chilean national electricity grid (SEN):
- 300+ generators (hydro, thermal, solar, wind, battery storage)
- 200+ transmission lines with loss modeling
- 30+ reservoirs with hydraulic cascade topology
- 10-block temporal resolution per month, 120-month horizon
"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any


import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from solver.core.schemas import SystemData

logger = logging.getLogger(__name__)

# Detect available CPUs
DEFAULT_WORKERS = max(1, os.cpu_count() or 1)


@dataclass
class SDDPConfig:
    """
    SDDP algorithm configuration.

    Attributes:
        max_iterations: Maximum number of iterations
        tolerance: Convergence tolerance (relative gap)
        n_forward_scenarios: Number of forward pass scenarios
        n_backward_scenarios: Number of backward pass scenarios
        solver_name: Solver to use (cplex, gurobi, highs)
        seed: Random seed for reproducibility
        verbose: Verbosity level (0=silent, 1=summary, 2=detailed)
        n_workers: Number of parallel workers (None=auto)
        parallel: Enable parallel execution
    """

    max_iterations: int = 100
    tolerance: float = 0.01  # 1% gap
    n_forward_scenarios: int = 1
    n_backward_scenarios: int = 1
    solver_name: str = "cplex"
    seed: int | None = None
    verbose: int = 1
    n_workers: int | None = None  # None = use all CPUs
    parallel: bool = False
    data_dir: str | None = None
    use_persistent_model: bool = False
    usar_convenios: bool = False  # Enable irrigation agreements
    mes_inicio: int = 4  # April default (hydrological year start)
    runtime_config: Any = None
    simulation_only: bool = False  # If True, only run forward pass
    usar_perturbacion_duales: bool = False
    epsilon_perturbacion: float = 0.1  # Volume perturbation epsilon (Hm3)
    valor_terminal_agua: float | None = None  # Terminal water value (USD/Hm3)
    modelar_perdidas: bool = True  # Model transmission losses

    # === SDDP stabilization parameters (LB > UB solution) ===
    use_expected_value_cuts: bool = True  # Average cuts over multiple hydro classes
    n_classes_for_cuts: int = 5  # Number of classes for EV cut averaging
    lb_use_expected_value: bool = True  # Compute LB as E[Q(x)] over classes
    lb_n_samples: int = 5  # Number of classes to sample for LB
    cut_regularization: bool = True  # Regularize duals to avoid extrapolation
    cut_reg_factor: float = 0.8  # Regularization factor (0-1, lower = more conservative)
    max_pi_magnitude: float = 5e4  # Maximum |pi| (USD/Hm3) — reduced for stability

    # === Battery model ===
    usar_baterias_completas: bool = True
    usar_multibloque: bool = True  # Multi-block architecture (Fortran-style for BESS)

    # === Seed cuts from Fortran ===
    load_seed_cuts: bool = True  # Load pre-converged Benders cuts from Fortran files

    @property
    def workers(self) -> int:
        """Effective number of workers."""
        if self.n_workers is not None:
            return max(1, self.n_workers)
        return DEFAULT_WORKERS


@dataclass
class BendersCut:
    """
    Represents a Benders optimality cut.

    A cut has the form:
        alpha >= rhs + sum(pi_emb[e] * (vol[e] - vol_ref[e]))
                     + sum(pi_laja[v] * (laja_var[v] - laja_ref[v]))
                     + sum(pi_maule[v] * (maule_var[v] - maule_ref[v]))

    Includes reservoir duals and water sharing agreement factors.
    """

    etapa: int
    rhs: float
    pi: dict[int, float]
    vol_ref: dict[int, float]
    pi_laja: dict[str, float] = field(default_factory=dict)
    laja_ref: dict[str, float] = field(default_factory=dict)
    pi_maule: dict[str, float] = field(default_factory=dict)
    maule_ref: dict[str, float] = field(default_factory=dict)
    iteration: int = 0

    def to_dict(self) -> dict:
        """Convert cut to dictionary for model consumption."""
        return {
            "rhs": self.rhs,
            "pi": self.pi,
            "vol_ref": self.vol_ref,
            "pi_laja": self.pi_laja,
            "laja_ref": self.laja_ref,
            "pi_maule": self.pi_maule,
            "maule_ref": self.maule_ref,
        }

    def has_convenio_terms(self) -> bool:
        """Returns True if the cut includes irrigation agreement terms."""
        return bool(self.pi_laja) or bool(self.pi_maule)


@dataclass
class SDDPResult:
    """
    SDDP algorithm results.

    Attributes:
        converged: Whether the algorithm converged
        iterations: Number of iterations performed
        lower_bound: Lower bound (optimal first-stage value)
        upper_bound: Upper bound (expected simulation cost)
        gap: Convergence gap
        execution_time: Execution time in seconds
    """

    converged: bool = False
    iterations: int = 0
    lower_bound: float = 0.0
    upper_bound: float = float("inf")
    gap: float = float("inf")
    execution_time: float = 0.0
    lower_bounds: list[float] = field(default_factory=list)
    upper_bounds: list[float] = field(default_factory=list)
    cuts_per_stage: dict[int, int] = field(default_factory=dict)

    @property
    def expected_cost(self) -> float:
        """Expected system cost (lower bound if converged)."""
        return self.lower_bound


class CutsManager:
    """
    Benders cuts manager.

    Administers cuts generated during the SDDP algorithm, organized by stage.
    """

    def __init__(self, n_etapas: int) -> None:
        self.n_etapas = n_etapas
        self._cuts: dict[int, list[BendersCut]] = {t: [] for t in range(1, n_etapas + 1)}

    def add_cut(self, cut: BendersCut) -> None:
        """Add a cut to the manager."""
        self._cuts[cut.etapa].append(cut)

    def get_cuts(self, etapa: int) -> list[BendersCut]:
        """Get cuts for a stage."""
        return self._cuts.get(etapa, [])

    def get_cuts_as_dicts(self, etapa: int) -> list[dict]:
        """Get cuts as dictionaries for model consumption."""
        return [cut.to_dict() for cut in self._cuts.get(etapa, [])]

    def n_cuts(self, etapa: int) -> int:
        return len(self._cuts.get(etapa, []))

    def total_cuts(self) -> int:
        return sum(len(cuts) for cuts in self._cuts.values())

    def summary(self) -> dict[int, int]:
        return {t: len(cuts) for t, cuts in self._cuts.items()}


class SDDPEngine:
    """
    SDDP algorithm engine.

    Implements the complete SDDP algorithm:
    - Forward pass: Forward simulation
    - Backward pass: Benders cut generation
    - Convergence criterion based on gap

    Example:
        >>> reader = LegacyDataReader("./casos/caso1")
        >>> system = reader.read_all()
        >>> config = SDDPConfig(max_iterations=50, tolerance=0.01)
        >>> engine = SDDPEngine(system, config)
        >>> result = engine.solve()
        >>> print(f"Expected cost: {result.expected_cost:.2f}")
    """

    def __init__(self, system: SystemData, config: SDDPConfig | None = None) -> None:
        self.system = system
        self.config = config or SDDPConfig()

        # Initialize RNG for reproducibility
        self._rng = np.random.default_rng(self.config.seed)

        # Benders cuts manager
        self.cuts = CutsManager(system.n_etapas)

        # Reservoir indices
        self._embalses_ids = [
            cen_id
            for cen_id, cen in system.centrales.items()
            if cen.tiene_embalse
        ]

        # Per-iteration results cache
        self._iteration_results: list[dict] = []

        # Auto-calculate terminal water value if not specified
        # Replicates Fortran behavior where water has value based on marginal thermal cost
        if self.config.valor_terminal_agua is None:
            self._init_terminal_water_value()

        # Load pre-converged Benders cuts from Fortran files
        # Replicates Fortran where SDDP starts with cuts from previous runs
        if self.config.load_seed_cuts:
            self._init_seed_cuts()

    # --- Initialization helpers (trimmed for brevity) ---
    # Full implementation includes: _init_terminal_water_value, _init_seed_cuts,
    # _init_baterias, _init_persistent_model, _init_convenios, _init_restricciones

    def solve(self) -> SDDPResult:
        """
        Execute the SDDP algorithm.

        Returns:
            SDDPResult with convergence info and bounds history
        """
        start_time = time.time()
        result = SDDPResult()

        if self.config.verbose >= 1:
            logger.info(
                f"Starting SDDP: {self.system.n_etapas} stages, "
                f"{len(self._embalses_ids)} reservoirs, "
                f"max_iter={self.config.max_iterations}"
            )

        for iteration in range(1, self.config.max_iterations + 1):
            if self.config.verbose >= 2:
                logger.info(f"=== Iteration {iteration} ===")

            # DO NOT clear cuts here — they must accumulate across iterations
            # as in Fortran! The PersistentStageModel handles incremental cuts
            # via logic in update_and_solve() (compares n_cuts_received vs
            # _n_cuts_in_model). This avoids calling set_instance() which would
            # destroy all persistent solver benefits.

            # Forward Pass (multiple scenarios if configured)
            forward_results = self._forward_pass_multiple(self.config.n_forward_scenarios)

            # Compute upper bound as average of scenario costs
            upper_bound = np.mean([r["costo_total"] for r in forward_results])
            result.upper_bounds.append(upper_bound)

            # Simulation-only mode: forward pass only, no backward
            if self.config.simulation_only:
                result.upper_bound = upper_bound
                result.lower_bound = upper_bound
                result.lower_bounds.append(upper_bound)
                result.gap = 0.0
                result.converged = True
                result.iterations = iteration
                break

            # Backward Pass (use states from scenario closest to average)
            best_idx = np.argmin([
                abs(r["costo_total"] - upper_bound) for r in forward_results
            ])
            self._backward_pass(forward_results[best_idx]["estados"])

            # Compute lower bound (resolve first stage with cuts)
            lower_bound = self._compute_lower_bound()
            result.lower_bounds.append(lower_bound)

            # Update best bounds
            if upper_bound < result.upper_bound:
                result.upper_bound = upper_bound
            result.lower_bound = lower_bound

            # Compute gap — works correctly for positive AND negative costs
            # For minimization: LB <= Optimal <= UB
            # Gap = |UB - LB| / max(|LB|, |UB|, eps)
            if lower_bound <= result.upper_bound:
                denominator = max(abs(lower_bound), abs(result.upper_bound), 1e-10)
                gap = abs(result.upper_bound - lower_bound) / denominator
            else:
                # LB > UB indicates cuts are not yet consistent
                gap = float("inf")
            result.gap = gap

            if self.config.verbose >= 1:
                logger.info(
                    f"Iter {iteration}: LB={lower_bound:.2f}, UB={upper_bound:.2f}, "
                    f"gap={gap*100:.2f}%, cuts={self.cuts.total_cuts()}"
                )

            # Check convergence
            if gap <= self.config.tolerance:
                result.converged = True
                result.iterations = iteration
                break

            result.iterations = iteration

        result.execution_time = time.time() - start_time
        result.cuts_per_stage = self.cuts.summary()

        if self.config.verbose >= 1:
            status = "converged" if result.converged else "did not converge"
            logger.info(
                f"SDDP {status} in {result.iterations} iterations, "
                f"time={result.execution_time:.2f}s"
            )

        return result

    def _backward_pass(self, estados: list[dict]) -> None:
        """
        Execute backward pass (cut generation).

        Traverses stages from back to front, generating Benders cuts
        to approximate the future cost function. Supports Expected Value
        Cuts when use_expected_value_cuts=True.

        Args:
            estados: States from the forward pass
        """
        # Traverse stages backward (except the last)
        for t in range(self.system.n_etapas - 1, 0, -1):
            estado = estados[t - 1]  # State at end of stage t
            volumenes_ref = estado["volumenes"]

            if self.config.use_expected_value_cuts:
                # Expected Value Cuts: average over multiple hydro classes
                cut = self._generate_expected_value_cut(t, volumenes_ref)
                if cut is not None:
                    self.cuts.add_cut(cut)
            elif self.config.parallel and self.config.n_backward_scenarios > 1:
                # Parallel execution of scenarios
                cuts = self._backward_pass_parallel(t, volumenes_ref)
                for cut in cuts:
                    if cut is not None:
                        self.cuts.add_cut(cut)
            else:
                # Sequential execution
                for _ in range(self.config.n_backward_scenarios):
                    clase_siguiente = self._sample_clase_hidrologica(t + 1)
                    cut = self._generate_cut(
                        etapa_actual=t,
                        volumenes_ref=volumenes_ref,
                        clase_siguiente=clase_siguiente,
                    )
                    if cut is not None:
                        self.cuts.add_cut(cut)

    def _generate_expected_value_cut(
        self,
        etapa_actual: int,
        volumenes_ref: dict[int, float],
    ) -> BendersCut | None:
        """
        Generate a Benders cut averaged over multiple hydrological classes.

        Expected Value Cut: averages rhs and pi over n_classes_for_cuts classes,
        producing a more stable cut less prone to over-estimation.

        Reference: Philpott & Guan (2008), "On the convergence of SDDP"

        Args:
            etapa_actual: Stage where the cut will be added
            volumenes_ref: Reference volumes

        Returns:
            Averaged Benders cut or None on error
        """
        n_clases_total = 1
        if self.system.config_hidrologica:
            n_clases_total = self.system.config_hidrologica.n_clases

        # Select classes to average (uniformly distributed)
        n_samples = min(self.config.n_classes_for_cuts, n_clases_total)
        if n_clases_total <= n_samples:
            clases = list(range(1, n_clases_total + 1))
        else:
            # Stratified sampling
            step = n_clases_total / n_samples
            clases = [int(1 + i * step) for i in range(n_samples)]

        # Accumulators for averaging
        rhs_sum = 0.0
        pi_sum: dict[int, float] = {e: 0.0 for e in self._embalses_ids}
        pi_laja_sum: dict[str, float] = {}
        pi_maule_sum: dict[str, float] = {}
        laja_ref_final: dict[str, float] = {}
        maule_ref_final: dict[str, float] = {}
        n_valid = 0

        for clase in clases:
            cut = self._generate_cut(
                etapa_actual=etapa_actual,
                volumenes_ref=volumenes_ref,
                clase_siguiente=clase,
            )
            if cut is not None:
                rhs_sum += cut.rhs
                for e, pi in cut.pi.items():
                    pi_sum[e] += pi

                # Accumulate irrigation agreement duals
                if cut.pi_laja:
                    for k, v in cut.pi_laja.items():
                        pi_laja_sum[k] = pi_laja_sum.get(k, 0.0) + v
                    if not laja_ref_final and cut.laja_ref:
                        laja_ref_final = cut.laja_ref.copy()

                if cut.pi_maule:
                    for k, v in cut.pi_maule.items():
                        pi_maule_sum[k] = pi_maule_sum.get(k, 0.0) + v
                    if not maule_ref_final and cut.maule_ref:
                        maule_ref_final = cut.maule_ref.copy()

                n_valid += 1

        if n_valid == 0:
            return None

        # Average
        rhs_avg = rhs_sum / n_valid
        pi_avg = {e: pi / n_valid for e, pi in pi_sum.items()}
        pi_laja_avg = {k: v / n_valid for k, v in pi_laja_sum.items()}
        pi_maule_avg = {k: v / n_valid for k, v in pi_maule_sum.items()}

        # Apply regularization if enabled
        if self.config.cut_regularization:
            pi_avg = self._regularize_duals(pi_avg)

        return BendersCut(
            etapa=etapa_actual,
            rhs=rhs_avg,
            pi=pi_avg,
            vol_ref=volumenes_ref.copy(),
            pi_laja=pi_laja_avg,
            laja_ref=laja_ref_final,
            pi_maule=pi_maule_avg,
            maule_ref=maule_ref_final,
            iteration=len(self._iteration_results) + 1,
        )

    def _regularize_duals(self, pi: dict[int, float]) -> dict[int, float]:
        """
        Regularize duals to prevent extreme extrapolation.

        Applies two types of regularization:
        1. Magnitude limit: |pi| <= max_pi_magnitude
        2. Contraction factor: pi *= cut_reg_factor

        Reference: Level Method (Lemarchal et al.)

        Args:
            pi: Dictionary of duals {reservoir_id: value}

        Returns:
            Regularized duals
        """
        pi_reg = {}
        for e, value in pi.items():
            # Apply regularization factor
            reg_value = value * self.config.cut_reg_factor

            # Limit magnitude
            if abs(reg_value) > self.config.max_pi_magnitude:
                reg_value = np.sign(reg_value) * self.config.max_pi_magnitude

            pi_reg[e] = reg_value

        return pi_reg

    def _generate_cut(
        self,
        etapa_actual: int,
        volumenes_ref: dict[int, float],
        clase_siguiente: int,
        simulacion: int = 1,
    ) -> BendersCut | None:
        """
        Generate a Benders cut including irrigation agreement variables.

        Includes reservoir duals and water sharing agreement factors.

        Args:
            etapa_actual: Stage where the cut will be added
            volumenes_ref: Reference volumes
            clase_siguiente: Hydrological class of the next stage
            simulacion: Simulation number (for irrigation agreements)

        Returns:
            Benders cut or None on error
        """
        etapa_siguiente = etapa_actual + 1

        # Get cuts for next stage (predict cost from stage+1 onward)
        cortes_futuros = self.cuts.get_cuts_as_dicts(etapa_siguiente)

        # Solve with reference volumes to obtain base cost and duals
        costo_base, volumenes_finales, duales_result = self._solve_stage_cost(
            etapa_siguiente, volumenes_ref, clase_siguiente, cortes_futuros,
            simulacion, return_duals=True
        )

        if costo_base is None:
            logger.warning(f"Cut generation infeasible at stage {etapa_siguiente}")
            return None

        # Dual extraction strategy:
        # 1. Try direct duals from balance_hidrico (faster)
        # 2. If all zeros or unavailable, use perturbation (more robust)
        duales_directos = None
        if duales_result is not None:
            if isinstance(duales_result, dict):
                if 'balance' in duales_result:
                    duales_directos = duales_result.get('balance', {})
                else:
                    duales_directos = duales_result

        usar_duales_directos = False
        if duales_directos is not None:
            n_nonzero = sum(1 for v in duales_directos.values() if abs(v) > 0.01)
            if n_nonzero > 0:
                usar_duales_directos = True
                duales_volumen = duales_directos

        if not usar_duales_directos:
            if self.config.usar_perturbacion_duales:
                duales_volumen = self._compute_perturbation_duals(
                    etapa_siguiente, volumenes_ref, clase_siguiente, cortes_futuros,
                    simulacion, costo_base
                )
            else:
                duales_volumen = duales_directos if duales_directos else {
                    e: 0.0 for e in self._embalses_ids
                }

        # Build Benders cut: alpha >= Q(x_bar) + pi^T (x - x_bar)
        rhs = costo_base

        return BendersCut(
            etapa=etapa_actual,
            rhs=rhs,
            pi=duales_volumen,
            vol_ref=volumenes_ref.copy(),
            iteration=len(self._iteration_results) + 1,
        )

    def _backward_pass_parallel(
        self, etapa: int, volumenes_ref: dict[int, float]
    ) -> list[BendersCut | None]:
        """
        Execute backward pass in parallel for multiple scenarios.

        Args:
            etapa: Current stage
            volumenes_ref: Reference volumes

        Returns:
            List of generated cuts
        """
        # Pre-sample hydrological classes
        clases = [
            self._sample_clase_hidrologica(etapa + 1)
            for _ in range(self.config.n_backward_scenarios)
        ]

        tasks = [
            (etapa, volumenes_ref.copy(), clase)
            for clase in clases
        ]

        cuts = []
        n_workers = min(self.config.workers, len(tasks))

        # Use ThreadPoolExecutor (better for I/O-bound solver calls)
        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            futures = [
                executor.submit(self._generate_cut, *task)
                for task in tasks
            ]
            for future in futures:
                try:
                    cut = future.result()
                    cuts.append(cut)
                except Exception as e:
                    logger.warning(f"Error in backward parallel: {e}")
                    cuts.append(None)

        return cuts

    # --- Forward pass and helper methods (trimmed for brevity) ---
    # Full implementation includes:
    # - _forward_pass: Stage-by-stage simulation with progress bar
    # - _forward_pass_multiblock: All blocks per stage simultaneously (Fortran-style)
    # - _forward_pass_multiple: Parallel multi-scenario forward pass
    # - _compute_lower_bound: Re-solve first stage with accumulated cuts
    # - _compute_perturbation_duals: Finite-difference dual estimation
    # - _solve_stage_cost: Solve all blocks of a stage, return cost + duals
    # - _solve_stage_cost_multiblock: Multi-block variant
    # - _sample_clase_hidrologica: Sample hydrological class from transition matrix
    # - _get_volumenes_iniciales: Extract initial reservoir volumes
    # - _init_terminal_water_value: Compute terminal water value from marginal thermals
    # - _init_seed_cuts: Load pre-converged cuts from Fortran binary files
    # - get_policy_simulation: Monte Carlo policy evaluation
