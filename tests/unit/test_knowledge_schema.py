from reply_agent.knowledge.loader import load_knowledge_base


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
