"""
CLI: Discover relationships from relational tables and materialize into a graph.

Usage:
    python discover_and_build.py                    # NetworkX (no Docker)
    python discover_and_build.py --backend neo4j    # Neo4j
    python discover_and_build.py --export-only      # Just generate schema configs
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from relationship_discovery import discover_from_directory, schema_to_dict
from backends.puppygraph_exporter import save_puppygraph_schema
from backends.stardog_exporter import save_stardog_mapping

DATA_DIR = Path(__file__).parent.parent / "data" / "sample_delta_tables"
OUTPUT_DIR = Path(__file__).parent.parent / "output"


def main():
    parser = argparse.ArgumentParser(description="Discover and build knowledge graph from relational data")
    parser.add_argument("--backend", choices=["simple", "networkx", "neo4j"], default="simple")
    parser.add_argument("--export-only", action="store_true", help="Only export schema configs, don't load graph")
    parser.add_argument("--data-dir", default=str(DATA_DIR))
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)

    print("=" * 60)
    print("STEP 1: Analyzing relational tables (NOT graph data)")
    print("=" * 60)
    schema = discover_from_directory(Path(args.data_dir))
    schema_dict = schema_to_dict(schema)

    schema_path = OUTPUT_DIR / "discovered_schema.json"
    with open(schema_path, "w", encoding="utf-8") as f:
        json.dump(schema_dict, f, indent=2)

    print(f"\n  Tables analyzed: {schema.tables_analyzed}")
    print(f"  Nodes discovered: {len(schema.nodes)}")
    for n in schema.nodes:
        print(f"    - {n.label} (from table '{n.source_table}', PK: {n.id_column})")
    print(f"  Relationships discovered: {len(schema.relationships)}")
    for r in schema.relationships:
        print(f"    - ({r.from_label})-[{r.type}]->({r.to_label})  [{r.discovery_method}]")
    if schema.discovery_notes:
        print(f"\n  Notes:")
        for note in schema.discovery_notes:
            print(f"    * {note}")
    print(f"\n  Schema saved to: {schema_path}")

    print("\n" + "=" * 60)
    print("STEP 2: Exporting platform-specific configs")
    print("=" * 60)

    pg_path = OUTPUT_DIR / "puppygraph_schema.json"
    save_puppygraph_schema(schema, str(pg_path))
    print(f"  PuppyGraph config: {pg_path}")

    sd_path = OUTPUT_DIR / "stardog_mapping.json"
    save_stardog_mapping(schema, str(sd_path))
    print(f"  Stardog mapping:   {sd_path}")

    if args.export_only:
        print("\nExport complete. Review output/ before materializing.")
        return

    print("\n" + "=" * 60)
    print(f"STEP 3: Materializing graph into {args.backend}")
    print("=" * 60)

    if args.backend == "neo4j":
        from backends.neo4j_backend import Neo4jBackend
        backend = Neo4jBackend()
    elif args.backend == "networkx":
        try:
            from backends.networkx_backend import NetworkXBackend
            backend = NetworkXBackend()
        except ImportError:
            print("  networkx not installed, falling back to simple backend")
            from backends.simple_backend import SimpleBackend
            backend = SimpleBackend()
    else:
        from backends.simple_backend import SimpleBackend
        backend = SimpleBackend()

    backend.load_schema(schema, args.data_dir)
    stats = backend.get_stats()
    print(f"\n  Graph loaded into {backend.name} ({backend.query_language})")
    print(f"  Nodes: {stats['nodes']}")
    print(f"  Relationships: {stats['relationships']}")

    # Save backend choice for API
    with open(OUTPUT_DIR / "active_backend.json", "w") as f:
        json.dump({"backend": args.backend}, f)

    print("\nDone! Start the API: python src/api/main.py")


if __name__ == "__main__":
    main()
