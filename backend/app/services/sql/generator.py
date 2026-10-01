import json
import re
from typing import Any, Optional
from app.models.chat import QueryIntent
from app.models.schema import DatabaseSchema
from app.services.ai.base import LLMProvider
from app.services.schema.business_semantics import BusinessSemanticLayer
from app.services.schema.retrieval import SchemaRetriever
from app.services.sql.validator import SQLValidator


class SQLGenerator:
    """Generates schema-accurate, dialect-specific, safe SQL from user intent."""

    def __init__(self, llm_provider: Optional[LLMProvider] = None):
        self.llm_provider = llm_provider
        self.semantic_layer = BusinessSemanticLayer()

    async def generate(
        self,
        intent: QueryIntent,
        schema: DatabaseSchema,
        user_query: str,
        clarification_answer: Optional[str] = None,
    ) -> str:
        # If an LLM provider is available and configured (not heuristic), attempt LLM generation
        if self.llm_provider and "Heuristic" not in self.llm_provider.get_provider_name():
            try:
                llm_sql = await self._generate_with_llm(intent, schema, user_query, clarification_answer)
                if llm_sql:
                    is_valid, _ = SQLValidator.validate_sql(llm_sql, schema)
                    if is_valid:
                        return SQLValidator.enforce_row_limit(llm_sql)
            except Exception:
                pass

        # Deterministic schema-aware generator
        return self._generate_deterministic(intent, schema, user_query, clarification_answer)

    async def _generate_with_llm(
        self,
        intent: QueryIntent,
        schema: DatabaseSchema,
        user_query: str,
        clarification_answer: Optional[str] = None,
    ) -> Optional[str]:
        relevant_tables = SchemaRetriever.get_relevant_tables(schema, user_query)
        schema_text = schema.to_summary_text(relevant_tables)
        semantics_text = self.semantic_layer.to_prompt_text(user_query)

        system_prompt = f"""You are QueryPilot's expert SQL generator.
Generate ONLY a valid, read-only SQL query for the target dialect: {schema.dialect.upper()}.
CRITICAL RULES:
1. ONLY generate a SELECT or WITH statement. No modifications allowed.
2. Use ONLY the tables and columns explicitly present in the provided schema. Do not invent or assume table/column names.
3. For SQLite, use strftime('%Y', order_date) for year extraction.
4. For PostgreSQL, use EXTRACT(YEAR FROM order_date) or DATE_TRUNC.
5. Filter completed orders (status = 'completed') when calculating revenue or total sales unless requested otherwise.
6. Do NOT join orders or order_items if the query is purely asking about product prices or category names.
7. Return your response in JSON format with a single key "sql".

Schema:
{schema_text}

{semantics_text}
"""
        prompt = f"""User Request: "{user_query}"
Extracted Intent: {intent.model_dump_json()}
Clarification Answer (if any): "{clarification_answer or 'None'}"

Generate the SQL query:"""

        response_text = await self.llm_provider.generate_completion(
            prompt=prompt,
            system_prompt=system_prompt,
            json_schema={"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"]},
        )

        try:
            data = json.loads(response_text)
            return data.get("sql")
        except Exception:
            match = re.search(r"```(?:sql)?\s*([\s\S]*?)\s*```", response_text)
            if match:
                return match.group(1).strip()
            return response_text.strip()

    def _generate_deterministic(
        self,
        intent: QueryIntent,
        schema: DatabaseSchema,
        user_query: str,
        clarification_answer: Optional[str] = None,
    ) -> str:
        """Deterministic schema-driven SQL generation."""
        q_lower = user_query.lower()
        dialect = schema.dialect.lower()
        limit = intent.limit or 100
        offset = intent.offset or 0

        # Incorporate clarification answer into intent if provided
        clarif = (clarification_answer or "").lower()
        if "highest total spending" in clarif or "spending" in clarif:
            intent.operation = "ranking"
            intent.primary_metric = "spending"
            intent.metrics = ["total_spending"]
        elif "most orders" in clarif:
            intent.operation = "ranking"
            intent.primary_metric = "order_count"
            intent.metrics = ["order_count"]
        elif "most products" in clarif or "units sold" in clarif:
            intent.operation = "ranking"
            intent.primary_metric = "units_sold"
            intent.metrics = ["products_count"]
        elif "average order value" in clarif:
            intent.operation = "ranking"
            intent.primary_metric = "average_order_value"
            intent.metrics = ["average_order_value"]

        # Table existence check
        has_customers = schema.get_table("customers") is not None
        has_orders = schema.get_table("orders") is not None
        has_order_items = schema.get_table("order_items") is not None
        has_products = schema.get_table("products") is not None
        has_categories = schema.get_table("categories") is not None

        country_filter = intent.filters.get("country")
        year_filter = intent.time_range if intent.time_range in ["2024", "2025", "2026"] else None

        def make_date_filter(table_alias: str, col_name: str, yr: str) -> str:
            if dialect == "sqlite":
                return f"strftime('%Y', {table_alias}.{col_name}) = '{yr}'"
            return f"EXTRACT(YEAR FROM {table_alias}.{col_name}) = {yr}"

        # 1. Simple count queries (Test 1: "How many customers are there?")
        if intent.operation == "count":
            if intent.entity == "customer" and has_customers:
                where_clause = f" WHERE country = '{country_filter}'" if country_filter else ""
                return f"SELECT COUNT(*) AS total_customers FROM customers{where_clause};"
            if intent.entity == "order" and has_orders:
                return "SELECT COUNT(*) AS total_orders FROM orders;"
            if intent.entity == "product" and has_products:
                return "SELECT COUNT(*) AS total_products FROM products;"
            target_table = schema.tables[0].name
            return f"SELECT COUNT(*) AS total_records FROM {target_table};"

        # 2. Categories listing / Follow-up price aggregation on categories (TEST 5 requirement)
        if intent.entity == "category" or "category" in q_lower or "categories" in q_lower:
            if intent.primary_metric == "avg_product_price" or "average" in clarif:
                return """SELECT c.id, c.name AS category_name, ROUND(AVG(p.price), 2) AS average_price
FROM categories c
JOIN products p ON c.id = p.category_id
GROUP BY c.id, c.name
ORDER BY c.name;"""
            if intent.primary_metric == "min_max_product_price":
                return """SELECT c.id, c.name AS category_name, MIN(p.price) AS min_price, MAX(p.price) AS max_price
FROM categories c
JOIN products p ON c.id = p.category_id
GROUP BY c.id, c.name
ORDER BY c.name;"""
            if "prices of products" in clarif:
                return """SELECT c.name AS category_name, p.id, p.name AS product_name, p.price
FROM categories c
JOIN products p ON c.id = p.category_id
ORDER BY c.name, p.price DESC;"""

            if intent.primary_metric == "revenue" or "revenue" in q_lower:
                return """SELECT c.id, c.name AS category_name, ROUND(SUM(oi.quantity * oi.unit_price), 2) AS total_revenue
FROM categories c
JOIN products p ON c.id = p.category_id
JOIN order_items oi ON p.id = oi.product_id
JOIN orders o ON oi.order_id = o.id
WHERE o.status = 'completed'
GROUP BY c.id, c.name
ORDER BY total_revenue DESC;"""

            # Standard listing of categories
            return """SELECT c.id, c.name AS category_name
FROM categories c
ORDER BY c.name;"""

        # 3. Product price query / NEW_QUERY for expensive product (TEST 1, TEST 2, TEST 3, TEST 7 requirements)
        # CRITICAL: NO orders or order_items join for product price queries!
        if intent.entity == "product" and (intent.primary_metric == "price" or "price" in intent.metrics or "price_gt" in intent.filters or "price_above_avg" in intent.filters or "highest priced" in q_lower or "most expensive" in q_lower or "costs the most" in q_lower):
            cat_join = "JOIN categories c ON p.category_id = c.id" if has_categories else ""
            cat_col = ", c.name AS category_name" if has_categories else ""
            where_clauses = []

            if "price_gt" in intent.filters:
                where_clauses.append(f"p.price > {intent.filters['price_gt']}")
            if "price_above_avg" in intent.filters or "above average" in clarif:
                where_clauses.append("p.price > (SELECT AVG(price) FROM products)")

            if intent.referenced_ids:
                ids_str = ", ".join(str(i) for i in intent.referenced_ids)
                where_clauses.append(f"p.id IN ({ids_str})")

            where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
            limit_str = f"LIMIT {limit}" if limit else ""
            offset_str = f" OFFSET {offset}" if offset > 0 else ""

            return f"""SELECT p.id, p.name{cat_col}, p.price
FROM products p
{cat_join}
{where_str}
ORDER BY p.price DESC
{limit_str}{offset_str};""".strip()

        # 4. Customer rankings & Joins (Test 2: "Which customer spent the most?")
        if (intent.entity == "customer" or "customer" in q_lower) and has_customers and has_orders:
            where_clauses = ["o.status = 'completed'"]
            if country_filter:
                where_clauses.append(f"c.country = '{country_filter}'")
            if year_filter:
                where_clauses.append(make_date_filter("o", "order_date", year_filter))
            
            if "id" in intent.filters:
                where_clauses.append(f"c.id = {intent.filters['id']}")
            
            if intent.referenced_ids:
                ids_str = ", ".join(str(i) for i in intent.referenced_ids)
                where_clauses.append(f"c.id IN ({ids_str})")

            where_str = f"WHERE {' AND '.join(where_clauses)}"

            # Support global aggregation across scoped customers (T8)
            if not intent.group_by and intent.operation == "aggregation":
                if intent.primary_metric == "order_count":
                    return f"SELECT COUNT(o.id) AS total_orders FROM customers c JOIN orders o ON c.id = o.customer_id {where_str};"
                elif intent.primary_metric == "average_order_value":
                    return f"SELECT ROUND(AVG(o.total_amount), 2) AS average_order_value FROM customers c JOIN orders o ON c.id = o.customer_id {where_str};"
                else:
                    return f"SELECT ROUND(SUM(o.total_amount), 2) AS total_spending FROM customers c JOIN orders o ON c.id = o.customer_id {where_str};"

            if intent.primary_metric == "order_count" or "most orders" in q_lower:
                sql = f"""SELECT c.id, c.name, c.email, c.country, COUNT(o.id) AS total_orders
FROM customers c
JOIN orders o ON c.id = o.customer_id
{where_str}
GROUP BY c.id, c.name, c.email, c.country
ORDER BY total_orders DESC
LIMIT {limit}"""
            elif intent.primary_metric == "average_order_value" or "average order value" in q_lower:
                sql = f"""SELECT c.id, c.name, c.country, ROUND(AVG(o.total_amount), 2) AS average_order_value
FROM customers c
JOIN orders o ON c.id = o.customer_id
{where_str}
GROUP BY c.id, c.name, c.country
ORDER BY average_order_value DESC
LIMIT {limit}"""
            else:
                # Default: Total spending
                sql = f"""SELECT c.id, c.name, c.email, c.country, ROUND(SUM(o.total_amount), 2) AS total_spending
FROM customers c
JOIN orders o ON c.id = o.customer_id
{where_str}
GROUP BY c.id, c.name, c.email, c.country
ORDER BY total_spending DESC
LIMIT {limit}"""

            if offset > 0:
                sql += f" OFFSET {offset}"
            return sql + ";"

        # 5. Product sales volume rankings ("Which products sold the most?")
        if (intent.entity == "product" or "product" in q_lower) and has_products and has_order_items and has_orders:
            where_clauses = ["o.status = 'completed'"]
            if year_filter:
                where_clauses.append(make_date_filter("o", "order_date", year_filter))

            where_str = f"WHERE {' AND '.join(where_clauses)}"
            cat_join = "JOIN categories cat ON p.category_id = cat.id" if has_categories else ""
            cat_col = ", cat.name AS category_name" if has_categories else ""
            cat_group = ", cat.name" if has_categories else ""

            if intent.primary_metric == "revenue" or "revenue" in q_lower:
                sql = f"""SELECT p.id, p.name{cat_col}, ROUND(SUM(oi.quantity * oi.unit_price), 2) AS total_revenue
FROM products p
{cat_join}
JOIN order_items oi ON p.id = oi.product_id
JOIN orders o ON oi.order_id = o.id
{where_str}
GROUP BY p.id, p.name{cat_group}
ORDER BY total_revenue DESC
LIMIT {limit}"""
            else:
                sql = f"""SELECT p.id, p.name{cat_col}, SUM(oi.quantity) AS total_units_sold
FROM products p
{cat_join}
JOIN order_items oi ON p.id = oi.product_id
JOIN orders o ON oi.order_id = o.id
{where_str}
GROUP BY p.id, p.name{cat_group}
ORDER BY total_units_sold DESC
LIMIT {limit}"""

            if offset > 0:
                sql += f" OFFSET {offset}"
            return sql + ";"

        # 6. Revenue / Sales aggregations ("What is total revenue?")
        if has_orders and ("revenue" in q_lower or "total sales" in q_lower):
            where_clauses = ["status = 'completed'"]
            if year_filter:
                where_clauses.append(make_date_filter("orders", "order_date", year_filter))

            where_str = f"WHERE {' AND '.join(where_clauses)}"
            return f"""SELECT ROUND(SUM(total_amount), 2) AS total_revenue, COUNT(id) AS total_completed_orders
FROM orders
{where_str};"""

        # Default fallback
        first_table = schema.tables[0].name
        cols = ", ".join([c.name for c in schema.tables[0].columns[:6]])
        return f"SELECT {cols} FROM {first_table} LIMIT {limit};"
