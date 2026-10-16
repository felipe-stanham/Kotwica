"""cap-007 TLS watch."""
import shutil
import socket
import ssl
import subprocess
import threading
import time

import pytest

from kotwica import health, tls_watch
from kotwica.tls_watch import check_tls
from tests.fixtures import NOW, healthy_state, host, make_config


def cert_expiring_in(days, now=NOW):
    return {
        "notAfter": time.strftime("%b %d %H:%M:%S %Y GMT", time.gmtime(now + days * 86400)),
        "issuer": ((("organizationName", "Let's Encrypt"),), (("commonName", "E6"),)),
    }


def watched(result, port=443):
    """A State whose single host carries this CertResult, evaluated through the Health Rules."""
    state = healthy_state([host(1, port, days=result.days_left, cert=result.status, error=result.error)])
    return health.evaluate(state, make_config(), NOW)


def test_tls_valid():
    result = check_tls("home.stanham.com", 443, "127.0.0.1", NOW, lambda *a: cert_expiring_in(40))
    assert (result.status, result.days_left, result.issuer) == ("valid", 40, "E6")
    assert watched(result)["health"] == "good"


def test_tls_expiring_warning_and_error():
    ten = check_tls("home.stanham.com", 443, None, NOW, lambda *a: cert_expiring_in(10))
    assert (watched(ten)["health"], watched(ten)["message"]) == ("warning", "home.stanham.com:443 cert expires in 10 days")
    two = check_tls("home.stanham.com", 443, None, NOW, lambda *a: cert_expiring_in(2))
    assert (watched(two)["health"], watched(two)["message"]) == ("error", "home.stanham.com:443 cert expires in 2 days")


def test_tls_invalid_on_verify_error():
    def connect(*a):
        raise ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate has expired")

    result = check_tls("home.stanham.com", 443, None, NOW, connect)
    assert result.status == "invalid" and "expired" in result.error
    assert watched(result)["health"] == "error"


def test_tls_alert_without_certificate_is_invalid_not_a_crash():
    def connect(*a):
        raise ssl.SSLError(1, "[SSL: TLSV1_ALERT_INTERNAL_ERROR] tlsv1 alert internal error")

    assert check_tls("h", 443, None, NOW, connect).status == "invalid"


def test_tls_unreachable_on_refused_reset_and_timeout():
    for exc in (ConnectionRefusedError(61, "Connection refused"), ConnectionResetError(54, "reset"), socket.timeout("timed out")):
        def connect(*a, exc=exc):
            raise exc

        result = check_tls("h", 443, None, NOW, connect)
        assert result.status == "unreachable" and result.error
    assert watched(check_tls("h", 443, None, NOW, connect))["health"] == "error"


def test_tls_sni_and_target():
    seen = {}

    def connect(connect_host, port, server_hostname):
        seen.update(host=connect_host, port=port, sni=server_hostname)
        return cert_expiring_in(40)

    check_tls("home.stanham.com", 8443, "127.0.0.1", NOW, connect)
    assert seen == {"host": "127.0.0.1", "port": 8443, "sni": "home.stanham.com"}
    check_tls("home.stanham.com", 443, None, NOW, connect)
    assert seen["host"] == "home.stanham.com"


@pytest.fixture
def self_signed_server(tmp_path):
    """A real local TLS server with a self-signed cert; records the SNI the client sent."""
    if shutil.which("openssl") is None:
        pytest.skip("openssl binary not available")
    key, crt = tmp_path / "k.pem", tmp_path / "c.pem"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(crt),
         "-subj", "/CN=home.stanham.com", "-days", "5", "-addext", "subjectAltName=DNS:home.stanham.com"],
        check=True, capture_output=True,
    )
    seen = []
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(crt), str(key))
    context.sni_callback = lambda sock, name, ctx: seen.append(name)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(5)
    listener.settimeout(5)

    def serve():
        try:
            while True:
                conn, _ = listener.accept()
                try:
                    context.wrap_socket(conn, server_side=True).close()
                except (ssl.SSLError, OSError):
                    pass
        except OSError:
            pass

    threading.Thread(target=serve, daemon=True).start()
    yield listener.getsockname()[1], seen
    listener.close()


def test_real_handshake_sends_sni_and_connects_to_target(self_signed_server):
    port, seen = self_signed_server
    result = check_tls("home.stanham.com", port, "127.0.0.1", time.time())
    assert result.status == "invalid" and "self-signed" in result.error  # untrusted CA, so verification fails
    assert seen == ["home.stanham.com"]


def test_real_connection_refused_is_unreachable():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    assert check_tls("home.stanham.com", port, "127.0.0.1", time.time()).status == "unreachable"


def test_real_server_that_resets_without_handshake_classifies_cleanly():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)

    def reset():
        conn, _ = listener.accept()
        conn.close()

    threading.Thread(target=reset, daemon=True).start()
    result = check_tls("home.stanham.com", listener.getsockname()[1], "127.0.0.1", time.time())
    listener.close()
    assert result.status in ("invalid", "unreachable") and result.error


@pytest.mark.integration
def test_int_tls_real_valid():
    result = check_tls("sha256.badssl.com", 443, None, time.time())
    assert result.status == "valid" and result.days_left > 0, result


@pytest.mark.integration
def test_int_tls_real_expired():
    result = check_tls("expired.badssl.com", 443, None, time.time())
    assert result.status == "invalid" and "expired" in result.error, result
