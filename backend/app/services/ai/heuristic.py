"""
Heuristic (Deterministic) AI Provider for QueryPilot.

Implements the full LLMProvider interface without any LLM API calls.
Used in test/offline mode and as fallback within the Gemini/OpenAI providers.

Design principles (update.txt Section 0):
- No raw keyword lookup tables for intent — use structured pattern recognition
- LLM proposes; this engine deterministically validates and structures
- Produce the same QueryIntent/ResultContext types as the LLM providers
"""
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
    ScopeEnum,
)
from app.models.schema import DatabaseSchema
from app.services.ai.base import LLMProvider


# ---------------------------------------------------------------------------
# Internal helpers – not exported
# ---------------------------------------------------------------------------

_DESTRUCTIVE_OPS = re.compile(
    r"\b(drop|delete|truncate|update|insert\s+into|alter\s+table|create\s+table|grant|revoke)\b",
    re.I,
)

_LIMIT_RE = re.compile(r"\btop\s+(\d+)\b", re.I)
_COUNTRY_RE = re.compile(
    r"\b(india|united\s+states|usa|united\s+kingdom|uk|germany|canada|australia|"
    r"japan|france|singapore|brazil)\b",
    re.I,
)
_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_CUSTOMER_ID_RE = re.compile(r"\bcustomer\s+(\d+)\b", re.I)
_NUM_RE = re.compile(r"(?:above|over|>|greater\s+than)?\s*\$?\s*(\d+(?:\.\d+)?)")

# Map country mention → canonical name
_COUNTRY_MAP = {
    "india": "India",
    "united states": "United States",
    "usa": "United States",
    "united kingdom": "United Kingdom",
    "uk": "United Kingdom",
    "germany": "Germany",
    "canada": "Canada",
    "australia": "Australia",
    "japan": "Japan",
    "france": "France",
    "singapore": "Singapore",
    "brazil": "Brazil",
}


def _extract_country(q: str) -> Optional[str]:
    m = _COUNTRY_RE.search(q)
    if m:
        return _COUNTRY_MAP.get(m.group(1).lower())
    return None


def _extract_limit(q: str) -> Optional[int]:
    m = _LIMIT_RE.search(q)
    return int(m.group(1)) if m else None


def _extract_year(q: str) -> Optional[str]:
    m = _YEAR_RE.search(q)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# QueryClassifier
# ---------------------------------------------------------------------------

class QueryClassifier:
    """Classifies user query turns relative to conversation state."""

    # Patterns that strongly indicate the user is referencing the previous result
    _REFERENCE_PATTERNS = [
        r"\b(it|its|their|them|they|those|these|her|his|him)\b",
        r"\b(the\s+)?(first|second|third|fourth|fifth|last)\s+one\b",
        r"\b(2nd|3rd|4th|5th)\s+one\b",
        r"\brunner[\s-]?up\b",
        r"\bthat\s+(category|product|customer|order)\b",
        r"\bfrom\s+them\b",
        r"\bby\s+(her|him|them)\b",
        r"\bhow\s+many\s+(are\s+there|of\s+them)\b",
    ]
    _REF_RE = re.compile("|".join(_REFERENCE_PATTERNS), re.I)

    # Patterns that indicate a refinement (parameter change, scope adjustment)
    _REFINEMENT_PATTERNS = [
        r"\bmake\s+that\b", r"\bchange\s+that\s+to\b", r"\bonly\s+top\b",
        r"\bcategory\s+wise\b", r"\bper\s+category\b",
        r"\bi\s+am\s+asking\s+total\b", r"\bjust\s+the\s+total\b",
        r"\bonly\s+(completed|from|in)\b", r"\bfilter\s+by\b",
        r"\bby\s+order\s+count\b", r"\bby\s+revenue\b",
        r"\bnot\s+(spending|revenue|orders|that)\b",
    ]
    _REFINE_RE = re.compile("|".join(_REFINEMENT_PATTERNS), re.I)

    _CORRECTION_PATTERNS = [
        r"\bi\s+meant\b", r"\bi\s+mean\b", r"\bi\s+am\s+asking\b",
        r"\bnot\s+this\b", r"\bnot\s+that\b", r"\binstead\b",
        r"\bactually\b", r"\brather\s+than\b",
    ]
    _CORRECT_RE = re.compile("|".join(_CORRECTION_PATTERNS), re.I)

    _SWITCH_PATTERNS = [
        r"\bforget\s+(that|about\s+it)\b", r"\bnever\s+mind\b",
        r"\bstart\s+over\b", r"\bnew\s+topic\b", r"\bclear\s+context\b",
        r"\blet'?s?\s+switch\b", r"\bnow\s+let'?s?\s+look\s+at\b",
    ]
    _SWITCH_RE = re.compile("|".join(_SWITCH_PATTERNS), re.I)

    @classmethod
    def classify(
        cls,
        query: str,
        previous_intent: Optional[QueryIntent],
        previous_result_context: Optional[ResultContext],
        schema: DatabaseSchema,
        in_clarification: bool = False,
    ) -> QueryClassificationEnum:
        q = query.strip()

        # Priority 1: pending clarification overrides most things
        if in_clarification:
            if cls._SWITCH_RE.search(q):
                return QueryClassificationEnum.CONTEXT_SWITCH
            return QueryClassificationEnum.CLARIFICATION_RESPONSE

        # Priority 2: context switch
        if cls._SWITCH_RE.search(q):
            return QueryClassificationEnum.CONTEXT_SWITCH

        # Priority 3: correction
        if cls._CORRECT_RE.search(q):
            return QueryClassificationEnum.CORRECTION

        # Priority 4: refinement
        if cls._REFINE_RE.search(q):
            return QueryClassificationEnum.QUERY_REFINEMENT

        # Priority 5: result reference (pronouns / demonstratives)
        if cls._REF_RE.search(q):
            return QueryClassificationEnum.RESULT_REFERENCE

        # Priority 6: elliptical follow-up ("what about India?", "and for 2025?")
        if previous_intent and re.match(
            r"^(what\s+about|how\s+about|and\s+for|and\s+in|and\s+with)\b", q, re.I
        ):
            return QueryClassificationEnum.FOLLOW_UP

        # Priority 7: entity switch → always a NEW_QUERY
        if previous_intent and previous_intent.entity:
            prev_e = previous_intent.entity.lower().rstrip("s")
            query_lower = q.lower()
            new_entities = {
                "product": ["product", "item", "sku"],
                "customer": ["customer", "buyer", "client"],
                "category": ["category", "categories"],
                "order": ["order", "purchase", "transaction"],
            }
            for entity, keywords in new_entities.items():
                if entity != prev_e and any(kw in query_lower for kw in keywords):
                    # Only a NEW_QUERY if not also referencing previous (pronouns check)
                    if not cls._REF_RE.search(q):
                        return QueryClassificationEnum.NEW_QUERY

        return QueryClassificationEnum.NEW_QUERY


# ---------------------------------------------------------------------------
# QueryAnalyzer
# ---------------------------------------------------------------------------

class QueryAnalyzer:
    """Extracts structured QueryIntent from natural-language text using heuristic pattern matching."""

    @classmethod
    def analyze_intent(
        cls,
        query: str,
        schema: DatabaseSchema,
        classification: QueryClassificationEnum,
        previous_intent: Optional[QueryIntent] = None,
        previous_result_context: Optional[ResultContext] = None,
    ) -> QueryIntent:
        q = query.lower().strip()

        # ── Safety: destructive operations ──────────────────────────────
        if _DESTRUCTIVE_OPS.search(q):
            kw = _DESTRUCTIVE_OPS.search(q).group(1)  # type: ignore[union-attr]
            return QueryIntent(
                operation="rejected",
                unsupported_reason=(
                    f"Destructive operation detected ('{kw}'). "
                    "QueryPilot only executes safe, read-only queries."
                ),
            )

        # ── Safety: unknown entities not in schema ───────────────────────
        schema_tables = {t.name.lower() for t in schema.tables}
        unknown_entities = {"supplier", "employee", "warehouse", "subscription", "shipment", "vendor", "payroll"}
        for ue in unknown_entities:
            if ue in q and ue not in schema_tables and f"{ue}s" not in schema_tables:
                return QueryIntent(
                    operation="unknown_entity",
                    unsupported_reason=(
                        f"I couldn't find a table or entity representing '{ue}' in the database schema."
                    ),
                )

        # ── Route by classification ──────────────────────────────────────
        if classification in (QueryClassificationEnum.CONTEXT_SWITCH, QueryClassificationEnum.NEW_QUERY):
            return cls._new_query_intent(q, schema)

        if classification in (
            QueryClassificationEnum.FOLLOW_UP,
            QueryClassificationEnum.QUERY_REFINEMENT,
            QueryClassificationEnum.CORRECTION,
            QueryClassificationEnum.RESULT_REFERENCE,
        ):
            return cls._follow_up_intent(q, schema, previous_intent, previous_result_context)

        # Fallback: treat as new query
        return cls._new_query_intent(q, schema)

    # ------------------------------------------------------------------
    # New Query intent extraction
    # ------------------------------------------------------------------

    @classmethod
    def _new_query_intent(cls, q: str, schema: DatabaseSchema) -> QueryIntent:
        intent = QueryIntent()
        intent.filters = {}

        # ── Limit / country / year ───────────────────────────────────────
        limit = _extract_limit(q)
        country = _extract_country(q)
        year = _extract_year(q)
        if country:
            intent.filters["country"] = country
        if year:
            intent.time_range = year

        # ── Customer ID ─────────────────────────────────────────────────
        cid = _CUSTOMER_ID_RE.search(q)
        if cid:
            intent.entity = "customer"
            intent.filters["id"] = int(cid.group(1))

        # ── Explicit entity detection ────────────────────────────────────
        if not intent.entity:
            if "categor" in q:
                intent.entity = "category"
            elif "customer" in q or "buyer" in q:
                intent.entity = "customer"
            elif "product" in q or "item" in q:
                intent.entity = "product"
            elif "order" in q:
                intent.entity = "order"

        # ── Ambiguous queries ────────────────────────────────────────────

        # "best customer" is ambiguous on metric
        if re.search(r"\bbest\s+customers?\b", q):
            intent.entity = "customer"
            intent.operation = "ranking"
            intent.is_ambiguous = True
            intent.ambiguities = [
                AmbiguityItem(
                    field="metric",
                    type="metric",
                    reason="'best customer' can be measured by spending, order count, or average order value.",
                    options=["Highest total spending", "Most orders placed", "Highest average order value"],
                )
            ]
            intent.clarification = ClarificationRequest(
                field_name="metric",
                question="What defines the 'best customer'?",
                options=["Highest total spending", "Most orders placed", "Highest average order value"],
            )
            return intent

        # "popular" product is ambiguous on metric
        if re.search(r"\bpopular\b", q):
            intent.entity = "product"
            intent.operation = "ranking"
            intent.is_ambiguous = True
            intent.ambiguities = [
                AmbiguityItem(
                    field="metric",
                    type="metric",
                    reason="'popular' can mean most units sold, most orders, or highest revenue.",
                    options=["Highest units sold", "Most orders placed", "Highest revenue"],
                )
            ]
            intent.clarification = ClarificationRequest(
                field_name="metric",
                question="What metric should I use for 'popular' products?",
                options=["Highest units sold", "Most orders placed", "Highest revenue"],
            )
            return intent

        # "expensive" without a clear threshold
        if re.search(r"\bexpensive\b", q) and not re.search(
            r"\b(highest[\s-]?priced|most\s+expensive|priciest|costs?\s+the\s+most|maximum\s+price)\b", q
        ):
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
                field_name="price_threshold",
                question="What price qualifies as 'expensive'?",
                options=["Price > $100", "Price > $500", "Top 10% highest priced", "Above average price"],
            )
            return intent

        # "recent" without explicit timeframe
        if re.search(r"\brecently?\b", q) and not re.search(
            r"\b(day|week|month|year|20\d{2})\b", q
        ):
            intent.entity = "customer" if "customer" in q else "order"
            intent.operation = "filter"
            intent.is_ambiguous = True
            intent.ambiguities = [
                AmbiguityItem(
                    field="time_range",
                    type="time",
                    reason="'Recent' does not specify an exact timeframe.",
                    options=["Last 7 days", "Last 30 days", "Last 90 days", "This year"],
                )
            ]
            intent.clarification = ClarificationRequest(
                field_name="time_range",
                question="How recent should 'recent' be?",
                options=["Last 7 days", "Last 30 days", "Last 90 days", "This year"],
            )
            return intent

        # ── Clear intent: operation + metric ─────────────────────────────

        # Superlatives → ranking of 1
        if re.search(r"\b(highest[\s-]?priced|most\s+expensive|priciest|costs?\s+the\s+most|maximum\s+price)\b", q):
            intent.entity = "product"
            intent.operation = "ranking"
            intent.primary_metric = "price"
            intent.sort_column = "price"
            intent.sort_direction = "descending"
            intent.limit = 1
            return intent

        # Count queries
        if re.search(r"\b(how\s+many|count)\b", q):
            intent.operation = "count"

        # Revenue / total sales
        elif re.search(r"\b(revenue|total\s+sales)\b", q):
            intent.operation = "aggregation"
            intent.primary_metric = "revenue"

        # Spending
        elif re.search(r"\b(spending|spent)\b", q):
            intent.operation = "ranking" if limit else "aggregation"
            intent.primary_metric = "spending"
            if not limit:
                limit = 10

        # Units sold
        elif re.search(r"\b(units?\s+sold|sold)\b", q):
            intent.operation = "ranking" if limit else "aggregation"
            intent.primary_metric = "units_sold"

        # Orders (as metric)
        elif re.search(r"\bmost\s+orders?\b", q):
            intent.operation = "ranking"
            intent.primary_metric = "order_count"
            if not limit:
                limit = 10

        # Grouping
        if re.search(r"\b(category[\s-]?wise|per\s+category|by\s+category)\b", q):
            intent.entity = "category"
            intent.group_by = "category"

        intent.limit = limit
        return intent

    # ------------------------------------------------------------------
    # Follow-up / Refinement / Reference intent extraction
    # ------------------------------------------------------------------

    @classmethod
    def _follow_up_intent(
        cls,
        q: str,
        schema: DatabaseSchema,
        previous_intent: Optional[QueryIntent],
        previous_result_context: Optional[ResultContext],
    ) -> QueryIntent:
        if not previous_intent:
            return cls._new_query_intent(q, schema)

        intent = previous_intent.model_copy(deep=True)
        intent.is_ambiguous = False
        intent.clarification = None

        # Resolve pronoun reference IDs
        if previous_result_context and previous_result_context.returned_ids:
            if re.search(r"\b(their|them|those|these|her|his|him)\b", q):
                intent.referenced_ids = list(previous_result_context.returned_ids)
                intent.target_entity_ids = list(previous_result_context.returned_ids)
                intent.scope = ScopeEnum.PREVIOUS_RESULT_SET

        # "second one" / "runner-up"
        if re.search(r"\b(second|2nd)\s+(one|highest|best|largest)\b|\brunner[\s-]?up\b", q):
            intent.limit = 1
            intent.offset = 1
            return intent

        # "make that top N" / "show top N"
        limit_m = re.search(r"\b(?:make\s+(?:it|that)|show|give\s+me|top)\s+(\d+)\b", q)
        if limit_m:
            intent.limit = int(limit_m.group(1))
            return intent

        # "how many" / "count them" → switch to count, preserve filters + scope
        if re.search(r"\b(how\s+many|count\s+(them|these|those))\b", q):
            intent.operation = "count"
            intent.limit = None
            intent.offset = None
            return intent

        # "only from {country}" / "filter by {country}"
        country = _extract_country(q)
        if country and re.search(r"\b(only|filter|from|in)\b", q):
            intent.filters = dict(intent.filters)
            intent.filters["country"] = country
            return intent

        # "their price" / "their prices" → price of previously referenced entities
        if re.search(r"\b(price|prices)\b", q) and re.search(r"\b(their|those|these|them)\b", q):
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
                            options=[
                                "Prices of products in each category",
                                "Average product price per category",
                                "Minimum and maximum product price per category",
                            ],
                        )
                    ],
                    clarification=ClarificationRequest(
                        field_name="category_price_aggregation",
                        question="The previous result contains categories, but price is stored for individual products. What would you like to see?",
                        options=[
                            "Prices of products in each category",
                            "Average product price per category",
                            "Minimum and maximum product price per category",
                        ],
                        missing_attribute="price",
                    ),
                )
            intent.primary_metric = "price"
            intent.metrics = ["price"]
            intent.sort_column = "price"
            return intent

        # Metric switch: "by revenue, not orders" / "by order count, not spending"
        if re.search(r"\bnot\s+(spending|orders?|revenue)\b", q):
            if re.search(r"\border\s+count\b|\bnumber\s+of\s+orders\b", q):
                intent.primary_metric = "order_count"
            elif re.search(r"\brevenue\b", q):
                intent.primary_metric = "revenue"
            elif re.search(r"\bspending\b|\bspent\b", q):
                intent.primary_metric = "spending"
            elif re.search(r"\bunits?\s+sold\b", q):
                intent.primary_metric = "units_sold"
            return intent

        # "revenue from them" / "revenue we get from them"
        if re.search(r"\brevenue\b", q):
            intent.primary_metric = "revenue"
            intent.operation = "aggregation"
            return intent

        # "i am asking total" → collapse group_by
        if re.search(r"\b(i\s+am\s+asking\s+total|just\s+the\s+total|give\s+me\s+the\s+total)\b", q):
            intent.group_by = None
            intent.operation = "aggregation"
            return intent

        # "category wise" / "per category" → group by category
        if re.search(r"\bcategory[\s-]?wise\b|\bper\s+category\b", q):
            intent.group_by = "category"
            return intent

        # Year filter follow-up ("and for 2024?")
        year = _extract_year(q)
        if year:
            intent.time_range = year
            return intent

        # "its sales" → ambiguous metric
        if re.search(r"\bits\s+sales\b", q):
            intent.is_ambiguous = True
            intent.ambiguities = [
                AmbiguityItem(
                    field="metric",
                    type="metric",
                    reason="'sales' is ambiguous.",
                    options=["Total Revenue", "Units Sold"],
                )
            ]
            intent.clarification = ClarificationRequest(
                field_name="metric",
                question="What do you mean by 'sales'?",
                options=["Total Revenue", "Units Sold"],
            )

        return intent

    # ------------------------------------------------------------------
    # Clarification resolution
    # ------------------------------------------------------------------

    @classmethod
    def resolve_clarification(
        cls,
        user_response: str,
        clarification_context: ClarificationContext,
        schema: DatabaseSchema,
    ) -> tuple[bool, Optional[QueryIntent], Optional[str], Optional[list[str]]]:
        resp = user_response.lower().strip()
        intent = clarification_context.current_intent
        field = clarification_context.missing_field

        # ── Price threshold clarification ────────────────────────────────
        if field == "price_threshold":
            # "highest" is still ambiguous
            if resp in ("highest", "highest price", "the highest"):
                return (
                    False,
                    None,
                    "I can interpret 'highest' in two ways:\n"
                    "1. Show the single highest-priced product.\n"
                    "2. Define expensive as price > $500.\n"
                    "Which do you mean?",
                    ["Single highest-priced product", "Price > $500 threshold"],
                )
            # Numeric threshold
            num_m = _NUM_RE.search(resp)
            if "above" in resp or "over" in resp or ">" in resp or num_m:
                val = float(num_m.group(1)) if num_m else 100.0
                updated = intent.model_copy(deep=True)
                updated.filters = dict(updated.filters)
                updated.filters["price_gt"] = val
                updated.is_ambiguous = False
                updated.clarification = None
                return True, updated, None, None
            if "average" in resp:
                updated = intent.model_copy(deep=True)
                updated.filters = dict(updated.filters)
                updated.filters["price_above_avg"] = True
                updated.is_ambiguous = False
                updated.clarification = None
                return True, updated, None, None
            if "10" in resp or "percent" in resp or "top 10" in resp:
                updated = intent.model_copy(deep=True)
                updated.filters = dict(updated.filters)
                updated.filters["price_top_10_percent"] = True
                updated.is_ambiguous = False
                updated.clarification = None
                return True, updated, None, None
            # "single highest-priced product"
            if "single" in resp or "highest-priced" in resp:
                updated = intent.model_copy(deep=True)
                updated.operation = "ranking"
                updated.primary_metric = "price"
                updated.sort_column = "price"
                updated.sort_direction = "descending"
                updated.limit = 1
                updated.is_ambiguous = False
                updated.clarification = None
                return True, updated, None, None

        # ── Category price aggregation clarification ─────────────────────
        if field == "category_price_aggregation":
            updated = intent.model_copy(deep=True)
            updated.entity = "category"
            updated.operation = "aggregation"
            updated.is_ambiguous = False
            updated.clarification = None
            if "average" in resp:
                updated.primary_metric = "avg_product_price"
            elif "min" in resp or "max" in resp:
                updated.primary_metric = "min_max_product_price"
            else:
                updated.primary_metric = "product_prices"
            return True, updated, None, None

        # ── Customer metric clarification ("best customer") ──────────────
        if field == "metric":
            updated = intent.model_copy(deep=True)
            updated.operation = "ranking"
            updated.sort_direction = "descending"
            updated.limit = updated.limit or 1
            updated.is_ambiguous = False
            updated.clarification = None

            if "spending" in resp:
                updated.entity = "customer"
                updated.primary_metric = "spending"
                updated.sort_column = "total_spending"
            elif "order" in resp:
                updated.primary_metric = "order_count"
                updated.sort_column = "total_orders"
            elif "unit" in resp or "purchased" in resp or "sold" in resp:
                updated.entity = "product"
                updated.primary_metric = "units_sold"
                updated.sort_column = "total_units_sold"
            elif "average" in resp and "order" in resp:
                updated.entity = "customer"
                updated.primary_metric = "average_order_value"
                updated.sort_column = "average_order_value"
            elif "revenue" in resp:
                updated.primary_metric = "revenue"
                updated.sort_column = "total_revenue"
            elif "total revenue" in resp or "units sold" in resp:
                updated.primary_metric = "units_sold" if "units" in resp else "revenue"
            return True, updated, None, None

        # ── Time range clarification ─────────────────────────────────────
        if field == "time_range":
            updated = intent.model_copy(deep=True)
            updated.is_ambiguous = False
            updated.clarification = None
            if "7" in resp or "week" in resp:
                updated.time_range = "last_7_days"
            elif "30" in resp or "month" in resp:
                updated.time_range = "last_30_days"
            elif "90" in resp:
                updated.time_range = "last_90_days"
            elif "year" in resp or "this year" in resp:
                updated.time_range = "this_year"
            return True, updated, None, None

        # Default: mark resolved
        updated = intent.model_copy(deep=True)
        updated.is_ambiguous = False
        updated.clarification = None
        return True, updated, None, None


# ---------------------------------------------------------------------------
# HeuristicAIProvider — full LLMProvider implementation
# ---------------------------------------------------------------------------

class HeuristicAIProvider(LLMProvider):
    """Deterministic Heuristic Engine implementing full LLMProvider interface.

    Used in offline/test mode. All results are deterministic and schema-driven.
    No API calls made.
    """

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
        # Heuristic: ambiguity already injected during analyze_intent
        return intent

    async def resolve_clarification(
        self,
        user_response: str,
        clarification_context: ClarificationContext,
        schema: DatabaseSchema,
    ) -> tuple[bool, Optional[QueryIntent], Optional[str], Optional[dict[str, Any]]]:
        resolved, updated_intent, follow_up_q, follow_up_opts = QueryAnalyzer.resolve_clarification(
            user_response=user_response,
            clarification_context=clarification_context,
            schema=schema,
        )
        return resolved, updated_intent, follow_up_q, follow_up_opts
