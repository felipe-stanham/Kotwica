"""cap-004 Public IP detection."""
import asyncio

import httpx

from kotwica.public_ip import detect_public_ip
from tests.fakes import FakeWorld

URLS = ["https://api.ipify.org", "https://icanhazip.com"]


def detect(world):
    async def run():
        async with world.factory()() as client:
            return await detect_public_ip(client, URLS)

    return asyncio.run(run())


def test_ip_agree():
    assert detect(FakeWorld("203.0.113.7", "203.0.113.7\n")).ip == "203.0.113.7"


def test_ip_disagree():
    result = detect(FakeWorld("203.0.113.7", "198.51.100.2"))
    assert result.ip is None and "disagree" in result.reason


def test_ip_one_fails():
    result = detect(FakeWorld(httpx.ReadTimeout("slow"), "203.0.113.7"))
    assert result.ip is None and result.reason


def test_ip_not_ipv4():
    result = detect(FakeWorld("<html>error</html>", "<html>error</html>"))
    assert result.ip is None and "invalid" in result.reason


def test_ipv6_answer_is_not_accepted():
    assert detect(FakeWorld("2001:db8::1", "2001:db8::1")).ip is None
