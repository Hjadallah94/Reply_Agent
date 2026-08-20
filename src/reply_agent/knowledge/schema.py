"""Pydantic schema for a business's knowledge base, manually entered as YAML for Phase 1
(Doc 3, Phase 1). Phase 2 replaces the *loading* mechanism (spreadsheet/doc upload -> chunk
-> embed) but should be able to produce these same shapes, so downstream code (retrieval,
generation) never needs to know whether a document came from hand-written YAML or an
ingestion pipeline.
"""

from pydantic import BaseModel, Field


class ProductVariant(BaseModel):
    label: str  # e.g. "size M", "red"
    stock_status: str = "in_stock"  # in_stock | out_of_stock | made_to_order


class Product(BaseModel):
    name: str
    description: str = ""
    price_jod: float
    variants: list[ProductVariant] = Field(default_factory=list)
    stock_status: str = "in_stock"

    def to_text(self) -> str:
        lines = [f"Product: {self.name}", f"Price: {self.price_jod} JOD"]
        if self.description:
            lines.append(f"Description: {self.description}")
        lines.append(f"Stock status: {self.stock_status}")
        for v in self.variants:
            lines.append(f"Variant: {v.label} — {v.stock_status}")
        return "\n".join(lines)


class Policy(BaseModel):
    topic: str  # e.g. "delivery", "returns", "payment"
    content: str

    def to_text(self) -> str:
        return f"Policy ({self.topic}): {self.content}"


class FAQPair(BaseModel):
    question: str
    answer: str

    def to_text(self) -> str:
        return f"Q: {self.question}\nA: {self.answer}"


class BrandVoiceSample(BaseModel):
    customer_message: str
    seller_reply: str


class KnowledgeBase(BaseModel):
    business_slug: str
    products: list[Product] = Field(default_factory=list)
    policies: list[Policy] = Field(default_factory=list)
    faqs: list[FAQPair] = Field(default_factory=list)
    brand_voice_samples: list[BrandVoiceSample] = Field(default_factory=list)
