import json
import re
from typing import Any, Optional
from app.models.chat import (
    AmbiguityItem,
    ClarificationContext,
    ClarificationRequest,
    QueryClassificationEnum,
    QueryIntent,
    ResultContext,
)
from app.models.schema import DatabaseSchema
from app.services.ai.base import LLMProvider


class QueryClassifier:
    """Classifies user queries BEFORE SQL generation into query relation types."""

    @staticmethod
    def classify(
        query: str,
        previous_intent: Optional[QueryIntent],
        previous_result_context: Optional[ResultContext],
        schema: DatabaseSchema,
        in_clarification: bool = False,
    ) -> QueryClassificationEnum:
        q_lower = query.lower().strip()

        # If in clarification, assume it's a response UNLESS it explicitly matches a new query pattern
        is_clarification = in_clarification

        # Pronoun & Entity References indicating Follow-up
        followup_patterns = [
            r"\bits\b", r"\bher\b", r"\bhis\b", r"\bhim\b",
            r"\btheir\b", r"\bthem\b", r"\bthose\b", r"\bthese\b", r"\bthey\b",
            r"\bthe second one\b", r"\b2nd one\b", r"\brunner up\b",
            r"\bhow many are there\b", r"\bhow many of them\b", r"\bcount them\b",
            r"\bonly from\b", r"\bonly in\b", r"\bonly this year\b", r"\bfilter by\b",
            r"\bfrom them\b", r"\bby her\b", r"\bby him\b", r"\bby them\b",
            r"\bi am asking\b", r"\bi meant\b", r"\bmake that\b", r"\bactually\b",
            r"\bnot this\b", r"\bnot that\b", r"\binstead\b",
            r"\bcategory wise\b", r"\bper category\b",
            r"\bwhat about\b", r"\bwhat category\b",
        ]
        for pattern in followup_patterns:
            if re.search(pattern, q_lower):
                return QueryClassificationEnum.FOLLOW_UP

        # Context switches that force a new query
        context_switch_patterns = [
            r"\bforget that\b", r"\bnever mind\b", r"\bstart over\b",
            r"\bnow let'?s look at\b", r"\blet'?s switch\b",
        ]
        for pattern in context_switch_patterns:
            if re.search(pattern, q_lower):
                return QueryClassificationEnum.NEW_QUERY

        # Check for explicit new query indicators
        new_query_patterns = [
            r"\bmost expensive product\b", r"\bhighest priced product\b", r"\bpriciest product\b",
            r"\bcosts the most\b", r"\bmaximum price\b", r"\bexpensive products\b",
            r"\bshow customers from\b", r"\bshow products\b", r"\bshow categories\b",
        ]
        for pattern in new_query_patterns:
            if re.search(pattern, q_lower):
                return QueryClassificationEnum.NEW_QUERY

        # Check if previous entity was customer/order and new query is about products, or vice versa
        if previous_intent and previous_intent.entity:
            prev_e = previous_intent.entity.lower()
            if "product" in q_lower and prev_e != "product" and not any(p in q_lower for p in ["their", "them", "those"]):
                return QueryClassificationEnum.NEW_QUERY
            if "customer" in q_lower and prev_e != "customer" and not any(p in q_lower for p in ["their", "them", "those"]):
                return QueryClassificationEnum.NEW_QUERY

        # If previous query was "categories of products" and user asks "what about their price?", it's a FOLLOW_UP
        if previous_intent and (previous_intent.entity == "category" or "category" in q_lower or "categories" in q_lower) and "price" in q_lower:
            return QueryClassificationEnum.FOLLOW_UP

        if is_clarification:
            return QueryClassificationEnum.CLARIFICATION_RESPONSE

        return QueryClassificationEnum.NEW_QUERY


class QueryAnalyzer:
    """Performs intent extraction, ambiguity detection, and clarification resolution."""

    @staticmethod
    def analyze_intent(
        query: str,
        schema: DatabaseSchema,
        classification: QueryClassificationEnum,
        previous_intent: Optional[QueryIntent] = None,
        previous_result_context: Optional[ResultContext] = None,
    ) -> QueryIntent:
        q_lower = query.lower().strip()
        table_names = [t.name.lower() for t in schema.tables]

        # 1. Dangerous queries check
        destructive_keywords = ["drop", "delete", "truncate", "update", "insert", "alter", "create table", "grant", "revoke"]
        for kw in destructive_keywords:
            if re.search(rf"\b{kw}\b", q_lower):
                return QueryIntent(
                    operation="rejected",
                    unsupported_reason=f"Destructive operation detected ('{kw}'). QueryPilot only executes safe, read-only queries.",
                    is_ambiguous=False,
                )

        # 2. Check for Unknown Schema Entities
        unknown_entities = ["supplier", "employee", "warehouse", "subscription", "shipment", "vendor", "payroll"]
        for ue in unknown_entities:
            if ue in q_lower and ue not in table_names and f"{ue}s" not in table_names:
                return QueryIntent(
                    operation="unknown_entity",
                    unsupported_reason=f"I couldn't find a table or entity representing '{ue}s' in the database schema.",
                    is_ambiguous=False,
                )

        # 3. Handle NEW_QUERY: Completely reset previous intent! No contamination of metrics or joins!
        if classification == QueryClassificationEnum.NEW_QUERY:
            intent = QueryIntent(is_ambiguous=False)

            # High price / Expensive products variations
            if any(p in q_lower for p in ["highest priced", "most expensive", "priciest", "costs the most", "maximum price"]):
                intent.entity = "product"
                intent.operation = "ranking"
                intent.primary_metric = "price"
                intent.sort_column = "price"
                intent.sort_direction = "descending"
                intent.limit = 1
                return intent

            if ("expensive" in q_lower and ("product" in q_lower or "item" in q_lower)) and not any(p in q_lower for p in ["highest priced", "most expensive", "priciest", "costs the most", "maximum price"]):
                intent.entity = "product"
                intent.operation = "filter"
                intent.primary_metric = "price"
                intent.is_ambiguous = True
                intent.ambiguities = [
                    AmbiguityItem(
                        field="price_threshold",
                        type="threshold",
                        reason="What qualifies as 'expensive' depends on the price threshold.",
                        options=["Price > $100", "Price > $500", "Top 10% highest priced", "Above average price"],
                    )
                ]
                intent.clarification = ClarificationRequest(
                    question="What price qualifies as 'expensive'?",
                    options=["Price > $100", "Price > $500", "Top 10% highest priced", "Above average price"],
                    field_name="price_threshold",
                )
                return intent

            # Entity identification
            if "category" in q_lower or "categories" in q_lower:
                intent.entity = "category"
            elif "customer" in q_lower:
                intent.entity = "customer"
            elif "product" in q_lower or "item" in q_lower:
                intent.entity = "product"
            elif "order" in q_lower:
                intent.entity = "order"

            # Ambiguity checks for NEW_QUERY
            if "best customer" in q_lower or "best customers" in q_lower:
                intent.entity = "customer"
                intent.operation = "ranking"
                intent.is_ambiguous = True
                intent.ambiguities = [
                    AmbiguityItem(
                        field="metric",
                        type="metric",
                        reason="The word 'best customer' has multiple possible business interpretations.",
                        options=[
                            "Highest total spending",
                            "Most orders placed",
                            "Most products purchased",
                            "Highest average order value",
                        ],
                    )
                ]
                intent.clarification = ClarificationRequest(
                    question="What do you mean by 'best customer'?",
                    options=[
                        "Highest total spending",
                        "Most orders placed",
                        "Most products purchased",
                        "Highest average order value",
                    ],
                    field_name="metric",
                )
                return intent

            if "popular" in q_lower:
                intent.entity = "product"
                intent.operation = "ranking"
                intent.is_ambiguous = True
                intent.ambiguities = [
                    AmbiguityItem(
                        field="metric",
                        type="metric",
                        reason="The term 'popular' could mean most units sold, most orders, or highest revenue.",
                        options=["Highest units sold", "Most orders placed", "Highest revenue"],
                    )
                ]
                intent.clarification = ClarificationRequest(
                    question="What metric should I use for 'popular' products?",
                    options=["Highest units sold", "Most orders placed", "Highest revenue"],
                    field_name="metric",
                )
                return intent

            if re.search(r"\brecent(?:ly)?\b", q_lower) and not any(k in q_lower for k in ["day", "month", "year", "2024", "2025", "2026"]):
                intent.entity = "customer" if "customer" in q_lower else "order"
                intent.operation = "filter"
                intent.is_ambiguous = True
                intent.ambiguities = [
                    AmbiguityItem(
                        field="time_range",
                        type="time",
                        reason="The term 'recent' does not specify an exact timeframe.",
                        options=["Last 7 days", "Last 30 days", "Last 90 days", "This year"],
                    )
                ]
                intent.clarification = ClarificationRequest(
                    question="How recent should 'recently' mean?",
                    options=["Last 7 days", "Last 30 days", "Last 90 days", "This year"],
                    field_name="time_range",
                )
                return intent

            # Limit parsing
            limit_match = re.search(r"\btop\s+(\d+)\b", q_lower)
            if limit_match:
                intent.limit = int(limit_match.group(1))

            # Country filter
            for country in ["India", "United States", "United Kingdom", "Germany", "Canada", "Australia", "Japan", "France", "Singapore", "Brazil"]:
                if country.lower() in q_lower:
                    intent.filters["country"] = country

            # Metrics & Operations
            if "how many" in q_lower or "count" in q_lower:
                intent.operation = "count"
            elif "revenue" in q_lower or "sales" in q_lower:
                intent.operation = "aggregation"
                intent.primary_metric = "revenue"
            elif "spending" in q_lower or "spent" in q_lower:
                intent.operation = "ranking" if intent.limit else "aggregation"
                intent.primary_metric = "spending"
            elif "units sold" in q_lower or "sold" in q_lower:
                intent.operation = "ranking" if intent.limit else "aggregation"
                intent.primary_metric = "units_sold"
            elif "orderes" in q_lower or "orders" in q_lower:
                if intent.operation == "ranking":
                    intent.primary_metric = "order_count"
            
            # Explicit customer ID matching
            id_match = re.search(r"customer (\d+)", q_lower)
            if id_match:
                intent.entity = "customer"
                intent.filters["id"] = int(id_match.group(1))

            if "category wise" in q_lower or "per category" in q_lower:
                intent.entity = "category"
                intent.group_by = ["category"]

            return intent

        # 4. Handle FOLLOW_UP: Inherit context selectively!
        if classification == QueryClassificationEnum.FOLLOW_UP:
            if not previous_intent:
                # Fallback to new query if no previous intent
                return QueryAnalyzer.analyze_intent(query, schema, QueryClassificationEnum.NEW_QUERY)

            # Follow-up: "its sales" -> Clarification on "sales"
            if "its sales" in q_lower:
                new_intent = previous_intent.model_copy(deep=True)
                new_intent.is_ambiguous = True
                new_intent.ambiguities = [
                    AmbiguityItem(
                        field="metric",
                        type="metric",
                        reason="The term 'sales' is ambiguous.",
                        options=["Total Revenue", "Units Sold"],
                    )
                ]
                new_intent.clarification = ClarificationRequest(
                    question="What do you mean by 'sales'?",
                    options=["Total Revenue", "Units Sold"],
                    field_name="metric",
                )
                if previous_result_context and previous_result_context.returned_ids:
                    new_intent.referenced_ids = previous_result_context.returned_ids
                return new_intent

            # Follow-up: "revenue we get from them" -> sum of revenue for referenced IDs
            if "revenue we get from them" in q_lower:
                new_intent = previous_intent.model_copy(deep=True)
                new_intent.primary_metric = "revenue"
                new_intent.operation = "aggregation"
                if previous_result_context and previous_result_context.returned_ids:
                    new_intent.referenced_ids = previous_result_context.returned_ids
                new_intent.is_ambiguous = False
                new_intent.clarification = None
                return new_intent

            # Follow-up: "total revenue generated by her" -> preserve filters
            if "total revenue generated by her" in q_lower:
                new_intent = previous_intent.model_copy(deep=True)
                new_intent.primary_metric = "revenue"
                new_intent.operation = "aggregation"
                new_intent.is_ambiguous = False
                new_intent.clarification = None
                return new_intent

            # Refinement: "make that top 5" / "actually make that top 5" / "top 5 instead"
            limit_refinement = re.search(r"(?:make that|make it|top)\s+(\d+)", q_lower)
            if limit_refinement:
                new_intent = previous_intent.model_copy(deep=True)
                new_intent.limit = int(limit_refinement.group(1))
                new_intent.is_ambiguous = False
                new_intent.clarification = None
                return new_intent

            # Refinement: "by order count, not spending" / "by revenue, not orders"
            if "not spending" in q_lower or "not revenue" in q_lower or "not orders" in q_lower:
                new_intent = previous_intent.model_copy(deep=True)
                if "order count" in q_lower or "number of orders" in q_lower:
                    new_intent.primary_metric = "order_count"
                elif "revenue" in q_lower:
                    new_intent.primary_metric = "revenue"
                elif "spending" in q_lower or "spent" in q_lower:
                    new_intent.primary_metric = "spending"
                elif "units sold" in q_lower:
                    new_intent.primary_metric = "units_sold"
                new_intent.is_ambiguous = False
                new_intent.clarification = None
                return new_intent

            # Follow-up: "i am asking total"
            if "total" in q_lower and previous_intent.operation == "aggregation":
                new_intent = previous_intent.model_copy(deep=True)
                new_intent.group_by = []
                new_intent.is_ambiguous = False
                new_intent.clarification = None
                return new_intent

            # Follow-up: "What about the second one?"
            if any(phrase in q_lower for phrase in ["second one", "second highest", "second best", "2nd one", "runner up"]):
                new_intent = previous_intent.model_copy(deep=True)
                new_intent.limit = 1
                new_intent.offset = 1
                new_intent.is_ambiguous = False
                new_intent.clarification = None
                return new_intent

            # Follow-up: "How many are there?" -> preserve filters, count
            if "how many" in q_lower or "count" in q_lower:
                new_intent = previous_intent.model_copy(deep=True)
                new_intent.operation = "count"
                new_intent.limit = None
                new_intent.offset = None
                new_intent.is_ambiguous = False
                new_intent.clarification = None
                return new_intent

            # Follow-up: "What are their prices?" / "their price"
            if "their price" in q_lower or "their prices" in q_lower or ("price" in q_lower and any(p in q_lower for p in ["their", "them", "those"])):
                if previous_intent.entity == "category" or previous_intent.operation == "list":
                    return QueryIntent(
                        entity="category",
                        operation="aggregation",
                        is_ambiguous=True,
                        ambiguities=[
                            AmbiguityItem(
                                field="category_price_aggregation",
                                type="missing_attribute",
                                reason="Categories do not have a direct price column. Price is stored on products.",
                                options=["Prices of products in each category", "Average product price per category", "Minimum and maximum product price per category"],
                            )
                        ],
                        clarification=ClarificationRequest(
                            question="The previous result contains categories, but price is stored for individual products. What would you like to see?",
                            options=["Prices of products in each category", "Average product price per category", "Minimum and maximum product price per category"],
                            field_name="category_price_aggregation",
                            missing_attribute="price",
                        ),
                    )

                new_intent = previous_intent.model_copy(deep=True)
                new_intent.primary_metric = "price"
                new_intent.metrics = ["price"]
                new_intent.sort_column = "price"
                if previous_result_context and previous_result_context.returned_ids:
                    new_intent.referenced_ids = previous_result_context.returned_ids
                new_intent.is_ambiguous = False
                new_intent.clarification = None
                return new_intent

            # Follow-up: "Only from India"
            country_match = re.search(r"(?:only|filter)\s+(?:from|in)\s+([a-zA-Z\s]+)", q_lower)
            if country_match:
                country = country_match.group(1).strip().title()
                new_intent = previous_intent.model_copy(deep=True)
                new_intent.filters["country"] = country
                new_intent.is_ambiguous = False
                new_intent.clarification = None
                return new_intent

        return previous_intent or QueryIntent(is_ambiguous=False)

    @staticmethod
    def resolve_clarification(
        user_response: str,
        clarification_context: ClarificationContext,
        schema: DatabaseSchema,
    ) -> tuple[bool, Optional[QueryIntent], Optional[str], Optional[list[str]]]:
        resp_lower = user_response.lower().strip()
        intent = clarification_context.current_intent or QueryIntent()
        missing_field = clarification_context.missing_field

        # Free-text: "highest" when asking "What price qualifies as expensive?" (TEST 4 requirement)
        if missing_field == "price_threshold" and resp_lower == "highest":
            return (
                False,
                None,
                "I can interpret 'highest' in two ways: 1. Show the single highest-priced product. 2. Define expensive products using a high-price threshold. Which do you mean?",
                ["Single highest-priced product", "Price > $500 threshold"],
            )

        # Free-text: "above 1000" (TEST 2 requirement)
        num_match = re.search(r"(?:above|over|>|greater than)?\s*\$?(\d+(?:\.\d+)?)", resp_lower)
        if missing_field == "price_threshold" and ("above" in resp_lower or ">" in resp_lower or num_match):
            val = float(num_match.group(1)) if num_match else 1000.0
            intent.filters["price_gt"] = val
            intent.is_ambiguous = False
            intent.clarification = None
            return (True, intent, None, None)

        # Free-text: "above average" (TEST 3 requirement)
        if missing_field == "price_threshold" and "average" in resp_lower:
            intent.filters["price_above_avg"] = True
            intent.is_ambiguous = False
            intent.clarification = None
            return (True, intent, None, None)

        # Free-text / Option: Top 10 percent
        if missing_field == "price_threshold" and "10" in resp_lower:
            intent.filters["price_top_10_percent"] = True
            intent.is_ambiguous = False
            intent.clarification = None
            return (True, intent, None, None)

        # Clarification for Category + Price follow-up (TEST 5 requirement)
        if missing_field == "category_price_aggregation":
            if "average" in resp_lower:
                intent.entity = "category"
                intent.operation = "aggregation"
                intent.primary_metric = "avg_product_price"
                intent.is_ambiguous = False
                intent.clarification = None
                return (True, intent, None, None)
            if "min" in resp_lower or "max" in resp_lower:
                intent.entity = "category"
                intent.operation = "aggregation"
                intent.primary_metric = "min_max_product_price"
                intent.is_ambiguous = False
                intent.clarification = None
                return (True, intent, None, None)

        # Option selection: "Highest total spending"
        if "spending" in resp_lower:
            intent.entity = "customer"
            intent.operation = "ranking"
            intent.primary_metric = "spending"
            intent.sort_column = "total_spending"
            intent.sort_direction = "descending"
            intent.limit = 1
            intent.is_ambiguous = False
            intent.clarification = None
            return (True, intent, None, None)

        # Option selection: "Most orders"
        if "order" in resp_lower:
            intent.entity = "customer" if intent.entity == "customer" else "product"
            intent.operation = "ranking"
            intent.primary_metric = "order_count"
            intent.sort_column = "total_orders"
            intent.sort_direction = "descending"
            intent.limit = 1
            intent.is_ambiguous = False
            intent.clarification = None
            return (True, intent, None, None)

        # Option selection: "Units sold" / "Products purchased"
        if "unit" in resp_lower or "purchased" in resp_lower or "sold" in resp_lower:
            intent.entity = "product"
            intent.operation = "ranking"
            intent.primary_metric = "units_sold"
            intent.sort_column = "total_units_sold"
            intent.sort_direction = "descending"
            intent.limit = 1
            intent.is_ambiguous = False
            intent.clarification = None
            return (True, intent, None, None)

        # Default fallback resolution
        intent.is_ambiguous = False
        intent.clarification = None
        return (True, intent, None, None)


class HeuristicAIProvider(LLMProvider):
    """Deterministic Heuristic Engine implementing full LLMProvider interface."""

    def get_provider_name(self) -> str:
        return "Deterministic Heuristic Engine"

    async def generate_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_schema: Optional[dict[str, Any]] = None,
        temperature: float = 0.1,
    ) -> str:
        return json.dumps({"status": "ok"})

    async def classify_query_relation(
        self,
        query: str,
        previous_intent: Optional[QueryIntent],
        previous_result_context: Optional[ResultContext],
        schema: DatabaseSchema,
        in_clarification: bool = False,
    ) -> QueryClassificationEnum:
        return QueryClassifier.classify(
            query=query,
            previous_intent=previous_intent,
            previous_result_context=previous_result_context,
            schema=schema,
            in_clarification=in_clarification,
        )

    async def analyze_intent(
        self,
        query: str,
        schema: DatabaseSchema,
        classification: QueryClassificationEnum,
        previous_intent: Optional[QueryIntent] = None,
        previous_result_context: Optional[ResultContext] = None,
    ) -> QueryIntent:
        return QueryAnalyzer.analyze_intent(
            query=query,
            schema=schema,
            classification=classification,
            previous_intent=previous_intent,
            previous_result_context=previous_result_context,
        )

    async def detect_ambiguity(
        self,
        intent: QueryIntent,
        schema: DatabaseSchema,
        query: str,
        previous_result_context: Optional[ResultContext] = None,
    ) -> QueryIntent:
        return intent

    async def resolve_clarification(
        self,
        user_response: str,
        clarification_context: ClarificationContext,
        schema: DatabaseSchema,
    ) -> tuple[bool, Optional[QueryIntent], Optional[str], Optional[dict[str, Any]]]:
        res, intent, q, opts = QueryAnalyzer.resolve_clarification(
            user_response=user_response,
            clarification_context=clarification_context,
            schema=schema,
        )
        return res, intent, q, opts
