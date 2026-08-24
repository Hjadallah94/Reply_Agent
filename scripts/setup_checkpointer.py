"""One-time setup: creates the LangGraph Postgres checkpointer's own tables (checkpoints,
checkpoint_blobs, etc. — separate from the Alembic-managed application schema). Re-running
is safe/idempotent.

Usage: uv run python scripts/setup_checkpointer.py
"""

import asyncio
import sys

from reply_agent.memory.checkpointer import setup_checkpointer_tables

if sys.platform == "win32":
    # psycopg's async driver doesn't support Windows' default ProactorEventLoop.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def main() -> None:
    await setup_checkpointer_tables()
    print("Checkpointer tables ready.")


if __name__ == "__main__":
    asyncio.run(main())
