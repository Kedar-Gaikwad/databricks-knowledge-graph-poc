# Databricks Knowledge Graph POC

## The Problem

Your company has **relational data in Databricks** — flat Delta tables with rows and columns. Unity Catalog tells you **lineage** (which pipeline produced which table), but it does **not** tell you **business relationships**:

- Which customers bought which products?
- Which suppliers provide those products?
- Which employees processed those orders?
- How are departments connected through shared accounts?

A **knowledge graph layer** sits on top of your existing tables and lets you **traverse** these relationships — like Neo4j, but fed from your Databricks lakehouse.

**Key point: your data is NOT already in graph format.** This POC shows how to discover relationships from relational tables and materialize them into a traversable graph.

---

## What This POC Demonstrates

```
┌─────────────────────────────────────────────────────────┐
│  DATABRICKS (relational — tables, NOT graphs)           │
│  customers │ orders │ products │ employees │ suppliers  │
└────────────────────────┬────────────────────────────────┘
                         │
              ┌──────────▼──────────┐
              │  RELATIONSHIP       │  ← Auto-discovers FKs, junction tables,
              │  DISCOVERY ENGINE   │    naming patterns from table metadata
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │  PROPOSED GRAPH     │  ← Human-reviewable schema:
              │  SCHEMA (JSON)      │    nodes, edges, discovery notes
              └──────────┬──────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
   ┌──────────┐   ┌──────────┐   ┌──────────┐
   │  Neo4j   │   │ NetworkX │   │ Config   │
   │ (Cypher) │   │ (in-mem) │   │ exporters│
   └──────────┘   └──────────┘   │ PuppyGraph│
                                  │ Stardog  │
                                  └──────────┘
                         │
              ┌──────────▼──────────┐
              │  GRAPH EXPLORER UI  │  ← Interactive traversal
              └─────────────────────┘
```

---

## Graph Platform Options Evaluated

| Platform | Integration with Databricks | Data Movement | Query Language | Best For |
|---|---|---|---|---|
| **Neo4j** | Official partner, Spark Connector | Optional (Virtual Graph = zero-copy) | Cypher | Production graph traversal, GraphRAG |
| **Stardog** | Partner Connect (one-click) | Virtual — queries SQL directly | SPARQL, GraphQL | Semantic layer, ontologies |
| **PuppyGraph** | Unity Catalog partner | Zero-ETL — maps tables via JSON | Gremlin, openCypher | Graph queries without a graph DB |
| **OntoBricks** | Databricks Labs (native) | Materializes to Delta triple store | GraphQL, SPARQL | Stay fully in Databricks |
| **Kobai Saturn** | Delta tables in Unity Catalog | Materializes inside lakehouse | Visual (Kobai Studio) | Graph in lakehouse, no external vendor |
| **NetworkX** (this POC) | N/A — local demo | In-memory from CSV | Python | Quick POC without infrastructure |

See [docs/partner-evaluation.md](docs/partner-evaluation.md) for full comparison.

---

## Quick Start

### Option A: No install needed (recommended)

```bash
cd databricks-knowledge-graph-poc

# 1. Discover relationships from relational tables
python src/discover_and_build.py

# 2. Start the API + graph explorer (stdlib only, no pip install)
python src/api/main.py
```

Open http://localhost:8000

> **Note:** The default backend uses pure Python — no `pip install` required.
> Python 3.14 is supported. If you previously hit `pydantic-core` build errors, you can skip `pip install` entirely.

### Option B: With Neo4j (production-like)

```bash
docker compose up -d          # Start Neo4j
pip install neo4j             # Only if using Neo4j backend
python src/discover_and_build.py --backend neo4j
python src/api/main.py
```

- Neo4j Browser: http://localhost:7474 (neo4j / knowledgegraph123)
- Graph Explorer: http://localhost:8000

---

## How Relationship Discovery Works

Given flat relational tables like:

```
customers(customer_id, name, segment, region)
orders(order_id, customer_id, order_date, processed_by)
order_items(order_item_id, order_id, product_id, quantity)
```

The discovery engine:

1. **Detects primary keys** — `customer_id` in `customers`, `order_id` in `orders`
2. **Detects foreign keys** — `customer_id` in `orders` → references `customers`
3. **Detects junction tables** — `order_items` has FKs to both `orders` and `products` → becomes a `CONTAINS` relationship
4. **Proposes a graph schema** — nodes (Customer, Order, Product) and edges (PLACED, CONTAINS, SUPPLIES)

Output: `output/discovered_schema.json` — review before materializing.

In production on Databricks, this metadata comes from **Unity Catalog** (`DESCRIBE TABLE`, `information_schema`) instead of CSV files.

---

## Project Structure

```
databricks-knowledge-graph-poc/
├── docs/
│   ├── partner-evaluation.md    # Platform comparison
│   ├── architecture.md          # Technical architecture
│   └── relational-to-graph.md   # How discovery works
├── data/sample_delta_tables/    # Relational CSVs (mimics Delta tables)
├── src/
│   ├── relationship_discovery.py  # Core: relational → graph schema
│   ├── discover_and_build.py      # CLI: discover + materialize
│   ├── backends/
│   │   ├── networkx_backend.py    # In-memory (no infra)
│   │   ├── neo4j_backend.py       # Neo4j (production)
│   │   ├── puppygraph_exporter.py # PuppyGraph config generator
│   │   └── stardog_exporter.py    # Stardog mapping generator
│   └── api/main.py                # REST API + graph explorer
├── notebooks/
│   └── 01_databricks_relational_to_graph.py  # Databricks notebook
├── visualization/index.html         # Interactive graph UI
├── output/                          # Generated schemas (gitignored)
└── docker-compose.yml               # Neo4j for Option B
```

---

## Recommended Path for Your Stakeholder

| Phase | Action | Tool |
|---|---|---|
| **1. POC** (now) | Run this repo, show traversal on sample data | NetworkX or Neo4j |
| **2. Discovery** | Point discovery engine at real Unity Catalog tables | `relationship_discovery.py` adapted for Spark |
| **3. Pilot** | Try zero-copy options first — no ETL | Neo4j Virtual Graph or PuppyGraph |
| **4. Production** | Materialize high-value subgraphs for performance | Neo4j Spark Connector or Stardog |

---

## Databricks Integration (Production)

The included notebook (`notebooks/01_databricks_relational_to_graph.py`) shows:

1. Reading Unity Catalog table metadata via `spark.sql("DESCRIBE TABLE ...")`
2. Running relationship discovery on real schemas
3. Syncing to Neo4j via the Spark Connector
4. Exporting PuppyGraph / Stardog configs for alternative platforms
