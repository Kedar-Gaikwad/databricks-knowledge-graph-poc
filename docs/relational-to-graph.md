# From Relational Tables to Knowledge Graph

## The Core Challenge

Databricks stores data as **relational Delta tables** — rows and columns. There is no inherent graph structure. Your stakeholder's data looks like this:

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   customers     │     │     orders      │     │   order_items   │
├─────────────────┤     ├─────────────────┤     ├─────────────────┤
│ customer_id (PK)│     │ order_id (PK)   │     │ order_item_id   │
│ name            │     │ customer_id (FK)│────▶│ order_id (FK)   │──┐
│ segment         │     │ order_date      │     │ product_id (FK) │  │
│ region          │     │ processed_by(FK)│     │ quantity        │  │
└─────────────────┘     └─────────────────┘     └─────────────────┘  │
         ▲                       │                                    │
         │                       │                                    ▼
         └───────────────────────┘                          ┌─────────────────┐
                                                              │    products     │
                                                              ├─────────────────┤
                                                              │ product_id (PK) │
                                                              │ name            │
                                                              │ category        │
                                                              └─────────────────┘
```

What they **want** is this:

```
(Customer)-[:PLACED]->(Order)-[:CONTAINS]->(Product)<-[:SUPPLIES]-(Supplier)
    │                      │
    │                      └─[:PROCESSED]─(Employee)-[:WORKS_IN]->(Department)
    │
    └─ region, segment as properties
```

## How We Get There

### Step 1: Metadata Extraction

**POC (local):** Read CSV headers and sample values.

**Production (Databricks):**
```sql
-- Unity Catalog metadata
DESCRIBE TABLE EXTENDED catalog.schema.customers;
SHOW FOREIGN KEYS IN catalog.schema;  -- if declared

-- Or via information_schema
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_catalog = 'company_catalog';
```

### Step 2: Relationship Discovery

The discovery engine (`src/relationship_discovery.py`) uses these heuristics:

| Signal | Example | Inferred Relationship |
|---|---|---|
| Column named `{entity}_id` | `customer_id` in `orders` | Order → Customer (FK) |
| Junction table (2+ FKs, few columns) | `order_items(order_id, product_id)` | Order -[CONTAINS]-> Product |
| Self-referential FK | `manager_id` in `employees` | Employee -[MANAGES]-> Employee |
| Column naming patterns | `processed_by` in `orders` | Order -[PROCESSED]- Employee |

**Important:** Discovered relationships are **proposals**. A data steward should review `output/discovered_schema.json` before materializing. Some relationships may need manual addition (e.g., semantic links not captured by FKs).

### Step 3: Schema Review

The output includes `discovery_notes` explaining decisions:
- Which tables became nodes vs. junction relationships
- Which FKs were detected and how
- Tables skipped (no detectable PK)

### Step 4: Materialization

Choose a backend based on your needs:

| Need | Backend | Data Movement |
|---|---|---|
| Quick demo, no infra | NetworkX (in-memory) | Loads from CSV |
| Production traversal, GraphRAG | Neo4j (+ Spark Connector) | Sync Delta → Neo4j |
| Zero-ETL, keep data in Databricks | PuppyGraph or Neo4j Virtual Graph | None — virtual mapping |
| Semantic reasoning, ontologies | Stardog (Partner Connect) | Virtual — SQL queries |
| Stay in Databricks only | OntoBricks (Databricks Labs) | Materializes to Delta triples |

### Step 5: Traversal

Once materialized, users can:
- Explore interactively (this POC's web UI)
- Run Cypher/Gremlin/SPARQL queries
- Build GraphRAG agents on top

## What Unity Catalog Lineage Does NOT Cover

| Unity Catalog Lineage | Knowledge Graph |
|---|---|
| `raw.customers` → `staging.customers` → `gold.customers` | Customer "Acme Corp" PLACED Order "O1001" |
| Pipeline A writes to Table B | Product "Cloud Analytics" SUPPLIED_BY "DataFlow Inc" |
| Column-level lineage (which source field maps where) | Employee "Carol White" PROCESSED Order "O1001" for Customer "Acme Corp" |

Lineage is about **data engineering pipelines**. Knowledge graphs are about **business entity relationships**. Both are valuable; they answer different questions.

## Databricks-Specific Discovery Enhancements (Production)

Beyond FK heuristics, production systems can also use:

1. **Unity Catalog tags/comments** — business descriptions hint at relationships
2. **LLM-assisted ontology** — OntoBricks and Neo4j Virtual Graph use LLMs to propose graph models from metadata
3. **Existing data contracts** — if your org defines schemas with FK constraints
4. **Column profiling** — value overlap between columns (e.g., 95% of `orders.customer_id` values exist in `customers.customer_id`)
