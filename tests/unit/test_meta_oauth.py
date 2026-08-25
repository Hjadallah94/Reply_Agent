from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reply_agent.onboarding.meta_oauth import EmbeddedSignupError, exchange_code_for_token


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


async def test_exchange_code_for_token_returns_access_token():
    response = _response(200, {"access_token": "token-123"})
    with patch("httpx.AsyncClient", return_value=_mock_async_client(response)):
        token = await exchange_code_for_token("some-code")
    assert token == "token-123"


async def test_exchange_code_for_token_raises_on_error():
    response = _response(400, text="bad code")
    with (
        patch("httpx.AsyncClient", return_value=_mock_async_client(response)),
        pytest.raises(EmbeddedSignupError),
    ):
        await exchange_code_for_token("bad-code")
