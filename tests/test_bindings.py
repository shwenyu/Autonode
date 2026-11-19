"""回归测试：订阅切换后的绑定记忆与自动恢复。

运行：python tests/test_bindings.py
"""

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import autonode as m


def fake_engine(groups, uid, binds):
    eng = types.SimpleNamespace()
    eng.cfg = {"groups": groups, "sub_bindings": binds}
    eng.runners = {}
    eng.sub_uid = uid
    eng._sub_sync_at = 0
    eng.bump_epoch = lambda reason: 1
    return eng


def prepare(proxies, uid="NEW"):
    m.current_subscription = lambda: {"uid": uid, "name": "x"}
    m.api = lambda ctx, method, path, payload=None, timeout=90: {"proxies": proxies}
    m.controller_ctx = lambda cfg: {}
    m.save_config = lambda cfg: None
    m.record_op = lambda *a, **k: None
    m.log = lambda *a, **k: None


def test_restores_remembered_binding():
    prepare({
        "CyberGuard": {"type": "Selector", "now": "n1", "all": ["n1"]},
        "GLOBAL": {"type": "Selector", "all": []},
    })
    groups = [{"id": "main", "label": "手动选择节点", "group": "♻️ old", "role": "general"}]
    eng = fake_engine(groups, "OLD", {"NEW": {"main": "CyberGuard"}})
    m.sync_subscription(eng)
    assert groups[0]["group"] == "CyberGuard", groups[0]
    assert eng.sub_uid == "NEW"


def test_auto_match_when_no_memory():
    prepare({
        "🧲 AI": {"type": "Selector", "now": "n1", "all": ["n1"]},
        "🔀 手动选择": {"type": "Selector", "all": ["n1"]},
        "GLOBAL": {"type": "Selector", "all": []},
    })
    groups = [
        {"id": "main", "label": "g", "group": "x", "role": "general"},
        {"id": "ai", "label": "ai", "group": "y", "role": "ai"},
    ]
    eng = fake_engine(groups, "OLD", {})
    m.sync_subscription(eng)
    by_id = {g["id"]: g["group"] for g in groups}
    assert by_id["ai"] == "🧲 AI", by_id
    assert by_id["main"] == "🔀 手动选择", by_id


def test_missing_target_falls_back():
    prepare({}, uid="NEW")
    groups = [{"id": "main", "label": "g", "group": "old-name", "role": "general"}]
    eng = fake_engine(groups, "OLD", {"NEW": {"main": "gone"}})
    m.sync_subscription(eng)
    # 没有可用分组时不崩，也不乱改
    assert groups[0]["group"] == "old-name"


if __name__ == "__main__":
    test_restores_remembered_binding()
    test_auto_match_when_no_memory()
    test_missing_target_falls_back()
    print("PASS: 订阅记忆恢复 / 无记忆自动匹配 / 目标缺失安全降级")
