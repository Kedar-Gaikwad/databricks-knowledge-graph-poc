"""
Export discovered graph schema to Stardog mapping hints.

Stardog creates a semantic knowledge graph layer over Databricks SQL.
Available via Databricks Partner Connect (one-click setup).
Reference: https://docs.databricks.com/aws/en/partners/semantic-layer/stardog
"""

import json
from relationship_discovery import DiscoveredSchema


def export_stardog_mapping(schema: DiscoveredSchema, datasource: str = "databricks") -> dict:
    """Generate Stardog virtual graph mapping configuration."""

    mappings = []

    for node in schema.nodes:
        col_select = ", ".join(
            f"`{c}` AS `{c}`" for c in [node.id_column] + node.property_columns
        )
        mappings.append({
            "name": f"map_{node.source_table}_to_{node.label}",
            "source": f"SELECT {col_select} FROM {datasource}.{node.source_table}",
            "target": f"urn:company:{node.label} /{{{{{node.id_column}}}}} a :{node.label}",
            "properties": {
                col: f"urn:company:{node.label} /{{{{{node.id_column}}}}} :{col} ?{col}."
                for col in node.property_columns
            },
        })

    for rel in schema.relationships:
        mappings.append({
            "name": f"map_{rel.source_table}_{rel.type}",
            "source": (
                f"SELECT `{rel.from_id_column}`, `{rel.to_id_column}`"
                + (f", {', '.join(f'`{c}`' for c in rel.property_columns)}" if rel.property_columns else "")
                + f" FROM {datasource}.{rel.source_table}"
            ),
            "target": (
                f"urn:company:{rel.from_label} /{{{{{rel.from_id_column}}}}} "
                f":{rel.type} urn:company:{rel.to_label} /{{{{{rel.to_id_column}}}}}"
            ),
            "discovery_method": rel.discovery_method,
        })

    return {
        "datasource": datasource,
        "integration": "Databricks Partner Connect",
        "ontology_prefix": "urn:company:",
        "mappings": mappings,
        "setup_steps": [
            "1. In Databricks: Partner Connect → Stardog → Connect",
            "2. In Stardog Studio: Create datasource pointing to your SQL warehouse",
            "3. Import these mappings or use Stardog Designer to model visually",
            "4. Query with SPARQL or explore in Stardog Explorer",
        ],
    }


def save_stardog_mapping(schema: DiscoveredSchema, output_path: str, **kwargs):
    config = export_stardog_mapping(schema, **kwargs)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    return config
