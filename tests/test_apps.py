"""回归测试：按应用聚合连接。

运行：python tests/test_apps.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import autonode as m


def test_aggregate():
    conns = {
        "connections": [
            {"metadata": {"process": "codex", "processPath": "/x/codex", "host": "chatgpt.com"},
             "upload": 10, "download": 1000, "rule": "DomainSuffix", "rulePayload": "chatgpt.com",
             "chains": ["直连-美国01", "🧲 AI"]},
            {"metadata": {"process": "codex", "processPath": "/x/codex", "host": "api.openai.com"},
             "upload": 5, "download": 500, "rule": "DomainSuffix", "rulePayload": "openai.com",
             "chains": ["直连-美国01", "🧲 AI"]},
            {"metadata": {"process": "WeChat", "processPath": "/x/WeChat", "host": "qq.com"},
             "upload": 1, "download": 10, "rule": "GeoIP", "rulePayload": "cn",
             "chains": ["DIRECT", "🌏 国内网站"]},
            {"metadata": {"host": "no-process.example"}, "upload": 0, "download": 0, "chains": []},
        ]
    }
    configs = {"tun": {"enable": False}, "find-process-mode": "strict", "mode": "rule"}

    def fake_api(ctx, method, path, payload=None, timeout=90):
        return conns if path == "/connections" else configs

    m.api = fake_api
    res = m.live_apps()
    assert res["ok"], res
    assert res["find_process_mode"] == "strict"
    assert res["tun"] is False
    names = [a["name"] for a in res["apps"]]
    assert names[0] == "codex", names
    codex = res["apps"][0]
    assert codex["conns"] == 2
    assert codex["download"] == 1500
    assert codex["outbound"] == ["直连-美国01"]
    assert "no-process.example" not in names


if __name__ == "__main__":
    test_aggregate()
    print("PASS: 应用聚合 / 出口识别 / 无进程连接忽略")
