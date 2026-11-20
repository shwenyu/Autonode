"""回归测试：钉住节点在地区不匹配、测速失败时仍然优先。"""
import os, sys, types
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import autonode as m

GROUP = {"id": "ai", "label": "AI", "group": "G", "regions": ["日本"],
         "test_url": "https://x", "timeout_ms": 1000, "max_workers": 2,
         "pinned_node": "lite-香港-03", "exclude_keywords": []}

def prepare(probe_ok=False):
    m.api = lambda ctx, method, path, payload=None, timeout=90: {
        "all": ["lite-香港-03", "日本01"], "now": "日本01"}
    m.controller_ctx = lambda cfg: {}
    m.probe_delay = lambda ctx, node, url, timeout: (120 if probe_ok else None)
    m.region_priority = lambda name, regions: ((0, "日本") if name == "日本01" else None)

def test_pinned_kept_even_if_probe_fails():
    prepare(probe_ok=False)
    cur, cur_ms, cands, flag, total, stats = m.evaluate({}, GROUP)
    assert [c["name"] for c in cands] == ["lite-香港-03"], cands
    assert cands[0]["ms"] == 9999

def test_pinned_found_when_probe_ok():
    prepare(probe_ok=True)
    cur, cur_ms, cands, flag, total, stats = m.evaluate({}, GROUP)
    assert cands[0]["name"] == "lite-香港-03", cands

if __name__ == "__main__":
    test_pinned_kept_even_if_probe_fails()
    test_pinned_found_when_probe_ok()
    print("PASS: 钉住节点优先（测速失败也保留）")
