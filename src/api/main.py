"""FastAPI service — graph traversal over auto-discovered relational schema."""

import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))

from relationship_discovery import discover_from_directory, schema_to_dict
from backends.networkx_backend import NetworkXBackend
from queries import TRAVERSAL_QUERIES

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "sample_delta_tables"
OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"
VIS_DIR = Path(__file__).parent.parent.parent / "visualization"

backend = None
discovered_schema = None


def _init_backend(backend_name: str):
    global backend, discovered_schema
    discovered_schema = discover_from_directory(DATA_DIR)

    if backend_name == "neo4j":
        try:
            from backends.neo4j_backend import Neo4jBackend
            backend = Neo4jBackend()
            backend.driver.verify_connectivity()
            backend.load_schema(discovered_schema, str(DATA_DIR))
        except Exception:
            print("Neo4j not available, falling back to NetworkX")
            backend = NetworkXBackend()
            backend.load_schema(discovered_schema, str(DATA_DIR))
    else:
        backend = NetworkXBackend()
        backend.load_schema(discovered_schema, str(DATA_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    backend_name = os.getenv("GRAPH_BACKEND", "networkx")
    config_path = OUTPUT_DIR / "active_backend.json"
    if config_path.exists():
        with open(config_path) as f:
            backend_name = json.load(f).get("backend", backend_name)
    _init_backend(backend_name)
    yield


app = FastAPI(
    title="Databricks Knowledge Graph API",
    description="Relational data → discovered relationships → traversable graph",
    version="0.2.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=str(VIS_DIR)), name="static")


class GraphNodeOut(BaseModel):
    id: str
    label: str
    properties: dict


class GraphEdgeOut(BaseModel):
    id: str
    source: str
    target: str
    label: str
    properties: dict


class GraphResponse(BaseModel):
    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]
    backend: str
    query_language: str


def _to_response(data) -> GraphResponse:
    return GraphResponse(
        nodes=[GraphNodeOut(**n.__dict__) for n in data.nodes],
        edges=[GraphEdgeOut(**e.__dict__) for e in data.edges],
        backend=backend.name,
        query_language=backend.query_language,
    )


@app.get("/")
async def root():
    return FileResponse(str(VIS_DIR / "index.html"))


@app.get("/health")
async def health():
    return {"status": "healthy", "backend": backend.name}


@app.get("/api/schema")
async def get_discovered_schema():
    """Return the auto-discovered graph schema from relational tables."""
    return schema_to_dict(discovered_schema)


@app.get("/api/platforms")
async def list_platforms():
    """Available graph platform options and their integration patterns."""
    return [
        {
            "name": "Neo4j",
            "type": "graph_database",
            "databricks_integration": "Official partner — Spark Connector + Virtual Graph (zero-copy)",
            "query_language": "Cypher",
            "data_movement": "Optional — Virtual Graph queries Databricks directly",
            "best_for": "Production graph traversal, GraphRAG, multi-hop queries",
        },
        {
            "name": "Stardog",
            "type": "semantic_knowledge_graph",
            "databricks_integration": "Partner Connect (one-click SQL warehouse setup)",
            "query_language": "SPARQL, GraphQL",
            "data_movement": "None — virtual semantic layer over SQL",
            "best_for": "Ontology-driven enterprises, semantic reasoning",
        },
        {
            "name": "PuppyGraph",
            "type": "graph_query_engine",
            "databricks_integration": "Unity Catalog partner — JSON schema mapping",
            "query_language": "Gremlin, openCypher",
            "data_movement": "None — zero-ETL graph over existing tables",
            "best_for": "Graph queries without managing a graph database",
        },
        {
            "name": "OntoBricks",
            "type": "knowledge_graph_platform",
            "databricks_integration": "Databricks Labs — native Unity Catalog integration",
            "query_language": "GraphQL, SPARQL",
            "data_movement": "Materializes triples to Delta/Lakebase",
            "best_for": "Stay fully within Databricks ecosystem",
        },
        {
            "name": "NetworkX",
            "type": "in_memory_graph",
            "databricks_integration": "N/A — local POC only",
            "query_language": "Python",
            "data_movement": "Loads from CSV/Delta export",
            "best_for": "Quick POC demonstration",
        },
    ]


@app.get("/api/queries")
async def list_queries():
    return [
        {"id": k, "name": v["name"], "description": v["description"]}
        for k, v in TRAVERSAL_QUERIES.items()
        if not v.get("requires_apoc")
    ]


@app.get("/api/traverse/{query_id}", response_model=GraphResponse)
async def traverse(query_id: str, entity_name: str = Query(default=None)):
    if query_id not in TRAVERSAL_QUERIES:
        raise HTTPException(404, f"Query '{query_id}' not found")

    query_def = TRAVERSAL_QUERIES[query_id]
    params = dict(query_def.get("params", {}))
    if entity_name:
        params["entity_name"] = entity_name

    if backend.name == "neo4j":
        data = backend.query(query_def["cypher"], params)
    else:
        nx_query_map = {
            "customer_products": "customer_products",
            "customer_supply_chain": "supply_chain",
            "simple_neighborhood": "neighborhood",
            "graph_overview": "full",
            "org_hierarchy": "full",
            "employee_orders": "neighborhood",
            "supplier_products": "supply_chain",
            "cross_department": "full",
        }
        data = backend.query(nx_query_map.get(query_id, "neighborhood"), params)

    return _to_response(data)


@app.get("/api/stats")
async def graph_stats():
    stats = backend.get_stats()
    return {**stats, "backend": backend.name, "query_language": backend.query_language}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
