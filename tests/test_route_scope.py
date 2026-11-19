"""回归测试：分流规则按订阅记忆。"""
import os, sys, types
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import autonode as m

def prepare(proxies, uid="NEW"):
    m.current_subscription = lambda: {"uid": uid, "name": "x"}
    m.api = lambda ctx, method, path, payload=None, timeout=90: {"proxies": proxies}
    m.controller_ctx = lambda cfg: {}
    m.save_config = lambda cfg: None
    m.record_op = lambda *a, **k: None
    m.log = lambda *a, **k: None

def engine(routes, binds, buckets, prev="OLD"):
    eng = types.SimpleNamespace()
    eng.cfg = {"groups": [{"id": "main", "label": "g", "group": "G", "role": "general", "enabled": True}],
               "routes": routes, "sub_bindings": binds, "sub_routes": buckets}
    eng.runners = {}
    eng.sub_uid = prev
    eng._sub_sync_at = 0
    eng.bump_epoch = lambda reason: 1
    return eng

def test_switch_uses_subscription_routes():
    prepare({"CyberGuard": {"type": "Selector", "now": "n", "all": ["n"]}})
    old_routes = [{"type": "DOMAIN-SUFFIX", "value": "openai.com", "target": "🧲 AI"}]
    new_routes = [{"type": "DOMAIN-SUFFIX", "value": "openai.com", "target": "CyberGuard"}]
    eng = engine(old_routes, {}, {"NEW": new_routes})
    m.sync_subscription(eng)
    assert eng.cfg["routes"] == new_routes, eng.cfg["routes"]
    # 旧订阅的规则被保存下来
    assert eng.cfg["sub_routes"]["OLD"] == old_routes, eng.cfg["sub_routes"]

def test_invalid_target_retargeted():
    prepare({"CyberGuard": {"type": "Selector", "now": "n", "all": ["n"]}})
    eng = engine([], {}, {"NEW": [{"type": "DOMAIN", "value": "x.com", "target": "走了"}]})
    m.sync_subscription(eng)
    assert eng.cfg["routes"][0]["target"] == "CyberGuard", eng.cfg["routes"]

if __name__ == "__main__":
    test_switch_uses_subscription_routes()
    test_invalid_target_retargeted()
    print("PASS: 规则按订阅恢复 / 失效目标自动迁移")
