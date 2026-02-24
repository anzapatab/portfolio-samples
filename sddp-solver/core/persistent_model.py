# Extract from production SDDP solver (108K+ LOC)
# Extract from full implementation (~860 lines). Shows the persistent model
# pattern that achieves 17x speedup by building the LP once and updating
# only mutable parameters between solves.
"""
Persistent stage model for performance optimization.

This module implements PersistentStageModel, an optimized version of StageModel
that reuses the model structure between calls, eliminating reconstruction overhead
and reducing execution time by ~17x.

Key differences vs StageModel:
- Builds the model ONCE in __init__
- Uses persistent solvers (CPLEX/Gurobi) with direct API (no file I/O)
- Updates only variable parameters in each call
- Handles Benders cuts incrementally

Expected gain: 5 hours -> 18 minutes for full SEN case
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pyomo.environ as pyo
from pyomo.core import Param, Var, Constraint, Objective, ConstraintList
from pyomo.opt import SolverFactory

if TYPE_CHECKING:
    from solver.core.schemas import SystemData
    from solver.core.config import StageModelConfig
    from solver.algorithm.sddp import BendersCut

logger = logging.getLogger(__name__)


class PersistentStageModel:
    """
    Optimized stage model that reuses structure between calls.

    This model is built ONCE and then only the parameters that vary
    between blocks/stages are updated:
    - Initial reservoir volumes
    - Inflows by hydrological class
    - Block duration
    - Benders cuts (added incrementally)

    Example:
        >>> # Build once
        >>> pmodel = PersistentStageModel(system, config, solver_name='cplex')
        >>>
        >>> # Solve multiple times updating only parameters
        >>> for etapa in range(n_etapas):
        >>>     for bloque in range(n_bloques):
        >>>         result = pmodel.update_and_solve(
        >>>             etapa=etapa,
        >>>             bloque=bloque,
        >>>             volumenes_iniciales=vols,
        >>>             clase_hidrologica=clase
        >>>         )
    """

    def __init__(
        self,
        system: SystemData,
        config: StageModelConfig,
        solver_name: str = "cplex",
    ):
        self.system = system
        self.config = config
        self.solver_name = solver_name

        # Pyomo model (built once)
        self.model = None

        # Persistent solver
        self.solver = None

        # Per-stage cut tracking
        # CRITICAL: Cuts are PER-STAGE, so the counter must be too!
        self._n_cuts_in_model = {}

        # Auxiliary data caches
        self._cache_initialized = False
        self._turbinado_hacia = {}   # {emb_id: [cen_ids that turbine towards this reservoir]}
        self._vertimiento_hacia = {} # {emb_id: [cen_ids that spill towards this reservoir]}
        self._embalses_ids = []
        self._centrales_ids = []
        self._barras_ids = []
        self._lineas_ids = []

        # Build model (once only)
        logger.info("Building persistent model (one time only)...")
        self._build_once()
        logger.info("Persistent model built successfully")

    def _build_once(self) -> None:
        """
        Build the Pyomo model ONCE.

        Similar to StageModel.build() but marks ALL variable parameters
        as 'mutable=True' to allow updates without rebuilding.

        Structure:
        1. Create concrete Pyomo model
        2. Define indices and sets
        3. Define parameters (MUTABLE for variables, fixed for constants)
        4. Define decision variables
        5. Define constraints
        6. Define objective function
        7. Create and initialize persistent solver
        """
        try:
            m = pyo.ConcreteModel(name="Persistent_StageModel")

            # Suffix for importing duals
            m.dual = pyo.Suffix(direction=pyo.Suffix.IMPORT)

            # Delegate construction for clarity
            self._build_indices()
            self._build_sets(m)
            self._build_parameters(m)
            self._build_variables(m)
            self._build_constraints(m)
            self._build_objective(m)

            self.model = m

            # Create and configure persistent solver
            self._initialize_solver()

        except Exception as e:
            logger.error(f"Error building persistent model: {e}")
            raise RuntimeError(f"Failed to build persistent model: {e}") from e

    def _initialize_solver(self) -> None:
        """
        Initialize the persistent solver WITHOUT loading the model yet.

        CRITICAL: DO NOT call set_instance() here because model parameters
        have invalid default values (e.g., vol_inicial=0 < vol_min).
        set_instance() is called in the first update_and_solve() when
        parameters have real values.
        """
        try:
            if self.solver_name.lower() == "cplex":
                try:
                    from pyomo.solvers.plugins.solvers.cplex_persistent import CPLEXPersistent
                    self.solver = CPLEXPersistent()
                    self._is_truly_persistent = True
                    self._instance_set = False
                    logger.info("CPLEXPersistent created (set_instance deferred to first solve)")
                except (ImportError, Exception) as e:
                    logger.warning(
                        f"CPLEXPersistent unavailable ({e}), using standard solver"
                    )
                    self.solver = pyo.SolverFactory("cplex")
                    self._is_truly_persistent = False
                    self._instance_set = True

            elif self.solver_name.lower() == "gurobi":
                try:
                    from pyomo.solvers.plugins.solvers.gurobi_persistent import GurobiPersistent
                    self.solver = GurobiPersistent()
                    self._is_truly_persistent = True
                    self._instance_set = False
                except (ImportError, Exception) as e:
                    self.solver = pyo.SolverFactory("gurobi")
                    self._is_truly_persistent = False
                    self._instance_set = True
            else:
                self.solver = pyo.SolverFactory(self.solver_name)
                self._is_truly_persistent = False
                self._instance_set = True

        except Exception as e:
            raise RuntimeError(f"Failed to initialize solver: {e}") from e

    def _build_indices(self) -> None:
        """Build system index lists and hydraulic topology maps."""
        self._embalses_ids = [
            c.id for c in self.system.centrales.values()
            if c.tipo.name.startswith('EMBALSE')
        ]
        self._centrales_ids = list(self.system.centrales.keys())
        self._barras_ids = list(self.system.barras.keys())
        self._lineas_ids = list(self.system.lineas.keys())

        # Build hydraulic cascade topology
        self._turbinado_hacia = {e: [] for e in self._embalses_ids}
        self._vertimiento_hacia = {e: [] for e in self._embalses_ids}

        # Indirect inflow maps (non-reservoir centrals whose inflows
        # flow to downstream reservoirs — replicates Fortran behavior)
        self._afluencias_indirectas_hacia = {e: [] for e in self._embalses_ids}

        def find_embalse_downstream(central_id: int, visited: set[int] | None = None) -> int | None:
            """Trace cascade to find first downstream reservoir."""
            if visited is None:
                visited = set()
            if central_id in visited:
                return None  # Cycle detected
            visited.add(central_id)

            if central_id not in self.system.centrales:
                return None
            central = self.system.centrales[central_id]

            if central.tiene_embalse:
                return central_id

            aguas_abajo_turb = getattr(central, 'central_aguas_abajo', None)
            aguas_abajo_vert = getattr(central, 'central_aguas_abajo_vert', None)

            for next_id in [aguas_abajo_turb, aguas_abajo_vert]:
                if next_id is not None:
                    if next_id in self.system.centrales and self.system.centrales[next_id].tiene_embalse:
                        return next_id

            for next_id in [aguas_abajo_turb, aguas_abajo_vert]:
                if next_id is not None:
                    result = find_embalse_downstream(next_id, visited.copy())
                    if result is not None:
                        return result
            return None

        for cen_id, central in self.system.centrales.items():
            if central.tiene_embalse:
                if hasattr(central, 'central_aguas_abajo') and central.central_aguas_abajo:
                    if central.central_aguas_abajo in self._embalses_ids:
                        self._turbinado_hacia[central.central_aguas_abajo].append(cen_id)
                if hasattr(central, 'central_aguas_abajo_vert') and central.central_aguas_abajo_vert:
                    if central.central_aguas_abajo_vert in self._embalses_ids:
                        self._vertimiento_hacia[central.central_aguas_abajo_vert].append(cen_id)
            else:
                embalse_destino = find_embalse_downstream(cen_id)
                if embalse_destino in self._afluencias_indirectas_hacia:
                    self._afluencias_indirectas_hacia[embalse_destino].append(cen_id)

    def _build_parameters(self, m: pyo.ConcreteModel) -> None:
        """
        Define model parameters.

        IMPORTANT: Parameters that change between calls must be mutable=True
        """
        # === MUTABLE PARAMETERS (change between calls) ===
        m.duracion_bloque = Param(mutable=True, default=168.0, doc="Duration in hours")
        m.vol_inicial = Param(m.EMBALSES, mutable=True, default=0.0, doc="Initial volume Hm3")
        m.afluencia = Param(m.EMBALSES, mutable=True, default=0.0, doc="Inflow m3/s")
        m.afluencia_indirecta = Param(m.EMBALSES, mutable=True, default=0.0, doc="Indirect inflow m3/s")

        # === FIXED PARAMETERS (system constants) ===
        m.vol_min = Param(m.EMBALSES, initialize=self._init_vol_min, doc="Min volume Hm3")
        m.vol_max = Param(m.EMBALSES, initialize=self._init_vol_max, doc="Max volume Hm3")
        m.rendimiento = Param(m.EMBALSES, initialize=self._init_rendimiento, doc="Efficiency MW/(m3/s)")
        m.caudal_max = Param(m.EMBALSES, initialize=self._init_caudal_max, doc="Max turbine flow m3/s")
        m.potencia_min = Param(m.CENTRALES, initialize=self._init_potencia_min, doc="Min power MW")
        m.potencia_max = Param(m.CENTRALES, initialize=self._init_potencia_max, doc="Max power MW")
        m.costo_variable = Param(m.CENTRALES, initialize=self._init_costo_var, doc="Variable cost USD/MWh")
        m.demanda = Param(m.BARRAS, mutable=True, initialize=self._init_demanda, doc="Demand MW")
        m.flujo_max = Param(m.LINEAS, initialize=self._init_flujo_max, doc="Max flow MW")

    def _build_variables(self, m: pyo.ConcreteModel) -> None:
        """Define decision variables."""
        m.gen = Var(m.CENTRALES, domain=pyo.NonNegativeReals, doc="Generation MW")
        m.flujo = Var(m.LINEAS, domain=pyo.Reals, doc="Line flow MW")
        m.volumen = Var(m.EMBALSES, domain=pyo.NonNegativeReals, doc="Final volume Hm3")
        m.turbinado = Var(m.EMBALSES, domain=pyo.NonNegativeReals, doc="Turbined flow m3/s")
        m.vertimiento = Var(m.EMBALSES, domain=pyo.NonNegativeReals, doc="Spilled flow m3/s")

        # Future cost variable (for Benders cuts)
        m.alpha = Var(domain=pyo.Reals, bounds=(0, 1e12), doc="Approximate future cost")

    def _build_constraints(self, m: pyo.ConcreteModel) -> None:
        """Define model constraints."""
        # Power balance per bus
        def balance_potencia_rule(m, b):
            gen_barra = sum(
                m.gen[c] for c in m.CENTRALES
                if self.system.centrales[c].barra == b
            )
            flujos_entrantes = sum(m.flujo[l] for l in m.LINEAS if m.barra_destino[l] == b)
            flujos_salientes = sum(m.flujo[l] for l in m.LINEAS if m.barra_origen[l] == b)
            return gen_barra - m.demanda[b] + flujos_entrantes - flujos_salientes == 0

        m.balance_potencia = Constraint(m.BARRAS, rule=balance_potencia_rule)

        # Generation limits
        m.gen_min_cons = Constraint(m.CENTRALES, rule=lambda m, c: m.gen[c] >= m.potencia_min[c])
        m.gen_max_cons = Constraint(m.CENTRALES, rule=lambda m, c: m.gen[c] <= m.potencia_max[c])

        # Transmission line limits
        m.flujo_limite = Constraint(m.LINEAS,
            rule=lambda m, l: (-m.flujo_max[l], m.flujo[l], m.flujo_max[l]))

        # Hydraulic constraints
        if self._embalses_ids:
            factor_conversion = 3.6 / 1e6  # m3/s * hours -> Hm3

            def balance_hidrico_rule(m, e):
                duracion = m.duracion_bloque
                aporte_turb = sum(m.turbinado[c] for c in self._turbinado_hacia[e] if c in m.EMBALSES)
                aporte_vert = sum(m.vertimiento[c] for c in self._vertimiento_hacia[e] if c in m.EMBALSES)
                return m.volumen[e] == (
                    m.vol_inicial[e]
                    + (m.afluencia[e] + m.afluencia_indirecta[e]
                       + aporte_turb + aporte_vert - m.turbinado[e] - m.vertimiento[e])
                    * duracion * factor_conversion
                )

            m.balance_hidrico = Constraint(m.EMBALSES, rule=balance_hidrico_rule)
            m.gen_turbinado = Constraint(m.EMBALSES,
                rule=lambda m, e: m.gen[e] == m.rendimiento[e] * m.turbinado[e])
            m.vol_min_cons = Constraint(m.EMBALSES, rule=lambda m, e: m.volumen[e] >= m.vol_min[e])
            m.turbinado_max_cons = Constraint(m.EMBALSES,
                rule=lambda m, e: m.turbinado[e] <= m.caudal_max[e])

        # ConstraintList for Benders cuts (added dynamically)
        m.cortes_benders = ConstraintList()

    def _build_objective(self, m: pyo.ConcreteModel) -> None:
        """Define objective function."""
        def costo_total_rule(m):
            costo_op = sum(m.costo_variable[c] * m.gen[c] * m.duracion_bloque for c in m.CENTRALES)
            return costo_op + m.alpha

        m.costo_total = Objective(rule=costo_total_rule, sense=pyo.minimize)

    # === Main method: update and solve ===

    def update_and_solve(
        self,
        etapa: int,
        bloque: int,
        volumenes_iniciales: dict[int, float],
        clase_hidrologica: int,
        cortes: list[BendersCut] | None = None,
    ) -> dict:
        """
        Update model parameters and solve (without rebuilding).

        This is the main method called at each block. Only updates mutable
        parameter values and solves using the already-built model structure.

        Args:
            etapa: Stage number (1-based)
            bloque: Block number (1-based)
            volumenes_iniciales: Initial volumes per reservoir {emb_id: vol_Hm3}
            clase_hidrologica: Hydrological class index
            cortes: Benders cuts to add (optional)

        Returns:
            Dictionary with results (costo_total, generacion, volumenes, etc.)

        Raises:
            RuntimeError: If the model is infeasible
        """
        try:
            # 1. Update initial volumes
            for emb_id in self._embalses_ids:
                self.model.vol_inicial[emb_id] = volumenes_iniciales.get(emb_id, 0.0)

            # 2. Update inflows
            afluencias = self._get_afluencias(etapa, bloque, clase_hidrologica)
            for emb_id in self._embalses_ids:
                self.model.afluencia[emb_id] = afluencias.get(emb_id, 0.0)

            # 2.5. Update indirect inflows (from non-reservoir centrals upstream)
            for emb_id in self._embalses_ids:
                afl_indirecta = 0.0
                for c in self._afluencias_indirectas_hacia.get(emb_id, []):
                    if self.system.config_hidrologica and c in self.system.config_hidrologica.afluencias:
                        afl_indirecta += self.system.config_hidrologica.afluencias[c].caudal(
                            bloque, clase_hidrologica
                        )
                self.model.afluencia_indirecta[emb_id] = afl_indirecta

            # 3. Update block duration
            duracion = self._get_duracion_bloque(bloque)
            self.model.duracion_bloque = duracion

            # 4. Update demand per bus
            for barra_id in self._barras_ids:
                self.model.demanda[barra_id] = self._get_demanda_barra(barra_id, bloque)

            # 4.5. First call: load model into persistent solver
            # IMPORTANT: set_instance() called HERE (after parameter updates)
            # NOT in __init__ where parameters have invalid defaults.
            if self._is_truly_persistent and not self._instance_set:
                logger.info("First update_and_solve call: loading model into persistent solver")
                self.solver.set_instance(self.model)
                self._instance_set = True

            # 5. Update Benders cuts — CRITICAL OPTIMIZATION (like Fortran):
            # Cuts ACCUMULATE in the persistent model, NOT cleared.
            # Only add NEW cuts (incremental).
            # IMPORTANT: Per-stage tracking because cuts are stage-specific!
            n_cortes_recibidos = len(cortes) if cortes else 0
            n_cortes_actuales = self._n_cuts_in_model.get(etapa, 0)

            if n_cortes_recibidos > n_cortes_actuales:
                n_nuevos = n_cortes_recibidos - n_cortes_actuales
                cortes_nuevos = cortes[-n_nuevos:]

                for corte in cortes_nuevos:
                    self._add_benders_cut(corte)

                self._n_cuts_in_model[etapa] = n_cortes_recibidos

            elif n_cortes_recibidos < n_cortes_actuales:
                # Abnormal: fewer cuts than before. Clear and re-add.
                logger.warning(f"Stage {etapa}: Cut reduction {n_cortes_actuales} -> {n_cortes_recibidos}")
                self._clear_benders_cuts()
                for corte in cortes:
                    self._add_benders_cut(corte)
                self._n_cuts_in_model = {etapa: n_cortes_recibidos}

            # 6. Solve
            if self._is_truly_persistent:
                result = self.solver.solve(tee=False)
            else:
                result = self.solver.solve(self.model, tee=False, load_solutions=True)

            if result.solver.termination_condition != pyo.TerminationCondition.optimal:
                raise RuntimeError(f"Infeasible model at stage {etapa}, block {bloque}")

            # 7. Extract results
            return self._extract_results()

        except Exception as e:
            logger.error(f"Error in update_and_solve: {e}")
            raise

    def _add_benders_cut(self, corte: BendersCut) -> None:
        """
        Add a Benders cut to the persistent model.

        Uses add_constraint() from the persistent solver to add the constraint
        without rebuilding the entire model.
        """
        # Build cut expression: alpha >= rhs + sum(pi[e] * (vol[e] - vol_ref[e]))
        expr = corte.rhs + sum(
            corte.pi[emb_id] * (self.model.volumen[emb_id] - corte.vol_ref[emb_id])
            for emb_id in corte.pi
        )

        self.model.cortes_benders.add(self.model.alpha >= expr)

        # Notify persistent solver of new constraint
        if self._is_truly_persistent:
            new_idx = len(self.model.cortes_benders)
            self.solver.add_constraint(self.model.cortes_benders[new_idx])

    def _extract_results(self) -> dict:
        """Extract solution results."""
        m = self.model

        def safe_value(var, default=0.0):
            try:
                v = pyo.value(var, exception=False)
                return v if v is not None else default
            except Exception:
                return default

        costo_total = safe_value(m.costo_total)
        alpha_val = safe_value(m.alpha)

        results = {
            'optimal': True,
            'costo_total': costo_total,
            'costo_inmediato': costo_total - alpha_val,
            'alpha': alpha_val,
            'generacion': {c: safe_value(m.gen[c]) for c in m.CENTRALES},
            'flujos': {l: safe_value(m.flujo[l]) for l in m.LINEAS},
        }

        if self._embalses_ids:
            results['volumenes'] = {e: safe_value(m.volumen[e]) for e in m.EMBALSES}
            results['turbinado'] = {e: safe_value(m.turbinado[e]) for e in m.EMBALSES}
            results['vertimientos'] = {e: safe_value(m.vertimiento[e]) for e in m.EMBALSES}

        return results

    def get_duals(self) -> dict:
        """Extract constraint duals (water value)."""
        duales = {}
        try:
            duales['valor_agua'] = {
                e: self.model.dual[self.model.balance_hidrico[e]]
                for e in self.model.EMBALSES
            }
        except (KeyError, AttributeError):
            duales['valor_agua'] = {}
        return duales

    # --- Parameter initialization helpers (trimmed for brevity) ---
    # Full implementation includes: _init_vol_min, _init_vol_max,
    # _init_rendimiento, _init_caudal_max, _init_potencia_min/max,
    # _init_costo_var, _init_demanda, _init_flujo_max,
    # _get_afluencias, _get_duracion_bloque, _get_demanda_barra,
    # _clear_benders_cuts, clear_all_cuts, _build_sets,
    # _build_convenios_constraints, _build_baterias_constraints
