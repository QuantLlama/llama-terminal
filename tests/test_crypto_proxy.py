"""Tests for crypto egress proxy configuration."""

import pytest

from src.services.crypto_proxy import apply_proxy, http_proxy_url


class _Exchange:
    def __init__(self):
        self.proxies = None


def test_no_proxy_by_default(monkeypatch):
    monkeypatch.delenv("CRYPTO_HTTP_PROXY", raising=False)
    exchange = _Exchange()

    assert http_proxy_url() is None
    assert apply_proxy(exchange) is exchange
    assert exchange.proxies is None


def test_proxy_is_applied_to_the_exchange(monkeypatch):
    monkeypatch.setenv("CRYPTO_HTTP_PROXY", "http://10.0.0.1:3128")
    exchange = _Exchange()

    apply_proxy(exchange)

    assert exchange.proxies == {"http": "http://10.0.0.1:3128", "https": "http://10.0.0.1:3128"}


def test_blank_proxy_is_treated_as_unset(monkeypatch):
    monkeypatch.setenv("CRYPTO_HTTP_PROXY", "   ")
    exchange = _Exchange()

    apply_proxy(exchange)

    assert exchange.proxies is None


def test_failure_to_apply_does_not_break_trading(monkeypatch):
    monkeypatch.setenv("CRYPTO_HTTP_PROXY", "http://10.0.0.1:3128")

    class _Broken:
        @property
        def proxies(self):
            return None

        @proxies.setter
        def proxies(self, value):
            raise RuntimeError("ccxt rejected it")

    apply_proxy(_Broken())  # must not raise
