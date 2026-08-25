from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reply_agent.onboarding.meta_oauth import EmbeddedSignupError
from reply_agent.onboarding.page_signup import (
    MultiplePagesError,
    NoPageSelectedError,
    get_linked_instagram_account_id,
    get_single_page_id,
    list_granted_pages,
    subscribe_page_to_app,
)


def _response(status_code=200, json_body=None, text=""):
    response = MagicMock()
    response.status_code = status_code
    response.json = MagicMock(return_value=json_body or {})
    response.text = text
    return response


def _mock_async_client(response):
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.post = AsyncMock(return_value=response)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=False)
    return context


async def test_list_granted_pages_returns_data():
    response = _response(200, {"data": [{"id": "page-1", "name": "Rose Abaya House"}]})
    with patch("httpx.AsyncClient", return_value=_mock_async_client(response)):
        pages = await list_granted_pages("token-123")
    assert pages == [{"id": "page-1", "name": "Rose Abaya House"}]


async def test_list_granted_pages_raises_on_error():
    response = _response(400, text="bad token")
    with (
        patch("httpx.AsyncClient", return_value=_mock_async_client(response)),
        pytest.raises(EmbeddedSignupError),
    ):
        await list_granted_pages("bad-token")


async def test_get_single_page_id_returns_the_one_page():
    response = _response(200, {"data": [{"id": "page-1", "name": "Rose Abaya House"}]})
    with patch("httpx.AsyncClient", return_value=_mock_async_client(response)):
        page_id = await get_single_page_id("token-123")
    assert page_id == "page-1"


async def test_get_single_page_id_raises_when_no_pages():
    response = _response(200, {"data": []})
    with (
        patch("httpx.AsyncClient", return_value=_mock_async_client(response)),
        pytest.raises(NoPageSelectedError),
    ):
        await get_single_page_id("token-123")


async def test_get_single_page_id_raises_when_multiple_pages():
    response = _response(
        200, {"data": [{"id": "page-1", "name": "A"}, {"id": "page-2", "name": "B"}]}
    )
    with (
        patch("httpx.AsyncClient", return_value=_mock_async_client(response)),
        pytest.raises(MultiplePagesError),
    ):
        await get_single_page_id("token-123")


async def test_get_linked_instagram_account_id_returns_id_when_present():
    response = _response(200, {"instagram_business_account": {"id": "ig-1"}})
    with patch("httpx.AsyncClient", return_value=_mock_async_client(response)):
        account_id = await get_linked_instagram_account_id("page-1", "token-123")
    assert account_id == "ig-1"


async def test_get_linked_instagram_account_id_returns_none_when_absent():
    response = _response(200, {})
    with patch("httpx.AsyncClient", return_value=_mock_async_client(response)):
        account_id = await get_linked_instagram_account_id("page-1", "token-123")
    assert account_id is None


async def test_subscribe_page_to_app_succeeds():
    response = _response(200, {"success": True})
    with patch("httpx.AsyncClient", return_value=_mock_async_client(response)):
        await subscribe_page_to_app("page-1", "token-123")


async def test_subscribe_page_to_app_raises_on_error():
    response = _response(403, text="forbidden")
    with (
        patch("httpx.AsyncClient", return_value=_mock_async_client(response)),
        pytest.raises(EmbeddedSignupError),
    ):
        await subscribe_page_to_app("page-1", "token-123")
