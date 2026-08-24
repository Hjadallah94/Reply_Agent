import pytest_asyncio

from reply_agent.db.session import get_engine


@pytest_asyncio.fixture(autouse=True)
async def _dispose_db_engine_after_test():
    """db/session.py's get_engine() is a process-lifetime @lru_cache singleton (correct for
    production — one event loop for the app's whole life). FastAPI's TestClient runs the ASGI
    app through its own internal event loop, separate from pytest-asyncio's, so a connection
    pool created in one test's loop breaks if reused from another. Disposing after every test
    forces a fresh pool (and fresh connections) on next use instead of reusing a stale one.
    """
    yield
    await get_engine().dispose()
