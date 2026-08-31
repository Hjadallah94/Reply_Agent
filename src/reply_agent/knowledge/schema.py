"""Pydantic schema for a business's knowledge base, manually entered as YAML for Phase 1
(Doc 3, Phase 1). Phase 2 replaces the *loading* mechanism (spreadsheet/doc upload -> chunk
-> embed) but should be able to produce these same shapes, so downstream code (retrieval,
generation) never needs to know whether a document came from hand-written YAML or an
ingestion pipeline.
"""

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


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


class Promotion(BaseModel):
    """Dashboard-only (Doc 3 Phase 6.5) — deliberately not part of KnowledgeBase below, since
    there's no spreadsheet sheet for it and the roadmap explicitly frames promotions as
    "managed directly" rather than re-uploaded. See knowledge/catalog.py and api/dashboard.py.
    """

    title: str
    description: str = ""
    discount_text: str  # free-form ("20% off", "3 for 10 JOD") — sellers phrase promos too
    # variably to force a numeric-only discount model.
    applies_to: str = ""  # optional, e.g. which product/category it targets
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def _ends_after_starts(self) -> "Promotion":
        if self.ends_at < self.starts_at:
            raise ValueError("ends_at must not be before starts_at")
        return self

    def to_text(self) -> str:
        lines = [f"Promotion: {self.title}"]
        if self.description:
            lines.append(self.description)
        lines.append(f"Discount: {self.discount_text}")
        if self.applies_to:
            lines.append(f"Applies to: {self.applies_to}")
        lines.append(f"Valid: {self.starts_at.isoformat()} to {self.ends_at.isoformat()}")
        return "\n".join(lines)


class KnowledgeBase(BaseModel):
    business_slug: str
    products: list[Product] = Field(default_factory=list)
    policies: list[Policy] = Field(default_factory=list)
    faqs: list[FAQPair] = Field(default_factory=list)
    brand_voice_samples: list[BrandVoiceSample] = Field(default_factory=list)
