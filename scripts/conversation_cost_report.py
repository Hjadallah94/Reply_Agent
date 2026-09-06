"""Doc 5 margin-verification roadmap — prints exactly what one conversation's messages cost in
third-party API calls (billing/cost_tracking.py's ApiCallLog rows), to check against Doc 5's
per-message cost assumptions. Not tenant-scoped (a plain read, no business_id known up front —
same reasoning as seed_business.py's own plain get_sessionmaker() use): this is an operator
tool, not something a business owner runs themselves.

Usage: uv run python scripts/conversation_cost_report.py "whatsapp:<business_id>:962790001234"
"""

import argparse
import asyncio
from collections import defaultdict

from sqlalchemy import select

from reply_agent.db.models import ApiCallLog
from reply_agent.db.session import get_sessionmaker


async def report(thread_id: str) -> None:
    async with get_sessionmaker()() as session:
        rows = (
            await session.scalars(
                select(ApiCallLog)
                .where(ApiCallLog.thread_id == thread_id)
                .order_by(ApiCallLog.created_at)
            )
        ).all()

    if not rows:
        print(f"No ApiCallLog rows found for thread_id={thread_id!r}.")
        return

    print(f"Cost report for {thread_id}\n{'=' * 60}")
    totals_by_provider: dict[str, float] = defaultdict(float)
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = 0.0

    for row in rows:
        token_bits = ""
        if row.input_tokens is not None or row.output_tokens is not None:
            token_bits = f"  in={row.input_tokens or 0} out={row.output_tokens or 0}"
        elif row.units is not None:
            token_bits = f"  units={row.units}"
        print(
            f"[{row.created_at.isoformat()}] {row.node_name:<40} {row.provider.value:<12} "
            f"{row.model:<28}{token_bits}  ${row.cost_usd:.6f}"
        )
        totals_by_provider[row.provider.value] += float(row.cost_usd)
        total_input_tokens += row.input_tokens or 0
        total_output_tokens += row.output_tokens or 0
        total_cost += float(row.cost_usd)

    print("-" * 60)
    for provider, cost in totals_by_provider.items():
        print(f"  {provider:<12} subtotal: ${cost:.6f}")
    print(f"\nTotal tokens: {total_input_tokens} in / {total_output_tokens} out")
    print(f"Total cost:   ${total_cost:.6f}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("thread_id")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(report(_parse_args().thread_id))
