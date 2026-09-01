"""Load sample Delta-table CSVs into Neo4j as a knowledge graph."""

import csv
import os
from pathlib import Path

from neo4j import GraphDatabase

from graph_model import MANAGER_RELATIONSHIP, NODE_MAPPINGS, RELATIONSHIP_MAPPINGS

DATA_DIR = Path(__file__).parent.parent / "data" / "sample_delta_tables"

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "knowledgegraph123")


def load_csv(table_name: str) -> list[dict]:
    path = DATA_DIR / f"{table_name}.csv"
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def clear_graph(driver):
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")


def create_nodes(driver):
    for mapping in NODE_MAPPINGS:
        rows = load_csv(mapping.table)
        if not rows:
            continue

        props = [mapping.id_column] + mapping.properties
        set_clause = ", ".join(f"n.{p} = row.{p}" for p in props)

        query = f"""
        UNWIND $rows AS row
        MERGE (n:{mapping.label} {{{mapping.id_column}: row.{mapping.id_column}}})
        SET {set_clause}
        """

        with driver.session() as session:
            session.run(query, rows=rows)
        print(f"  Created {len(rows)} {mapping.label} nodes")


def create_relationships(driver):
    for rel in RELATIONSHIP_MAPPINGS:
        rows = load_csv(rel.source_table)
        if not rows:
            continue

        prop_set = ""
        if rel.properties:
            prop_set = " SET " + ", ".join(f"r.{p} = row.{p}" for p in rel.properties)

        query = f"""
        UNWIND $rows AS row
        MATCH (a:{rel.from_label} {{{rel.from_id_column}: row.{rel.from_id_column}}})
        MATCH (b:{rel.to_label} {{{rel.to_id_column}: row.{rel.to_id_column}}})
        MERGE (a)-[r:{rel.type}]->(b){prop_set}
        """

        with driver.session() as session:
            result = session.run(query, rows=rows)
            result.consume()
        print(f"  Created {rel.type} relationships from {rel.source_table}")


def create_manager_relationships(driver):
    rel = MANAGER_RELATIONSHIP
    rows = [r for r in load_csv(rel.source_table) if r.get("manager_id")]

    query = f"""
    UNWIND $rows AS row
    MATCH (mgr:{rel.from_label} {{{rel.from_id_column}: row.{rel.from_id_column}}})
    MATCH (emp:{rel.to_label} {{{rel.to_id_column}: row.{rel.to_id_column}}})
    MERGE (mgr)-[r:{rel.type}]->(emp)
    """

    with driver.session() as session:
        session.run(query, rows=rows)
    print(f"  Created {len(rows)} {rel.type} relationships")


def create_indexes(driver):
    indexes = [
        "CREATE INDEX IF NOT EXISTS FOR (c:Customer) ON (c.customer_id)",
        "CREATE INDEX IF NOT EXISTS FOR (p:Product) ON (p.product_id)",
        "CREATE INDEX IF NOT EXISTS FOR (o:Order) ON (o.order_id)",
        "CREATE INDEX IF NOT EXISTS FOR (e:Employee) ON (e.employee_id)",
        "CREATE INDEX IF NOT EXISTS FOR (d:Department) ON (d.department_id)",
        "CREATE INDEX IF NOT EXISTS FOR (s:Supplier) ON (s.supplier_id)",
        "CREATE INDEX IF NOT EXISTS FOR (c:Customer) ON (c.name)",
    ]
    with driver.session() as session:
        for idx in indexes:
            session.run(idx)
    print("  Indexes created")


def print_stats(driver):
    with driver.session() as session:
        nodes = session.run("MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt ORDER BY label")
        print("\nGraph Statistics:")
        print("-" * 30)
        for record in nodes:
            print(f"  {record['label']}: {record['cnt']} nodes")

        rels = session.run("MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS cnt ORDER BY type")
        for record in rels:
            print(f"  {record['type']}: {record['cnt']} relationships")


def sync():
    print(f"Connecting to Neo4j at {NEO4J_URI}...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    try:
        driver.verify_connectivity()
        print("Connected. Clearing existing graph...")
        clear_graph(driver)

        print("\nCreating nodes...")
        create_nodes(driver)

        print("\nCreating relationships...")
        create_relationships(driver)
        create_manager_relationships(driver)

        print("\nCreating indexes...")
        create_indexes(driver)

        print_stats(driver)
        print("\nSync complete!")
    finally:
        driver.close()


if __name__ == "__main__":
    sync()
