"""回归测试：版本号比较（检查更新的基础）。

运行：python tests/test_update.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import autonode as m


def test_parse():
    assert m._ver_tuple("v1.5.4") == (1, 5, 4)
    assert m._ver_tuple("1.5") == (1, 5)
    assert m._ver_tuple("") == ()


def test_order():
    assert m._ver_tuple("1.10.0") > m._ver_tuple("1.9.9")
    assert m._ver_tuple("2.0.0") > m._ver_tuple("1.99.99")
    assert m._ver_tuple("v1.5.4") == m._ver_tuple("1.5.4")


def test_has_update_logic():
    def has(cur, latest):
        return m._ver_tuple(latest) > m._ver_tuple(cur)

    assert not has("1.5.4", "1.5.4")
    assert has("1.5.4", "1.5.5")
    assert not has("1.5.4", "1.5.3")


if __name__ == "__main__":
    test_parse()
    test_order()
    test_has_update_logic()
    print("PASS: 版本解析 / 排序 / 更新判定")
