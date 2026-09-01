"""
Export discovered graph schema to PuppyGraph configuration format.

PuppyGraph is a zero-ETL graph engine — it maps existing SQL/Delta tables
to a graph schema via JSON config. No data movement required.
Reference: https://unitycatalog.io/blogs/integrating-unity-catalog-with-puppygraph-for-real-time-graph-analysis/
"""

import json
from relationship_discovery import DiscoveredSchema, schema_to_dict


def export_puppygraph_schema(
    schema: DiscoveredSchema,
    catalog: str = "company_catalog",
    schema_name: str = "sales",
) -> dict:
    """Generate PuppyGraph JSON schema from discovered relational metadata."""

    vertices = []
    for node in schema.nodes:
        vertices.append({
            "label": node.label,
            "attributes": [
                {"type": _infer_type(col), "name": col}
                for col in [node.id_column] + node.property_columns
            ],
            "mappedTableSource": {
                "catalog": catalog,
                "schema": schema_name,
                "table": node.source_table,
                "metaFields": {"id": node.id_column},
            },
        })

    edges = []
    for rel in schema.relationships:
        edges.append({
            "label": rel.type,
            "from": rel.from_label,
            "to": rel.to_label,
            "attributes": [
                {"type": _infer_type(col), "name": col}
                for col in rel.property_columns
            ],
            "mappedTableSource": {
                "catalog": catalog,
                "schema": schema_name,
                "table": rel.source_table,
                "metaFields": {
                    "from": rel.from_id_column,
                    "to": rel.to_id_column,
                },
            },
        })

    return {
        "catalogs": [{
            "name": catalog,
            "type": "databricks",
            "metastore": "unity",
            "warehouse": {
                "type": "sql",
                "server": "<your-databricks-host>",
                "httpPath": "<your-sql-warehouse-http-path>",
                "token": "<personal-access-token>",
            },
        }],
        "vertices": vertices,
        "edges": edges,
    }


def _infer_type(col_name: str) -> str:
    lower = col_name.lower()
    if any(k in lower for k in ("amount", "price", "budget", "revenue", "value", "rating")):
        return "Double"
    if any(k in lower for k in ("quantity", "days", "age")):
        return "Long"
    if any(k in lower for k in ("date",)):
        return "String"
    return "String"


def save_puppygraph_schema(schema: DiscoveredSchema, output_path: str, **kwargs):
    config = export_puppygraph_schema(schema, **kwargs)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    return config
