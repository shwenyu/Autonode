"""回归测试：dry-run 不得写入，手动切换不得被回退分支覆盖。

运行：python tests/test_dryrun.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import autonode as m

GROUP = {
    "id": "t", "label": "TEST", "group": "G", "min_healthy": 1,
    "regions": ["日本"], "keep_factor": 1.3, "keep_offset_ms": 30,
}


class FakeEngine:
    cfg = {"socket": "", "api_host": "127.0.0.1", "api_port": 1}


def install_fakes(epoch_after=None):
    """替换 api/evaluate，记录 PUT；epoch_after 用于模拟测速期间的手动切换。"""
    puts = []

    def fake_api(ctx, method, path, payload=None, timeout=90):
        if method == "PUT":
            puts.append((path, payload))
        return {}

    class Runner:
        manual_epoch = 0

    def fake_evaluate(ctx, g):
        if epoch_after is not None:
            Runner.manual_epoch = epoch_after
        return ("dead-node", None,
                [{"name": "good-node", "region": "日本", "priority": 0,
                  "ms": 100, "verify_ms": None}],
                "verify-all-failed")

    m.api = fake_api
    m.evaluate = fake_evaluate
    return puts, Runner


def test_dry_run_never_writes():
    puts, _ = install_fakes()
    res = m.run_group(FakeEngine(), GROUP, dry_run=True)
    assert res["action"] == "dry-run", res
    assert len(puts) == 0, "dry-run 不应写入，实际 PUT %d 次" % len(puts)

    res = m.run_group(FakeEngine(), GROUP, dry_run=False)
    assert res["action"] == "switch", res
    assert len(puts) == 1, "正式运行应当切换一次"


def test_manual_switch_wins():
    puts, Runner = install_fakes(epoch_after=1)
    res = m.run_group(FakeEngine(), GROUP, dry_run=False, runner=Runner())
    assert res["action"] == "skip", res
    assert len(puts) == 0, "手动切换后不应再回退"


if __name__ == "__main__":
    test_dry_run_never_writes()
    test_manual_switch_wins()
    print("PASS: dry-run 不写入；手动切换优先")
