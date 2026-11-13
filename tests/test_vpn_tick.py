"""回归测试：系统 VPN 保持连接逻辑。

运行：python tests/test_vpn_tick.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import autonode as m


class FakeEngine:
    cfg = {"vpn_keep": ["Aida", "Home"], "vpn_interval": 60}


def test_tick():
    calls = []
    m.list_system_vpns = lambda: [
        {"name": "Aida", "status": "Disconnected", "proto": "PPP:L2TP"},
        {"name": "Home", "status": "Connected", "proto": "IKEv2"},
    ]
    m.vpn_action = lambda name, action: (calls.append((name, action)), {"ok": True})[1]

    cooldown = {}
    first = m.vpn_tick(FakeEngine(), cooldown)
    assert first == ["Aida"], first
    assert calls == [("Aida", "connect")], calls

    # 冷却期内不应重复重连
    second = m.vpn_tick(FakeEngine(), cooldown)
    assert second == [], second
    assert calls == [("Aida", "connect")], calls


def test_no_keep_list():
    calls = []
    m.list_system_vpns = lambda: [{"name": "Aida", "status": "Disconnected", "proto": "PPP:L2TP"}]
    m.vpn_action = lambda name, action: (calls.append(name), {"ok": True})[1]

    class Empty:
        cfg = {"vpn_keep": []}

    assert m.vpn_tick(Empty(), {}) == []
    assert calls == [], "没有勾选「保持」时不应连接"


if __name__ == "__main__":
    test_tick()
    test_no_keep_list()
    print("PASS: 断线重连 / 已连接不动 / 冷却 / 未勾选不动作")
