from gpu_watcher.privacy import REDACTED_IP, redact_ip


def test_redact_ip_keeps_localhost():
    assert redact_ip("127.0.0.1") == "127.0.0.1"
    assert redact_ip("::1") == "::1"


def test_redact_ip_hides_remote_addresses():
    remote_ip = ".".join(("203", "0", "113", "99"))
    assert redact_ip(remote_ip) == REDACTED_IP
