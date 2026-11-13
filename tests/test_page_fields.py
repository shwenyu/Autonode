"""回归测试：设置面板字段完整性。

防止模板漂移导致 fillGroupForm 抛异常、默认值全部不显示。

运行：python tests/test_page_fields.py
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import autonode as m

REQUIRED = {
    "interval_seconds",
    "test_url",
    "verify_url",
    "keep_factor",
    "keep_offset_ms",
    "min_healthy",
    "verify_top",
    "manual_hold_seconds",
    "role",
    "verify_provider",
}


def test_fields_present():
    fields = set(re.findall(r'data-field="([a-z_]+)"', m.PAGE))
    missing = REQUIRED - fields
    assert not missing, "设置面板缺少字段: %s" % ", ".join(sorted(missing))


def test_no_unguarded_lookup():
    """fillGroupForm 里每个字段查找都应有空值保护（field()/if 判断）。"""
    body = m.PAGE.split("function fillGroupForm", 1)[1].split("function renderGroups", 1)[0]
    raw = re.findall(r"card\.querySelector\('\[data-field=\"[a-z_]+\"\]'\)\.value", body)
    assert not raw, "fillGroupForm 中仍有未保护的 querySelector 直接取值: %s" % raw


if __name__ == "__main__":
    test_fields_present()
    test_no_unguarded_lookup()
    print("PASS: 设置字段齐全、查找均有保护")
