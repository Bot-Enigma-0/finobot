import base64
from unittest.mock import MagicMock
from finobot.trading212 import Trading212, DEMO_URL
from finobot.live import plan


def _client(**kw):
    s = MagicMock()
    s.headers = {}
    resp = MagicMock(ok=True, status_code=200, content=b"{}")
    resp.json.return_value = {"id": 1}
    s.request.return_value = resp
    return Trading212(session=s, **kw), s


def test_defaults_to_demo_and_basic_auth():
    c, s = _client(api_key="k", api_secret="sec")
    assert c.base == DEMO_URL
    assert s.headers["Authorization"] == "Basic " + base64.b64encode(b"k:sec").decode()


def test_legacy_key_auth_and_order_body():
    c, s = _client(api_key="k", api_secret="")
    assert s.headers["Authorization"] == "k"
    c.market_order("AAPL_US_EQ", -0.5)
    method, url = s.request.call_args.args
    assert (method, url) == ("POST", DEMO_URL + "/equity/orders/market")
    assert s.request.call_args.kwargs["json"] == {"ticker": "AAPL_US_EQ", "quantity": -0.5}


def test_plan():
    assert plan(1.0, 50, 10, 0, 100) == 5           # buy into full budget
    assert plan(0.0, 50, 10, 5, 0) == -5            # exit
    assert plan(1.0, 50, 10, 4.95, 100) == 0        # below minimum trade value
    assert abs(plan(1.0, 50, 10, 0, 20) - 1.98) < 1e-9  # capped by free cash
