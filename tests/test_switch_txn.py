"""回归测试：订阅切换事务（成功路径 / 验证失败回滚）。"""
import os, sys, tempfile, types, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import autonode as m

PROFILES = """# test
current: AAAA
items:
- uid: AAAA
  type: remote
  name: Alpha
  url: https://example.com/a
- uid: BBBB
  type: remote
  name: Beta
  url: https://example.com/b
"""

def setup(tmp, alive=True, proxies=True):
    path = os.path.join(tmp, "profiles.yaml")
    open(path, "w").write(PROFILES)
    m.IS_MAC = True
    m._profiles_path = lambda: path
    m.STATE_DIR = os.path.join(tmp, "state")
    os.makedirs(m.STATE_DIR, exist_ok=True)
    m.save_config = lambda cfg: None
    m.record_op = lambda *a, **k: None
    m.log = lambda *a, **k: None
    m.subprocess.run = lambda *a, **k: types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
    m.controller_alive = lambda cfg: alive
    m.controller_ctx = lambda cfg: {}
    m.api = lambda ctx, method, p, payload=None, timeout=90: (
        {"proxies": {"G": {"type": "Selector", "all": []}}} if proxies else {"proxies": {}})
    eng = types.SimpleNamespace(cfg={}, bump_epoch=lambda r: 1, sub_uid="AAAA")
    return eng, path

def test_success():
    with tempfile.TemporaryDirectory() as tmp:
        eng, path = setup(tmp)
        r = m.switch_subscription(eng, "BBBB")
        assert r["ok"], r
        assert "current: BBBB" in open(path).read()
        names = [s["step"] for s in r["steps"]]
        assert names[:3] == ["precheck", "backup", "quit"], names
        assert "rollback" not in names

def test_rollback_on_start_failure():
    with tempfile.TemporaryDirectory() as tmp:
        eng, path = setup(tmp, alive=False, proxies=False)
        r = m.switch_subscription(eng, "BBBB")
        assert not r["ok"], r
        # 回滚后 current 仍是原订阅
        assert "current: AAAA" in open(path).read(), open(path).read()
        steps = {s["step"]: s["ok"] for s in r["steps"]}
        assert steps.get("rollback") is True, steps

def test_missing_uid_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        eng, path = setup(tmp)
        r = m.switch_subscription(eng, "ZZZZ")
        assert not r["ok"] and "不存在" in r["error"], r

if __name__ == "__main__":
    test_success()
    test_rollback_on_start_failure()
    test_missing_uid_rejected()
    print("PASS: 切换事务成功 / 验证失败回滚 / 非法目标拒绝")
