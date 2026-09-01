"""HTTP API server using Python stdlib only — no FastAPI/pydantic required."""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from relationship_discovery import discover_from_directory, schema_to_dict
from backends.simple_backend import SimpleBackend
from queries import TRAVERSAL_QUERIES

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "sample_delta_tables"
OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"
VIS_DIR = Path(__file__).parent.parent.parent / "visualization"
PORT = int(os.getenv("API_PORT", "8000"))

backend = None
discovered_schema = None


def get_backend():
    global backend, discovered_schema
    if backend is not None:
        return backend

    discovered_schema = discover_from_directory(DATA_DIR)
    backend_name = os.getenv("GRAPH_BACKEND", "simple")
    config_path = OUTPUT_DIR / "active_backend.json"
    if config_path.exists():
        with open(config_path) as f:
            backend_name = json.load(f).get("backend", backend_name)

    if backend_name == "neo4j":
        try:
            from backends.neo4j_backend import Neo4jBackend
            backend = Neo4jBackend()
            backend.driver.verify_connectivity()
            backend.load_schema(discovered_schema, str(DATA_DIR))
            return backend
        except Exception:
            print("Neo4j unavailable, using simple in-memory backend")

    if backend_name == "networkx":
        try:
            from backends.networkx_backend import NetworkXBackend
            backend = NetworkXBackend()
            backend.load_schema(discovered_schema, str(DATA_DIR))
            return backend
        except ImportError:
            print("networkx not installed, using simple in-memory backend")

    backend = SimpleBackend()
    backend.load_schema(discovered_schema, str(DATA_DIR))
    return backend


def graph_to_dict(data):
    return {
        "nodes": [{"id": n.id, "label": n.label, "properties": n.properties} for n in data.nodes],
        "edges": [{"id": e.id, "source": e.source, "target": e.target,
                    "label": e.label, "properties": e.properties} for e in data.edges],
        "backend": backend.name,
        "query_language": backend.query_language,
    }


NX_QUERY_MAP = {
    "customer_products": "customer_products",
    "customer_supply_chain": "supply_chain",
    "simple_neighborhood": "neighborhood",
    "graph_overview": "full",
    "org_hierarchy": "full",
    "employee_orders": "neighborhood",
    "supplier_products": "supply_chain",
    "cross_department": "full",
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {args[0]}")

    def _json(self, data, status=200):
        body = json.dumps(data, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path, content_type="text/html"):
        if not path.exists():
            self.send_error(404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        get_backend()
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            return self._file(VIS_DIR / "index.html")

        if path == "/health":
            return self._json({"status": "healthy", "backend": backend.name})

        if path == "/api/schema":
            return self._json(schema_to_dict(discovered_schema))

        if path == "/api/stats":
            stats = backend.get_stats()
            return self._json({**stats, "backend": backend.name, "query_language": backend.query_language})

        if path == "/api/queries":
            return self._json([
                {"id": k, "name": v["name"], "description": v["description"]}
                for k, v in TRAVERSAL_QUERIES.items() if not v.get("requires_apoc")
            ])

        if path == "/api/platforms":
            return self._json([
                {"name": "Neo4j", "query_language": "Cypher", "data_movement": "Optional (Virtual Graph)"},
                {"name": "Stardog", "query_language": "SPARQL", "data_movement": "None (Partner Connect)"},
                {"name": "PuppyGraph", "query_language": "openCypher", "data_movement": "None (zero-ETL)"},
                {"name": "OntoBricks", "query_language": "GraphQL", "data_movement": "Materializes to Delta"},
            ])

        if path.startswith("/api/traverse/"):
            query_id = path.split("/api/traverse/")[1]
            if query_id not in TRAVERSAL_QUERIES:
                return self._json({"error": f"Query '{query_id}' not found"}, 404)

            query_def = TRAVERSAL_QUERIES[query_id]
            qparams = dict(query_def.get("params", {}))
            if "entity_name" in params:
                qparams["entity_name"] = params["entity_name"][0]

            if backend.name == "neo4j":
                data = backend.query(query_def["cypher"], qparams)
            else:
                qtype = NX_QUERY_MAP.get(query_id, "neighborhood")
                data = backend.query(qtype, qparams)

            return self._json(graph_to_dict(data))

        self.send_error(404)


def main():
    print(f"Starting Knowledge Graph API on http://localhost:{PORT}")
    print("No pip dependencies required for the default backend.")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
