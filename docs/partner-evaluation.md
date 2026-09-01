# Databricks Knowledge Graph Partner Evaluation

## Executive Summary

Your data in Databricks is **relational** — flat Delta tables with rows and columns. There is no graph structure today. Unity Catalog lineage shows *pipeline flow* (table A → table B), but not *business relationships* (Customer → Order → Product → Supplier).

This evaluation covers **Databricks partners and options** that can build a traversable knowledge graph layer on top of your existing relational data — "like Neo4j" but integrated with your lakehouse.

**No single "right" answer** — the best option depends on whether you want zero data movement, semantic reasoning, or maximum traversal performance. See the decision matrix at the bottom.

---

## The Core Problem: Relational → Graph

```
WHAT YOU HAVE (Databricks)          WHAT YOU NEED (Knowledge Graph)
─────────────────────────          ──────────────────────────────
customers.csv / Delta table        (Customer)─[:PLACED]→(Order)
orders.csv / Delta table                  │
order_items.csv / Delta table             └─[:CONTAINS]→(Product)
products.csv / Delta table                      ↑
suppliers.csv / Delta table              [:SUPPLIES]─(Supplier)

Flat tables with FK columns        Nodes + edges you can traverse
No graph structure                 Multi-hop queries, visual exploration
```

**The graph layer must be built** — by discovering FK relationships, junction tables, and naming patterns from your existing schemas. None of the platforms below require you to restructure your data.

---

## Platform Options

### 1. Neo4j — Graph Database (like the stakeholder asked for)

| Aspect | Details |
|---|---|
| **What it is** | Dedicated graph database — industry standard for relationship traversal |
| **Databricks integration** | Official partner; Neo4j Connector for Apache Spark |
| **How it handles relational data** | Spark Connector reads Delta tables, maps rows → nodes/relationships |
| **Zero-copy option** | Neo4j Virtual Graph (public preview) — AI proposes graph model from Databricks tables, query in Cypher without ETL |
| **Query language** | Cypher |
| **Traversal UI** | Neo4j Browser, Bloom, Aura Console |
| **Data movement** | Materialized (Spark sync) OR zero-copy (Virtual Graph) |
| **Best for** | Production graph traversal, GraphRAG, the "Neo4j-like" experience |

**Integration paths:**
1. **Virtual Graph** (start here) — Connect Aura to Databricks; AI discovers relationships from table metadata; query immediately
2. **Spark Connector** (production) — Scheduled sync of Delta → Neo4j for performance-critical traversals
3. **MCP Server** — Databricks AI agents can query the graph

---

### 2. Stardog — Semantic Knowledge Graph

| Aspect | Details |
|---|---|
| **What it is** | Enterprise knowledge graph with semantic/ontology layer |
| **Databricks integration** | ✅ **Partner Connect** — one-click setup from Databricks console |
| **How it handles relational data** | Virtual graph over Databricks SQL — maps tables to RDF triples |
| **Query language** | SPARQL, GraphQL, SQL |
| **Traversal UI** | Stardog Explorer, Studio, Designer |
| **Data movement** | None — queries SQL warehouse directly |
| **Best for** | Ontology-driven orgs, semantic reasoning, fastest Databricks integration |

**Why consider it:** Easiest to set up (Partner Connect). Good if your stakeholder cares about *meaning* and *semantics* beyond just traversal.

---

### 3. PuppyGraph — Zero-ETL Graph Query Engine

| Aspect | Details |
|---|---|
| **What it is** | Graph query engine that maps SQL tables to graph via JSON config |
| **Databricks integration** | First Unity Catalog graph engine partner |
| **How it handles relational data** | JSON schema maps table columns → graph vertices/edges; no data copy |
| **Query language** | Gremlin, openCypher |
| **Traversal UI** | Built-in graph explorer |
| **Data movement** | None — queries Delta tables in place |
| **Best for** | Graph queries without managing a separate graph database |

**Why consider it:** If the stakeholder wants traversal but doesn't want another database to manage.

---

### 4. OntoBricks — Databricks Labs (Native)

| Aspect | Details |
|---|---|
| **What it is** | Databricks Labs project — builds knowledge graphs inside the lakehouse |
| **Databricks integration** | Native — reads Unity Catalog metadata directly |
| **How it handles relational data** | LLM generates OWL ontology from table metadata → R2RML mappings → materialized triples in Delta |
| **Query language** | GraphQL, SPARQL |
| **Traversal UI** | Interactive knowledge graph viewer (OntoViz) |
| **Data movement** | Materializes to Delta/Lakebase (stays in Databricks) |
| **Best for** | Teams that want to stay 100% within Databricks |

**Why consider it:** No external vendor, no data leaves Databricks. LLM auto-discovers relationships from your table metadata.

---

### 5. Kobai Saturn — Graph in the Lakehouse

| Aspect | Details |
|---|---|
| **What it is** | Graph representation as Delta tables within Unity Catalog |
| **Databricks integration** | Graph schema stored and governed in Unity Catalog |
| **How it handles relational data** | Visual modeling in Kobai Studio → materializes entity/relationship instances as Delta tables |
| **Query language** | Visual (Kobai Studio) |
| **Data movement** | Materializes inside Databricks |
| **Best for** | Enterprises requiring graph capability with full UC governance, no external platform |

---

## Decision Matrix

| Criteria | Neo4j | Stardog | PuppyGraph | OntoBricks | Kobai Saturn |
|---|---|---|---|---|---|
| "Like Neo4j" traversal | ★★★★★ | ★★★★ | ★★★★ | ★★★ | ★★★ |
| Easiest Databricks setup | ★★★ | ★★★★★ | ★★★★ | ★★★★★ | ★★★ |
| Zero data movement | ★★★★ | ★★★★★ | ★★★★★ | ★★ | ★★★ |
| Auto-discover relationships | ★★★★ (Virtual Graph) | ★★★ | ★★★ | ★★★★★ (LLM) | ★★★ |
| GraphRAG / AI agents | ★★★★★ | ★★★ | ★★★ | ★★★★ | ★★★ |
| Maturity / ecosystem | ★★★★★ | ★★★★ | ★★★ | ★★★ | ★★★ |
| Stays in Databricks | ★★ | ★★ | ★★★★ | ★★★★★ | ★★★★★ |

---

## Recommended Approach

### Phase 1 — POC (this repository)
- Run relationship discovery on sample relational data
- Demonstrate traversal with NetworkX (no infra) or Neo4j (Docker)
- Export configs for PuppyGraph and Stardog
- Show stakeholder the discovered schema and interactive explorer

### Phase 2 — Pilot with real data
Try **two options in parallel** (low cost, no commitment):
1. **Neo4j Virtual Graph** — connect to your Databricks workspace, let AI propose the graph model
2. **Stardog via Partner Connect** — one-click from Databricks console

### Phase 3 — Production
- Pick the winner from Phase 2
- Materialize high-value subgraphs if virtual query performance isn't enough
- Integrate with GraphRAG / AI agents

---

## What This POC Generates

Running `python src/discover_and_build.py` produces:

| Output | Purpose |
|---|---|
| `output/discovered_schema.json` | Proposed graph model from relational tables — **review before materializing** |
| `output/puppygraph_schema.json` | Ready-to-upload PuppyGraph config |
| `output/stardog_mapping.json` | Stardog virtual graph mapping hints |
| Interactive graph explorer | Traversal UI at http://localhost:8000 |
