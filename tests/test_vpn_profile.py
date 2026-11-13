"""回归测试：VPN 配置描述文件生成。

运行：python tests/test_vpn_profile.py
"""

import os
import plistlib
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import autonode as m


def test_ikev2():
    data = m.build_vpn_mobileconfig("学校 VPN", "IKEv2", "vpn.example.edu",
                                    "user@example.edu", "pw", "")
    d = plistlib.loads(data)
    assert d["PayloadType"] == "Configuration"
    vpn = d["PayloadContent"][0]
    assert vpn["VPNType"] == "IKEv2"
    assert vpn["IKEv2"]["RemoteAddress"] == "vpn.example.edu"
    assert vpn["PPP"]["AuthName"] == "user@example.edu"
    assert vpn["PayloadDisplayName"] == "学校 VPN"


def test_l2tp():
    data = m.build_vpn_mobileconfig("老式 VPN", "L2TP", "vpn.example.edu",
                                    "user", "pw", "shared-secret")
    d = plistlib.loads(data)
    vpn = d["PayloadContent"][0]
    assert vpn["VPNType"] == "L2TP"
    assert vpn["PPP"]["CommRemoteAddress"] == "vpn.example.edu"
    assert vpn["IPSec"]["AuthenticationMethod"] == "SharedSecret"
    assert vpn["IPSec"]["SharedSecret"] == b"shared-secret"


def test_uuid_unique():
    a = plistlib.loads(m.build_vpn_mobileconfig("A", "IKEv2", "a.edu", "", "", ""))
    b = plistlib.loads(m.build_vpn_mobileconfig("B", "IKEv2", "b.edu", "", "", ""))
    assert a["PayloadUUID"] != b["PayloadUUID"]
    assert a["PayloadContent"][0]["PayloadUUID"] != b["PayloadContent"][0]["PayloadUUID"]


if __name__ == "__main__":
    test_ikev2()
    test_l2tp()
    test_uuid_unique()
    print("PASS: IKEv2 / L2TP / UUID 唯一")
