"""Ingests a seller's catalog workbook (.xlsx with Products/Policies/FAQs sheets) for an
existing business — the Phase 2 replacement for hand-typed YAML (Doc 3 Phase 2).

Usage: uv run python scripts/ingest_catalog.py --file catalog.xlsx --business "Rose Abaya House"
"""

import argparse
import asyncio
import sys

from sqlalchemy import select

from reply_agent.db.models import Business
from reply_agent.db.session import get_sessionmaker
from reply_agent.knowledge.loader import sync_knowledge_base
from reply_agent.knowledge.spreadsheet_ingest import WorkbookParseError, parse_catalog_workbook


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, help="Path to the .xlsx catalog workbook")
    parser.add_argument("--business", required=True, help="Exact business name to ingest into")
    args = parser.parse_args()

    try:
        kb, issues = parse_catalog_workbook(args.file, business_slug=args.business)
    except WorkbookParseError as exc:
        print(f"Cannot ingest: {exc}")
        sys.exit(1)

    for issue in issues:
        print(f"WARNING: {issue}")

    async with get_sessionmaker()() as session:
        business = await session.scalar(select(Business).where(Business.name == args.business))
        if business is None:
            print(f"No business found named {args.business!r} — create it first.")
            sys.exit(1)

        doc_count = await sync_knowledge_base(session, business.id, kb)

    print(
        f"Ingested {len(kb.products)} products, {len(kb.policies)} policies, "
        f"{len(kb.faqs)} FAQs ({doc_count} documents embedded) for {args.business!r}."
    )
    if issues:
        print(f"{len(issues)} row(s) skipped — see warnings above.")


if __name__ == "__main__":
    asyncio.run(main())
