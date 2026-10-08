"""httpx.MockTransport fakes for the echo services and the GoDaddy API."""
import json

import httpx

DOMAIN = "stanham.com"


class FakeWorld:
    """Routes requests by host. Every request is recorded in `requests`."""

    def __init__(self, echo_a="203.0.113.7", echo_b="203.0.113.7\n", record=None, get_status=200, put_status=200):
        self.echo = {"api.ipify.org": echo_a, "icanhazip.com": echo_b}
        self.record = record  # list of {"data","ttl"} or None for an empty GET result
        self.get_status, self.put_status = get_status, put_status
        self.requests = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host in self.echo:
            answer = self.echo[request.url.host]
            if isinstance(answer, Exception):
                raise answer
            return httpx.Response(200, text=answer)
        assert request.url.host == "api.godaddy.com", request.url
        if request.method == "GET":
            if self.get_status != 200:
                return httpx.Response(self.get_status, json={"code": "FAKE", "message": "secret-ish body"})
            return httpx.Response(200, json=self.record if self.record is not None else [])
        if request.method == "PUT":
            if self.put_status == 200:
                self.record = json.loads(request.content)
            return httpx.Response(self.put_status, json={})
        raise AssertionError("unexpected method %s" % request.method)

    def factory(self):
        return lambda: httpx.AsyncClient(transport=httpx.MockTransport(self))

    @property
    def godaddy(self):
        return [r for r in self.requests if r.url.host == "api.godaddy.com"]
