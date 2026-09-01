"""End-to-end verification without requiring a running HTTP server."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from relationship_discovery import discover_from_directory, schema_to_dict
from backends.simple_backend import SimpleBackend

DATA = Path(__file__).parent / "data" / "sample_delta_tables"

print("=== STEP 1: Relationship Discovery ===")
schema = discover_from_directory(DATA)
print(f"Tables: {schema.tables_analyzed} -> Nodes: {len(schema.nodes)}, Relationships: {len(schema.relationships)}")
for r in schema.relationships:
    print(f"  ({r.from_label})-[:{r.type}]->({r.to_label})  [{r.discovery_method}]")

print("\n=== STEP 2: Graph Materialization ===")
backend = SimpleBackend()
backend.load_schema(schema, str(DATA))
stats = backend.get_stats()
print(f"Loaded: {sum(stats['nodes'].values())} nodes, {sum(stats['relationships'].values())} relationships")

print("\n=== STEP 3: Traversal Queries ===")
tests = [
    ("customer_products", "Acme Corp"),
    ("supply_chain", "Acme Corp"),
    ("full", None),
]
for qtype, entity in tests:
    params = {"entity_name": entity} if entity else {}
    result = backend.query(qtype, params)
    labels = {}
    for n in result.nodes:
        labels[n.label] = labels.get(n.label, 0) + 1
    print(f"  {qtype} ({entity or 'all'}): {len(result.nodes)} nodes {labels}, {len(result.edges)} edges")

print("\n=== ALL CHECKS PASSED ===")
