"""回归测试：首次运行自动发现分组（不依赖本机分组命名）。"""
import os, sys, types
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import autonode as m

def fake_engine():
    eng = types.SimpleNamespace()
    eng.cfg = {"groups": []}
    eng.runners = {}
    return eng

def prepare(proxies):
    m.api = lambda ctx, method, path, payload=None, timeout=90: {"proxies": proxies}
    m.controller_ctx = lambda cfg: {}
    m.save_config = lambda cfg: None
    m.record_op = lambda *a, **k: None
    m.log = lambda *a, **k: None
    m.current_subscription = lambda: {"uid": "U1", "name": "s"}
    def bootstrap(engine):
        names = []
        for name, info in proxies.items():
            if info.get("type") != "Selector" or name.upper() == "GLOBAL":
                continue
            if (info.get("now") or "").upper() in ("DIRECT", "REJECT"):
                continue
            names.append(name)
        return [m._normalize_group({"id": "g%d" % (i+1), "label": n, "group": n}) for i, n in enumerate(names[:6])]
    eng = fake_engine()
    eng.bump_epoch = lambda reason: 1
    eng._bootstrap_groups = lambda: bootstrap(eng)
    return eng

def test_first_run_discovers():
    eng = prepare({
        "GLOBAL": {"type": "Selector", "now": "DIRECT"},
        "CyberGuard": {"type": "Selector", "now": "n1"},
        "故障转移": {"type": "Fallback", "now": "n1"},
        "自动选择": {"type": "URLTest", "now": "n1"},
        "直连组": {"type": "Selector", "now": "DIRECT"},
    })
    m.sync_subscription(eng)
    # 只纳管 Selector（URLTest/Fallback 由内核自己选，纳管会互相抢）
    assert len(eng.cfg["groups"]) == 1, eng.cfg["groups"]
    names = [g["group"] for g in eng.cfg["groups"]]
    assert names == ["CyberGuard"], names

if __name__ == "__main__":
    test_first_run_discovers()
    print("PASS: 首次运行按控制器实际分组自动纳管")
