# Extract from production SDDP solver (108K+ LOC)
# Extract from full implementation (~940 lines). Shows the dataclass schemas
# that model the complete hydrothermal power system: generators, reservoirs,
# transmission network, hydrology, batteries, and irrigation agreements.
"""
Data schemas for the hydrothermal dispatch system.

Defines the data structures (dataclasses) that represent all components
of the hydrothermal electrical system: temporal configuration, network
topology, generation centrals, hydrology, demand, maintenance,
reserves, and battery storage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from solver.core.enums import TipoCentral, TipoPerdidas, TipoReserva, UnidadTiempo

if TYPE_CHECKING:
    from collections.abc import Mapping


# =============================================================================
# TEMPORAL CONFIGURATION
# =============================================================================


@dataclass(frozen=True, slots=True)
class Etapa:
    """
    A temporal stage of the planning horizon.

    Attributes:
        numero: Stage number (1-indexed)
        ano: Year of the stage
        mes: Month (1-12)
        duracion: Duration in the specified time unit
        tasa_descuento: Discount rate for this stage
    """

    numero: int
    ano: int
    mes: int
    duracion: float
    unidad_tiempo: UnidadTiempo = UnidadTiempo.MES
    tasa_descuento: float = 0.10
    dependencia_hidrologica: bool = True

    @property
    def horas(self) -> float:
        """Total duration in hours."""
        return self.duracion * self.unidad_tiempo.horas


@dataclass(frozen=True, slots=True)
class Bloque:
    """
    An hourly block within a stage.

    Attributes:
        numero: Block number (1-indexed)
        etapa: Stage number this block belongs to
        duracion: Block duration in hours
    """

    numero: int
    etapa: int
    duracion: float
    nombre: str = ""

    def __post_init__(self) -> None:
        if self.duracion <= 0:
            raise ValueError(f"Block duration must be > 0, got {self.duracion}")


@dataclass(slots=True)
class ConfiguracionTemporal:
    """Complete temporal configuration of the problem."""

    etapas: list[Etapa]
    bloques: list[Bloque]

    @property
    def n_etapas(self) -> int:
        return len(self.etapas)

    @property
    def n_bloques(self) -> int:
        return len(self.bloques)

    def bloques_por_etapa(self, etapa: int) -> list[Bloque]:
        return [b for b in self.bloques if b.etapa == etapa]

    def duracion_etapa(self, etapa: int) -> float:
        return sum(b.duracion for b in self.bloques_por_etapa(etapa))


# =============================================================================
# SYSTEM TOPOLOGY
# =============================================================================


@dataclass(frozen=True, slots=True)
class Barra:
    """A bus (node) of the electrical system."""

    id: int
    nombre: str

    def __hash__(self) -> int:
        return hash(self.id)


@dataclass(slots=True)
class Linea:
    """
    A transmission line.

    Attributes:
        capacidad_ab: Capacity A->B in MW
        capacidad_ba: Capacity B->A in MW
        resistencia: Resistance in Ohms (for loss modeling)
        reactancia: Reactance in Ohms
        n_tramos: Number of segments for loss linearization
    """

    id: int
    nombre: str
    barra_origen: int
    barra_destino: int
    capacidad_ab: float
    capacidad_ba: float
    voltaje_nominal: float = 220.0
    resistencia: float = 0.0
    reactancia: float = 0.01
    operativa: bool = True
    es_hvdc: bool = False
    modelar_perdidas: bool = True
    n_tramos: int = 3

    @property
    def susceptancia(self) -> float:
        if self.reactancia <= 0:
            return 0.0
        return 1.0 / self.reactancia

    @property
    def coef_perdidas(self) -> float:
        """Quadratic loss coefficient: R/V^2. Losses = coef * P^2."""
        if self.voltaje_nominal <= 0 or self.resistencia <= 0:
            return 0.0
        return self.resistencia / (self.voltaje_nominal ** 2)


# =============================================================================
# GENERATION CENTRALS
# =============================================================================


@dataclass(slots=True)
class Central:
    """
    A generation central (base class for all types).

    Attributes:
        tipo: Central type (E=reservoir, S=run-of-river, P=pass-through, T=thermal, B=battery, F=solar/wind)
        costo_variable: Variable cost in $/MWh
        costos_por_etapa: Per-stage cost overrides
    """

    id: int
    nombre: str
    tipo: TipoCentral
    barra: int
    potencia_min: float = 0.0
    potencia_max: float = 0.0
    costo_variable: float = 0.0
    factor_disponibilidad: float = 1.0
    costos_por_etapa: dict[int, float] = field(default_factory=dict)

    @property
    def es_hidraulica(self) -> bool:
        return TipoCentral.es_hidraulica(self.tipo)

    @property
    def tiene_embalse(self) -> bool:
        return TipoCentral.tiene_embalse(self.tipo)

    def costo_variable_etapa(self, etapa: int) -> float:
        return self.costos_por_etapa.get(etapa, self.costo_variable)


@dataclass(slots=True)
class CentralHidraulica(Central):
    """
    Hydraulic central extension.

    Models reservoir storage, turbine efficiency, hydraulic cascade
    topology, and seepage losses.
    """

    caudal_max: float = 0.0
    rendimiento: float = 1.0
    volumen_max: float = 0.0
    volumen_min: float = 0.0
    volumen_inicial: float = 0.0
    volumen_final: float = 0.0
    cota_max: float = 0.0
    cota_min: float = 0.0
    filtracion: float = 0.0
    central_aguas_abajo: int | None = None       # Downstream for turbined flow
    central_aguas_abajo_vert: int | None = None   # Downstream for spilled flow
    usa_funcion_costo_futuro: bool = True
    factor_escala: float = 1.0


@dataclass(slots=True)
class CentralTermica(Central):
    """Thermal central with unit commitment parameters."""

    costo_partida: float = 0.0
    tiempo_minimo_operacion: float = 0.0
    tiempo_minimo_detencion: float = 0.0
    rampa_subida: float = float("inf")
    rampa_bajada: float = float("inf")


# =============================================================================
# HYDROLOGY
# =============================================================================


@dataclass(slots=True)
class Afluencia:
    """
    Inflows to a hydraulic central.

    Attributes:
        caudales: Array of flows (n_blocks, n_classes) in m3/s
    """

    central_id: int
    caudales: NDArray[np.float64]  # shape: (n_bloques, n_clases)

    @property
    def n_bloques(self) -> int:
        return self.caudales.shape[0]

    @property
    def n_clases(self) -> int:
        return self.caudales.shape[1]

    def caudal(self, bloque: int, clase: int) -> float:
        return float(self.caudales[bloque - 1, clase - 1])


@dataclass(slots=True)
class ConfiguracionHidrologica:
    """
    Complete hydrological configuration.

    Attributes:
        n_clases: Number of hydrological classes
        afluencias: Inflows per central {central_id -> Afluencia}
        indices_simulacion: Class indices by (simulation, stage)
        indices_apertura: Scenario tree branching indices
    """

    n_clases: int
    n_simulaciones: int
    afluencias: dict[int, Afluencia]
    indices_simulacion: NDArray[np.int32]  # shape: (n_simul, n_etapas)
    indices_apertura: NDArray[np.int32] | None = None
    n_aperturas: NDArray[np.int32] | None = None

    def clase_simulacion(self, simulacion: int, etapa: int) -> int:
        return int(self.indices_simulacion[simulacion - 1, etapa - 1])


# =============================================================================
# BATTERY ENERGY STORAGE SYSTEMS (BESS)
# =============================================================================


@dataclass
class Bateria:
    """
    Battery Energy Storage System (BESS).

    Models charge/discharge cycles with efficiency losses,
    state-of-charge constraints, and multiple injection sources.
    """

    id: int
    nombre: str
    central_id: int
    barra: int
    energia_min: float = 0.0
    energia_max: float = 0.0
    factor_perdida_descarga: float = 0.95
    inyectores: list = field(default_factory=list)
    energia_min_bloque: dict[int, float] = field(default_factory=dict)
    energia_max_bloque: dict[int, float] = field(default_factory=dict)

    @property
    def eficiencia_ciclo(self) -> float:
        """Round-trip efficiency (charge + discharge)."""
        if not self.inyectores:
            return self.factor_perdida_descarga
        fpc_avg = sum(i.factor_perdida_carga for i in self.inyectores) / len(self.inyectores)
        return fpc_avg * self.factor_perdida_descarga


# =============================================================================
# MAIN CONTAINER
# =============================================================================


@dataclass(slots=True)
class SystemData:
    """
    Main container with all system data.

    Groups all components needed to build and solve the optimization model.
    """

    config_temporal: ConfiguracionTemporal
    barras: dict[int, Barra]
    lineas: dict[int, Linea]
    centrales: dict[int, Central]
    demanda: "Demanda"
    config_hidrologica: ConfiguracionHidrologica | None = None
    costos_variables: "CostosVariables | None" = None
    mantenimiento_centrales: dict = field(default_factory=dict)
    mantenimiento_lineas: dict = field(default_factory=dict)
    mantenimiento_embalses: dict = field(default_factory=dict)
    config_reservas: "ConfiguracionReservas | None" = None
    baterias: dict[int, Bateria] = field(default_factory=dict)
    rebalses: dict = field(default_factory=dict)
    filtraciones: dict = field(default_factory=dict)
    extracciones: dict = field(default_factory=dict)
    costos_min_embalse: dict = field(default_factory=dict)
    perdidas_transmision_activo: bool = True
    modo_perdidas: TipoPerdidas = TipoPerdidas.MIXTO
    nombre_caso: str = ""

    @property
    def n_etapas(self) -> int:
        return self.config_temporal.n_etapas

    @property
    def n_centrales(self) -> int:
        return len(self.centrales)

    @property
    def centrales_hidraulicas(self) -> dict[int, Central]:
        return {k: v for k, v in self.centrales.items() if v.es_hidraulica}

    @property
    def centrales_termicas(self) -> dict[int, Central]:
        return {k: v for k, v in self.centrales.items() if v.tipo == TipoCentral.TERMICA}

    @property
    def centrales_con_embalse(self) -> dict[int, Central]:
        return {k: v for k, v in self.centrales.items() if v.tiene_embalse}

    # Full implementation also includes: Demanda, CostosVariables,
    # MantenimientoCentral, MantenimientoEmbalse, MantenimientoLinea,
    # ZonaReserva, CentralReserva, ConfiguracionReservas,
    # RebalseEmbalse, FiltracionEmbalse, ExtraccionEmbalse, CostoMinEmbalse
