import re
from typing import Optional
from app.models.schema import DatabaseSchema, TableInfo


class SchemaRetriever:
    """Intelligently retrieves the relevant subset of tables and relationships

    for a given query rather than sending the entire schema.
    """

    # Keyword synonyms to help match colloquial business terms to database schema
    SYNONYM_MAP = {
        "client": ["customer", "customers", "users"],
        "buyer": ["customer", "customers"],
        "shopper": ["customer", "customers"],
        "user": ["customer", "customers"],
        "spend": ["orders", "total_amount", "spending", "price", "order_items"],
        "spent": ["orders", "total_amount", "spending", "price", "order_items"],
        "cost": ["price", "total_amount", "unit_price"],
        "money": ["total_amount", "price", "revenue"],
        "sale": ["orders", "order_items", "total_amount"],
        "sales": ["orders", "order_items", "total_amount"],
        "purchase": ["orders", "order_items"],
        "bought": ["orders", "order_items", "products"],
        "buy": ["orders", "order_items", "products"],
        "item": ["order_items", "products"],
        "product": ["products", "order_items", "categories"],
        "category": ["categories", "products"],
        "revenue": ["orders", "total_amount", "order_items"],
        "turnover": ["orders", "total_amount"],
        "profit": ["orders", "order_items"],
        "country": ["customers", "country"],
        "date": ["orders", "order_date", "created_at"],
        "recent": ["orders", "order_date", "created_at"],
        "today": ["orders", "order_date"],
        "month": ["orders", "order_date"],
        "year": ["orders", "order_date"],
        "status": ["orders", "status"],
    }

    @classmethod
    def extract_keywords(cls, query: str) -> set[str]:
        words = re.findall(r"\b[a-zA-Z0-9_]+\b", query.lower())
        keywords = set(words)
        # Add synonyms
        for word in words:
            if word in cls.SYNONYM_MAP:
                keywords.update(cls.SYNONYM_MAP[word])
        return keywords

    @classmethod
    def score_table(cls, table: TableInfo, keywords: set[str]) -> float:
        score = 0.0
        t_name = table.name.lower()

        # Direct table name match
        if t_name in keywords or t_name.rstrip("s") in keywords or f"{t_name}s" in keywords:
            score += 10.0

        for col in table.columns:
            c_name = col.name.lower()
            if c_name in keywords:
                score += 5.0
            for kw in keywords:
                if kw in c_name:
                    score += 2.0

        return score

    @classmethod
    def get_relevant_tables(
        cls,
        schema: DatabaseSchema,
        query: str,
        max_tables: int = 8,
    ) -> list[str]:
        """Returns the list of table names that are most relevant to the query,

        including foreign-key junction tables needed to link them.
        """
        if len(schema.tables) <= 6:
            # Small schema: always provide full schema for accuracy and join completeness
            return schema.get_table_names()

        keywords = cls.extract_keywords(query)
        scored: list[tuple[str, float]] = []

        for table in schema.tables:
            score = cls.score_table(table, keywords)
            scored.append((table.name, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        top_tables = {name for name, s in scored if s > 0}

        # If no tables matched specifically, take top 4
        if not top_tables:
            top_tables = {name for name, _ in scored[:4]}

        # Graph expansion: Find intermediate tables connecting the selected tables via foreign keys
        expanded = set(top_tables)
        for rel in schema.relationships:
            if rel.from_table in top_tables and rel.to_table in top_tables:
                continue
            # If a table connects two selected tables
            for other_table in top_tables:
                if (rel.from_table in top_tables and rel.to_table == other_table) or \
                   (rel.to_table in top_tables and rel.from_table == other_table):
                    expanded.add(rel.from_table)
                    expanded.add(rel.to_table)

        # Limit to max_tables
        result = list(expanded)
        if len(result) > max_tables:
            # Keep highest scored
            score_dict = dict(scored)
            result.sort(key=lambda t: score_dict.get(t, 0), reverse=True)
            result = result[:max_tables]

        return result
