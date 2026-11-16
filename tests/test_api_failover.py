from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from backend.google_analysis_provider import RotatingSerpApiProvider, SerpApiQuotaExceeded
from backend.main import search_places_with_failover
from backend.places import PlacesQuotaExceeded, PlacesSearchReport


class FakeKeyRepository:
    def __init__(self):
        self.keys = [("key-one", "one"), ("key-two", "two")]
        self.index = 0
        self.failures = []
        self.usage = []

    def active(self):
        return self.keys[self.index]

    def failover(self, key_id, detail="", invalid=False):
        self.failures.append((key_id, invalid))
        if self.index + 1 >= len(self.keys):
            return False
        self.index += 1
        return True

    def record_usage(self, key_id):
        self.usage.append(key_id)


def test_places_retries_same_search_with_next_key_after_quota():
    keys = FakeKeyRepository()
    expected = PlacesSearchReport(scanned=3, pages=1)
    search = AsyncMock(side_effect=[PlacesQuotaExceeded("limite"), expected])
    with patch("backend.main.api_keys", return_value=keys), patch("backend.main.search_eligible_profiles", search):
        result = asyncio.run(search_places_with_failover("gás em Vicente Pires", 50))
    assert result is expected
    assert keys.failures == [("one", False)]
    assert search.await_args_list[0].args[0] == "key-one"
    assert search.await_args_list[1].args[0] == "key-two"


def test_serpapi_retries_request_with_next_key_after_quota():
    keys = FakeKeyRepository()
    provider = RotatingSerpApiProvider(keys, timeout=10)
    provider._request = AsyncMock(side_effect=[SerpApiQuotaExceeded("limite"), {"local_results": []}])
    result = asyncio.run(provider._get({"engine": "google_maps", "q": "gás"}))
    assert result == {"local_results": []}
    assert keys.failures == [("one", False)]
    assert keys.usage == ["two"]
    assert provider._request.await_args_list[0].args[1] == "key-one"
    assert provider._request.await_args_list[1].args[1] == "key-two"
