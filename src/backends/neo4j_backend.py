"""Neo4j backend — production-grade graph database (Databricks partner)."""

import csv
import os
import uuid
from pathlib import Path

from neo4j import GraphDatabase

from backends.base import GraphBackend, GraphData, GraphEdge, GraphNode
from relationship_discovery import DiscoveredSchema

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "knowledgegraph123")


class Neo4jBackend(GraphBackend):
    @property
    def name(self) -> str:
        return "neo4j"

    @property
    def query_language(self) -> str:
        return "Cypher"

    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    def clear(self) -> None:
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    def _load_csv(self, data_dir: Path, table: str) -> list[dict]:
        with open(data_dir / f"{table}.csv", newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def load_schema(self, schema: DiscoveredSchema, data_dir: str) -> None:
        self.clear()
        data_path = Path(data_dir)

        for node_def in schema.nodes:
            rows = self._load_csv(data_path, node_def.source_table)
            if not rows:
                continue
            all_props = [node_def.id_column] + node_def.property_columns
            set_clause = ", ".join(f"n.{p} = row.{p}" for p in all_props)
            query = f"""
            UNWIND $rows AS row
            MERGE (n:{node_def.label} {{{node_def.id_column}: row.{node_def.id_column}}})
            SET {set_clause}
            """
            with self.driver.session() as session:
                session.run(query, rows=rows)

        for rel_def in schema.relationships:
            rows = self._load_csv(data_path, rel_def.source_table)
            if not rows:
                continue

            if rel_def.discovery_method == "fk_column_self_ref":
                pk_col = rel_def.to_id_column
                query = f"""
                UNWIND $rows AS row
                MATCH (mgr:{rel_def.from_label} {{{rel_def.from_id_column}: row.{rel_def.from_id_column}}})
                MATCH (emp:{rel_def.to_label} {{{pk_col}: row.{pk_col}}})
                WHERE row.{rel_def.from_id_column} IS NOT NULL AND row.{rel_def.from_id_column} <> ''
                MERGE (mgr)-[r:{rel_def.type}]->(emp)
                """
            else:
                prop_set = ""
                if rel_def.property_columns:
                    prop_set = " SET " + ", ".join(f"r.{p} = row.{p}" for p in rel_def.property_columns)
                query = f"""
                UNWIND $rows AS row
                MATCH (a:{rel_def.from_label} {{{rel_def.from_id_column}: row.{rel_def.from_id_column}}})
                MATCH (b:{rel_def.to_label} {{{rel_def.to_id_column}: row.{rel_def.to_id_column}}})
                MERGE (a)-[r:{rel_def.type}]->(b){prop_set}
                """

            with self.driver.session() as session:
                session.run(query, rows=rows)

    def query(self, cypher: str, params: dict) -> GraphData:
        with self.driver.session() as session:
            result = session.run(cypher, params)
            return self._records_to_graph(list(result))

    def _records_to_graph(self, records) -> GraphData:
        nodes_map: dict[str, GraphNode] = {}
        edges: list[GraphEdge] = []

        for record in records:
            for value in record.values():
                if value is None:
                    continue
                if hasattr(value, "labels"):
                    nid = str(value.element_id)
                    if nid not in nodes_map:
                        nodes_map[nid] = GraphNode(
                            id=nid,
                            label=list(value.labels)[0] if value.labels else "Unknown",
                            properties=dict(value),
                        )
                elif hasattr(value, "type"):
                    for node in [value.start_node, value.end_node]:
                        nid = str(node.element_id)
                        if nid not in nodes_map:
                            nodes_map[nid] = GraphNode(
                                id=nid,
                                label=list(node.labels)[0] if node.labels else "Unknown",
                                properties=dict(node),
                            )
                    edges.append(GraphEdge(
                        id=str(value.element_id) or str(uuid.uuid4()),
                        source=str(value.start_node.element_id),
                        target=str(value.end_node.element_id),
                        label=value.type,
                        properties=dict(value),
                    ))
                elif hasattr(value, "start_node"):
                    for node in value.nodes:
                        nid = str(node.element_id)
                        if nid not in nodes_map:
                            nodes_map[nid] = GraphNode(
                                id=nid,
                                label=list(node.labels)[0] if node.labels else "Unknown",
                                properties=dict(node),
                            )
                    for rel in value.relationships:
                        edges.append(GraphEdge(
                            id=str(rel.element_id) or str(uuid.uuid4()),
                            source=str(rel.start_node.element_id),
                            target=str(rel.end_node.element_id),
                            label=rel.type,
                            properties=dict(rel),
                        ))

        seen = set()
        unique_edges = []
        for e in edges:
            key = (e.source, e.target, e.label)
            if key not in seen:
                seen.add(key)
                unique_edges.append(e)

        return GraphData(nodes=list(nodes_map.values()), edges=unique_edges)

    def get_stats(self) -> dict:
        with self.driver.session() as session:
            nodes = {
                r["label"]: r["count"]
                for r in session.run("MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count ORDER BY label")
            }
            rels = {
                r["type"]: r["count"]
                for r in session.run("MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS count ORDER BY type")
            }
        return {"nodes": nodes, "relationships": rels}

    def close(self):
        self.driver.close()
