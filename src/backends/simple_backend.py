"""Pure-Python in-memory graph backend — no pip dependencies required."""

import csv
import uuid
from collections import defaultdict
from pathlib import Path

from backends.base import GraphBackend, GraphData, GraphEdge, GraphNode
from relationship_discovery import DiscoveredSchema


class SimpleBackend(GraphBackend):
    """Local in-memory graph using plain dicts — works on any Python 3.10+."""

    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.out_edges: dict[str, list[tuple[str, str, dict]]] = defaultdict(list)
        self.in_edges: dict[str, list[tuple[str, str, dict]]] = defaultdict(list)

    @property
    def name(self) -> str:
        return "simple"

    @property
    def query_language(self) -> str:
        return "Python traversal"

    def clear(self) -> None:
        self.nodes.clear()
        self.out_edges.clear()
        self.in_edges.clear()

    def _load_csv(self, data_dir: Path, table: str) -> list[dict]:
        with open(data_dir / f"{table}.csv", newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def load_schema(self, schema: DiscoveredSchema, data_dir: str) -> None:
        self.clear()
        data_path = Path(data_dir)

        for node_def in schema.nodes:
            for row in self._load_csv(data_path, node_def.source_table):
                pk_val = row[node_def.id_column]
                node_id = f"{node_def.label}:{pk_val}"
                props = {k: row[k] for k in node_def.property_columns if k in row}
                props[node_def.id_column] = pk_val
                props["name"] = props.get("name", pk_val)
                self.nodes[node_id] = {"label": node_def.label, **props}

        for rel_def in schema.relationships:
            for row in self._load_csv(data_path, rel_def.source_table):
                from_pk = row.get(rel_def.from_id_column)
                to_pk = row.get(rel_def.to_id_column)
                if not from_pk or not to_pk:
                    continue
                from_id = f"{rel_def.from_label}:{from_pk}"
                to_id = f"{rel_def.to_label}:{to_pk}"
                if from_id not in self.nodes or to_id not in self.nodes:
                    continue
                props = {k: row[k] for k in rel_def.property_columns if k in row}
                self.out_edges[from_id].append((to_id, rel_def.type, props))
                self.in_edges[to_id].append((from_id, rel_def.type, props))

    def _subgraph(self, node_ids: set[str]) -> GraphData:
        nodes = [
            GraphNode(id=nid, label=self.nodes[nid]["label"],
                      properties={k: v for k, v in self.nodes[nid].items() if k != "label"})
            for nid in node_ids if nid in self.nodes
        ]
        edges, seen = [], set()
        for nid in node_ids:
            for target, label, props in self.out_edges.get(nid, []):
                if target not in node_ids:
                    continue
                key = (nid, target, label)
                if key not in seen:
                    seen.add(key)
                    edges.append(GraphEdge(id=str(uuid.uuid4()), source=nid, target=target,
                                           label=label, properties=props))
        return GraphData(nodes=nodes, edges=edges)

    def query(self, query_type: str, params: dict) -> GraphData:
        if query_type == "full":
            return self._subgraph(set(self.nodes))

        entity_name = params.get("entity_name", "")
        depth = int(params.get("depth", 2))

        start = [n for n, d in self.nodes.items()
                 if d.get("name") == entity_name or entity_name in n]
        if not start and query_type != "full":
            return GraphData([], [])

        if query_type == "neighborhood":
            visited, frontier = set(), set(start)
            for _ in range(depth):
                nxt = set()
                for node in frontier:
                    visited.add(node)
                    for t, _, _ in self.out_edges.get(node, []):
                        if t not in visited:
                            nxt.add(t)
                    for s, _, _ in self.in_edges.get(node, []):
                        if s not in visited:
                            nxt.add(s)
                frontier = nxt
                visited |= nxt
            return self._subgraph(visited)

        if query_type in ("customer_products", "supply_chain"):
            pattern = ["PLACED", "CONTAINS"] if query_type == "customer_products" else ["PLACED", "CONTAINS", "SUPPLIES"]
            return self._pattern(start, pattern, reverse_last=(query_type == "supply_chain"))

        return self._subgraph(set(start))

    def _pattern(self, start_nodes, rel_types, reverse_last=False):
        visited, current = set(start_nodes), set(start_nodes)
        for i, rel in enumerate(rel_types):
            nxt = set()
            for node in current:
                for t, lbl, _ in self.out_edges.get(node, []):
                    if lbl == rel:
                        nxt.add(t)
                if reverse_last and i == len(rel_types) - 1:
                    for s, lbl, _ in self.in_edges.get(node, []):
                        if lbl == rel:
                            nxt.add(s)
            visited |= nxt
            current = nxt
        return self._subgraph(visited)

    def get_stats(self) -> dict:
        nc: dict[str, int] = {}
        for d in self.nodes.values():
            nc[d["label"]] = nc.get(d["label"], 0) + 1
        rc: dict[str, int] = {}
        for edges in self.out_edges.values():
            for _, lbl, _ in edges:
                rc[lbl] = rc.get(lbl, 0) + 1
        return {"nodes": nc, "relationships": rc}
