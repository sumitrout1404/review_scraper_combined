import json

import httpx
import pytest

from collector.errors import BlockedError, FetchError, ResponseShapeError, TransientFetchError
from collector.fetchers.base import Throttle
from collector.fetchers.http_graphql import HttpGraphQLSource
from collector.properties import PROPERTIES_BY_ID
from collector.raw_capture import RawCapture
from collector.settings import BOOKING_BASE_URL, Settings

PROP = PROPERTIES_BY_ID["potts-point"]


def _source(handler) -> HttpGraphQLSource:
    client = httpx.Client(base_url=BOOKING_BASE_URL, transport=httpx.MockTransport(handler))
    return HttpGraphQLSource(Settings(), Throttle(0), RawCapture(Settings().debug_dir, False), client=client)


def test_happy_path_sends_expected_request(graphql_body):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["cookie"] = request.headers.get("cookie")
        return httpx.Response(200, json=graphql_body)

    page = _source(handler).fetch_page(PROP, 25)
    assert page.found == 25 and page.total_count == 2459
    assert seen["body"]["variables"]["input"]["skip"] == 25
    assert seen["cookie"] is None  # no cookies/session needed or sent


@pytest.mark.parametrize(
    ("response", "exc"),
    [
        (httpx.Response(429, headers={"retry-after": "7"}), TransientFetchError),
        (httpx.Response(503), TransientFetchError),
        (httpx.Response(202, text="<script>window.awsWafCookieDomainList=[]</script>"), BlockedError),
        (httpx.Response(403, text="Forbidden"), BlockedError),
        (httpx.Response(404, text="not found"), FetchError),
        (httpx.Response(200, text="<html>odd</html>"), ResponseShapeError),
    ],
)
def test_error_classification(response, exc):
    with pytest.raises(exc) as info:
        _source(lambda request: response).fetch_page(PROP, 0)
    if response.status_code == 429:
        assert info.value.retry_after == 7.0


def test_timeouts_are_transient():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(TransientFetchError):
        _source(handler).fetch_page(PROP, 0)


def test_throttle_enforces_minimum_gap():
    now = [0.0]
    slept: list[float] = []
    throttle = Throttle(2.0, 0.0, clock=lambda: now[0], sleep=lambda s: (slept.append(s), now.__setitem__(0, now[0] + s)))
    throttle.wait()
    now[0] += 0.5
    throttle.wait()
    assert slept == [1.5]
