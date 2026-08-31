from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from reply_agent.knowledge.loader import load_knowledge_base
from reply_agent.knowledge.schema import Promotion


def test_example_business_knowledge_base_loads_and_validates():
    kb = load_knowledge_base("example_business")

    assert kb.products, "expected at least one product"
    assert kb.policies, "expected at least one policy"
    assert kb.faqs, "expected at least one FAQ"
    assert kb.brand_voice_samples, "expected at least one brand-voice sample"

    black_abaya = next(p for p in kb.products if p.name == "Classic Black Abaya")
    assert black_abaya.price_jod == 24
    assert any(
        v.label == "size L" and v.stock_status == "out_of_stock" for v in black_abaya.variants
    )


def test_product_to_text_includes_price_and_stock():
    kb = load_knowledge_base("example_business")
    product = kb.products[0]
    text = product.to_text()
    assert str(product.price_jod) in text
    assert product.stock_status in text


def test_promotion_to_text_includes_discount_and_validity_window():
    starts = datetime(2026, 9, 1, 9, 0)
    ends = datetime(2026, 9, 7, 21, 0)
    promo = Promotion(
        title="Back to School",
        description="Notebooks and pens",
        discount_text="20% off",
        applies_to="stationery",
        starts_at=starts,
        ends_at=ends,
    )
    text = promo.to_text()
    assert "Back to School" in text
    assert "20% off" in text
    assert "stationery" in text
    assert starts.isoformat() in text
    assert ends.isoformat() in text


def test_promotion_rejects_ends_at_before_starts_at():
    with pytest.raises(ValidationError):
        Promotion(
            title="Bad window",
            discount_text="10% off",
            starts_at=datetime(2026, 9, 7),
            ends_at=datetime(2026, 9, 7) - timedelta(days=1),
        )
