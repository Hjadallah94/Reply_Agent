import io

import pytest
from openpyxl import Workbook

from reply_agent.knowledge.spreadsheet_ingest import WorkbookParseError, parse_catalog_workbook


def _workbook(sheets: dict[str, list[list]]) -> io.BytesIO:
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def test_parses_a_full_workbook():
    wb = _workbook(
        {
            "Products": [
                ["name", "description", "price_jod", "stock_status", "variants"],
                [
                    "Black Abaya",
                    "Everyday abaya",
                    24,
                    "in_stock",
                    "size S:in_stock; size L:out_of_stock",
                ],
            ],
            "Policies": [
                ["topic", "content"],
                ["delivery", "1-2 days in Amman"],
            ],
            "FAQs": [
                ["question", "answer"],
                ["Do you ship abroad?", "Not yet"],
            ],
        }
    )

    kb, issues = parse_catalog_workbook(wb, business_slug="test-business")

    assert issues == []
    assert len(kb.products) == 1
    assert kb.products[0].name == "Black Abaya"
    assert kb.products[0].price_jod == 24
    assert [v.label for v in kb.products[0].variants] == ["size S", "size L"]
    assert [v.stock_status for v in kb.products[0].variants] == ["in_stock", "out_of_stock"]
    assert kb.policies[0].topic == "delivery"
    assert kb.faqs[0].question == "Do you ship abroad?"


def test_missing_required_column_raises():
    wb = _workbook({"Products": [["name", "description"], ["Black Abaya", "desc"]]})

    with pytest.raises(WorkbookParseError, match="price_jod"):
        parse_catalog_workbook(wb, business_slug="test-business")


def test_bad_row_is_skipped_not_fatal():
    wb = _workbook(
        {
            "Products": [
                ["name", "price_jod"],
                ["Good Product", 24],
                ["Bad Product", "not-a-number"],
            ]
        }
    )

    kb, issues = parse_catalog_workbook(wb, business_slug="test-business")

    assert len(kb.products) == 1
    assert kb.products[0].name == "Good Product"
    assert len(issues) == 1
    assert "row 3" in issues[0]


def test_empty_name_cell_is_skipped():
    wb = _workbook({"Products": [["name", "price_jod"], ["", 24]]})

    kb, issues = parse_catalog_workbook(wb, business_slug="test-business")

    assert kb.products == []
    assert len(issues) == 1


def test_missing_optional_sheet_is_not_an_error():
    wb = _workbook({"Products": [["name", "price_jod"], ["Black Abaya", 24]]})

    kb, issues = parse_catalog_workbook(wb, business_slug="test-business")

    assert issues == []
    assert kb.policies == []
    assert kb.faqs == []


def test_product_with_no_variants_cell():
    wb = _workbook({"Products": [["name", "price_jod"], ["Kimono", 18]]})

    kb, _ = parse_catalog_workbook(wb, business_slug="test-business")

    assert kb.products[0].variants == []
