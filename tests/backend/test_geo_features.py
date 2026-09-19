"""pg_featureserv behind the JWT: role-gated and scoped to the jurisdiction.

pg_featureserv is not running in the test environment, so its HTTP answer is
faked -- with parcels from BOTH states, so the test also proves that the
response is filtered here even when the upstream filter is ignored.
"""

from __future__ import annotations

import httpx
import pytest
from demo_users import CENTRAL_OFFICER, CITIZEN_A, DEO, STATE_OFFICER, TEHSILDAR

pytestmark = pytest.mark.integration

URL = "/api/v1/geo/features/gis_published_parcels"


def feature(village):
    return {"type": "Feature", "id": village, "properties": {"village_id": village}}


@pytest.fixture
def upstream(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append((url, params))
        if "/items/" in url:
            village = url.rsplit("/", 1)[-1].removesuffix(".json")
            return httpx.Response(200, json=feature(village), request=httpx.Request("GET", url))
        return httpx.Response(200, request=httpx.Request("GET", url), json={
            "type": "FeatureCollection",
            "features": [feature("LOC-VIL-01"), feature("LOC-VIL-02"),
                         feature("LOC-VIL-BR-01")],
        })

    monkeypatch.setattr(httpx, "get", fake_get)
    return calls


@pytest.mark.parametrize("email", [CITIZEN_A, DEO])
def test_citizens_and_deos_are_refused(client, auth, upstream, email):
    assert client.get(URL, headers=auth(email)).status_code == 403
    assert upstream == []


def villages(client, auth, email):
    response = client.get(URL, headers=auth(email))
    assert response.status_code == 200, response.text
    return {f["properties"]["village_id"] for f in response.json()["features"]}


def test_the_tehsildar_sees_only_their_jurisdiction(client, auth, upstream):
    assert villages(client, auth, TEHSILDAR) == {"LOC-VIL-01", "LOC-VIL-02"}
    sent = upstream[0][1]["filter"]
    assert "LOC-VIL-01" in sent and "LOC-VIL-BR-01" not in sent


def test_a_state_officer_sees_their_state_only(client, auth, upstream):
    assert villages(client, auth, STATE_OFFICER) == {"LOC-VIL-01", "LOC-VIL-02"}


def test_central_oversight_sees_every_state(client, auth, upstream):
    assert "LOC-VIL-BR-01" in villages(client, auth, CENTRAL_OFFICER)


def test_an_out_of_scope_item_is_not_found(client, auth, upstream):
    assert client.get(f"{URL}/LOC-VIL-BR-01", headers=auth(TEHSILDAR)).status_code == 404
    assert client.get(f"{URL}/LOC-VIL-01", headers=auth(TEHSILDAR)).status_code == 200


def test_only_the_published_view_is_proxied(client, auth, upstream):
    response = client.get("/api/v1/geo/features/owners", headers=auth(TEHSILDAR))
    assert response.status_code == 404
    assert upstream == []


def test_an_unreachable_featureserv_is_a_503(client, auth, monkeypatch):
    def down(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", down)
    assert client.get(URL, headers=auth(TEHSILDAR)).status_code == 503
