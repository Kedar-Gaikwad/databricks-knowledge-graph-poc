"""
Discover graph schema from relational Databricks Delta tables.

Databricks stores data as flat tables (rows/columns) — NOT as nodes and edges.
This module analyzes table metadata and infers:
  - Which tables become graph nodes (entities)
  - Which columns imply relationships (foreign keys, junction tables)
  - A proposed graph model that a human can review before materializing
"""

import csv
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class ColumnInfo:
    name: str
    sample_values: list[str] = field(default_factory=list)
    is_primary_key: bool = False
    is_foreign_key: bool = False
    references_table: Optional[str] = None
    references_column: Optional[str] = None


@dataclass
class TableInfo:
    name: str
    columns: list[ColumnInfo]
    row_count: int
    is_junction_table: bool = False


@dataclass
class DiscoveredNode:
    label: str
    source_table: str
    id_column: str
    property_columns: list[str]


@dataclass
class DiscoveredRelationship:
    type: str
    source_table: str
    from_label: str
    from_id_column: str
    to_label: str
    to_id_column: str
    property_columns: list[str] = field(default_factory=list)
    discovery_method: str = ""  # fk_column | junction_table | naming_pattern


@dataclass
class DiscoveredSchema:
    nodes: list[DiscoveredNode]
    relationships: list[DiscoveredRelationship]
    tables_analyzed: int
    discovery_notes: list[str]


# Common patterns in relational schemas
FK_SUFFIXES = ("_id", "_key", "_code", "_num", "_no")
JUNCTION_INDICATORS = 2  # tables with exactly 2+ FK columns and few other columns


def _singularize(name: str) -> str:
    """Rough singularization for entity labels: customers → Customer."""
    if name.endswith("ies"):
        return name[:-3].capitalize() + "y"
    if name.endswith("ses") or name.endswith("xes"):
        return name[:-2].capitalize()
    if name.endswith("s") and not name.endswith("ss"):
        return name[:-1].capitalize()
    return name.capitalize()


def _table_from_column(col_name: str, all_tables: set[str]) -> Optional[str]:
    """
    Infer referenced table from column name.
    e.g. customer_id → customers, processed_by → employees (with alias map)
    """
    col_lower = col_name.lower()

    # Direct: customer_id → customers
    for suffix in FK_SUFFIXES:
        if col_lower.endswith(suffix):
            base = col_lower[: -len(suffix)]
            candidates = [base, base + "s", base + "es"]
            for c in candidates:
                if c in all_tables:
                    return c

    # Reverse lookup: column base matches table name prefix
    for table in all_tables:
        if col_lower.startswith(table.rstrip("s")):
            return table

    return None


def load_table_metadata(data_dir: Path) -> list[TableInfo]:
    """Read CSV files (standing in for Delta tables) and extract column metadata."""
    tables = []
    for csv_file in sorted(data_dir.glob("*.csv")):
        with open(csv_file, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if not rows:
                continue

            columns = []
            for col_name in reader.fieldnames:
                samples = [r[col_name] for r in rows[:5] if r.get(col_name)]
                columns.append(ColumnInfo(name=col_name, sample_values=samples))

            tables.append(TableInfo(name=csv_file.stem, columns=columns, row_count=len(rows)))

    return tables


def discover_primary_keys(tables: list[TableInfo]) -> None:
    """Infer PKs: column named {table_singular}_id or just 'id'."""
    for table in tables:
        for col in table.columns:
            expected_pk = f"{table.name.rstrip('s')}_id"
            if col.name == expected_pk or col.name == "id":
                col.is_primary_key = True
                break
        # Fallback: first column ending in _id
        if not any(c.is_primary_key for c in table.columns):
            for col in table.columns:
                if col.name.endswith("_id"):
                    col.is_primary_key = True
                    break


def discover_foreign_keys(tables: list[TableInfo]) -> None:
    """Infer FKs by matching column names to other tables' PKs."""
    all_table_names = {t.name for t in tables}
    pk_map: dict[str, tuple[str, str]] = {}  # column_name → (table, column)

    for table in tables:
        for col in table.columns:
            if col.is_primary_key:
                pk_map[col.name] = (table.name, col.name)

    for table in tables:
        for col in table.columns:
            if col.is_primary_key:
                continue

            # Direct PK name match: customer_id in orders → customers.customer_id
            if col.name in pk_map:
                ref_table, ref_col = pk_map[col.name]
                if ref_table != table.name:
                    col.is_foreign_key = True
                    col.references_table = ref_table
                    col.references_column = ref_col
                    continue

            # Pattern match: processed_by → employees
            ref = _table_from_column(col.name, all_table_names)
            if ref and ref != table.name:
                ref_table_obj = next(t for t in tables if t.name == ref)
                ref_pk = next((c.name for c in ref_table_obj.columns if c.is_primary_key), None)
                if ref_pk:
                    col.is_foreign_key = True
                    col.references_table = ref
                    col.references_column = ref_pk


def detect_junction_tables(tables: list[TableInfo]) -> None:
    """Tables with 2+ FKs and few descriptive columns are likely junction/bridge tables."""
    for table in tables:
        fk_cols = [c for c in table.columns if c.is_foreign_key]
        non_fk = [c for c in table.columns if not c.is_foreign_key and not c.is_primary_key]
        if len(fk_cols) >= 2 and len(non_fk) <= 3:
            table.is_junction_table = True


def _relationship_name(from_table: str, to_table: str, col_name: str) -> str:
    """Generate a readable relationship type from context."""
    if "manager" in col_name:
        return "MANAGES"
    if "supplier" in col_name or "supply" in col_name:
        return "SUPPLIES"
    if "customer" in col_name or "placed" in col_name:
        return "PLACED"
    if "product" in col_name and "order" in from_table:
        return "CONTAINS"
    if "department" in col_name:
        return "WORKS_IN"
    if "process" in col_name:
        return "PROCESSED"
    if "employee" in col_name or "user" in col_name:
        return "ASSOCIATED_WITH"
    return f"RELATES_TO_{_singularize(to_table).upper()}"


def build_graph_schema(tables: list[TableInfo]) -> DiscoveredSchema:
    """Transform discovered relational metadata into a proposed graph schema."""
    notes: list[str] = []
    nodes: list[DiscoveredNode] = []
    relationships: list[DiscoveredRelationship] = []

    # Step 1: Non-junction tables become nodes
    for table in tables:
        if table.is_junction_table:
            notes.append(f"Table '{table.name}' detected as junction/bridge table (not a node)")
            continue

        pk_col = next((c.name for c in table.columns if c.is_primary_key), None)
        if not pk_col:
            notes.append(f"Table '{table.name}' has no detectable PK — skipped as node")
            continue

        props = [
            c.name for c in table.columns
            if not c.is_primary_key and not c.is_foreign_key
        ]

        nodes.append(DiscoveredNode(
            label=_singularize(table.name),
            source_table=table.name,
            id_column=pk_col,
            property_columns=props,
        ))

    node_by_table = {n.source_table: n for n in nodes}

    # Step 2: FK columns in non-junction tables → direct relationships
    for table in tables:
        if table.is_junction_table:
            continue
        from_node = node_by_table.get(table.name)
        if not from_node:
            continue

        for col in table.columns:
            if not col.is_foreign_key or not col.references_table:
                continue
            to_node = node_by_table.get(col.references_table)
            if not to_node:
                continue

            # Self-referential (e.g. manager_id → employees)
            if col.references_table == table.name:
                rel_type = _relationship_name(table.name, col.references_table, col.name)
                relationships.append(DiscoveredRelationship(
                    type=rel_type,
                    source_table=table.name,
                    from_label=to_node.label,
                    from_id_column=col.name,
                    to_label=from_node.label,
                    to_id_column=next(c.name for c in table.columns if c.is_primary_key),
                    discovery_method="fk_column_self_ref",
                ))
            else:
                rel_type = _relationship_name(table.name, col.references_table, col.name)
                relationships.append(DiscoveredRelationship(
                    type=rel_type,
                    source_table=table.name,
                    from_label=from_node.label,
                    from_id_column=next(c.name for c in table.columns if c.is_primary_key),
                    to_label=to_node.label,
                    to_id_column=col.name,
                    discovery_method="fk_column",
                ))

    # Step 3: Junction tables → relationships between the two entity tables
    for table in tables:
        if not table.is_junction_table:
            continue
        fk_cols = [c for c in table.columns if c.is_foreign_key]
        if len(fk_cols) < 2:
            continue

        from_node = node_by_table.get(fk_cols[0].references_table)
        to_node = node_by_table.get(fk_cols[1].references_table)
        if not from_node or not to_node:
            continue

        extra_props = [
            c.name for c in table.columns
            if not c.is_foreign_key and not c.is_primary_key
        ]

        rel_type = f"{from_node.label.upper()}_TO_{to_node.label.upper()}"
        if "order" in table.name and "item" in table.name:
            rel_type = "CONTAINS"
        elif "product" in table.name and "supplier" in table.name:
            rel_type = "SUPPLIES"

        relationships.append(DiscoveredRelationship(
            type=rel_type,
            source_table=table.name,
            from_label=from_node.label,
            from_id_column=fk_cols[0].name,
            to_label=to_node.label,
            to_id_column=fk_cols[1].name,
            property_columns=extra_props,
            discovery_method="junction_table",
        ))

    return DiscoveredSchema(
        nodes=nodes,
        relationships=relationships,
        tables_analyzed=len(tables),
        discovery_notes=notes,
    )


def discover_from_directory(data_dir: Path) -> DiscoveredSchema:
    """Full pipeline: load tables → discover PKs/FKs → build graph schema."""
    tables = load_table_metadata(data_dir)
    discover_primary_keys(tables)
    discover_foreign_keys(tables)
    detect_junction_tables(tables)
    return build_graph_schema(tables)


def schema_to_dict(schema: DiscoveredSchema) -> dict:
    return {
        "tables_analyzed": schema.tables_analyzed,
        "discovery_notes": schema.discovery_notes,
        "nodes": [asdict(n) for n in schema.nodes],
        "relationships": [asdict(r) for r in schema.relationships],
    }


if __name__ == "__main__":
    import json
    data_dir = Path(__file__).parent.parent / "data" / "sample_delta_tables"
    schema = discover_from_directory(data_dir)
    print(json.dumps(schema_to_dict(schema), indent=2))
