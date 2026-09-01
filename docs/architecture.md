# Architecture: Knowledge Graph Layer on Databricks

## Problem Statement

Databricks Unity Catalog provides **data lineage** (pipeline-level: table A → table B → dashboard), but stakeholders need **entity-relationship traversal** (business-level: Customer → Order → Product → Supplier → Employee).

## Target Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     DATABRICKS LAKEHOUSE                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │  customers   │  │   orders     │  │   products   │  ...         │
│  │ (Delta Table)│  │ (Delta Table)│  │ (Delta Table)│              │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
│         │                 │                 │                       │
│         └─────────────────┼─────────────────┘                       │
│                           │                                         │
│              Unity Catalog (governance, lineage, ACLs)              │
└───────────────────────────┼─────────────────────────────────────────┘
                            │
            ┌───────────────┼───────────────┐
            │               │               │
            ▼               ▼               ▼
   ┌────────────┐  ┌──────────────┐  ┌──────────────┐
   │ Neo4j      │  │ Neo4j Virtual│  │ Stardog /    │
   │ Spark      │  │ Graph        │  │ PuppyGraph   │
   │ Connector  │  │ (zero-copy)  │  │ (alternatives)│
   └─────┬──────┘  └──────┬───────┘  └──────────────┘
         │                │
         ▼                ▼
   ┌─────────────────────────────────────────┐
   │         KNOWLEDGE GRAPH LAYER           │
   │  Nodes: Customer, Product, Order, ...   │
   │  Edges: PLACED, CONTAINS, SUPPLIES, ... │
   └─────────────────┬───────────────────────┘
                     │
         ┌───────────┼───────────┐
         ▼           ▼           ▼
   ┌──────────┐ ┌────────┐ ┌──────────┐
   │ Cypher   │ │ Graph  │ │ GraphRAG │
   │ Queries  │ │ Explorer│ │ Agents  │
   └──────────┘ └────────┘ └──────────┘
```

## Graph Model (Enterprise Sample Domain)

### Nodes (Entities)
| Label | Source Table | Key Properties |
|---|---|---|
| `Customer` | `customers` | customer_id, name, segment, region |
| `Product` | `products` | product_id, name, category, price |
| `Order` | `orders` | order_id, order_date, total_amount, status |
| `Employee` | `employees` | employee_id, name, title, department |
| `Supplier` | `suppliers` | supplier_id, name, country |
| `Department` | `departments` | department_id, name, budget |

### Relationships (Business Relations)
| Relationship | From → To | Source | Meaning |
|---|---|---|---|
| `PLACED` | Customer → Order | `orders.customer_id` | Customer placed order |
| `CONTAINS` | Order → Product | `order_items` | Order contains product |
| `SUPPLIES` | Supplier → Product | `product_suppliers` | Supplier provides product |
| `WORKS_IN` | Employee → Department | `employees.department_id` | Employee belongs to dept |
| `MANAGES` | Employee → Employee | `employees.manager_id` | Reporting hierarchy |
| `PROCESSED` | Employee → Order | `orders.processed_by` | Employee handled order |
| `LOCATED_IN` | Customer → Region | derived | Geographic grouping |

## Data Flow (Production)

1. **Extract** — Read Delta tables from Unity Catalog via Spark
2. **Transform** — Map rows to graph nodes/relationships (this POC: `src/sync_to_neo4j.py`)
3. **Load** — Write to Neo4j via Spark Connector or neo4j Python driver
4. **Query** — Cypher traversal via API (`src/api/`) or Neo4j Browser
5. **Visualize** — Graph explorer UI (`visualization/`)

## POC vs Production

| Component | POC (this repo) | Production |
|---|---|---|
| Data source | CSV files mimicking Delta tables | Unity Catalog Delta tables |
| Sync | Python script (`sync_to_neo4j.py`) | Neo4j Spark Connector on Databricks cluster |
| Graph DB | Neo4j Community (Docker) | Neo4j Aura Enterprise or self-managed |
| API | FastAPI local | Databricks Model Serving or container |
| Auth | None | Unity Catalog + Neo4j RBAC + SSO |

## Example Traversal Queries

```cypher
// Find all products a customer has purchased (2-hop)
MATCH (c:Customer {name: 'Acme Corp'})-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
RETURN c, o, p

// Find supply chain for a customer's purchases (3-hop)
MATCH (c:Customer)-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)<-[:SUPPLIES]-(s:Supplier)
RETURN c, o, p, s

// Employee hierarchy who processed customer orders (4-hop)
MATCH (c:Customer)-[:PLACED]->(o:Order)<-[:PROCESSED]-(e:Employee)-[:MANAGES*0..2]-(mgr:Employee)
RETURN c, o, e, mgr
```
