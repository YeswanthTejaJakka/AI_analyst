import pytest
from app.models.chat import ConversationStateEnum
from app.models.chat import ClarifyRequest

@pytest.mark.asyncio
async def test_regression_conv_a(pipeline, sample_schema, sample_adapter, conversation):
    # Conversation A
    # "Which products are the most popular?"
    msg1 = await pipeline.process_query(
        "Which products are the most popular?",
        conversation, sample_schema, sample_adapter
    )
    assert msg1.clarification is not None
    conversation.messages.append(msg1)
    
    # "Give me the most highest priced product."
    msg2 = await pipeline.process_query(
        "Give me the most highest priced product.",
        conversation, sample_schema, sample_adapter
    )
    # This must become a NEW_QUERY and use products.price, not popularity
    assert msg2.sql is not None
    assert "price" in msg2.sql.lower()
    assert "units_sold" not in msg2.sql.lower()
    assert msg2.classification == "NEW_QUERY"

@pytest.mark.asyncio
async def test_regression_conv_b(pipeline, sample_schema, sample_adapter, conversation):
    # Conversation B
    msg1 = await pipeline.process_query(
        "Give me expensive products.",
        conversation, sample_schema, sample_adapter
    )
    assert msg1.clarification is not None
    assert msg1.clarification.field_name == "price_threshold"
    
    # Send custom input
    clarif_req = ClarifyRequest(field_name="price_threshold", custom_input="above average")
    msg2 = await pipeline.process_clarification(clarif_req, conversation, sample_schema, sample_adapter)
    
    assert msg2.sql is not None
    assert "AVG(PRICE)" in msg2.sql.upper()

@pytest.mark.asyncio
async def test_regression_conv_c(pipeline, sample_schema, sample_adapter, conversation):
    # Conversation C
    msg1 = await pipeline.process_query(
        "Give me expensive products.",
        conversation, sample_schema, sample_adapter
    )
    assert msg1.clarification is not None
    
    clarif_req = ClarifyRequest(field_name="price_threshold", custom_input="highest")
    msg2 = await pipeline.process_clarification(clarif_req, conversation, sample_schema, sample_adapter)
    
    # Should ask ANOTHER clarification
    assert msg2.sql is None
    assert msg2.clarification is not None
    assert "Which do you mean" in msg2.content or "specify" in msg2.content

@pytest.mark.asyncio
async def test_regression_conv_d(pipeline, sample_schema, sample_adapter, conversation):
    # Conversation D
    msg1 = await pipeline.process_query(
        "Give me the categories of products.",
        conversation, sample_schema, sample_adapter
    )
    assert msg1.sql is not None
    conversation.messages.append(msg1)
    
    msg2 = await pipeline.process_query(
        "What about their price?",
        conversation, sample_schema, sample_adapter
    )
    assert msg2.clarification is not None
    assert "categor" in msg2.content.lower() and "price" in msg2.content.lower()

@pytest.mark.asyncio
async def test_regression_conv_e(pipeline, sample_schema, sample_adapter, conversation):
    # Conversation E
    msg1 = await pipeline.process_query(
        "Show the top 5 products by units sold.",
        conversation, sample_schema, sample_adapter
    )
    assert msg1.sql is not None
    conversation.messages.append(msg1)
    
    msg2 = await pipeline.process_query(
        "What are their prices?",
        conversation, sample_schema, sample_adapter
    )
    assert msg2.sql is not None
    # Verify that the 5 products are retained (ID filtering or limit/offset inheritance)
    assert "IN (" in msg2.sql.upper()

@pytest.mark.asyncio
async def test_regression_conv_f(pipeline, sample_schema, sample_adapter, conversation):
    # Conversation F
    msg1 = await pipeline.process_query(
        "Show the top 5 products by units sold.",
        conversation, sample_schema, sample_adapter
    )
    conversation.messages.append(msg1)
    
    msg2 = await pipeline.process_query(
        "Give me the highest priced product.",
        conversation, sample_schema, sample_adapter
    )
    # NEW QUERY, shouldn't inherit units_sold
    assert msg2.classification == "NEW_QUERY"
    assert msg2.sql is not None
    assert "units_sold" not in msg2.sql.lower()
    assert "price" in msg2.sql.lower()

@pytest.mark.asyncio
async def test_regression_conv_g(pipeline, sample_schema, sample_adapter, conversation):
    # Conversation G
    msg1 = await pipeline.process_query(
        "Show customers from India.",
        conversation, sample_schema, sample_adapter
    )
    assert msg1.sql is not None
    conversation.messages.append(msg1)
    
    msg2 = await pipeline.process_query(
        "How many are there?",
        conversation, sample_schema, sample_adapter
    )
    assert msg2.sql is not None
    assert "COUNT" in msg2.sql.upper()
    assert "India" in msg2.sql

@pytest.mark.asyncio
async def test_regression_conv_h(pipeline, sample_schema, sample_adapter, conversation):
    # Conversation H
    msg1 = await pipeline.process_query(
        "Show customers from India.",
        conversation, sample_schema, sample_adapter
    )
    conversation.messages.append(msg1)
    
    msg2 = await pipeline.process_query(
        "Show expensive products.",
        conversation, sample_schema, sample_adapter
    )
    assert msg2.classification == "NEW_QUERY"
    # Should ask clarification, and NOT inherit India filter
    assert msg2.clarification is not None
    intent = msg2.intent
    assert "India" not in intent.filters.values()
