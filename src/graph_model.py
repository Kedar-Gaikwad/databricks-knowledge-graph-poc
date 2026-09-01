"""Graph schema definitions mapping Databricks Delta tables to Neo4j nodes and relationships."""

from dataclasses import dataclass, field


@dataclass
class NodeMapping:
    label: str
    table: str
    id_column: str
    properties: list[str]


@dataclass
class RelationshipMapping:
    type: str
    source_table: str
    from_label: str
    from_id_column: str
    to_label: str
    to_id_column: str
    properties: list[str] = field(default_factory=list)


NODE_MAPPINGS: list[NodeMapping] = [
    NodeMapping("Customer", "customers", "customer_id", ["name", "segment", "region", "email", "annual_revenue"]),
    NodeMapping("Product", "products", "product_id", ["name", "category", "price", "sku"]),
    NodeMapping("Order", "orders", "order_id", ["order_date", "total_amount", "status"]),
    NodeMapping("Employee", "employees", "employee_id", ["name", "title", "hire_date"]),
    NodeMapping("Department", "departments", "department_id", ["name", "budget", "location"]),
    NodeMapping("Supplier", "suppliers", "supplier_id", ["name", "country", "rating", "contact_email"]),
]

RELATIONSHIP_MAPPINGS: list[RelationshipMapping] = [
    RelationshipMapping("PLACED", "orders", "Customer", "customer_id", "Order", "order_id"),
    RelationshipMapping(
        "CONTAINS", "order_items", "Order", "order_id", "Product", "product_id",
        ["quantity", "unit_price"],
    ),
    RelationshipMapping(
        "SUPPLIES", "product_suppliers", "Supplier", "supplier_id", "Product", "product_id",
        ["lead_time_days", "contract_value"],
    ),
    RelationshipMapping("WORKS_IN", "employees", "Employee", "employee_id", "Department", "department_id"),
    RelationshipMapping("PROCESSED", "orders", "Employee", "processed_by", "Order", "order_id"),
]

# Self-referential relationship handled separately in sync
MANAGER_RELATIONSHIP = RelationshipMapping(
    "MANAGES", "employees", "Employee", "manager_id", "Employee", "employee_id",
)
