"""In-memory graph backend using NetworkX — no external services needed for POC demo."""

import csv
import uuid
from pathlib import Path

import networkx as nx

from backends.base import GraphBackend, GraphData, GraphEdge, GraphNode
from relationship_discovery import DiscoveredSchema


class NetworkXBackend(GraphBackend):
    """Local in-memory graph — useful for POC without Docker/Neo4j."""

    def __init__(self):
        self.graph = nx.MultiDiGraph()
        self._node_index: dict[str, str] = {}  # "Label:pk_value" → node_id

    @property
    def name(self) -> str:
        return "networkx"

    @property
    def query_language(self) -> str:
        return "Python/NetworkX traversal"

    def clear(self) -> None:
        self.graph.clear()
        self._node_index.clear()

    def _load_csv(self, data_dir: Path, table: str) -> list[dict]:
        with open(data_dir / f"{table}.csv", newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def load_schema(self, schema: DiscoveredSchema, data_dir: str) -> None:
        self.clear()
        data_path = Path(data_dir)

        for node_def in schema.nodes:
            rows = self._load_csv(data_path, node_def.source_table)
            for row in rows:
                pk_val = row[node_def.id_column]
                node_id = f"{node_def.label}:{pk_val}"
                props = {k: row[k] for k in node_def.property_columns if k in row}
                props[node_def.id_column] = pk_val
                props["name"] = props.get("name", pk_val)
                self.graph.add_node(node_id, label=node_def.label, **props)
                self._node_index[node_id] = node_id

        for rel_def in schema.relationships:
            rows = self._load_csv(data_path, rel_def.source_table)
            for row in rows:
                from_pk = row.get(rel_def.from_id_column)
                to_pk = row.get(rel_def.to_id_column)
                if not from_pk or not to_pk:
                    continue

                from_id = f"{rel_def.from_label}:{from_pk}"
                to_id = f"{rel_def.to_label}:{to_pk}"

                if from_id not in self.graph or to_id not in self.graph:
                    continue

                edge_props = {k: row[k] for k in rel_def.property_columns if k in row}
                self.graph.add_edge(from_id, to_id, label=rel_def.type, **edge_props)

    def _subgraph_to_data(self, node_ids: set) -> GraphData:
        nodes, edges = [], []
        seen_edges = set()

        for nid in node_ids:
            if nid not in self.graph:
                continue
            data = self.graph.nodes[nid]
            nodes.append(GraphNode(
                id=nid,
                label=data.get("label", "Unknown"),
                properties={k: v for k, v in data.items() if k != "label"},
            ))

        sub = self.graph.subgraph(node_ids)
        for u, v, key, data in sub.edges(keys=True, data=True):
            edge_key = (u, v, data.get("label", ""))
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            edges.append(GraphEdge(
                id=str(uuid.uuid4()),
                source=u,
                target=v,
                label=data.get("label", "RELATED"),
                properties={k: v for k, v in data.items() if k != "label"},
            ))

        return GraphData(nodes=nodes, edges=edges)

    def query(self, query_type: str, params: dict) -> GraphData:
        """Supported query_type values: neighborhood, full, supply_chain, customer_products."""
        if query_type == "full":
            return self._subgraph_to_data(set(self.graph.nodes))

        entity_name = params.get("entity_name", "")
        depth = params.get("depth", 2)

        # Find starting nodes by name
        start_nodes = [
            n for n, d in self.graph.nodes(data=True)
            if d.get("name") == entity_name or entity_name in n
        ]

        if not start_nodes and query_type != "full":
            return GraphData(nodes=[], edges=[])

        if query_type == "neighborhood":
            visited = set()
            frontier = set(start_nodes)
            for _ in range(depth):
                next_frontier = set()
                for node in frontier:
                    visited.add(node)
                    for neighbor in set(self.graph.successors(node)) | set(self.graph.predecessors(node)):
                        if neighbor not in visited:
                            next_frontier.add(neighbor)
                frontier = next_frontier
                visited |= frontier
            return self._subgraph_to_data(visited)

        if query_type == "customer_products":
            return self._traverse_pattern(start_nodes, ["PLACED", "CONTAINS"])

        if query_type == "supply_chain":
            return self._traverse_pattern(start_nodes, ["PLACED", "CONTAINS", "SUPPLIES"], reverse_last=True)

        return self._subgraph_to_data(set(start_nodes))

    def _traverse_pattern(self, start_nodes, rel_types, reverse_last=False):
        """Follow specific relationship types from start nodes."""
        visited = set(start_nodes)
        current = set(start_nodes)

        for i, rel_type in enumerate(rel_types):
            next_nodes = set()
            for node in current:
                for _, target, data in self.graph.out_edges(node, data=True):
                    if data.get("label") == rel_type:
                        next_nodes.add(target)
                for source, _, data in self.graph.in_edges(node, data=True):
                    if data.get("label") == rel_type:
                        next_nodes.add(source)
            visited |= next_nodes
            current = next_nodes

        return self._subgraph_to_data(visited)

    def get_stats(self) -> dict:
        node_counts: dict[str, int] = {}
        for _, data in self.graph.nodes(data=True):
            label = data.get("label", "Unknown")
            node_counts[label] = node_counts.get(label, 0) + 1

        rel_counts: dict[str, int] = {}
        for _, _, data in self.graph.edges(data=True):
            label = data.get("label", "Unknown")
            rel_counts[label] = rel_counts.get(label, 0) + 1

        return {"nodes": node_counts, "relationships": rel_counts}
