"""回归测试：分流目标排序（分组在前、DIRECT/REJECT 在后、排除 GLOBAL）。

运行：python tests/test_targets.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import autonode as m


def test_order():
    proxies = {
        "DIRECT": {"type": "Direct"},
        "GLOBAL": {"type": "Selector"},
        "REJECT": {"type": "Reject"},
        "♻️ 手动选择节点": {"type": "Selector"},
        "🧲 AI": {"type": "Selector"},
        "♻️ 自动选择": {"type": "URLTest"},
    }
    m.api = lambda ctx, method, path, payload=None, timeout=90: {"proxies": proxies}
    targets = m.list_targets({"host": "127.0.0.1", "port": 1})
    assert targets[:3] == ["♻️ 手动选择节点", "🧲 AI", "♻️ 自动选择"], targets
    assert targets[-2:] == ["DIRECT", "REJECT"], targets
    assert "GLOBAL" not in targets


if __name__ == "__main__":
    test_order()
    print("PASS: 分组优先、DIRECT/REJECT 次之、GLOBAL 排除")
