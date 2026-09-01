"""Pre-built Cypher traversal queries for the knowledge graph POC."""

TRAVERSAL_QUERIES = {
    "customer_products": {
        "name": "Customer → Products Purchased",
        "description": "Find all products a customer has purchased through their orders",
        "cypher": """
            MATCH (c:Customer {name: $entity_name})-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
            RETURN c, o, p
        """,
        "params": {"entity_name": "Acme Corp"},
    },
    "customer_supply_chain": {
        "name": "Customer → Supply Chain",
        "description": "Trace from customer purchases back to suppliers (3-hop)",
        "cypher": """
            MATCH (c:Customer {name: $entity_name})-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)<-[:SUPPLIES]-(s:Supplier)
            RETURN c, o, p, s
        """,
        "params": {"entity_name": "Acme Corp"},
    },
    "employee_orders": {
        "name": "Employee → Orders Processed",
        "description": "Find all orders processed by an employee and their customers",
        "cypher": """
            MATCH (e:Employee {name: $entity_name})-[:PROCESSED]->(o:Order)<-[:PLACED]-(c:Customer)
            RETURN e, o, c
        """,
        "params": {"entity_name": "Carol White"},
    },
    "org_hierarchy": {
        "name": "Organization Hierarchy",
        "description": "Employee management chain and department structure",
        "cypher": """
            MATCH (e:Employee)-[:WORKS_IN]->(d:Department)
            OPTIONAL MATCH (mgr:Employee)-[:MANAGES]->(e)
            RETURN e, d, mgr
        """,
        "params": {},
    },
    "supplier_products": {
        "name": "Supplier → Products → Customers",
        "description": "Full supply chain: which customers buy products from a supplier",
        "cypher": """
            MATCH (s:Supplier {name: $entity_name})-[:SUPPLIES]->(p:Product)<-[:CONTAINS]-(o:Order)<-[:PLACED]-(c:Customer)
            RETURN s, p, o, c
        """,
        "params": {"entity_name": "DataFlow Inc"},
    },
    "full_neighborhood": {
        "name": "Entity Neighborhood (configurable depth)",
        "description": "Explore all relationships within N hops of any entity",
        "cypher": """
            MATCH (start)
            WHERE start.name = $entity_name OR start.customer_id = $entity_name
               OR start.product_id = $entity_name OR start.order_id = $entity_name
            CALL apoc.path.subgraphAll(start, {maxLevel: $depth})
            YIELD nodes, relationships
            RETURN nodes, relationships
        """,
        "params": {"entity_name": "Acme Corp", "depth": 2},
        "requires_apoc": True,
    },
    "simple_neighborhood": {
        "name": "Entity Neighborhood (2-hop, no APOC)",
        "description": "Explore relationships within 2 hops — works without APOC plugin",
        "cypher": """
            MATCH (start)
            WHERE start.name = $entity_name
            MATCH path = (start)-[*1..2]-(connected)
            RETURN path
            LIMIT 50
        """,
        "params": {"entity_name": "Acme Corp"},
    },
    "cross_department": {
        "name": "Cross-Department Connections",
        "description": "How departments connect through shared customers/orders",
        "cypher": """
            MATCH (e1:Employee)-[:WORKS_IN]->(d1:Department),
                  (e2:Employee)-[:WORKS_IN]->(d2:Department),
                  (e1)-[:PROCESSED]->(o:Order)<-[:PROCESSED]-(e2)
            WHERE d1 <> d2
            RETURN d1, e1, o, e2, d2
        """,
        "params": {},
    },
    "graph_overview": {
        "name": "Full Graph Overview",
        "description": "Sample of the entire knowledge graph for visualization",
        "cypher": """
            MATCH (n)-[r]->(m)
            RETURN n, r, m
            LIMIT 100
        """,
        "params": {},
    },
}
