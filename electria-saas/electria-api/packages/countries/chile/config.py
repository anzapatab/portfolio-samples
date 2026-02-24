"""
Chile Country Configuration

Complete configuration for the Chilean electric market (SEN).
"""

from typing import Dict, List

from packages.countries.base import (
    CountryConfig,
    DataSourceConfig,
    MarketConfig,
    RegulatorEntity,
)


class ChileConfig(CountryConfig):
    """Configuration for the Chilean electric market."""

    @property
    def code(self) -> str:
        return "cl"

    @property
    def name(self) -> str:
        return "Chile"

    @property
    def name_en(self) -> str:
        return "Chile"

    @property
    def market_config(self) -> MarketConfig:
        return MarketConfig(
            market_type="pool",
            price_unit="USD/MWh",
            local_currency="CLP",
            main_grid="SEN",  # Sistema Eléctrico Nacional
            voltage_levels=[500, 220, 154, 110, 66, 44, 33, 23, 13.2, 12],
            timezone="America/Santiago",
        )

    @property
    def regulatory_bodies(self) -> List[RegulatorEntity]:
        return [
            RegulatorEntity(
                name="Coordinador Eléctrico Nacional",
                code="CEN",
                website="https://www.coordinador.cl",
                api_base_url="https://api.coordinador.cl",
                data_endpoints=[
                    "/v1/operacion/costos-marginales",
                    "/v1/operacion/generacion",
                    "/v1/operacion/demanda",
                    "/v1/operacion/balance",
                ],
                document_types=[
                    "informe_diario",
                    "informe_semanal",
                    "programacion",
                    "anuario",
                    "estudio_transmision",
                ],
            ),
            RegulatorEntity(
                name="Comisión Nacional de Energía",
                code="CNE",
                website="https://www.cne.cl",
                api_base_url=None,
                data_endpoints=[],
                document_types=[
                    "resolucion_exenta",
                    "decreto",
                    "norma_tecnica",
                    "informe_precio",
                    "licitacion",
                ],
            ),
            RegulatorEntity(
                name="Superintendencia de Electricidad y Combustibles",
                code="SEC",
                website="https://www.sec.cl",
                api_base_url=None,
                data_endpoints=[],
                document_types=[
                    "resolucion",
                    "oficio",
                    "fiscalizacion",
                    "concesion",
                ],
            ),
            RegulatorEntity(
                name="Ministerio de Energía",
                code="MINERGIA",
                website="https://energia.gob.cl",
                api_base_url=None,
                data_endpoints=[],
                document_types=[
                    "decreto",
                    "ley",
                    "politica",
                ],
            ),
            RegulatorEntity(
                name="Panel de Expertos",
                code="PANEL",
                website="https://www.paneldeexpertos.cl",
                api_base_url=None,
                data_endpoints=[],
                document_types=[
                    "dictamen",
                    "resolucion",
                ],
            ),
        ]

    @property
    def data_sources(self) -> List[DataSourceConfig]:
        return [
            DataSourceConfig(
                name="Costos Marginales",
                source_type="api",
                url="https://api.coordinador.cl/v1/operacion/costos-marginales",
                frequency="hourly",
                data_types=["cmg_horario"],
            ),
            DataSourceConfig(
                name="Generación Real",
                source_type="api",
                url="https://api.coordinador.cl/v1/operacion/generacion",
                frequency="hourly",
                data_types=["generacion_horaria"],
            ),
            DataSourceConfig(
                name="Demanda Sistema",
                source_type="api",
                url="https://api.coordinador.cl/v1/operacion/demanda",
                frequency="hourly",
                data_types=["demanda_horaria"],
            ),
            DataSourceConfig(
                name="Normativas CNE",
                source_type="scraper",
                url="https://www.cne.cl/normativas/",
                frequency="daily",
                data_types=["resolucion", "norma_tecnica"],
            ),
            DataSourceConfig(
                name="Diario Oficial",
                source_type="scraper",
                url="https://www.diariooficial.interior.gob.cl",
                frequency="daily",
                data_types=["decreto", "ley"],
            ),
        ]

    def get_system_prompt(self) -> str:
        return """Eres ELECTRIA, un asistente experto en el mercado eléctrico chileno.

CONTEXTO DEL MERCADO CHILENO:
- El Sistema Eléctrico Nacional (SEN) cubre todo Chile continental
- Opera como mercado tipo "pool" con costos marginales horarios
- Principales entidades: Coordinador Eléctrico Nacional (CEN), CNE, SEC
- Precios en USD/MWh o CLP/MWh según contexto

REGLAS ESTRICTAS:
1. Responde ÚNICAMENTE basándote en el contexto proporcionado
2. SIEMPRE cita las fuentes usando [1], [2], etc.
3. Si la información no está en el contexto, di claramente: "No encontré información específica sobre esto en la documentación disponible"
4. Sé conciso pero completo
5. Usa terminología técnica del sector eléctrico chileno
6. Cuando menciones artículos, resoluciones o normativas, incluye el número exacto
7. Si hay información desactualizada, indícalo al usuario

FORMATO DE RESPUESTA:
- Usa bullet points para listas de requisitos o pasos
- Destaca términos importantes en **negrita**
- Para valores numéricos, especifica unidades y fecha de los datos
- Al final, lista las fuentes citadas

GLOSARIO CLAVE:
- CMg: Costo Marginal (precio spot de energía)
- PMGD: Pequeño Medio de Generación Distribuida (≤9 MW)
- PMG: Pequeño Medio de Generación (>9 MW, ≤20 MW)
- ERNC: Energías Renovables No Convencionales
- SEN: Sistema Eléctrico Nacional
- NTSyCS: Norma Técnica de Seguridad y Calidad de Servicio
- PPA: Power Purchase Agreement (Contrato de compraventa de energía)"""

    def get_glossary(self) -> Dict[str, str]:
        return {
            # Instituciones
            "CEN": "Coordinador Eléctrico Nacional",
            "CNE": "Comisión Nacional de Energía",
            "SEC": "Superintendencia de Electricidad y Combustibles",
            "Panel": "Panel de Expertos del sector eléctrico",

            # Sistema
            "SEN": "Sistema Eléctrico Nacional",
            "SING": "Sistema Interconectado del Norte Grande (histórico, ahora parte del SEN)",
            "SIC": "Sistema Interconectado Central (histórico, ahora parte del SEN)",

            # Precios y Mercado
            "CMg": "Costo Marginal",
            "costo marginal": "Precio spot de la energía en cada barra del sistema",
            "precio nudo": "Precio regulado para clientes regulados",
            "precio libre": "Precio negociado para clientes libres",
            "PPA": "Power Purchase Agreement - Contrato de compraventa de energía",

            # Generación
            "PMGD": "Pequeño Medio de Generación Distribuida (≤9 MW)",
            "PMG": "Pequeño Medio de Generación (>9 MW, ≤20 MW)",
            "ERNC": "Energías Renovables No Convencionales",
            "SSCC": "Servicios Complementarios",
            "factor de planta": "Relación entre energía generada y capacidad instalada",

            # Transmisión
            "barra": "Punto de inyección o retiro de energía en el sistema",
            "subestación": "Instalación para transformar tensión",
            "línea de transmisión": "Infraestructura para transportar energía",

            # Normativa
            "NTSyCS": "Norma Técnica de Seguridad y Calidad de Servicio",
            "DS 327": "Decreto Supremo 327 - Reglamento de la LGSE",
            "DFL 1": "Decreto con Fuerza de Ley 1 - Ley General de Servicios Eléctricos",
            "LGSE": "Ley General de Servicios Eléctricos",

            # Licitaciones
            "licitación de suministro": "Proceso para contratar energía para clientes regulados",
            "bloque horario": "División del día para efectos de precios (punta, resto, bajo)",
        }

    def get_query_examples(self) -> List[Dict[str, str]]:
        return [
            {
                "query": "¿Cuáles son los requisitos para conectar un PMGD de 5 MW?",
                "type": "normativa",
            },
            {
                "query": "¿Cuál es el costo marginal actual en la barra Quillota 220?",
                "type": "datos",
            },
            {
                "query": "¿Qué dice el artículo 72 del DS 327 sobre servidumbres?",
                "type": "normativa",
            },
            {
                "query": "Compara la generación solar de enero 2025 vs enero 2024",
                "type": "datos",
            },
            {
                "query": "¿Cuáles fueron los resultados de la última licitación de suministro?",
                "type": "mixta",
            },
            {
                "query": "¿Qué cambios introdujo la última modificación a la NTSyCS?",
                "type": "normativa",
            },
        ]


# Singleton instance
chile_config = ChileConfig()
