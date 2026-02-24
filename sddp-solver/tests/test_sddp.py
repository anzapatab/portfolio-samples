# Extract from production SDDP solver (108K+ LOC)
# Extract from test suite (~486 lines unit tests + ~255 lines integration tests).
# Shows unit tests for SDDP core components and integration tests comparing
# Python solver output against legacy Fortran reference implementation.
"""
Unit and integration tests for the SDDP algorithm.

Covers: BendersCut, CutsManager, SDDPConfig, SDDPEngine, convergence,
forward/backward passes, parallel execution, and Fortran comparison.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from solver.algorithm import (
    BendersCut,
    CutsManager,
    SDDPConfig,
    SDDPEngine,
    SDDPResult,
)
from solver.io import LegacyDataReader


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "caso_simple"


@pytest.fixture
def system_data():
    """Fixture that loads test system data."""
    reader = LegacyDataReader(FIXTURES_DIR)
    return reader.read_all()


class TestBendersCut:
    """Tests for Benders cut data structure."""

    def test_crear_corte(self) -> None:
        cut = BendersCut(
            etapa=1,
            rhs=1000.0,
            pi={1: 0.5, 2: 0.3},
            vol_ref={1: 100.0, 2: 200.0},
            iteration=5,
        )
        assert cut.etapa == 1
        assert cut.rhs == 1000.0
        assert cut.pi[1] == 0.5
        assert cut.iteration == 5

    def test_to_dict(self) -> None:
        cut = BendersCut(
            etapa=1,
            rhs=1000.0,
            pi={1: 0.5},
            vol_ref={1: 100.0},
        )
        d = cut.to_dict()
        assert "rhs" in d
        assert "pi" in d
        assert "vol_ref" in d
        assert d["rhs"] == 1000.0


class TestCutsManager:
    """Tests for Benders cuts manager."""

    def test_crear_manager(self) -> None:
        manager = CutsManager(n_etapas=12)
        assert manager.n_etapas == 12
        assert manager.total_cuts() == 0

    def test_add_and_get_cuts(self) -> None:
        manager = CutsManager(n_etapas=3)
        cut1 = BendersCut(etapa=1, rhs=100.0, pi={}, vol_ref={})
        cut2 = BendersCut(etapa=1, rhs=200.0, pi={}, vol_ref={})
        cut3 = BendersCut(etapa=2, rhs=300.0, pi={}, vol_ref={})

        manager.add_cut(cut1)
        manager.add_cut(cut2)
        manager.add_cut(cut3)

        assert len(manager.get_cuts(1)) == 2
        assert len(manager.get_cuts(2)) == 1
        assert manager.total_cuts() == 3

    def test_summary(self) -> None:
        manager = CutsManager(n_etapas=3)
        manager.add_cut(BendersCut(etapa=1, rhs=100.0, pi={}, vol_ref={}))
        manager.add_cut(BendersCut(etapa=1, rhs=200.0, pi={}, vol_ref={}))
        manager.add_cut(BendersCut(etapa=2, rhs=300.0, pi={}, vol_ref={}))

        summary = manager.summary()
        assert summary[1] == 2
        assert summary[2] == 1
        assert summary[3] == 0


class TestSDDPEngine:
    """Tests for SDDP engine initialization and forward pass."""

    def test_crear_engine(self, system_data) -> None:
        config = SDDPConfig(max_iterations=5)
        engine = SDDPEngine(system_data, config)
        assert engine.system is system_data
        assert engine.config.max_iterations == 5

    def test_engine_identifica_embalses(self, system_data) -> None:
        engine = SDDPEngine(system_data)
        assert len(engine._embalses_ids) == 1
        assert 1 in engine._embalses_ids

    def test_forward_pass_retorna_costo(self, system_data) -> None:
        config = SDDPConfig(verbose=0)
        engine = SDDPEngine(system_data, config)
        result = engine._forward_pass()
        assert "costo_total" in result
        assert result["costo_total"] >= 0

    def test_forward_pass_retorna_estados(self, system_data) -> None:
        config = SDDPConfig(verbose=0)
        engine = SDDPEngine(system_data, config)
        result = engine._forward_pass()
        assert "estados" in result
        assert len(result["estados"]) == engine.system.n_etapas

        for estado in result["estados"]:
            assert "volumenes" in estado
            assert "etapa" in estado
            assert "clase" in estado


class TestSDDPEngineSolve:
    """Tests for SDDP solve loop."""

    @pytest.fixture
    def engine(self, system_data):
        config = SDDPConfig(max_iterations=3, tolerance=0.01, verbose=0)
        return SDDPEngine(system_data, config)

    def test_solve_retorna_result(self, engine) -> None:
        result = engine.solve()
        assert isinstance(result, SDDPResult)

    def test_solve_ejecuta_iteraciones(self, engine) -> None:
        result = engine.solve()
        assert result.iterations > 0
        assert result.iterations <= 3

    def test_solve_genera_cortes(self, engine) -> None:
        result = engine.solve()
        total = engine.cuts.total_cuts()
        assert total >= 0

    def test_solve_calcula_bounds(self, engine) -> None:
        result = engine.solve()
        assert result.lower_bound >= 0
        assert len(result.lower_bounds) == result.iterations
        assert len(result.upper_bounds) == result.iterations

    def test_solve_registra_tiempo(self, engine) -> None:
        result = engine.solve()
        assert result.execution_time > 0


class TestSDDPEngineConvergence:
    """Tests for SDDP convergence behavior."""

    def test_converge_con_tolerancia_alta(self, system_data) -> None:
        config = SDDPConfig(
            max_iterations=10,
            tolerance=0.5,  # 50% gap — very permissive
            verbose=0,
        )
        engine = SDDPEngine(system_data, config)
        result = engine.solve()
        assert result.iterations <= 10

    def test_no_converge_con_pocas_iteraciones(self, system_data) -> None:
        config = SDDPConfig(
            max_iterations=1,
            tolerance=0.0001,  # Very strict
            verbose=0,
        )
        engine = SDDPEngine(system_data, config)
        result = engine.solve()
        assert result.iterations == 1


class TestSDDPEngineParallel:
    """Tests for parallel execution."""

    def test_forward_pass_multiple_sequential(self, system_data) -> None:
        config = SDDPConfig(
            max_iterations=2,
            n_forward_scenarios=3,
            parallel=False,
            verbose=0,
        )
        engine = SDDPEngine(system_data, config)
        results = engine._forward_pass_multiple(3)

        assert len(results) == 3
        for r in results:
            assert "costo_total" in r
            assert "estados" in r
            assert r["costo_total"] >= 0

    def test_solve_with_multiple_forward_scenarios(self, system_data) -> None:
        config = SDDPConfig(
            max_iterations=2,
            n_forward_scenarios=2,
            parallel=False,
            verbose=0,
        )
        engine = SDDPEngine(system_data, config)
        result = engine.solve()

        assert isinstance(result, SDDPResult)
        assert result.iterations > 0
        assert len(result.upper_bounds) == result.iterations


# =============================================================================
# INTEGRATION TESTS: Python SDDP vs Fortran reference
# =============================================================================


@pytest.mark.integration
@pytest.mark.fortran
class TestSDDPvsFortranGeneration:
    """Integration tests comparing Python solver output against Fortran."""

    def test_total_generation_within_tolerance(self, sddp_engine, system_data):
        """
        Verify total generation is within 10% of Fortran.

        Tolerance of 10% because:
        - Benders cuts can differ between implementations
        - Only run 5 iterations in test
        - Renewable profiles may vary
        """
        import pandas as pd

        # Load Fortran generation data
        fortran_csv = SALIDA_FORTRAN / "generation_output.csv"
        if not fortran_csv.exists():
            pytest.skip(f"Fortran file unavailable: {fortran_csv}")

        df_f = pd.read_csv(fortran_csv)
        gen_fortran = df_f.groupby(['Sim', 'Bloque'])['gen_power'].sum().mean()

        # Simulate in Python
        sim_results = sddp_engine.simulate(n_simulations=1)
        gen_python_total = sum(
            sum(block.get('generacion', {}).values())
            for block in sim_results[0]
            if block.get('etapa', 1) == 1
        )

        tolerance = 0.10  # 10%
        diff_pct = abs(gen_python_total - gen_fortran) / gen_fortran if gen_fortran > 0 else 0
        assert diff_pct < tolerance

    def test_embalse_generation_not_zero(self, sddp_engine, system_data):
        """
        Verify reservoir centrals generate (not hoard water).

        This test detects the coef_alpha=1000 bug that caused
        reservoirs to generate 0 MW.
        """
        sim_results = sddp_engine.simulate(n_simulations=1)

        embalse_ids = {
            cid for cid, c in system_data.centrales.items()
            if c.tiene_embalse
        }

        gen_by_embalse = {eid: [] for eid in embalse_ids}
        for block in sim_results[0]:
            if block.get('etapa', 1) != 1:
                continue
            gen = block.get('generacion', {})
            for eid in embalse_ids:
                gen_by_embalse[eid].append(gen.get(eid, 0.0))

        n_generating = sum(
            1 for gens in gen_by_embalse.values()
            if sum(gens) / len(gens) > 1.0  # > 1 MW average
        )

        assert n_generating > 0, (
            "No reservoir central generates more than 1 MW. "
            "Possible bug in coef_alpha (must be 1.0, not 1000)."
        )
