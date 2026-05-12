from gpu_watcher.attribution import Attributor, ProcessContext
from gpu_watcher.config import IdentityConfig
from gpu_watcher.models import GpuProcess
from gpu_watcher.privacy import REDACTED_IP
from gpu_watcher.tailscale import TailscaleResolver

REMOTE_IP = ".".join(("203", "0", "113", "42"))
REMOTE_IP_2 = ".".join(("203", "0", "113", "43"))


class FakeInspector:
    def __init__(self, context):
        self.context = context

    def inspect(self, pid):
        return self.context


def test_attribution_prefers_tailscale_identity():
    resolver = TailscaleResolver(
        {
            "Peer": {
                "node": {
                    "TailscaleIPs": [REMOTE_IP],
                    "HostName": "alice-mac",
                    "User": "alice@example.com",
                }
            }
        }
    )
    attributor = Attributor(
        IdentityConfig(),
        tailscale=resolver,
        inspector=FakeInspector(ProcessContext("ubuntu", REMOTE_IP)),
    )

    attr = attributor.attribute(GpuProcess(pid=123, gpu_uuid="gpu-1"))

    assert attr.label == "alice@example.com"
    assert attr.source == "tailscale"
    assert attr.linux_user == "ubuntu"
    assert attr.remote_ip == REDACTED_IP


def test_attribution_uses_ip_label_when_tailscale_missing():
    attributor = Attributor(
        IdentityConfig(ip_labels={REMOTE_IP_2: "Bob"}),
        tailscale=TailscaleResolver({"Peer": {}}),
        inspector=FakeInspector(ProcessContext("ubuntu", REMOTE_IP_2)),
    )

    attr = attributor.attribute(GpuProcess(pid=123, gpu_uuid="gpu-1"))

    assert attr.label == "Bob"
    assert attr.source == "ip_label"
    assert attr.remote_ip == REDACTED_IP


def test_attribution_falls_back_to_linux_user_label():
    attributor = Attributor(
        IdentityConfig(user_labels={"ubuntu": "Shared Account"}),
        inspector=FakeInspector(ProcessContext("ubuntu", None)),
    )

    attr = attributor.attribute(GpuProcess(pid=123, gpu_uuid="gpu-1"))

    assert attr.label == "Shared Account"
    assert attr.source == "linux_user"


def test_attribution_preserves_localhost_ip():
    attributor = Attributor(
        IdentityConfig(),
        tailscale=TailscaleResolver({"Peer": {}}),
        inspector=FakeInspector(ProcessContext("local", "127.0.0.1")),
    )

    attr = attributor.attribute(GpuProcess(pid=123, gpu_uuid="gpu-1"))

    assert attr.remote_ip == "127.0.0.1"
