"""Syncs a seller's order-tracking sheet for an existing business (Doc 2 Section 2.6) — a
full replace per sync, meant to be re-run whenever the seller's order sheet changes (much more
often than the catalog).

Usage: uv run python scripts/sync_orders.py --file orders.xlsx --business "Rose Abaya House"
"""

import argparse
import asyncio
import sys

from sqlalchemy import select

from reply_agent.db.models import Business
from reply_agent.db.session import get_sessionmaker
from reply_agent.orders.spreadsheet_ingest import OrderWorkbookParseError, parse_orders_workbook
from reply_agent.orders.sync import sync_orders


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, help="Path to the .xlsx orders workbook")
    parser.add_argument("--business", required=True, help="Exact business name to sync into")
    args = parser.parse_args()

    try:
        records, issues = parse_orders_workbook(args.file)
    except OrderWorkbookParseError as exc:
        print(f"Cannot sync: {exc}")
        sys.exit(1)

    for issue in issues:
        print(f"WARNING: {issue}")

    async with get_sessionmaker()() as session:
        business = await session.scalar(select(Business).where(Business.name == args.business))
        if business is None:
            print(f"No business found named {args.business!r} — create it first.")
            sys.exit(1)

        count = await sync_orders(session, business.id, records)
        await session.commit()

    print(f"Synced {count} orders for {args.business!r}.")
    if issues:
        print(f"{len(issues)} row(s) skipped — see warnings above.")


if __name__ == "__main__":
    asyncio.run(main())
