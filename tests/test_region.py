"""回归测试：地区识别链。

运行：python tests/test_region.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import autonode as m

CASES = {
    "lite-香港-01": "香港",
    "lite-美国01": "美国",
    "US-LosAngeles-01": "美国",
    "HK-01": "香港",
    "JP-Tokyo-02": "日本",
    "Singapore-Premium": "新加坡",
    "de-frankfurt-1": "德国",
    "英国-伦敦": "英国",
    "pro-乌克兰-2x": "乌克兰",
    "pro-哈萨克斯坦-2x": "哈萨克斯坦",
    "pro-家庭宽带-墨西哥UNINET-5x": "墨西哥",
    "pro-老挝-2x": "老挝",
    "节点A": None,
    "line-01": None,
}


def test_detection():
    for name, want in CASES.items():
        got = m.detect_region(name)
        assert got == want, "%s -> %r，期望 %r" % (name, got, want)


def test_override_wins():
    m.refresh_region_state({"region_overrides": {"line-01": "日本"}}, {})
    assert m.detect_region("line-01") == "日本"
    m.refresh_region_state({"region_overrides": {}}, {})
    assert m.detect_region("line-01") is None


def test_server_fallback():
    m.refresh_region_state({"region_overrides": {}}, {"神秘节点X": "hk01.example.com"})
    assert m.detect_region("神秘节点X") == "香港"
    m.refresh_region_state({"region_overrides": {}}, {})


def test_unknown_chip():
    assert m.region_priority("节点A", ["日本", "未知"]) == (2, "未知")
    assert m.region_priority("节点A", ["日本"]) is None


if __name__ == "__main__":
    test_detection()
    test_override_wins()
    test_server_fallback()
    test_unknown_chip()
    print("PASS: 别名 / 覆盖优先 / 服务器兜底 / 未知分组")
