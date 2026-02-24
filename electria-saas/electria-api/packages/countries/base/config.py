"""
Base Country Configuration

Abstract interface that all country configurations must implement.
This enables the multi-country architecture.
"""

from abc import ABC, abstractmethod
from typing import List, Dict

from pydantic import BaseModel


class RegulatorEntity(BaseModel):
    """Regulatory entity in the electric market."""

    name: str
    code: str
    website: str
    api_base_url: str | None = None
    data_endpoints: List[str] = []
    document_types: List[str] = []


class MarketConfig(BaseModel):
    """Electric market configuration."""

    market_type: str  # "pool", "bilateral", "mixed"
    price_unit: str  # "USD/MWh", "CLP/MWh"
    local_currency: str  # "CLP", "COP", "PEN"
    main_grid: str  # "SEN", "SIN", etc.
    voltage_levels: List[float]  # kV levels
    timezone: str  # "America/Santiago"


class DataSourceConfig(BaseModel):
    """Configuration for a data source."""

    name: str
    source_type: str  # "api", "scraper", "manual"
    url: str
    frequency: str  # "hourly", "daily", "on_change"
    data_types: List[str]


class CountryConfig(ABC):
    """
    Abstract base class for country configurations.

    Each country module must implement this interface to integrate
    with the ELECTRIA platform.
    """

    @property
    @abstractmethod
    def code(self) -> str:
        """ISO 3166-1 alpha-2 country code (e.g., 'cl', 'co', 'pe')."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Country name in Spanish."""
        pass

    @property
    @abstractmethod
    def name_en(self) -> str:
        """Country name in English."""
        pass

    @property
    @abstractmethod
    def market_config(self) -> MarketConfig:
        """Electric market configuration."""
        pass

    @property
    @abstractmethod
    def regulatory_bodies(self) -> List[RegulatorEntity]:
        """List of regulatory entities."""
        pass

    @property
    @abstractmethod
    def data_sources(self) -> List[DataSourceConfig]:
        """List of data sources for ingestion."""
        pass

    @abstractmethod
    def get_system_prompt(self) -> str:
        """
        Get the specialized system prompt for Claude.

        This prompt should include country-specific context,
        terminology, and instructions for the AI assistant.
        """
        pass

    @abstractmethod
    def get_glossary(self) -> Dict[str, str]:
        """
        Get glossary of technical terms.

        Used for query expansion and understanding domain-specific language.
        """
        pass

    @abstractmethod
    def get_query_examples(self) -> List[Dict[str, str]]:
        """
        Get example queries for few-shot prompting.

        Returns list of {"query": "...", "type": "normativa|datos|mixta"}
        """
        pass

    def get_pinecone_namespace(self) -> str:
        """Get the Pinecone namespace for this country's documents."""
        return f"docs-{self.code}"

    def get_timescale_schema(self) -> str:
        """Get the TimescaleDB schema name for this country's data."""
        return f"data_{self.code}"
