"""A transient broker failure at boot must not leave the gateway stopped."""
import asyncio

from src.services.startup_retry import connect_with_retry


class Engine:
    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def start(self):
        self.calls += 1
        return self.results.pop(0)


class Gateway:
    def __init__(self):
        self.is_running = False
        self.starts = 0

    def start(self):
        self.starts += 1
        self.is_running = True


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_gateway_starts_after_a_later_successful_connection():
    engine, gateway = Engine([False, False, True]), Gateway()
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    assert _run(connect_with_retry(engine, gateway, attempts=5, delay=2, sleep=fake_sleep)) is True
    assert engine.calls == 3
    assert gateway.starts == 1 and gateway.is_running
    assert sleeps == [2, 2], "it must wait between failures, not hammer the broker"


def test_an_exception_on_one_attempt_does_not_abort_the_retry():
    engine, gateway = Engine([True]), Gateway()

    def boom():
        raise RuntimeError("connector down")

    engine.start = boom
    engine.calls = 0
    calls = {"n": 0}

    def start():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("connector down")
        return True

    engine.start = start
    assert _run(connect_with_retry(engine, gateway, attempts=3, delay=0, sleep=_noop)) is True
    assert calls["n"] == 2 and gateway.is_running


async def _noop(_seconds):
    return None


def test_exhausting_attempts_reports_failure_and_leaves_the_gateway_alone():
    engine, gateway = Engine([False, False]), Gateway()
    assert _run(connect_with_retry(engine, gateway, attempts=2, delay=0, sleep=_noop)) is False
    assert engine.calls == 2
    assert gateway.starts == 0


def test_an_already_running_gateway_is_not_started_twice():
    engine, gateway = Engine([True]), Gateway()
    gateway.is_running = True
    assert _run(connect_with_retry(engine, gateway, attempts=2, delay=0, sleep=_noop)) is True
    assert gateway.starts == 0
