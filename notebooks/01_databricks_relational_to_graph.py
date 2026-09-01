# Databricks Notebook: Relational Tables → Knowledge Graph
#
# This notebook demonstrates how to discover relationships from your
# existing Databricks Delta tables (which are NOT in graph format)
# and materialize them into a traversable knowledge graph.
#
# Run on a Databricks cluster with:
#   - Unity Catalog enabled
#   - Neo4j Spark Connector (for Option B)
#   - Or just metadata extraction (for Option A)

# COMMAND ----------

# MAGIC %md
# MAGIC # Knowledge Graph from Relational Databricks Data
# MAGIC
# MAGIC **Problem:** Our data lives in flat Delta tables. Unity Catalog gives us lineage
# MAGIC (pipeline A → table B), but NOT business relationships (Customer → Order → Product).
# MAGIC
# MAGIC **Solution:** Discover relationships from table metadata, then materialize into a graph layer.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1: Extract Table Metadata from Unity Catalog

# COMMAND ----------

catalog = "company_catalog"
schema = "sales"

tables_df = spark.sql(f"""
    SELECT table_name, column_name, data_type, ordinal_position
    FROM {catalog}.information_schema.columns
    WHERE table_schema = '{schema}'
    ORDER BY table_name, ordinal_position
""")

display(tables_df)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2: Discover Relationships (FK patterns, junction tables)
# MAGIC
# MAGIC Heuristics applied:
# MAGIC - Column `{table_singular}_id` in another table → foreign key
# MAGIC - Table with 2+ FK columns and few other columns → junction/bridge table
# MAGIC - Self-referential FK (e.g. `manager_id`) → hierarchy relationship

# COMMAND ----------

from pyspark.sql import functions as F

# Group columns by table
tables = {}
for row in tables_df.collect():
    tname = row.table_name
    if tname not in tables:
        tables[tname] = {"columns": [], "pk": None, "fks": []}
    tables[tname]["columns"].append(row.column_name)

    # Detect PK: {table_singular}_id
    expected_pk = tname.rstrip("s") + "_id"
    if row.column_name == expected_pk or row.column_name == "id":
        tables[tname]["pk"] = row.column_name

# Detect FKs: column name matches another table's PK
all_pks = {info["pk"]: tname for tname, info in tables.items() if info["pk"]}

for tname, info in tables.items():
    for col in info["columns"]:
        if col in all_pks and all_pks[col] != tname:
            info["fks"].append({
                "column": col,
                "references_table": all_pks[col],
                "references_column": col,
            })

# Print discovered schema
print("=== DISCOVERED GRAPH SCHEMA ===\n")
print("NODES (from non-junction tables):")
for tname, info in tables.items():
    if len(info["fks"]) >= 2 and len(info["columns"]) <= len(info["fks"]) + 2:
        print(f"  [JUNCTION] {tname} → will become relationships")
        continue
    if info["pk"]:
        props = [c for c in info["columns"] if c != info["pk"] and c not in [f["column"] for f in info["fks"]]]
        print(f"  :{tname.rstrip('s').capitalize()} (table: {tname}, PK: {info['pk']}, props: {props})")

print("\nRELATIONSHIPS:")
for tname, info in tables.items():
    for fk in info["fks"]:
        from_label = tname.rstrip("s").capitalize()
        to_label = fk["references_table"].rstrip("s").capitalize()
        print(f"  ({from_label})-[RELATES_TO]->({to_label})  via {tname}.{fk['column']}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3A: Export for PuppyGraph (zero-ETL, no data movement)
# MAGIC
# MAGIC PuppyGraph maps your existing Delta tables to a graph via JSON config.
# MAGIC Upload the generated schema to PuppyGraph to query with Gremlin/openCypher.

# COMMAND ----------

import json

puppygraph_config = {
    "catalogs": [{
        "name": catalog,
        "type": "databricks",
        "metastore": "unity",
    }],
    "vertices": [],
    "edges": [],
}

for tname, info in tables.items():
    if info["pk"] and not (len(info["fks"]) >= 2):
        puppygraph_config["vertices"].append({
            "label": tname.rstrip("s").capitalize(),
            "mappedTableSource": {
                "catalog": catalog, "schema": schema,
                "table": tname, "metaFields": {"id": info["pk"]},
            },
        })

print(json.dumps(puppygraph_config, indent=2))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3B: Sync to Neo4j via Spark Connector (materialized graph)
# MAGIC
# MAGIC For production traversal performance, materialize the graph into Neo4j.
# MAGIC Requires: `neo4j` Spark connector on cluster.

# COMMAND ----------

# Uncomment when Neo4j is configured:
#
# NEO4J_URI = dbutils.secrets.get("neo4j", "uri")
# NEO4J_USER = dbutils.secrets.get("neo4j", "user")
# NEO4J_PASSWORD = dbutils.secrets.get("neo4j", "password")
#
# # Load each entity table as nodes
# for tname, info in tables.items():
#     if not info["pk"]:
#         continue
#     df = spark.table(f"{catalog}.{schema}.{tname}")
#     (df.write
#         .format("org.neo4j.spark.DataSource")
#         .option("url", NEO4J_URI)
#         .option("authentication.type", "basic")
#         .option("authentication.basic.username", NEO4J_USER)
#         .option("authentication.basic.password", NEO4J_PASSWORD)
#         .option("labels", f":{tname.rstrip('s').capitalize()}")
#         .option("node.keys", info["pk"])
#         .mode("Overwrite")
#         .save())
#
# # Load relationships from FK columns
# for tname, info in tables.items():
#     for fk in info["fks"]:
#         df = spark.table(f"{catalog}.{schema}.{tname}").select(
#             info["pk"], fk["column"]
#         )
#         (df.write
#             .format("org.neo4j.spark.DataSource")
#             .option("url", NEO4J_URI)
#             .option("authentication.type", "basic")
#             .option("authentication.basic.username", NEO4J_USER)
#             .option("authentication.basic.password", NEO4J_PASSWORD)
#             .option("relationship", "RELATES_TO")
#             .option("relationship.save.strategy", "keys")
#             .option("relationship.source.labels", f":{tname.rstrip('s').capitalize()}")
#             .option("relationship.source.node.keys", info["pk"])
#             .option("relationship.target.labels", f":{fk['references_table'].rstrip('s').capitalize()}")
#             .option("relationship.target.node.keys", fk["column"])
#             .mode("Overwrite")
#             .save())

print("Neo4j sync code ready — uncomment when Neo4j credentials are configured.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4: Example Traversal Queries (Cypher)
# MAGIC
# MAGIC Once materialized, these queries traverse business relationships
# MAGIC that don't exist in Unity Catalog lineage:

# COMMAND ----------

example_queries = {
    "customer_products": """
        // What products has a customer purchased?
        MATCH (c:Customer {name: 'Acme Corp'})-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
        RETURN c.name, o.order_id, p.name, p.category
    """,
    "supply_chain": """
        // Full supply chain: customer → product → supplier
        MATCH (c:Customer)-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)<-[:SUPPLIES]-(s:Supplier)
        RETURN c.name AS customer, p.name AS product, s.name AS supplier, s.country
    """,
    "employee_network": """
        // Who processed orders and what's their management chain?
        MATCH (c:Customer)-[:PLACED]->(o:Order)<-[:PROCESSED]-(e:Employee)
        OPTIONAL MATCH (mgr:Employee)-[:MANAGES*1..3]->(e)
        RETURN c.name, o.order_id, e.name AS processor, collect(mgr.name) AS management_chain
    """,
}

for name, query in example_queries.items():
    print(f"--- {name} ---")
    print(query)
    print()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Alternative Platforms (no Neo4j required)
# MAGIC
# MAGIC | Platform | Setup | Data Movement | Query Language |
# MAGIC |---|---|---|---|
# MAGIC | **Stardog** | Databricks Partner Connect → one click | None (virtual) | SPARQL |
# MAGIC | **PuppyGraph** | Upload JSON schema to PuppyGraph | None (zero-ETL) | Gremlin, openCypher |
# MAGIC | **OntoBricks** | Install from Databricks Labs | Materializes to Delta | GraphQL |
# MAGIC | **Neo4j Virtual Graph** | Connect Aura to Databricks | None (zero-copy) | Cypher |
