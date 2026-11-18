"""回归测试：min_healthy 阈值按节点池大小自适应。

运行：python tests/test_minhealthy.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import autonode as m

GROUP = {
    "id": "t", "label": "TEST", "group": "G", "min_healthy": 3,
    "regions": ["日本"], "keep_factor": 1.3, "keep_offset_ms": 30,
    "test_url": "https://www.gstatic.com/generate_204", "timeout_ms": 3000,
}


class Engine:
    cfg = {"socket": "", "api_host": "127.0.0.1", "api_port": 1}


def cands(n, ms=100):
    return [{"name": "n%d" % i, "region": "日本", "priority": 0, "ms": ms, "verify_ms": None}
            for i in range(n)]


def run(total, candidates, current="dead", current_ms=None):
    puts = []

    def fake_api(ctx, method, path, payload=None, timeout=90):
        if method == "PUT":
            puts.append(path)
        return {}

    m.api = fake_api
    m.evaluate = lambda ctx, g: (current, current_ms, candidates, None, total)
    res = m.run_group(Engine(), GROUP, dry_run=False)
    return res, puts


def test_small_pool_switches():
    # 只有 3 个节点、2 个可用、当前节点已死 → 必须能切
    res, puts = run(3, cands(2), current_ms=None)
    assert res["action"] == "switch", res
    assert puts, "应当写入新节点"


def test_tiny_pool_switches():
    # 只有 2 个节点、1 个可用 → 也必须能切
    res, _ = run(2, cands(1), current_ms=None)
    assert res["action"] == "switch", res


def test_large_pool_still_guards():
    # 大池子、可用数过低（2 < 3）且当前节点健康 → 仍然跳过，避免网络整体异常时乱切
    res, _ = run(10, cands(2), current="n0", current_ms=100)
    assert res["action"] == "skip", res
    assert "阈值 3" in res["message"], res["message"]


def test_mid_pool_no_false_skip():
    # 4 个节点 → 阈值降为 2，2 个可用时不应跳过
    res, _ = run(4, cands(2, ms=120), current="n0", current_ms=100)
    assert res["action"] != "skip", res


if __name__ == "__main__":
    test_small_pool_switches()
    test_tiny_pool_switches()
    test_large_pool_still_guards()
    test_mid_pool_no_false_skip()
    print("PASS: 小池子可切换 / 大池子仍防抖")
