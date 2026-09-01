"""Abstract graph backend interface — swap Neo4j, NetworkX, PuppyGraph, etc."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from relationship_discovery import DiscoveredSchema, DiscoveredNode, DiscoveredRelationship


@dataclass
class GraphNode:
    id: str
    label: str
    properties: dict


@dataclass
class GraphEdge:
    id: str
    source: str
    target: str
    label: str
    properties: dict


@dataclass
class GraphData:
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class GraphBackend(ABC):
    """Common interface for all graph storage/query engines."""

    @abstractmethod
    def load_schema(self, schema: DiscoveredSchema, data_dir: str) -> None:
        """Materialize discovered schema + relational data into the graph."""

    @abstractmethod
    def query(self, cypher_or_gremlin: str, params: dict) -> GraphData:
        """Execute a traversal query and return nodes/edges."""

    @abstractmethod
    def get_stats(self) -> dict:
        """Return node/relationship counts."""

    @abstractmethod
    def clear(self) -> None:
        """Remove all graph data."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend identifier."""

    @property
    @abstractmethod
    def query_language(self) -> str:
        """Cypher, Gremlin, SPARQL, etc."""
