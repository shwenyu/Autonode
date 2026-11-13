#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Clash Verge 多代理组自动选优（带本地网页控制台）

支持同时管理多个代理组，每组独立配置间隔、地区偏好、防抖参数。
对 ChatGPT 这类"高风控"分组，可开启「验证」步骤：
先用中性地址筛出前 N 名，再各发一次目标地址探测，避免批量请求被打限速。

启动:
  ./clash_auto_node.py --serve      # 常驻 + 网页控制台（LaunchAgent 用）
  ./clash_auto_node.py --once [id]  # 只跑一次
  ./clash_auto_node.py --dry-run    # 只测速不切换

控制台: http://127.0.0.1:8765
配置:   ~/.config/autonode/config.json
日志:   ~/.config/autonode/pick.log
"""

import concurrent.futures
import glob
import html
import http.client
import json
import os
import platform
import plistlib
import re
import shutil
import shlex
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = "1.5.2"

BASE_DIR = os.path.expanduser("~/.config/autonode")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
LOG_FILE = os.path.join(BASE_DIR, "pick.log")
LOG_MAX_BYTES = 512 * 1024

REGION_CHOICES = [
    "日本", "新加坡", "美国", "香港", "台湾", "韩国",
    "德国", "英国", "荷兰", "法国", "加拿大", "澳大利亚",
    "马来西亚", "泰国", "越南", "菲律宾", "印度尼西亚",
    "土耳其", "迪拜", "瑞士", "西班牙", "意大利", "瑞典",
    "波兰", "巴西", "阿根廷", "南非", "新西兰", "爱尔兰",
    "奥地利", "比利时", "丹麦", "挪威", "芬兰", "俄罗斯", "印度",
]

REGION_UNKNOWN = "未知"

REGION_ALIASES = {
    "日本": ["日本", "japan", "jp", "jpn", "tokyo", "osaka", "nrt", "hnd", "kix", "东京", "大阪"],
    "新加坡": ["新加坡", "singapore", "sg", "sgp", "狮城"],
    "美国": ["美国", "united states", "usa", "us", "america", "lax", "sjc", "seattle", "dallas",
             "ashburn", "silicon", "洛杉矶", "西雅图", "硅谷", "纽约"],
    "香港": ["香港", "hong kong", "hongkong", "hk", "hkg"],
    "台湾": ["台湾", "台灣", "taiwan", "tw", "twn", "taipei", "台北"],
    "韩国": ["韩国", "韓國", "korea", "kr", "kor", "seoul", "首尔", "仁川"],
    "德国": ["德国", "germany", "de", "deu", "frankfurt", "fra", "berlin", "法兰克福"],
    "英国": ["英国", "united kingdom", "uk", "gbr", "london", "lon", "lhr", "伦敦"],
    "荷兰": ["荷兰", "netherlands", "nl", "nld", "amsterdam", "ams", "阿姆斯特丹"],
    "法国": ["法国", "france", "fr", "paris", "cdg", "巴黎"],
    "加拿大": ["加拿大", "canada", "ca", "can", "toronto", "vancouver", "多伦多"],
    "澳大利亚": ["澳大利亚", "澳洲", "australia", "au", "aus", "sydney", "syd", "悉尼"],
    "马来西亚": ["马来西亚", "malaysia", "my", "mys", "kuala lumpur", "吉隆坡"],
    "泰国": ["泰国", "thailand", "th", "tha", "bangkok", "曼谷"],
    "越南": ["越南", "vietnam", "vn", "vnm", "hanoi", "河内"],
    "菲律宾": ["菲律宾", "philippines", "ph", "phl", "manila", "马尼拉"],
    "印度尼西亚": ["印度尼西亚", "印尼", "indonesia", "id", "idn", "jakarta", "雅加达"],
    "土耳其": ["土耳其", "turkey", "tr", "tur", "istanbul", "伊斯坦布尔"],
    "迪拜": ["迪拜", "dubai", "ae", "are", "阿联酋"],
    "瑞士": ["瑞士", "switzerland", "ch", "che", "zurich", "苏黎世"],
    "西班牙": ["西班牙", "spain", "es", "esp", "madrid", "马德里"],
    "意大利": ["意大利", "italy", "it", "ita", "milan", "米兰"],
    "瑞典": ["瑞典", "sweden", "se", "swe", "stockholm", "斯德哥尔摩"],
    "波兰": ["波兰", "poland", "pl", "pol", "warsaw", "华沙"],
    "巴西": ["巴西", "brazil", "br", "bra", "sao paulo", "圣保罗"],
    "阿根廷": ["阿根廷", "argentina", "ar", "arg", "buenos aires"],
    "南非": ["南非", "south africa", "za", "zaf", "johannesburg"],
    "新西兰": ["新西兰", "new zealand", "nz", "nzl", "auckland", "奥克兰"],
    "爱尔兰": ["爱尔兰", "ireland", "ie", "irl", "dublin", "都柏林"],
    "奥地利": ["奥地利", "austria", "at", "aut", "vienna", "维也纳"],
    "比利时": ["比利时", "belgium", "be", "bel", "brussels", "布鲁塞尔"],
    "丹麦": ["丹麦", "denmark", "dk", "dnk", "copenhagen", "哥本哈根"],
    "挪威": ["挪威", "norway", "no", "nor", "oslo", "奥斯陆"],
    "芬兰": ["芬兰", "finland", "fi", "fin", "helsinki", "赫尔辛基"],
    "俄罗斯": ["俄罗斯", "russia", "ru", "rus", "moscow", "莫斯科"],
    "印度": ["印度", "india", "in", "ind", "mumbai", "孟买"],
}

REGION_EXTRA = {
    "中国": ["中国", "china", "cn", "chn", "回国", "上海", "北京", "广州", "深圳"],
    "乌克兰": ["乌克兰", "ukraine", "ua", "ukr", "kyiv", "kiev"],
    "以色列": ["以色列", "israel", "il", "isr", "tel aviv"],
    "保加利亚": ["保加利亚", "bulgaria", "bg", "bgr", "sofia"],
    "克罗地亚": ["克罗地亚", "croatia", "hr", "hrv", "zagreb"],
    "哈萨克斯坦": ["哈萨克斯坦", "kazakhstan", "kz", "kaz", "almaty"],
    "哥斯达黎加": ["哥斯达黎加", "costa rica", "cr", "cri"],
    "埃及": ["埃及", "egypt", "eg", "egy", "cairo"],
    "塞尔维亚": ["塞尔维亚", "serbia", "rs", "srb", "belgrade"],
    "墨西哥": ["墨西哥", "mexico", "mx", "mex"],
    "尼日利亚": ["尼日利亚", "nigeria", "ng", "nga", "lagos"],
    "巴基斯坦": ["巴基斯坦", "pakistan", "pk", "pak", "karachi"],
    "希腊": ["希腊", "greece", "gr", "grc", "athens"],
    "智利": ["智利", "chile", "cl", "chl", "santiago"],
    "柬埔寨": ["柬埔寨", "cambodia", "kh", "khm", "phnom penh"],
    "秘鲁": ["秘鲁", "peru", "pe", "per", "lima"],
    "立陶宛": ["立陶宛", "lithuania", "lt", "ltu", "vilnius"],
    "老挝": ["老挝", "laos", "la", "lao", "vientiane"],
    "阿尔巴尼亚": ["阿尔巴尼亚", "albania", "al", "alb", "tirana"],
    "马里": ["马里", "mali", "ml", "mli", "bamako"],
    "匈牙利": ["匈牙利", "hungary", "hu", "hun", "budapest"],
    "捷克": ["捷克", "czech", "cz", "cze", "prague"],
    "罗马尼亚": ["罗马尼亚", "romania", "ro", "rou", "bucharest"],
    "斯洛伐克": ["斯洛伐克", "slovakia", "sk", "svk", "bratislava"],
    "斯洛文尼亚": ["斯洛文尼亚", "slovenia", "si", "svn", "ljubljana"],
    "爱沙尼亚": ["爱沙尼亚", "estonia", "ee", "est", "tallinn"],
    "拉脱维亚": ["拉脱维亚", "latvia", "lv", "lva", "riga"],
    "卢森堡": ["卢森堡", "luxembourg", "lu", "lux"],
    "葡萄牙": ["葡萄牙", "portugal", "pt", "prt", "lisbon"],
    "哥伦比亚": ["哥伦比亚", "colombia", "co", "col", "bogota"],
    "沙特阿拉伯": ["沙特", "沙特阿拉伯", "saudi", "sa", "sau", "riyadh"],
    "卡塔尔": ["卡塔尔", "qatar", "qa", "qat", "doha"],
    "孟加拉": ["孟加拉", "bangladesh", "bd", "bgd", "dhaka"],
    "斯里兰卡": ["斯里兰卡", "sri lanka", "lk", "lka", "colombo"],
    "尼泊尔": ["尼泊尔", "nepal", "np", "npl", "kathmandu"],
    "缅甸": ["缅甸", "myanmar", "mm", "mmr", "yangon"],
    "澳门": ["澳门", "澳門", "macau", "macao", "mo"],
    "关岛": ["关岛", "guam", "gu"],
    "阿曼": ["阿曼", "oman", "om", "omn", "muscat"],
    "科威特": ["科威特", "kuwait", "kw", "kwt"],
    "约旦": ["约旦", "jordan", "jo", "jor", "amman"],
    "黎巴嫩": ["黎巴嫩", "lebanon", "lb", "lbn", "beirut"],
    "摩洛哥": ["摩洛哥", "morocco", "ma", "mar", "casablanca"],
    "突尼斯": ["突尼斯", "tunisia", "tn", "tun", "tunis"],
    "肯尼亚": ["肯尼亚", "kenya", "ke", "ken", "nairobi"],
    "加纳": ["加纳", "ghana", "gh", "gha", "accra"],
    "塞舌尔": ["塞舌尔", "seychelles", "sc", "syc"],
    "毛里求斯": ["毛里求斯", "mauritius", "mu", "mus"],
    "巴拿马": ["巴拿马", "panama", "pa", "pan"],
    "乌拉圭": ["乌拉圭", "uruguay", "uy", "ury", "montevideo"],
    "巴拉圭": ["巴拉圭", "paraguay", "py", "pry", "asuncion"],
    "玻利维亚": ["玻利维亚", "bolivia", "bo", "bol", "lapaz"],
    "委内瑞拉": ["委内瑞拉", "venezuela", "ve", "ven", "caracas"],
    "厄瓜多尔": ["厄瓜多尔", "ecuador", "ec", "ecu", "quito"],
}
REGION_ALIASES.update(REGION_EXTRA)
for _r in REGION_EXTRA:
    if _r not in REGION_CHOICES:
        REGION_CHOICES.append(_r)

_REGION_STATE = {"overrides": {}, "servers": {}}


def _match_aliases(text):
    low = (text or "").lower()
    if not low:
        return None
    for region, aliases in REGION_ALIASES.items():
        for alias in aliases:
            if alias.isascii() and len(alias) <= 3:
                if re.search(r"(?<![a-z])%s(?![a-z])" % re.escape(alias), low):
                    return region
            elif alias in low:
                return region
    return None


def detect_region(name):
    """识别链：人工覆盖 > 节点名 > 服务器主机名 > 未知。"""
    overrides = _REGION_STATE.get("overrides") or {}
    if name in overrides:
        return overrides[name]
    hit = _match_aliases(name)
    if hit:
        return hit
    server = (_REGION_STATE.get("servers") or {}).get(name)
    if server:
        return _match_aliases(server)
    return None


def load_profile_servers(clash_dir):
    """从当前订阅里解析 节点名 -> 服务器地址，供地区推断兜底。"""
    if not clash_dir:
        return {}
    try:
        with open(os.path.join(clash_dir, "profiles.yaml"), encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return {}
    m = re.search(r"^current:\s*(\S+)\s*$", text, re.M)
    if not m:
        return {}
    path = os.path.join(clash_dir, "profiles", "%s.yaml" % m.group(1))
    try:
        with open(path, encoding="utf-8") as fh:
            body = fh.read()
    except OSError:
        return {}
    servers = {}
    for line in body.splitlines():
        if "server:" not in line:
            continue
        nm = re.search(r"name:\s*(?:'([^']*)'|\"([^\"]*)\"|([^,}]+))", line)
        sv = re.search(r"server:\s*([^,}\s]+)", line)
        if nm and sv:
            name = (nm.group(1) or nm.group(2) or nm.group(3) or "").strip()
            if name:
                servers[name] = sv.group(1).strip()
    return servers


def refresh_region_state(cfg, servers=None):
    _REGION_STATE["overrides"] = dict(cfg.get("region_overrides") or {})
    if servers is not None:
        _REGION_STATE["servers"] = dict(servers)


COMMON = {
    "enabled": True,
    "test_url": "https://www.gstatic.com/generate_204",
    "timeout_ms": 3000,
    "interval_seconds": 300,
    "min_healthy": 3,
    "keep_factor": 1.30,
    "keep_offset_ms": 30,
    "max_workers": 8,
    "verify_url": "",
    "verify_top": 0,
    "verify_timeout_ms": 8000,
    "verify_mode": "lazy",
    "verify_good_ms": 2000,
    "verify_gap_seconds": 1.5,
    "manual_hold_seconds": 1800,
}

DEFAULT_GROUPS = [
    {
        "id": "main",
        "label": "手动选择节点",
        "group": "♻️ 手动选择节点",
        "enabled": True,
        "interval_seconds": 300,
        "min_healthy": 3,
        "keep_factor": 1.30,
        "keep_offset_ms": 30,
        "max_workers": 8,
        "test_url": "https://www.gstatic.com/generate_204",
        "verify_url": "",
        "verify_top": 0,
        "regions": ["日本", "新加坡", "美国", "香港", "台湾", "韩国",
                    "德国", "英国", "荷兰", "法国", "加拿大", "澳大利亚"],
    },
    {
        "id": "ai",
        "label": "🧲 AI",
        "group": "🧲 AI",
        "enabled": True,
        "interval_seconds": 1800,
        "min_healthy": 2,
        "keep_factor": 1.50,
        "keep_offset_ms": 100,
        "max_workers": 6,
        "test_url": "https://www.gstatic.com/generate_204",
        # 只对前 3 名各发一次 chatgpt 探测，避免批量请求被 Cloudflare 限速
        "verify_url": "https://chatgpt.com/cdn-cgi/trace",
        "verify_top": 3,
        "regions": ["日本", "新加坡", "美国", "德国", "英国", "韩国",
                    "台湾", "加拿大", "法国", "荷兰"],
    },
]

DEFAULT_CONFIG = {
    "enabled": True,
    "socket": "",
    "api_host": "127.0.0.1",
    "api_port": 9090,
    "api_secret": "",
    "clash_dir": "",
    "port": 8765,
    "groups": [],
    "custom_groups": [],
    "vpn_keep": [],
    "region_overrides": {},
    "vpn_interval": 60,
    "routes": [],
}

EXCLUDE_KEYWORDS = (
    "剩余流量", "距离下次", "套餐到期", "官網", "官网", "懒人",
    "手动选择", "自动选择", "负载均衡", "故障转移",
    "DIRECT", "REJECT", "REJECT-DROP", "PASS",
    "♻️", "⚖️", "🌏", "🎬", "📺", "🔎", "🧲", "📲", "🎙", "☁️", "🍎",
)


# ------------------------------------------------------------------ 基础

def _normalize_group(item):
    cfg = dict(COMMON)
    cfg.update(item)
    cfg.setdefault("id", "g%d" % abs(hash(cfg.get("group", ""))))
    cfg.setdefault("label", cfg.get("group", "group"))
    label = cfg.get("label") or ""
    if not cfg.get("role"):
        cfg["role"] = "ai" if "AI" in label.upper() else "general"
    if cfg["role"] == "ai":
        # AI 通道：低频、粘滞（只要当前节点验证通过就不换），避免 IP 漂移触发风控
        item_interval = item.get("interval_seconds")
        if not item_interval:
            cfg["interval_seconds"] = 1800
        if item.get("keep_factor") is None:
            cfg["keep_factor"] = 2.0
        if item.get("keep_offset_ms") is None:
            cfg["keep_offset_ms"] = 300
        if not cfg.get("verify_url"):
            cfg["verify_url"] = "https://chatgpt.com/cdn-cgi/trace"
            cfg["verify_top"] = int(cfg.get("verify_top") or 3)
    cfg["interval_seconds"] = max(60, int(cfg["interval_seconds"]))
    cfg["min_healthy"] = max(1, int(cfg["min_healthy"]))
    cfg["max_workers"] = max(1, int(cfg["max_workers"]))
    if not isinstance(cfg.get("regions"), list) or not cfg["regions"]:
        cfg["regions"] = ["日本", "新加坡", "美国"]
    return cfg


def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
            saved = json.load(fh)
    except Exception:
        return cfg

    if isinstance(saved, dict):
        if "socket" in saved:
            cfg["socket"] = saved["socket"]
        if "port" in saved:
            cfg["port"] = saved["port"]
        if "enabled" in saved:
            cfg["enabled"] = bool(saved["enabled"])
        if isinstance(saved.get("groups"), list) and saved["groups"]:
            cfg["groups"] = [_normalize_group(g) for g in saved["groups"]]
        elif "group" in saved:  # 兼容旧版单组配置
            legacy = {k: v for k, v in saved.items() if k not in ("port", "socket", "enabled")}
            legacy.setdefault("id", "main")
            legacy.setdefault("label", legacy.get("group", "手动选择节点"))
            cfg["groups"] = [_normalize_group(legacy), _normalize_group(DEFAULT_GROUPS[1])]
    return cfg


def save_config(cfg):
    os.makedirs(BASE_DIR, exist_ok=True)
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_FILE)


# AI 站点默认清单（用于一键预置分流规则）
AI_PROVIDERS = [
    ("chatgpt", "ChatGPT", "https://chatgpt.com/cdn-cgi/trace"),
    ("claude", "Claude", "https://claude.ai/"),
    ("gemini", "Gemini", "https://gemini.google.com/"),
    ("perplexity", "Perplexity", "https://www.perplexity.ai/"),
    ("copilot", "Copilot", "https://copilot.microsoft.com/"),
    ("grok", "Grok", "https://grok.com/"),
]

AI_DOMAINS = [
    "openai.com", "chatgpt.com", "oaistatic.com", "oaiusercontent.com",
    "anthropic.com", "claude.ai", "gemini.google.com", "bard.google.com",
    "copilot.microsoft.com", "perplexity.ai", "poe.com", "midjourney.com",
    "huggingface.co", "openrouter.ai", "groq.com", "together.ai",
    "x.ai", "grok.com", "character.ai", "runwayml.com",
]


# ---------------------------------------------------------------- 环境探测

CLASH_DIR_CANDIDATES = [
    "~/Library/Application Support/io.github.clash-verge-rev.clash-verge-rev",
    "~/.local/share/io.github.clash-verge-rev.clash-verge-rev",
    "~/.config/io.github.clash-verge-rev.clash-verge-rev",
    "~/AppData/Roaming/io.github.clash-verge-rev.clash-verge-rev",
]

SOCKET_GLOBS = [
    "/var/run/clash-verge-service/users/*/verge-mihomo.sock",
    "/var/tmp/verge/verge-mihomo.sock",
    "/tmp/verge-mihomo.sock",
    "/tmp/verge/*.sock",
]


def detect_clash_dir():
    for path in CLASH_DIR_CANDIDATES:
        path = os.path.expanduser(path)
        if os.path.isdir(path):
            return path
    return ""


def detect_socket(current=""):
    if current and os.path.exists(current):
        return current
    for pattern in SOCKET_GLOBS:
        for hit in sorted(glob.glob(os.path.expanduser(pattern))):
            if os.path.exists(hit):
                return hit
    return current


def active_rules_uid(clash_dir):
    """从 profiles.yaml 里找出当前订阅对应的「规则模板」uid。"""
    try:
        with open(os.path.join(clash_dir, "profiles.yaml"), encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None, None
    m = re.search(r"^current:\s*(\S+)\s*$", text, re.M)
    if not m:
        return None, None
    cur = m.group(1)
    start = text.find("- uid: %s" % cur)
    if start < 0:
        return cur, None
    nxt = text.find("- uid:", start + 5)
    block = text[start:(nxt if nxt > 0 else len(text))]
    m2 = re.search(r"^\s+rules:\s*(\S+)\s*$", block, re.M)
    return cur, (m2.group(1) if m2 else None)


def active_groups_uid(clash_dir):
    """当前订阅的「分组模板」uid。"""
    try:
        with open(os.path.join(clash_dir, "profiles.yaml"), encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None, None
    m = re.search(r"^current:\s*(\S+)\s*$", text, re.M)
    if not m:
        return None, None
    cur = m.group(1)
    start = text.find("- uid: %s" % cur)
    if start < 0:
        return cur, None
    nxt = text.find("- uid:", start + 5)
    blk = text[start:(nxt if nxt > 0 else len(text))]
    m2 = re.search(r"^\s+groups:\s*(\S+)\s*$", blk, re.M)
    return cur, (m2.group(1) if m2 else None)


def write_groups(clash_dir, uid, groups):
    """把自定义分组写进 Verge 的分组模板（prepend）。"""
    path = os.path.join(clash_dir, "profiles", "%s.yaml" % uid)
    if not os.path.isdir(os.path.dirname(path)):
        raise RuntimeError("找不到 profiles 目录")
    if os.path.exists(path) and not os.path.exists(path + ".bak"):
        shutil.copy2(path, path + ".bak")
    lines = ["# Generated by autonode（自定义分组）", "prepend:"]
    for g in groups:
        lines.append("  - name: " + json.dumps(g.get("name", ""), ensure_ascii=False))
        lines.append("    type: select")
        lines.append("    proxies:")
        for m in g.get("members", []):
            lines.append("      - " + json.dumps(m, ensure_ascii=False))
    if not groups:
        lines = ["# Generated by autonode（自定义分组）", "prepend: []"]
    lines += ["append: []", "delete: []", ""]
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    os.replace(tmp, path)
    return path


def list_targets(ctx):
    """可选的分流目标：分组在前，DIRECT/REJECT 放最后（避免默认选中直连）。"""
    groups = []
    try:
        data = api(ctx, "GET", "/proxies", timeout=10).get("proxies", {})
        for name, info in data.items():
            if info.get("type") in ("Selector", "URLTest", "Fallback") and name.strip().upper() != "GLOBAL":
                if name not in groups:
                    groups.append(name)
    except Exception:
        pass
    return groups + ["DIRECT", "REJECT"]


def write_rules(clash_dir, uid, routes):
    path = os.path.join(clash_dir, "profiles", "%s.yaml" % uid)
    if not os.path.isdir(os.path.dirname(path)):
        raise RuntimeError("找不到 profiles 目录：%s" % os.path.dirname(path))
    if os.path.exists(path) and not os.path.exists(path + ".bak"):
        shutil.copy2(path, path + ".bak")

    lines = ["# Generated by autonode（网页控制台的分流规则）", "prepend:"]
    for r in routes:
        rule = "%s,%s,%s" % (r.get("type", "DOMAIN-SUFFIX"), r.get("value", ""), r.get("target", "DIRECT"))
        lines.append("  - " + json.dumps(rule, ensure_ascii=False))
    if not routes:
        lines = ["# Generated by autonode（网页控制台的分流规则）", "prepend: []"]
    lines += ["append: []", "delete: []", ""]

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    os.replace(tmp, path)
    return path


def windows_self_install():
    """PyInstaller 单文件 exe 首次运行时：把自己装到 %APPDATA%，建快捷方式并启动。"""
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    dest = os.path.join(appdata, "autonode")
    os.makedirs(dest, exist_ok=True)
    exe_dst = os.path.join(dest, "ClashAutoNode.exe")
    src = sys.executable
    if os.path.abspath(src) != os.path.abspath(exe_dst):
        shutil.copy2(src, exe_dst)

    ps = (
        "$ws=New-Object -ComObject WScript.Shell;"
        "$s=$ws.CreateShortcut([IO.Path]::Combine([Environment]::GetFolderPath('Startup'),'ClashAutoNode.lnk'));"
        "$s.TargetPath='%s';$s.Arguments='--installed --serve';$s.WorkingDirectory='%s';$s.WindowStyle=7;$s.Save();"
        "$u=[IO.Path]::Combine([Environment]::GetFolderPath('Desktop'),'Clash 节点控制台.url');"
        "Set-Content -Path $u -Value '[InternetShortcut]','URL=http://127.0.0.1:8765' -Encoding ASCII"
        % (exe_dst, dest)
    )
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                   capture_output=True)

    subprocess.Popen([exe_dst, "--installed", "--serve"],
                     creationflags=0x00000008, close_fds=True)
    time.sleep(1.5)
    webbrowser.open("http://127.0.0.1:8765/")

    # 安装信息 + 兼容性提示
    try:
        import ctypes
        info = (
            "Windows 版本 : %s\n"
            "系统架构     : %s\n"
            "运行环境     : 自带 Python 运行时（无需系统安装）\n\n"
            "安装位置 : %s\n"
            "控制台   : http://127.0.0.1:8765\n\n"
            "已创建：开机自启 + 桌面快捷方式。\n"
            "关闭窗口不会停止后台服务；卸载请运行 uninstall.ps1。"
        ) % (platform.version(), platform.machine(), dest)
        ctypes.windll.user32.MessageBoxW(0, info, "Clash 节点自动选优 - 安装完成", 0x40)
    except Exception:
        pass
    return True


def list_system_vpns():
    """列出 macOS 系统 VPN（L2TP / IKEv2 / IPSec / 第三方 tunnel）。"""
    if not IS_MAC:
        return []
    try:
        out = subprocess.run(["scutil", "--nc", "list"], capture_output=True,
                             text=True, timeout=10).stdout
    except Exception:
        return []
    vpns = []
    for line in out.splitlines():
        m = re.match(r'^\*?\s*\(([^)]+)\)\s+(\S+)\s+(\S+)\s+"([^"]+)"\s+\[([^\]]+)\]', line.strip())
        if m:
            vpns.append({"status": m.group(1), "id": m.group(2), "type": m.group(3),
                         "name": m.group(4), "proto": m.group(5)})
    return vpns


def vpn_tick(engine, cooldown=None):
    """检查一轮需要保持的 VPN，返回本轮尝试重连的名称列表。"""
    cooldown = cooldown if cooldown is not None else {}
    names = list(engine.cfg.get("vpn_keep") or [])
    if not names:
        return []
    try:
        current = {v["name"]: v["status"] for v in list_system_vpns()}
    except Exception:
        return []
    now = time.time()
    acted = []
    for name in names:
        status = current.get(name)
        if status is None or status == "Connected":
            cooldown.pop(name, None)
            continue
        if now - cooldown.get(name, 0) < 120:
            continue
        cooldown[name] = now
        res = vpn_action(name, "connect")
        detail = "成功" if res.get("ok") else ("失败：" + str(res.get("error") or res.get("output")))
        log("[VPN] %s 当前 %s，自动重连%s" % (name, status, detail))
        acted.append(name)
    return acted


def vpn_watchdog(engine):
    """定时检查「保持连接」的系统 VPN，断线自动重连。"""
    if not IS_MAC:
        return
    cooldown = {}
    while True:
        try:
            interval = max(15, int(engine.cfg.get("vpn_interval", 60)))
        except Exception:
            interval = 60
        time.sleep(interval)
        vpn_tick(engine, cooldown)


def build_vpn_mobileconfig(name, kind, server, account, password, secret):
    """生成 VPN 配置描述文件（.mobileconfig），由系统弹窗确认安装。"""
    import uuid as _uuid
    uid = str(_uuid.uuid4()).upper()
    payload = {
        "PayloadType": "com.apple.vpn.managed",
        "PayloadVersion": 1,
        "PayloadIdentifier": "com.autonode.vpn." + uid,
        "PayloadUUID": uid,
        "PayloadDisplayName": name,
        "UserDefinedName": name,
        "VPNType": kind,
    }
    if kind == "IKEv2":
        payload["IKEv2"] = {
            "RemoteAddress": server,
            "LocalIdentifier": account or server,
            "RemoteIdentifier": server,
            "AuthenticationMethod": "None",
            "ExtendedAuthEnabled": 1,
        }
        payload["PPP"] = {"AuthName": account or "", "AuthPassword": password or ""}
    else:
        payload["PPP"] = {
            "AuthName": account or "",
            "AuthPassword": password or "",
            "CommRemoteAddress": server,
        }
        payload["IPSec"] = {
            "AuthenticationMethod": "SharedSecret",
            "SharedSecret": (secret or "").encode("utf-8"),
        }
    root = {
        "PayloadType": "Configuration",
        "PayloadVersion": 1,
        "PayloadIdentifier": "com.autonode.profile." + uid,
        "PayloadUUID": str(_uuid.uuid4()).upper(),
        "PayloadDisplayName": name,
        "PayloadOrganization": "Autonode",
        "PayloadContent": [payload],
    }
    return plistlib.dumps(root)


def vpn_action(name, action):
    if not IS_MAC:
        return {"ok": False, "error": "系统 VPN 托管目前只支持 macOS"}
    if action not in ("connect", "disconnect"):
        return {"ok": False, "error": "unknown action"}
    if not name:
        return {"ok": False, "error": "缺少 VPN 名称"}
    cmd = ["scutil", "--nc", "start" if action == "connect" else "stop", name]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    ok = r.returncode == 0
    return {"ok": ok, "output": (r.stdout or r.stderr or "").strip()}


def service_label():
    """找出本机安装的 LaunchAgent（本地/分发版本 label 可能不同）。"""
    for path in glob.glob(os.path.expanduser("~/Library/LaunchAgents/*autonode*.plist")):
        try:
            out = subprocess.run(["plutil", "-extract", "Label", "raw", "-o", "-", path],
                                 capture_output=True, text=True, timeout=5)
            label = (out.stdout or "").strip()
            if out.returncode == 0 and label:
                return path, label
        except Exception:
            continue
    return None, None


def service_control(action):
    """stop / restart 后台服务。用独立进程执行，避免把自己杀掉时请求中断。"""
    if not IS_MAC:
        # Windows/Linux：没有 launchd，直接退出进程；开机自启由快捷方式/启动项决定
        if action == "stop":
            threading.Timer(0.5, lambda: os._exit(0)).start()
        return {"ok": True, "action": action, "note": "no-launchd"}

    plist, label = service_label()
    if not label:
        return {"ok": False, "error": "找不到 LaunchAgent（可能不是用安装脚本装的）"}
    uid = os.getuid()
    cmd = "sleep 1; launchctl bootout gui/%d/%s" % (uid, label)
    if action == "restart":
        cmd += "; sleep 1; launchctl bootstrap gui/%d %s" % (uid, shlex.quote(plist))
    subprocess.Popen(["/bin/sh", "-c", cmd], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"ok": True, "label": label, "action": action}


IS_WIN = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"


def restart_verge():
    """让 Verge 重新生成配置并拉起内核（内核是 root 进程，只能由它自己重启）。"""
    if IS_WIN:
        subprocess.run(["taskkill", "/IM", "Clash Verge.exe", "/F"], capture_output=True)
        time.sleep(2)
        try:
            os.startfile("clash-verge://")   # 由协议拉起客户端
        except Exception:
            pass
        return True
    subprocess.run(["pkill", "-TERM", "-f", "Clash Verge.app/Contents/MacOS/clash-verge"],
                   check=False)
    time.sleep(2)
    r = subprocess.run(["open", "-b", "io.github.clash-verge-rev.clash-verge-rev"], check=False)
    if r.returncode != 0:
        subprocess.run(["open", "-a", "Clash Verge"], check=False)
    return True


def fetch_subscription(url, timeout=25):
    """拉一次订阅做校验，返回 (ok, info)。"""
    import urllib.request
    if not re.match(r"^https?://", url or ""):
        return False, {"error": "只支持 http/https 链接"}

    # 先走本地代理（多半已开着），失败再直连
    for proxy in ("http://127.0.0.1:7897", None):
        try:
            handlers = [urllib.request.ProxyHandler({"http": proxy, "https": proxy})] if proxy else []
            opener = urllib.request.build_opener(*handlers)
            req = urllib.request.Request(url, headers={
                "User-Agent": "clash-verge/v2.5.10",
                "Accept": "*/*",
            })
            with opener.open(req, timeout=timeout) as resp:
                raw = resp.read(400000)
                text = raw.decode("utf-8", "ignore")
                looks = ("proxies:" in text) or ("proxy-groups:" in text)
                return True, {
                    "status": resp.status,
                    "size": len(raw),
                    "clash": looks,
                    "via": proxy or "direct",
                    "head": text[:120].replace("\n", " "),
                }
        except Exception as exc:
            last = str(exc)
    return False, {"error": last}


def rescan_groups(engine):
    """重新扫描代理组，把新出现的分组加进来（订阅导入后调用）。"""
    engine.controller = detect_controller(engine.cfg) or {}
    found = engine._bootstrap_groups()
    known = {g.get("group") for g in engine.cfg.get("groups", [])}
    added = []
    next_id = 1 + max([int(g["id"][1:]) for g in engine.cfg["groups"]
                       if g["id"].startswith("g") and g["id"][1:].isdigit()] or [0])
    # 只补「主分组」：名字里带 手动 / AI / 选择 的，最多 2 个，
    # 避免把国外流媒体、Discord 这类细分分组也纳管。
    def primary(g):
        label = g.get("label", "")
        return ("手动" in label) or ("AI" in label.upper()) or ("选择" in label)

    for g in [x for x in found if primary(x)][:2]:
        if g["group"] in known:
            continue
        g["id"] = "g%d" % next_id
        next_id += 1
        engine.cfg["groups"].append(g)
        runner = Runner(engine, g)
        engine.runners[g["id"]] = runner
        threading.Thread(target=runner.loop, daemon=True).start()
        added.append(g["label"])
    if added:
        save_config(engine.cfg)
        log("重新扫描：新增分组 %s" % "、".join(added))
    return added


def log(msg):
    os.makedirs(BASE_DIR, exist_ok=True)
    try:
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > LOG_MAX_BYTES:
            os.replace(LOG_FILE, LOG_FILE + ".1")
    except OSError:
        pass
    line = "[%s] %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError:
        pass


def fmt_ms(value):
    return "%dms" % value if isinstance(value, int) and value > 0 else "-"


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path, timeout=10):
        super().__init__("localhost", timeout=timeout)
        self._unix_path = path

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self._unix_path)
        self.sock = sock


def controller_ctx(cfg):
    """把配置里的控制器信息转成统一描述：unix socket 或 TCP。"""
    unix = cfg.get("socket") or ""
    if unix and os.path.exists(unix):
        return {"unix": unix, "secret": cfg.get("api_secret", "")}
    return {"host": cfg.get("api_host", "127.0.0.1"),
            "port": int(cfg.get("api_port", 9090)),
            "secret": cfg.get("api_secret", "")}


def detect_controller(cfg):
    """先找 Clash Verge 的 unix socket，再试各客户端的常见控制端口。"""
    path = detect_socket(cfg.get("socket", ""))
    if path:
        cfg["socket"] = path
        return {"kind": "unix", "target": path}
    for port in (cfg.get("api_port") or 9090, 9097, 9091, 9099, 9093, 6170):
        ctx = {"host": "127.0.0.1", "port": int(port), "secret": cfg.get("api_secret", "")}
        try:
            info = api(ctx, "GET", "/version", timeout=2)
            if info.get("version"):
                cfg["api_port"] = int(port)
                return {"kind": "tcp", "target": "127.0.0.1:%d" % int(port),
                        "version": info.get("version")}
        except Exception:
            continue
    return None


def api(ctx, method, path, payload=None, timeout=90):
    secret = ctx.get("secret") or ""
    if ctx.get("unix"):
        conn = UnixHTTPConnection(ctx["unix"], timeout=timeout)
    else:
        conn = http.client.HTTPConnection(ctx.get("host", "127.0.0.1"),
                                          int(ctx.get("port", 9090)), timeout=timeout)
    try:
        body = None
        headers = {}
        if secret:
            headers["Authorization"] = "Bearer " + secret
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        if resp.status >= 400:
            raise RuntimeError("%s %s -> HTTP %s %s" % (method, path, resp.status, raw[:200]))
        return json.loads(raw) if raw else {}
    finally:
        conn.close()


# ------------------------------------------------------------------ 选优

def is_node(name):
    return not any(k in name for k in EXCLUDE_KEYWORDS)


def region_priority(name, regions):
    region = detect_region(name)
    if region is None:
        if REGION_UNKNOWN in regions:
            return len(regions), REGION_UNKNOWN
        return None
    if region in regions:
        return regions.index(region), region
    return None


def probe_delay(ctx, node, url, timeout_ms):
    path = "/proxies/%s/delay?url=%s&timeout=%d" % (
        urllib.parse.quote(node, safe=""),
        urllib.parse.quote(url, safe=""),
        int(timeout_ms),
    )
    try:
        res = api(ctx, "GET", path, timeout=int(timeout_ms) / 1000.0 + 6)
        delay = res.get("delay")
        return delay if isinstance(delay, int) and delay > 0 else None
    except Exception:
        return None


def evaluate(ctx, g):
    """两阶段筛选：先全量中性测速，再对前 N 名做目标验证。"""
    group_path = "/proxies/%s" % urllib.parse.quote(g["group"], safe="")
    group = api(ctx, "GET", group_path, timeout=10)
    all_nodes = group.get("all") or []
    current = group.get("now") or ""

    targets = [n for n in all_nodes if is_node(n) and region_priority(n, g["regions"]) is not None]

    delays = {}

    def probe(name):
        return name, probe_delay(ctx, name, g["test_url"], g["timeout_ms"])

    with concurrent.futures.ThreadPoolExecutor(max_workers=int(g["max_workers"])) as pool:
        for name, ms in pool.map(probe, targets):
            if ms:
                delays[name] = ms

    candidates = []
    for name, ms in delays.items():
        pri, region = region_priority(name, g["regions"])
        candidates.append({"name": name, "region": region, "priority": pri,
                           "ms": ms, "verify_ms": None})
    candidates.sort(key=lambda x: (x["ms"], x["priority"]))

    # 第二阶段：目标验证
    # 关键：必须**串行**探测。同一出口 IP 并发打 chatgpt.com 会被 Cloudflare 判为异常
    # （实测 3 并发全部失败，逐个间隔 3 秒则 3/3 成功）。
    # lazy（默认）：先验证当前节点，合格就收工；不合格才逐个验证候选，命中即停。
    if g.get("verify_url") and int(g.get("verify_top", 0)) > 0:
        mode = g.get("verify_mode", "lazy")
        good_ms = int(g.get("verify_good_ms", 2000))
        vtimeout = g.get("verify_timeout_ms", 8000)
        verify_gap = float(g.get("verify_gap_seconds", 1.5))

        cur_v = None
        if current and is_node(current):
            cur_v = probe_delay(ctx, current, g["verify_url"], vtimeout)
            if mode == "lazy" and cur_v and cur_v <= good_ms:
                for c in candidates:
                    if c["name"] == current:
                        c["verify_ms"] = cur_v
                return current, delays.get(current), candidates, "current-good"
            time.sleep(verify_gap)

        shortlist = candidates[:int(g["verify_top"])]
        good = []
        for c in shortlist:
            if c["name"] == current:
                c["verify_ms"] = cur_v
            else:
                c["verify_ms"] = probe_delay(ctx, c["name"], g["verify_url"], vtimeout)
            if c["verify_ms"]:
                good.append(c)
                if c["verify_ms"] <= good_ms:
                    break  # 已经足够好，不再多打
            time.sleep(verify_gap)

        if good:
            good.sort(key=lambda x: x["verify_ms"])
            rest = [c for c in candidates if c not in shortlist]
            candidates = good + rest
        else:
            return current, delays.get(current), candidates, "verify-all-failed"

    return current, delays.get(current), candidates, None


def run_group(engine, g, dry_run=False, runner=None):
    ctx = controller_ctx(engine.cfg)
    epoch = runner.manual_epoch if runner is not None else 0
    res = {"at": datetime.now().strftime("%H:%M:%S"), "group": g["label"], "id": g["id"]}

    if not (ctx.get("unix") or ctx.get("host")):
        res.update(action="skip", message="Clash 未运行（找不到控制端口）")
        log("[%s] 跳过：找不到 Clash 控制端口" % g["label"])
        return res

    try:
        current, current_ms, candidates, flag = evaluate(ctx, g)
    except Exception as exc:
        res.update(action="error", message=str(exc))
        log("[%s] 测速失败 %s" % (g["label"], exc))
        return res

    res.update(current=current, current_ms=current_ms,
               candidates=[{k: v for k, v in c.items() if k != "priority"} for c in candidates[:40]],
               total=len(candidates))

    if flag == "current-good":
        cur_v = None
        for c in candidates:
            if c["name"] == current:
                cur_v = c.get("verify_ms")
                break
        msg = "当前节点 %s 验证通过（%s），保持不动" % (current, fmt_ms(cur_v or current_ms))
        res.update(action="keep", message=msg, best=current, best_ms=cur_v or current_ms)
        log("[%s] %s" % (g["label"], msg))
        return res

    if flag == "verify-all-failed":
        # 目标站点全都不通时，如果当前节点连基础测速都没响应，说明它已经死了，
        # 此时回退到基础延迟最好的节点，总比守着一个死节点强。
        if current_ms is None and candidates:
            fallback = candidates[0]

            if dry_run:
                msg = "DRY-RUN 将回退 %s -> %s (%s)" % (
                    current or "-", fallback["name"], fmt_ms(fallback["ms"]))
                res.update(action="dry-run", message=msg,
                           best=fallback["name"], best_ms=fallback["ms"])
                log("[%s] %s" % (g["label"], msg))
                return res

            if runner is not None and runner.manual_epoch != epoch:
                msg = "检测到手动切换，放弃回退"
                res.update(action="skip", message=msg)
                log("[%s] %s" % (g["label"], msg))
                return res

            try:
                api(ctx, "PUT", "/proxies/%s" % urllib.parse.quote(g["group"], safe=""),
                    {"name": fallback["name"]}, timeout=10)
                msg = "目标验证全失败且当前节点无响应，回退到 %s (%s)" % (
                    fallback["name"], fmt_ms(fallback["ms"]))
                res.update(action="switch", message=msg, best=fallback["name"],
                           best_ms=fallback["ms"], current=fallback["name"],
                           current_ms=fallback["ms"])
                log("[%s] %s" % (g["label"], msg))
                return res
            except Exception as exc:
                log("[%s] 回退切换失败：%s" % (g["label"], exc))

        msg = "候选节点全部未通过目标验证，保持 %s 不动" % (current or "-")
        res.update(action="skip", message=msg)
        log("[%s] %s" % (g["label"], msg))
        return res

    if len(candidates) < int(g["min_healthy"]):
        msg = "可用节点仅 %d 个（< %d），不切换" % (len(candidates), g["min_healthy"])
        res.update(action="skip", message=msg)
        log("[%s] %s" % (g["label"], msg))
        return res

    best = candidates[0]
    best_score = best["verify_ms"] or best["ms"]

    cur_verify = None
    for c in candidates:
        if c["name"] == current:
            cur_verify = c["verify_ms"]
            break
    cur_score = cur_verify or current_ms

    verify_on = bool(g.get("verify_url")) and int(g.get("verify_top", 0)) > 0
    if verify_on:
        # 验证模式下必须同类比较：当前节点没通过验证（None）就视为不可用
        keep = (
            cur_verify is not None
            and best.get("verify_ms") is not None
            and cur_verify <= best["verify_ms"] * float(g["keep_factor"]) + int(g["keep_offset_ms"])
        )
        cur_score = cur_verify
    else:
        keep = (
            is_node(current)
            and region_priority(current, g["regions"]) is not None
            and isinstance(cur_score, int) and cur_score > 0
            and cur_score <= best_score * float(g["keep_factor"]) + int(g["keep_offset_ms"])
        )

    tag = "[%s] " % g["label"]
    if keep:
        msg = "保持 %s (%s)，最优 %s (%s)" % (current, fmt_ms(cur_score), best["name"], fmt_ms(best_score))
        res.update(action="keep", message=msg, best=best["name"], best_ms=best_score)
        log(tag + msg)
        return res

    if dry_run:
        msg = "DRY-RUN 将切换 %s (%s) -> %s (%s)" % (current or "-", fmt_ms(cur_score),
                                                       best["name"], fmt_ms(best_score))
        res.update(action="dry-run", message=msg, best=best["name"], best_ms=best_score)
        log(tag + msg)
        return res

    if runner is not None and runner.manual_epoch != epoch:
        msg = "检测到手动切换，放弃本轮自动切换"
        res.update(action="skip", message=msg)
        log("[%s] %s" % (g["label"], msg))
        return res

    try:
        api(ctx, "PUT", "/proxies/%s" % urllib.parse.quote(g["group"], safe=""),
            {"name": best["name"]}, timeout=10)
    except Exception as exc:
        res.update(action="error", message="切换失败: %s" % exc)
        log(tag + "切换失败 %s -> %s : %s" % (current, best["name"], exc))
        return res

    msg = "切换 %s (%s) -> %s (%s) [%s]" % (current or "-", fmt_ms(cur_score),
                                            best["name"], fmt_ms(best_score), best["region"])
    res.update(action="switch", message=msg, best=best["name"], best_ms=best_score,
               current=best["name"], current_ms=best_score)
    log(tag + msg)
    return res


def switch_group_node(engine, gid, name):
    """手动把某个分组切到指定节点，并在 hold 时间内禁止自动切换。"""
    runner = engine.group(gid)
    if not runner:
        return {"ok": False, "error": "unknown group"}
    runner.manual_epoch += 1
    ctx = controller_ctx(engine.cfg)
    try:
        api(ctx, "PUT", "/proxies/%s" % urllib.parse.quote(runner.cfg["group"], safe=""),
            {"name": name}, timeout=10)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    hold = int(runner.cfg.get("manual_hold_seconds", 1800))
    runner.hold_until = time.time() + hold
    runner.status["current"] = name
    runner.status["current_ms"] = None
    runner.status["last_detail"] = {
        "action": "manual",
        "at": datetime.now().strftime("%H:%M:%S"),
        "message": "手动切换到 %s，锁定 %d 分钟" % (name, hold // 60),
    }
    log("[%s] 手动切换到 %s（锁定 %d 分钟）"
        % (runner.cfg.get("label", gid), name, hold // 60))
    return {"ok": True, "hold_seconds": hold}


def site_check(engine, gid, url, top=12):
    """按需诊断：某个网址在哪些节点上能打开（不会常驻轮询）。"""
    runner = engine.group(gid)
    if not runner:
        engine.site = {"running": False, "url": url, "gid": gid, "results": [],
                       "error": "unknown group"}
        return
    ctx = controller_ctx(engine.cfg)
    g = runner.cfg
    engine.site = {"running": True, "url": url, "gid": gid, "results": [], "error": None}

    try:
        data = api(ctx, "GET", "/proxies/%s" % urllib.parse.quote(g["group"], safe=""), timeout=10)
        all_nodes = [n for n in (data.get("all") or []) if is_node(n)]
        current = data.get("now") or ""

        # 优先复用上一轮已知的延迟排行，避免每次都对上百个节点做全量测速
        cached = [c.get("name") for c in (runner.status.get("candidates") or [])
                  if c.get("name") in all_nodes]
        delays = {}

        if len(cached) >= 4:
            ranked = cached
        else:
            def warm(name):
                return name, probe_delay(ctx, name, "https://www.gstatic.com/generate_204", 2000)

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                for name, ms in pool.map(warm, all_nodes[:60]):
                    if ms:
                        delays[name] = ms
            ranked = sorted(delays, key=lambda n: delays[n])

        shortlist = ([current] if current else []) + \
                    [n for n in ranked if n != current][:max(1, top - 1)]

        results = []
        for idx, name in enumerate(shortlist):
            ms = probe_delay(ctx, name, url, 8000)
            results.append({"name": name, "ms": ms, "warm": delays.get(name)})
            engine.site["results"] = results
            engine.site["progress"] = "%d/%d" % (idx + 1, len(shortlist))
            time.sleep(1)
    except Exception as exc:
        engine.site["error"] = str(exc)
    finally:
        engine.site["running"] = False


# ------------------------------------------------------------------ 引擎

class Runner(object):
    def __init__(self, engine, gcfg):
        self.engine = engine
        self.cfg = gcfg
        self.lock = threading.Lock()
        self.status = {"running": False, "last_run": None,
                       "last_detail": {"action": "none", "message": "尚未运行"}}
        self.next_at = time.time()
        self.hold_until = 0.0
        self.manual_epoch = 0

    def loop(self):
        while not self.engine.stopped:
            now = time.time()
            if (self.cfg.get("enabled") and now >= self.next_at
                    and now >= self.hold_until):
                self.run(block=True)
                self.next_at = time.time() + int(self.cfg["interval_seconds"])
            time.sleep(1)

    def run(self, block=False):
        def job():
            if not self.lock.acquire(blocking=False):
                return
            try:
                self.status["running"] = True
                epoch = self.manual_epoch
                res = run_group(self.engine, self.cfg, runner=self)
                if self.manual_epoch != epoch:
                    return
                self.status["last_detail"] = res
                self.status["last_run"] = res.get("at")
                self.status["current"] = res.get("current")
                self.status["current_ms"] = res.get("current_ms")
                self.status["candidates"] = res.get("candidates", [])
            except Exception as exc:
                self.status["last_detail"] = {"action": "error", "message": str(exc),
                                              "at": datetime.now().strftime("%H:%M:%S")}
            finally:
                self.status["running"] = False
                self.lock.release()

        if block:
            job()
        else:
            threading.Thread(target=job, daemon=True).start()
        self.next_at = time.time() + int(self.cfg["interval_seconds"])

    def snapshot(self):
        st = dict(self.status)
        st["config"] = self.cfg
        st["hold_remaining"] = max(0, int(self.hold_until - time.time()))
        return st


class Engine(object):
    def __init__(self):
        self.cfg = load_config()
        self.cfg["clash_dir"] = self.cfg.get("clash_dir") or detect_clash_dir()
        self.controller = detect_controller(self.cfg) or {}
        refresh_region_state(self.cfg, load_profile_servers(self.cfg.get("clash_dir")))
        self.stopped = False
        self.site = {"running": False, "url": "", "results": []}
        if not self.cfg.get("groups"):
            self.cfg["groups"] = self._bootstrap_groups()
        save_config(self.cfg)
        self.runners = {}
        for g in self.cfg["groups"]:
            self.runners[g["id"]] = Runner(self, g)
        self._started = False

    def add_group(self, name):
        name = (name or "").strip()
        if not name or name.upper() == "GLOBAL":
            return None
        if any(g.get("group") == name for g in self.cfg["groups"]):
            return None
        next_id = 1 + max([int(g["id"][1:]) for g in self.cfg["groups"]
                           if g["id"].startswith("g") and g["id"][1:].isdigit()] or [0])
        g = _normalize_group({"id": "g%d" % next_id, "label": name, "group": name,
                              "enabled": True, "interval_seconds": 900})
        self.cfg["groups"].append(g)
        save_config(self.cfg)
        runner = Runner(self, g)
        self.runners[g["id"]] = runner
        threading.Thread(target=runner.loop, daemon=True).start()
        log("新增分组：%s" % name)
        return g

    def remove_group(self, gid):
        for idx, g in enumerate(self.cfg["groups"]):
            if g["id"] != gid:
                continue
            self.cfg["groups"].pop(idx)
            save_config(self.cfg)
            runner = self.runners.pop(gid, None)
            if runner:
                runner.cfg["enabled"] = False
            log("移除分组：%s" % g.get("label", gid))
            return True
        return False

    def _bootstrap_groups(self):
        """首次运行时自动发现可管理的选择器分组。"""
        ctx = controller_ctx(self.cfg)
        try:
            data = api(ctx, "GET", "/proxies", timeout=5).get("proxies", {})
        except Exception:
            return []
        names = []
        for name, info in data.items():
            if info.get("type") != "Selector":
                continue
            if name.upper() == "GLOBAL":
                continue
            if (info.get("now") or "").upper() in ("DIRECT", "REJECT"):
                continue          # 本来就是直连的分组（国内网站/苹果服务等）不用管
            names.append(name)

        def score(n):
            s = 0
            if "手动" in n:
                s -= 10
            if "AI" in n.upper():
                s -= 8
            if "选择" in n:
                s -= 5
            return s

        order = list(data)
        names.sort(key=lambda n: (score(n), order.index(n)))

        groups = []
        for name in names[:6]:
            groups.append(_normalize_group({
                "id": "g%d" % (len(groups) + 1),
                "label": name,
                "group": name,
                "enabled": True,
                "interval_seconds": 900,
            }))
        return groups

    def start(self):
        if self._started:
            return
        self._started = True
        for r in self.runners.values():
            threading.Thread(target=r.loop, daemon=True).start()
        threading.Thread(target=self._watch_env, daemon=True).start()

    def _watch_env(self):
        """Clash 后启动 / 首次安装时，自动探测分组并接管。"""
        while not self.stopped:
            if not self.runners:
                self.controller = detect_controller(self.cfg) or {}
                groups = self._bootstrap_groups()
                if groups:
                    self.cfg["groups"] = groups
                    save_config(self.cfg)
                    for g in groups:
                        runner = Runner(self, g)
                        self.runners[g["id"]] = runner
                        threading.Thread(target=runner.loop, daemon=True).start()
                    log("自动发现 %d 个分组：%s" % (len(groups),
                                                "、".join(g["label"] for g in groups)))
            time.sleep(10)

    def group(self, gid):
        return self.runners.get(gid)

    def update_group(self, gid, patch):
        cfg = json.loads(json.dumps(self.cfg))
        for g in cfg["groups"]:
            if g["id"] != gid:
                continue
            for key in ("enabled", "group", "label", "interval_seconds", "min_healthy",
                        "keep_factor", "keep_offset_ms", "max_workers", "test_url",
                        "verify_url", "verify_top", "timeout_ms", "regions",
                        "verify_mode", "verify_good_ms", "manual_hold_seconds", "role"):
                if key in patch:
                    g[key] = patch[key]
            g = _normalize_group(g)
            for i, item in enumerate(cfg["groups"]):
                if item["id"] == gid:
                    cfg["groups"][i] = g
            self.cfg = cfg
            save_config(cfg)
            runner = self.runners.get(gid)
            if runner:
                runner.cfg = g
                runner.next_at = time.time() + int(g["interval_seconds"])
            log("[%s] 配置已更新：间隔 %ss，地区 %s，防抖 %.2f +%dms，验证 %d 个"
                % (g["label"], g["interval_seconds"], ",".join(g["regions"]),
                   float(g["keep_factor"]), int(g["keep_offset_ms"]), int(g.get("verify_top") or 0)))
            return g
        return None


# ------------------------------------------------------------------ 网页

PAGE = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Autonode</title>
<style>
:root{--bg:#0f1115;--card:#171a21;--line:#262b36;--fg:#e6e9ef;--dim:#8b93a7;--ok:#43c884;--warn:#e0b341;--bad:#e05a5a;--accent:#4c8dff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}
.wrap{max-width:1020px;margin:0 auto;padding:22px 18px 60px}
h1{font-size:17px;margin:0 0 3px}
.sub{color:var(--dim);font-size:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:14px}
.card h2{font-size:13px;margin:0 0 10px;color:var(--dim);font-weight:600}
.hd{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:14px}
.nav{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:16px}
.nav button{padding:8px 15px;border-radius:10px;border:1px solid var(--line);background:#171a21;color:var(--fg);font-size:13px;cursor:pointer}
.nav button.on{background:var(--accent);border-color:var(--accent);color:#fff}
button{background:#232936;color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:7px 13px;font-size:13px;cursor:pointer}
button:hover{border-color:#3a4358}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
button.ghost{background:transparent}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;background:#232936;color:var(--dim)}
.badge.ok{background:rgba(67,200,132,.15);color:var(--ok)}
.badge.warn{background:rgba(224,179,65,.15);color:var(--warn)}
.badge.bad{background:rgba(224,90,90,.15);color:var(--bad)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:760px){.grid{grid-template-columns:1fr}}
.muted{color:var(--dim)}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.big{font-size:17px;font-weight:600;word-break:break-all}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
label{display:block;margin:8px 0 4px;font-size:12px;color:var(--dim)}
input,select{background:#11141a;border:1px solid var(--line);color:var(--fg);border-radius:8px;padding:7px 10px;font-size:13px;width:100%}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.chip{display:flex;align-items:center;gap:5px;background:#11141a;border:1px solid var(--line);border-radius:999px;padding:4px 9px;font-size:12px;cursor:pointer}
.chip input{width:auto;margin:0}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:6px 4px;border-bottom:1px solid var(--line)}
th{color:var(--dim);font-weight:500;font-size:12px}
pre{background:#11141a;border:1px solid var(--line);border-radius:8px;padding:12px;max-height:60vh;overflow:auto;font-size:12px;margin:0;white-space:pre-wrap}
details summary{cursor:pointer;font-size:12px;color:var(--dim);margin-top:12px}
.ghd{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
.gname{font-weight:600}
.modal{position:fixed;inset:0;background:rgba(0,0,0,.6);display:flex;align-items:center;justify-content:center;padding:30px;z-index:50}
.modal[hidden]{display:none}
.modal .box{background:var(--card);border:1px solid var(--line);border-radius:12px;width:min(900px,100%);max-height:80vh;padding:16px;display:flex;flex-direction:column;gap:10px}
</style></head>
<body><div class="wrap">

<div class="hd">
  <div>
    <h1>Autonode</h1>
    <div class="sub" style="margin-bottom:4px">关闭窗口只是关掉页面，后台服务继续运行；要点「退出」才会真正停止。</div>
<div class="sub"><span id="state" class="badge">加载中</span> · <span id="ctl" class="muted"></span> · <span id="aistat" class="muted"></span> · <span class="muted" id="ver"></span></div>
  </div>
  <div class="row">
    <button id="logbtn" class="ghost">日志</button>
    <button id="restartbtn" class="ghost">重启服务</button>
    <button id="quitbtn" class="ghost">退出</button>
  </div>
</div>

<div class="nav">
  <button data-nav="groups" class="on">分组</button>
  <button data-nav="routes">分流规则</button>
  <button data-nav="sub">订阅</button>
  <button data-nav="site">站点诊断</button>
  <button data-nav="vpn">VPN</button>
</div>

<section id="sec-groups">
  <div class="card">
    <div class="row">
      <select id="addsel" style="flex:1"></select>
      <button id="addbtn">添加分组</button>
      <button id="newgroupbtn" class="ghost">新建分组</button>
      <button id="rescanbtn" class="ghost">扫描新分组</button>
    </div>
    <div class="muted" id="addmsg" style="margin-top:8px">从客户端已有分组里挑一个纳管；不在这里的分组不会被自动切换。</div>
  </div>
  <div id="gcards"></div>
</section>

<section id="sec-routes" hidden>
  <div class="card">
    <h2>分流规则（全局）</h2>
    <div class="muted" style="margin-bottom:8px">让指定网站走直连或某个分组。保存后点「应用」会重启内核（仅 Clash Verge 支持）。</div>
    <table><thead><tr><th style="width:150px">匹配方式</th><th>值</th><th style="width:190px">走向</th><th style="width:52px"></th></tr></thead>
    <tbody id="rt"></tbody></table>
    <div class="row" style="margin-top:10px">
      <select id="rt-type" style="width:150px">
        <option value="DOMAIN-SUFFIX">域名后缀</option>
        <option value="DOMAIN">完整域名</option>
        <option value="DOMAIN-KEYWORD">域名关键词</option>
        <option value="IP-CIDR">IP 段</option>
        <option value="PROCESS-NAME">进程名</option>
      </select>
      <input id="rt-value" placeholder="example.com" style="flex:1">
      <select id="rt-target" style="width:190px"></select>
      <button id="rt-add">添加</button>
      <button id="rt-ai" class="ghost">导入 AI 站点规则</button>
      <button class="primary" id="rt-apply">保存并应用</button>
    </div>
    <div class="muted" id="rt-msg" style="margin-top:8px"></div>
  </div>
</section>

<section id="sec-sub" hidden>
  <div class="card">
    <h2>订阅导入</h2>
    <div class="muted" style="margin-bottom:8px">粘贴订阅链接，先校验能否拉取，再交给客户端导入。挂载（系统代理/TUN）由客户端完成。</div>
    <div class="row">
      <input id="sub-url" placeholder="https://example.com/api/v1/client/subscribe?token=..." style="flex:1">
      <button id="sub-check">校验</button>
      <button class="primary" id="sub-import">导入</button>
      <button class="ghost" id="sub-rescan">同步分组</button>
    </div>
    <div class="muted" id="sub-msg" style="margin-top:8px"></div>
  </div>
</section>

<section id="sec-site" hidden>
  <div class="card">
    <h2>站点诊断</h2>
    <div class="muted" style="margin-bottom:8px">打不开某个网站时，测一下哪些节点能打开，再一键切换。只在你点击时运行。</div>
    <div class="row">
      <select id="site-group" style="width:220px"></select>
      <input id="site-url" placeholder="https://linkinghub.elsevier.com/" style="flex:1">
      <button id="site-run">测试</button>
    </div>
    <div class="muted" id="site-msg" style="margin-top:8px">未运行</div>
    <div id="site-res" style="margin-top:10px"></div>
  </div>
</section>

<section id="sec-vpn" hidden>
  <div class="card">
    <h2>系统 VPN</h2>
    <div class="muted">管理 macOS 里已配置的 VPN（L2TP / IKEv2 / IPSec / 第三方客户端）。Clash 内核不支持这些协议，所以它们不会出现在节点列表里，只能在这里连接/断开。勾选「保持」后每 60 秒检查一次，断线自动重连。</div>
    <div class="row" style="margin-top:10px">
      <button id="vpn-new" class="primary">新建 VPN</button>
      <button id="vpn-refresh">刷新</button>
      <a class="muted" href="x-apple.systempreferences:com.apple.Network-Settings.extension">打开系统设置 →</a>
    </div>
    <table style="margin-top:10px">
      <thead><tr><th>名称</th><th>类型</th><th>状态</th><th style="width:80px">保持</th><th style="width:100px"></th></tr></thead>
      <tbody id="vpn-body"></tbody>
    </table>
    <div class="muted" id="vpn-msg" style="margin-top:8px"></div>
  </div>
</section>

<div class="modal" id="vpnmodal" hidden>
  <div class="box">
    <div class="row" style="justify-content:space-between"><b>新建 VPN（生成配置描述文件）</b><button id="vpn-close" class="ghost">关闭</button></div>
    <div class="muted">macOS 不允许应用直接写系统 VPN 配置，这里生成 .mobileconfig，由系统弹窗确认安装。安装完成后点「刷新」即可管理。</div>
    <div class="grid">
      <div><label>名称</label><input id="vpn-name" placeholder="学校 VPN"></div>
      <div><label>类型</label><select id="vpn-type"><option value="IKEv2">IKEv2</option><option value="L2TP">L2TP over IPSec</option></select></div>
      <div><label>服务器</label><input id="vpn-server" placeholder="vpn.example.edu"></div>
      <div><label>账号</label><input id="vpn-account" placeholder="用户名"></div>
      <div><label>密码</label><input id="vpn-password" type="password"></div>
      <div><label>共享密钥（L2TP 需要）</label><input id="vpn-secret" type="password"></div>
    </div>
    <div class="row"><button class="primary" id="vpn-create">生成并安装</button><span class="muted" id="vpn-create-msg"></span></div>
  </div>
</div>

<div class="modal" id="regionmodal" hidden>
  <div class="box">
    <div class="row" style="justify-content:space-between"><b>未识别地区的节点</b><button id="rg-close" class="ghost">关闭</button></div>
    <div class="muted">选中地区后会记住，下次测速按新地区参与排序。</div>
    <div style="overflow:auto;max-height:55vh"><table><thead><tr><th>节点</th><th style="width:180px">地区</th></tr></thead>
    <tbody id="rg-body"></tbody></table></div>
    <div class="muted" id="rg-excluded" style="max-height:130px;overflow:auto"></div>
    <div class="muted" id="rg-msg"></div>
  </div>
</div>

<div class="modal" id="newgroupmodal" hidden>
  <div class="box">
    <div class="row" style="justify-content:space-between"><b>新建分组</b><button id="ng-close" class="ghost">关闭</button></div>
    <div class="muted">会写进 Clash Verge 的分组模板并重启内核（约 15 秒）。之后点「扫描新分组」纳管。</div>
    <label>分组名称</label><input id="ng-name" placeholder="例如 AI-Claude">
    <label>成员（可多选，按住 ⌘/Ctrl）</label>
    <select id="ng-members" multiple size="10" style="width:100%"></select>
    <div class="row"><button class="primary" id="ng-create">创建并应用</button><span class="muted" id="ng-msg"></span></div>
  </div>
</div>
<div class="modal" id="logmodal" hidden>
  <div class="box">
    <div class="row" style="justify-content:space-between"><b>运行日志</b><div class="row"><button id="logreload" class="ghost">刷新</button><button id="logclose" class="ghost">关闭</button></div></div>
    <pre id="logpre" class="mono"><!--LOGTAIL--></pre>
  </div>
</div>

</div>
<script>
var STATUS=null, CTL={}, ROUTES=[], RT_TARGETS=[], SITE={}, NAV='groups';
var PROVIDERS=[];

function loadProviders(){
  get('/api/presets/ai-providers').then(function(d){
    PROVIDERS = d.providers || [];
    if(STATUS){ var box=el('gcards'); if(box) box.dataset.sig=''; renderGroups(STATUS); updateGroups(STATUS); }
  });
}

function el(id){ return document.getElementById(id); }
function badge(t,c){ return '<span class="badge '+(c||'')+'">'+t+'</span>'; }
function post(u,b){ return fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})}).then(function(r){return r.json();}); }
function get(u){ return fetch(u,{cache:'no-store'}).then(function(r){return r.json();}); }

document.querySelectorAll('[data-nav]').forEach(function(b){
  b.onclick = function(){
    NAV = b.dataset.nav;
    document.querySelectorAll('[data-nav]').forEach(function(x){ x.classList.toggle('on', x===b); });
    ['groups','routes','sub','site','vpn'].forEach(function(n){ el('sec-'+n).hidden = (n!==NAV); });
    if(NAV==='routes') el('newgroupbtn').onclick = function(){
  el('newgroupmodal').hidden = false;
  el('ng-msg').textContent = '';
  get('/api/proxies').then(function(d){
    el('ng-members').innerHTML = (d.proxies||[]).map(function(n){
      var q = String(n).replace(/&/g,'&amp;').replace(/"/g,'&quot;');
      return '<option value="'+q+'">'+n+'</option>';
    }).join('');
  });
};
el('ng-close').onclick = function(){ el('newgroupmodal').hidden = true; };
el('newgroupmodal').onclick = function(e){ if(e.target===el('newgroupmodal')) el('newgroupmodal').hidden = true; };
el('ng-create').onclick = function(){
  var name = (el('ng-name').value||'').trim();
  var members = Array.from(el('ng-members').selectedOptions).map(function(o){ return o.value; });
  if(!name || !members.length){ el('ng-msg').textContent = '填名称并选成员'; return; }
  el('ng-msg').textContent = '创建中…';
  post('/api/groups/create',{name:name, members:members}).then(function(r){
    el('ng-msg').textContent = r.ok ? '已写入，内核重启中（约 15 秒后点「扫描新分组」）'
                                    : ('失败：' + (r.error||''));
  });
};

function openRegionModal(){
  el('regionmodal').hidden = false;
  el('rg-msg').textContent = '加载中…';
  get('/api/regions/unknown').then(function(d){
    var regs = d.regions || [];
    var opts = '<option value="">（未设置）</option>' + regs.map(function(r){
      return '<option value="' + r + '">' + r + '</option>';
    }).join('');
    var rows = (d.nodes || []).map(function(n){
      var q = String(n).replace(/&/g, '&amp;').replace(/"/g, '&quot;');
      return '<tr><td class="mono">' + n + '</td><td><select data-rg="' + q + '">' + opts + '</select></td></tr>';
    }).join('');
    el('rg-body').innerHTML = rows || '<tr><td colspan="2" class="muted">全部节点都已识别出地区</td></tr>';
    el('rg-msg').textContent = (d.nodes || []).length
      ? ('共 ' + d.nodes.length + ' 个未识别')
      : '所有真实节点都已识别出地区';
    var ex = d.excluded || [];
    el('rg-excluded').innerHTML = ex.length
      ? ('<div style="margin-top:10px">已排除的非节点条目（不参与测速）：</div>'
         + ex.map(function(x){ return '<div class="mono" style="font-size:12px">· ' + x.name + '</div>'; }).join(''))
      : '';
  }).catch(function(){ el('rg-msg').textContent = '加载失败'; });
}

if(el('rg-close')) el('rg-close').onclick = function(){ el('regionmodal').hidden = true; };
if(el('regionmodal')) el('regionmodal').onclick = function(e){
  if(e.target === el('regionmodal')) el('regionmodal').hidden = true;
};

document.addEventListener('change', function(e){
  var sel = e.target;
  if(!sel || !sel.matches || !sel.matches('select[data-rg]')) return;
  post('/api/regions/override', {name: sel.dataset.rg, region: sel.value}).then(function(){
    el('rg-msg').textContent = '已保存：' + sel.dataset.rg + ' → ' + (sel.value || '未设置');
  });
});

function loadVpns(){
  get('/api/vpn').then(function(d){
    var rows = (d.vpns||[]).map(function(v){
      var q = String(v.name).replace(/&/g,'&amp;').replace(/"/g,'&quot;');
      var on = (v.status === 'Connected');
      var on2 = (d.keep||[]).indexOf(v.name) >= 0;
      return '<tr><td>'+v.name+'</td><td>'+v.proto+'</td><td>'+v.status+'</td>'
        + '<td><input type="checkbox" data-keep="'+q+'"'+(on2?' checked':'')+'></td><td>'
        + (on ? '<button data-vpn="disconnect" data-name="'+q+'">断开</button>'
              : '<button data-vpn="connect" data-name="'+q+'">连接</button>')
        + '</td></tr>';
    }).join('');
    var tb = el('vpn-body');
    if(tb) tb.innerHTML = rows || '<tr><td colspan="5" class="muted">系统里没有找到 VPN 配置（可在系统设置里添加）</td></tr>';
    var msg = el('vpn-msg');
    if(msg) msg.textContent = (d.platform && d.platform !== 'Darwin') ? ('当前平台 ' + d.platform + ' 暂不支持') : '';
  }).catch(function(){});
}

if(el('vpn-refresh')) el('vpn-refresh').onclick = loadVpns;

if(el('vpn-new')) el('vpn-new').onclick = function(){
  el('vpnmodal').hidden = false;
  el('vpn-create-msg').textContent = '';
};
if(el('vpn-close')) el('vpn-close').onclick = function(){ el('vpnmodal').hidden = true; };
if(el('vpnmodal')) el('vpnmodal').onclick = function(e){
  if(e.target === el('vpnmodal')) el('vpnmodal').hidden = true;
};
if(el('vpn-create')) el('vpn-create').onclick = function(){
  var body = {
    name: (el('vpn-name').value || '').trim(),
    type: el('vpn-type').value,
    server: (el('vpn-server').value || '').trim(),
    account: (el('vpn-account').value || '').trim(),
    password: el('vpn-password').value,
    secret: el('vpn-secret').value
  };
  if(!body.name || !body.server){ el('vpn-create-msg').textContent = '名称和服务器必填'; return; }
  el('vpn-create-msg').textContent = '生成中…';
  post('/api/vpn/create', body).then(function(r){
    el('vpn-create-msg').textContent = r.ok
      ? '已生成，请在系统弹窗里点「安装」'
      : ('失败：' + (r.error || ''));
    if(r.ok) setTimeout(function(){ el('vpnmodal').hidden = true; loadVpns(); }, 2500);
  });
};

document.addEventListener('change', function(e){
  var c = e.target;
  if(!c || !c.matches || !c.matches('input[data-keep]')) return;
  post('/api/vpn/keep',{name:c.dataset.keep, enabled:c.checked}).then(function(){
    loadVpns();
  });
});

document.addEventListener('click', function(e){
  var t = e.target;
  if(!t || !t.closest) return;
  var b = t.closest('button[data-vpn]');
  if(!b) return;
  b.disabled = true;
  post('/api/vpn',{name:b.dataset.name, action:b.dataset.vpn}).then(function(r){
    if(!r.ok) alert('操作失败：' + (r.error || r.output || ''));
    setTimeout(loadVpns, 1500);
  });
});

loadProviders();
loadRoutes();
    if(NAV==='site' && STATUS) fillSiteGroups(STATUS);
    if(NAV==='vpn') loadVpns();
  };
});

var logTimer = null;

function loadLog(){
  var ctrl = window.AbortController ? new AbortController() : null;
  var timer = setTimeout(function(){ if(ctrl) ctrl.abort(); }, 5000);
  fetch('/api/log',{cache:'no-store', signal: ctrl ? ctrl.signal : undefined})
    .then(function(r){ if(!r.ok) throw new Error('HTTP '+r.status); return r.text(); })
    .then(function(t){ el('logpre').textContent = t || '（日志为空）'; })
    .catch(function(e){
      el('logpre').textContent += '\n\n[刷新失败：' + (e && e.name === 'AbortError' ? '请求超时' : e.message) + ']';
    })
    .then(function(){ clearTimeout(timer); });
}

function openLog(){
  el('logmodal').hidden = false;
  loadLog();
  if(logTimer) clearInterval(logTimer);
  logTimer = setInterval(loadLog, 3000);
}

function closeLog(){
  el('logmodal').hidden = true;
  if(logTimer){ clearInterval(logTimer); logTimer = null; }
}

el('logbtn').onclick = openLog;

el('quitbtn').onclick = function(){
  if(!confirm('退出后台服务？\n\n退出后自动选节点、AI 通道保活都会停止，网页也会无法访问。\n（关闭窗口不会停止服务，只有这个按钮会）')) return;
  post('/api/service',{action:'stop'}).then(function(){
    document.body.innerHTML = '<div style="padding:60px;text-align:center;color:#8b93a7">服务已退出。要重新启动：<br><br>'
      + '<code style="color:#e6e9ef">launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/*autonode.plist</code></div>';
  });
};

el('restartbtn').onclick = function(){
  if(!confirm('重启后台服务？页面会在几秒后断开，之后刷新即可重连。')) return;
  post('/api/service',{action:'restart'}).then(function(){
    el('state').textContent = '重启中…';
  });
};
el('logreload').onclick = loadLog;
el('logclose').onclick = closeLog;
el('logmodal').onclick = function(e){ if(e.target===el('logmodal')) closeLog(); };
document.addEventListener('keydown', function(e){ if(e.key==='Escape') closeLog(); });

/* ---------------- 分组 ---------------- */
function groupCard(g){
  var c = g.config, id = g.id;
  return '<div class="card gcard" data-gid="'+id+'">'
    + '<div class="ghd"><div><span class="gname">'+g.label+'</span> <span class="badge" data-role="state">-</span></div>'
    + '<div class="row"><button data-act="run">立即检测</button>'
    + '<button data-act="toggle" class="ghost">暂停</button>'
    + '<button data-act="remove" class="ghost">移除</button></div></div>'
    + '<div class="grid" style="margin-top:12px">'
    + '<div><div class="muted">当前节点</div><div class="big mono" data-role="current">-</div>'
    + '<div class="muted" data-role="meta">-</div><div class="muted" data-role="last">-</div></div>'
    + '<div><div class="muted">本轮结果</div><div data-role="action" style="margin:6px 0">-</div>'
    + '<div class="muted" data-role="msg">-</div></div></div>'
    + '<div style="margin-top:12px"><table><thead><tr><th>节点</th><th>地区</th><th style="width:70px">延迟</th><th style="width:84px">ChatGPT</th><th style="width:62px"></th></tr></thead>'
    + '<tbody data-role="cand"></tbody></table></div>'
    + '<details><summary>设置</summary><div class="grid">'
    + '<div><label>检查间隔</label><select data-field="interval_seconds"></select>'
    + '<label>测速地址</label><input data-field="test_url">'
    + '<label>AI 服务（验证用）</label><select data-field="verify_provider"></select>'
    + '<label>自定义验证地址（留空关闭验证）</label><input data-field="verify_url">'
    + '<label>手动切换后锁定(分钟)</label><input data-field="manual_hold_seconds" type="number" min="0" step="5">'
    + '</div><div>'
    + '<label>防抖系数</label><input data-field="keep_factor" type="number" step="0.05" min="1">'
    + '<label>防抖偏移(ms)</label><input data-field="keep_offset_ms" type="number" step="10" min="0">'
    + '<label>最少可用节点</label><input data-field="min_healthy" type="number" min="1">'
    + '<label>验证候选数</label><input data-field="verify_top" type="number" min="0">'
    + '</div></div>'
    + '<label style="margin-top:12px">地区偏好</label><div class="chips" data-role="regions"></div>'
    + '<div class="row" style="margin-top:12px"><button class="primary" data-act="save">保存设置</button><button class="ghost" data-act="regions">未识别地区…</button>'
    + '<span class="muted" data-role="save"></span></div></details></div>';
}

function fillGroupForm(card, g){
  var c = g.config;
  var sel = card.querySelector('[data-field="interval_seconds"]');
  if(!sel.options.length){
    [60,120,180,300,600,900,1800,3600].forEach(function(v){
      var o=document.createElement('option'); o.value=v; o.textContent=(v<3600?(v/60)+' 分钟':'1 小时'); sel.appendChild(o);
    });
  }
  sel.value = String(c.interval_seconds);
  ['test_url','verify_url'].forEach(function(k){ card.querySelector('[data-field="'+k+'"]').value = c[k] || ''; });
  card.querySelector('[data-field="keep_factor"]').value = c.keep_factor;
  card.querySelector('[data-field="keep_offset_ms"]').value = c.keep_offset_ms;
  card.querySelector('[data-field="min_healthy"]').value = c.min_healthy;
  card.querySelector('[data-field="verify_top"]').value = c.verify_top || 0;
  card.querySelector('[data-field="manual_hold_seconds"]').value = Math.round((c.manual_hold_seconds||1800)/60);
  card.querySelector('[data-field="role"]').value = c.role || 'general';
  var psel = card.querySelector('[data-field="verify_provider"]');
  if(psel){
    var opts = '<option value="">（不使用验证）</option>';
    opts += PROVIDERS.map(function(p){
      return '<option value="'+p.url+'">'+p.name+'</option>';
    }).join('');
    opts += '<option value="__custom">自定义…</option>';
    psel.innerHTML = opts;
    var hit = PROVIDERS.filter(function(p){ return p.url === (c.verify_url||''); })[0];
    psel.value = hit ? hit.url : ((c.verify_url||'') ? '__custom' : '');
    psel.onchange = function(){
      if(psel.value === '__custom'){ card.querySelector('[data-field="verify_url"]').focus(); return; }
      card.querySelector('[data-field="verify_url"]').value = psel.value;
    };
  }
  var box = card.querySelector('[data-role="regions"]'), cur = c.regions||[];
  box.innerHTML = (STATUS.region_choices||[]).concat(['未知']).map(function(r){
    var on = cur.indexOf(r)>=0 ? ' checked' : '';
    return '<label class="chip"><input type="checkbox" value="'+r+'"'+on+'>'+r+'</label>';
  }).join('');
}

function renderGroups(s){
  var box = el('gcards');
  var html = s.groups.map(groupCard).join('');
  if(box.dataset.sig !== s.groups.map(function(g){return g.id+g.label;}).join('|')){
    box.innerHTML = html;
    box.dataset.sig = s.groups.map(function(g){return g.id+g.label;}).join('|');
    s.groups.forEach(function(g){ fillGroupForm(box.querySelector('[data-gid="'+g.id+'"]'), g); });
  }
}

function updateGroups(s){
  s.groups.forEach(function(g){
    var card = document.querySelector('.gcard[data-gid="'+g.id+'"]'); if(!card) return;
    var st = g.status || {}, d = st.last_detail || {};
    var rb = card.querySelector('[data-role="role"]');
    if(rb){ rb.textContent = (g.config.role === 'ai') ? 'AI 通道' : '通用';
            rb.className = 'badge ' + (g.config.role === 'ai' ? 'warn' : ''); }
    card.querySelector('[data-role="current"]').textContent = st.current || '未知';
    card.querySelector('[data-role="meta"]').textContent = (st.current_ms ? st.current_ms+' ms' : '延迟未知');
    var hold = st.hold_remaining > 0 ? ' · 手动锁定 '+Math.ceil(st.hold_remaining/60)+' 分钟' : '';
    card.querySelector('[data-role="last"]').textContent = '上次运行：'+(st.last_run||'-')+(st.running?' · 测速中…':'')+hold;
    var map = {switch:['已切换','ok'],keep:['保持不变','ok'],skip:['已跳过','warn'],error:['出错','bad'],manual:['手动','ok'],'dry-run':['演练','warn'],none:['等待','']};
    var m = map[d.action]||['-',''];
    card.querySelector('[data-role="action"]').innerHTML = badge(m[0], m[1]);
    card.querySelector('[data-role="msg"]').textContent = d.message || '-';
    var rows = (st.candidates||[]).map(function(c){
      var q = c.name.replace(/"/g,'&quot;');
      return '<tr><td class="mono">'+c.name+'</td><td>'+c.region+'</td><td>'+c.ms+' ms</td><td>'
        + (c.verify_ms? c.verify_ms+' ms':'-') + '</td>'
        + '<td><button data-act="switch" data-node="'+q+'">切换</button></td></tr>';
    }).join('');
    card.querySelector('[data-role="cand"]').innerHTML = rows || '<tr><td colspan="5" class="muted">暂无数据</td></tr>';
    var tb = card.querySelector('[data-act="toggle"]');
    if(tb) tb.textContent = g.config.enabled ? '暂停' : '恢复';
  });
}

document.addEventListener('click', function(e){
  var t = e.target; if(!t || !t.closest) return;
  var btn = t.closest('.gcard [data-act]');
  if(!btn) return;
  var card = btn.closest('.gcard'), gid = card.dataset.gid, act = btn.dataset.act;
  var g = (STATUS.groups||[]).filter(function(x){return x.id===gid;})[0];
  if(act==='run'){ post('/api/run',{id:gid}); setTimeout(refresh,800); }
  else if(act==='toggle'){ post('/api/config',{id:gid,patch:{enabled:!g.config.enabled}}).then(refresh); }
  else if(act==='remove'){
    if(confirm('不再自动管理「'+g.label+'」？')){ post('/api/groups/remove',{id:gid}).then(function(){ refresh(); }); }
  }
  else if(act==='switch'){ post('/api/switch',{id:gid,name:btn.dataset.node}).then(function(){ setTimeout(refresh,600); }); }
  else if(act==='regions'){ openRegionModal(); }
  else if(act==='save'){
    var regions = Array.from(card.querySelectorAll('[data-role="regions"] input:checked')).map(function(i){return i.value;});
    var patch = {
      interval_seconds: parseInt(card.querySelector('[data-field="interval_seconds"]').value,10),
      test_url: card.querySelector('[data-field="test_url"]').value.trim(),
      verify_url: card.querySelector('[data-field="verify_url"]').value.trim(),
      keep_factor: parseFloat(card.querySelector('[data-field="keep_factor"]').value),
      keep_offset_ms: parseInt(card.querySelector('[data-field="keep_offset_ms"]').value,10),
      min_healthy: parseInt(card.querySelector('[data-field="min_healthy"]').value,10),
      verify_top: parseInt(card.querySelector('[data-field="verify_top"]').value,10),
      manual_hold_seconds: parseInt(card.querySelector('[data-field="manual_hold_seconds"]').value,10)*60,
      role: card.querySelector('[data-field="role"]').value,
      regions: regions
    };
    post('/api/config',{id:gid,patch:patch}).then(function(){
      card.querySelector('[data-role="save"]').textContent = '已保存';
      setTimeout(function(){ card.querySelector('[data-role="save"]').textContent=''; }, 2500);
    });
  }
});

el('addbtn').onclick = function(){
  var name = el('addsel').value;
  if(!name) return;
  post('/api/groups/add',{name:name}).then(function(r){
    el('addmsg').textContent = r.ok ? ('已添加：'+name) : '添加失败（可能已存在）';
    refresh();
  });
};
el('rescanbtn').onclick = function(){
  post('/api/groups/rescan',{}).then(function(r){
    el('addmsg').textContent = (r.added&&r.added.length) ? ('新增：'+r.added.join('、')) : '没有新分组';
    refresh();
  });
};

function loadAvailable(){
  get('/api/groups/available').then(function(r){
    var sel = el('addsel');
    var free = (r.groups||[]).filter(function(x){ return !x.managed; });
    sel.innerHTML = free.map(function(x){
      var q=String(x.name).replace(/&/g,'&amp;').replace(/"/g,'&quot;');
      return '<option value="'+q+'">'+q+'（当前：'+x.now+'）</option>';
    }).join('') || '<option value="">（没有可添加的分组）</option>';
  });
}

/* ---------------- 分流 ---------------- */
function loadRoutes(){
  get('/api/routes').then(function(d){
    ROUTES = d.routes || [];
    RT_TARGETS = d.targets || ['DIRECT'];
    var sel = el('rt-target');
    sel.innerHTML = RT_TARGETS.map(function(t){
      var q=String(t).replace(/&/g,'&amp;').replace(/"/g,'&quot;');
      return '<option value="'+q+'">'+t+'</option>';
    }).join('');
    renderRoutes(d);
    if(!sel.dataset.init){
      sel.dataset.init = '1';
      var ai = ((STATUS && STATUS.groups) || []).filter(function(g){ return (g.config.role||'') === 'ai'; })[0];
      var prefer = ai && ai.config.group;
      sel.value = (prefer && RT_TARGETS.indexOf(prefer) >= 0) ? prefer : (RT_TARGETS[0] || '');
    }
  });
}

document.addEventListener('change', function(e){
  var s = e.target;
  if(!s || !s.matches || !s.matches('select[data-rtt]')) return;
  var i = parseInt(s.dataset.rtt, 10);
  if(ROUTES[i]){ ROUTES[i].target = s.value; saveRoutes(); }
});
function renderRoutes(d){
  el('rt').innerHTML = (ROUTES||[]).map(function(r,i){
    var opts = RT_TARGETS.map(function(t){
      var q = String(t).replace(/&/g,'&amp;').replace(/"/g,'&quot;');
      return '<option value="'+q+'"'+(t === r.target ? ' selected' : '')+'>'+t+'</option>';
    }).join('');
    return '<tr><td>'+r.type+'</td><td class="mono">'+r.value+'</td>'
      + '<td><select data-rtt="'+i+'" style="width:100%">'+opts+'</select></td>'
      + '<td><button data-rtdel="'+i+'">删</button></td></tr>';
  }).join('') || '<tr><td colspan="4" class="muted">还没有规则</td></tr>';
  if(d && d.rules_uid === null) el('rt-msg').textContent = '提示：当前订阅没有「规则」模板，应用会失败。';
}
function saveRoutes(){ return post('/api/routes',{routes:ROUTES}).then(function(r){ ROUTES = r.routes||ROUTES; renderRoutes(); }); }
el('rt-add').onclick = function(){
  var v = (el('rt-value').value||'').trim(); if(!v) return;
  ROUTES.push({type:el('rt-type').value, value:v, target:el('rt-target').value});
  el('rt-value').value='';
  saveRoutes().then(function(){ el('rt-msg').textContent='已添加，点「保存并应用」生效'; });
};
document.addEventListener('click', function(e){
  var t=e.target; if(!t||!t.closest) return;
  var b=t.closest('button[data-rtdel]');
  if(b){ ROUTES.splice(parseInt(b.dataset.rtdel,10),1); saveRoutes(); }
});
el('rt-ai').onclick = function(){
  var target = el('rt-target').value || '';
  if(!target || target === 'DIRECT' || target === 'REJECT'){
    el('rt-msg').textContent = '先在「走向」里选一个分组（AI 规则不能导入到直连）';
    return;
  }
  get('/api/presets/ai').then(function(d){
    var have = {}; ROUTES.forEach(function(r){ have[r.type+'|'+r.value+'|'+r.target] = 1; });
    var added = 0;
    (d.domains||[]).forEach(function(dom){
      var key = 'DOMAIN-SUFFIX|'+dom+'|'+target;
      if(have[key]) return;
      ROUTES.push({type:'DOMAIN-SUFFIX', value:dom, target:target}); added++;
    });
    saveRoutes().then(function(){
      el('rt-msg').textContent = added ? ('已导入 '+added+' 条 AI 站点规则，点「保存并应用」生效')
                                       : 'AI 站点规则已存在';
    });
  });
};

el('rt-apply').onclick = function(){
  if(CTL.kind !== 'unix'){ el('rt-msg').textContent='分流规则应用依赖 Clash Verge 的配置目录'; return; }
  el('rt-msg').textContent = '正在写入并重启内核…';
  post('/api/routes',{routes:ROUTES}).then(function(){ return post('/api/routes/apply',{}); })
    .then(function(r){ el('rt-msg').textContent = r.ok ? '已写入，内核重启中（约 15 秒）' : ('失败：'+(r.error||'')); });
};

/* ---------------- 订阅 ---------------- */
el('sub-check').onclick = function(){
  var u=(el('sub-url').value||'').trim(); if(!u){ el('sub-msg').textContent='先填链接'; return; }
  el('sub-msg').textContent='校验中…';
  post('/api/subscribe/check',{url:u}).then(function(r){
    if(r.ok){ var i=r.info;
      el('sub-msg').textContent='可访问 · '+Math.round((i.size||0)/1024)+' KB · '
        +(i.clash?'看起来是 Clash 配置':'不像标准 Clash 配置（可能是 base64）')+' · 经由 '+i.via;
    } else el('sub-msg').textContent='失败：'+((r.info&&r.info.error)||'');
  });
};
el('sub-import').onclick = function(){
  var u=(el('sub-url').value||'').trim(); if(!u){ el('sub-msg').textContent='先填链接'; return; }
  if(CTL.kind === 'unix'){
    window.location.href='clash://install-config?url='+encodeURIComponent(u);
    el('sub-msg').textContent='已请求 Verge 导入：确认并启用后，点「同步分组」';
  } else if(navigator.clipboard){
    navigator.clipboard.writeText(u).then(function(){ el('sub-msg').textContent='已复制，去客户端里粘贴导入'; });
  } else {
    el('sub-msg').textContent='手动复制：'+u;
  }
};
el('sub-rescan').onclick = function(){
  post('/api/groups/rescan',{}).then(function(r){
    el('sub-msg').textContent=(r.added&&r.added.length)?('新增分组：'+r.added.join('、')):'没有新分组';
    refresh();
  });
};

/* ---------------- 站点诊断 ---------------- */
function fillSiteGroups(s){
  var sel=el('site-group');
  var cur=sel.value;
  sel.innerHTML=(s.groups||[]).map(function(g){
    var q=String(g.id).replace(/"/g,'&quot;');
    return '<option value="'+q+'">'+g.label+'</option>';
  }).join('');
  if(cur) sel.value=cur;
}
el('site-run').onclick = function(){
  var gid=el('site-group').value, u=(el('site-url').value||'').trim();
  if(!gid||!u){ el('site-msg').textContent='选分组 + 填网址'; return; }
  el('site-msg').textContent='测试中…'; el('site-res').innerHTML='';
  post('/api/sitecheck',{id:gid,url:u}).then(function(){ pollSite(); });
};
function pollSite(){
  get('/api/sitecheck').then(function(s){
    var gid=(STATUS.groups||[]).filter(function(g){return g.label===s.gid;})[0];
    var rows=(s.results||[]).map(function(x){
      var ok=x.ms?'<span style="color:var(--ok)">'+x.ms+' ms</span>':'<span style="color:var(--bad)">打不开</span>';
      var q=x.name.replace(/"/g,'&quot;');
      return '<tr><td class="mono">'+x.name+'</td><td>'+ok+'</td>'
        + '<td><button data-site-switch="'+q+'">切换</button></td></tr>';
    }).join('');
    el('site-res').innerHTML = rows?('<table><thead><tr><th>节点</th><th>结果</th><th style="width:62px"></th></tr></thead><tbody>'+rows+'</tbody></table>'):'';
    el('site-msg').textContent = s.running ? ('测试中 '+(s.progress||'')+' …')
      : (s.error?('出错：'+s.error):('完成，共 '+((s.results||[]).length)+' 个节点'));
    if(s.running) setTimeout(pollSite, 1500);
  });
}
document.addEventListener('click', function(e){
  var t=e.target; if(!t||!t.closest) return;
  var b=t.closest('button[data-site-switch]');
  if(b){
    post('/api/switch',{id:el('site-group').value, name:b.dataset.siteSwitch})
      .then(function(){ el('site-msg').textContent='已切换'; refresh(); });
  }
});

/* ---------------- 刷新 ---------------- */
var failCount = 0, retryTimer = null;

function setState(text, cls){
  var e = el('state');
  if(!e) return;
  e.textContent = text;
  e.className = 'badge ' + (cls || '');
}

function refresh(){
  var ctrl = window.AbortController ? new AbortController() : null;
  var timer = setTimeout(function(){ if(ctrl) ctrl.abort(); }, 4000);
  fetch('/api/status',{cache:'no-store', signal: ctrl ? ctrl.signal : undefined})
   .then(function(r){ if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); })
   .then(function(s){
    clearTimeout(timer);
    failCount = 0;
    STATUS = s;
    CTL = s.controller || {};
    el('ctl').textContent = CTL.kind==='unix' ? 'Clash Verge (unix socket)'
      : (CTL.kind==='tcp' ? ('控制器 '+CTL.target) : '未检测到客户端');
    setState('运行中', 'ok');
    if(el('ver')) el('ver').textContent = 'v' + (s.version || '');
    el('sub-import').textContent = (CTL.kind==='unix')?'在 Verge 中导入':'复制订阅链接';
    var ai = (s.groups||[]).filter(function(g){ return (g.config.role||'') === 'ai'; })[0];
    el('aistat').textContent = ai ? ('AI 通道：'+(ai.status.current||'-')+' · '+
      (ai.status.current_ms? ai.status.current_ms+' ms':'未测')) : '未配置 AI 通道';
    renderGroups(s);
    updateGroups(s);
    if(NAV==='site') fillSiteGroups(s);
    if(!el('addsel').options.length || el('addsel').options[0].value==='') loadAvailable();
   })
   .catch(function(){
    clearTimeout(timer);
    failCount++;
    if(failCount >= 3){ setState('连接失败', 'bad'); }
    else { setState('连接中…', 'warn'); }
    if(!retryTimer){
      retryTimer = setTimeout(function(){ retryTimer = null; refresh(); }, 1200);
    }
   });
}

document.addEventListener('visibilitychange', function(){
  if(!document.hidden){ failCount = 0; refresh(); }
});

refresh(); setInterval(refresh, 5000);
setTimeout(loadAvailable, 800);
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    engine = None

    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        eng = self.engine
        if path in ("/", "/index.html"):
            try:
                with open(LOG_FILE, "r", encoding="utf-8") as fh:
                    tail = "".join(fh.readlines()[-100:])
            except OSError:
                tail = "（暂无日志）"
            page = PAGE.replace("<!--LOGTAIL-->", html.escape(tail or "（暂无日志）"))
            return self._send(200, page, "text/html; charset=utf-8")
        if path == "/api/status":
            groups = []
            for gid, runner in eng.runners.items():
                snap = runner.snapshot()
                snap["id"] = gid
                snap["label"] = runner.cfg.get("label", gid)
                groups.append({"id": gid, "label": runner.cfg.get("label", gid),
                               "status": snap, "config": runner.cfg})
            body = {"enabled": eng.cfg["enabled"], "port": eng.cfg["port"],
                    "version": VERSION,
                    "controller": eng.controller,
                    "groups": groups, "region_choices": REGION_CHOICES}
            return self._send(200, json.dumps(body, ensure_ascii=False))
        if path == "/api/log":
            try:
                with open(LOG_FILE, "r", encoding="utf-8") as fh:
                    lines = fh.readlines()[-80:]
            except OSError:
                lines = ["（暂无日志）\n"]
            return self._send(200, "".join(lines), "text/plain; charset=utf-8")
        if path == "/api/nodes":
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            gid = (qs.get("id") or [""])[0]
            runner = eng.group(gid)
            if not runner:
                return self._send(404, json.dumps({"error": "unknown group"}))
            try:
                data = api(controller_ctx(eng.cfg), "GET",
                           "/proxies/%s" % urllib.parse.quote(runner.cfg["group"], safe=""),
                           timeout=10)
            except Exception as exc:
                return self._send(500, json.dumps({"error": str(exc)}, ensure_ascii=False))
            nodes = [n for n in (data.get("all") or []) if is_node(n)]
            return self._send(200, json.dumps({"now": data.get("now"), "nodes": nodes},
                                              ensure_ascii=False))
        if path == "/api/sitecheck":
            return self._send(200, json.dumps(self.engine.site, ensure_ascii=False))
        if path == "/api/groups/available":
            ctx = controller_ctx(eng.cfg)
            try:
                data = api(ctx, "GET", "/proxies", timeout=10).get("proxies", {})
            except Exception as exc:
                return self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
            managed = {g.get("group") for g in eng.cfg["groups"]}
            out = []
            for name, info in data.items():
                if info.get("type") not in ("Selector", "URLTest", "Fallback"):
                    continue
                if name.strip().upper() == "GLOBAL":
                    continue
                out.append({"name": name, "type": info.get("type"),
                            "now": info.get("now"), "managed": name in managed})
            return self._send(200, json.dumps({"ok": True, "groups": out}, ensure_ascii=False))
        if path == "/api/regions/unknown":
            ctx = controller_ctx(eng.cfg)
            try:
                data = api(ctx, "GET", "/proxies", timeout=10).get("proxies", {})
            except Exception as exc:
                return self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
            unknown = []
            excluded = []
            for name, info in data.items():
                ptype = info.get("type")
                if ptype in ("Selector", "URLTest", "Fallback", "Direct", "Reject", "Compatible",
                             "Pass", "PassRule", "RejectDrop"):
                    continue
                if not is_node(name):
                    excluded.append({"name": name, "type": ptype})
                    continue
                if detect_region(name) is None:
                    unknown.append(name)
            return self._send(200, json.dumps({"ok": True, "nodes": unknown,
                                               "excluded": excluded,
                                               "regions": REGION_CHOICES,
                                               "overrides": eng.cfg.get("region_overrides") or {}},
                                              ensure_ascii=False))
        if path == "/api/vpn":
            return self._send(200, json.dumps({
                "ok": True, "vpns": list_system_vpns(), "platform": platform.system(),
                "keep": eng.cfg.get("vpn_keep") or [],
                "interval": eng.cfg.get("vpn_interval", 60)}, ensure_ascii=False))
        if path == "/api/presets/ai-providers":
            return self._send(200, json.dumps(
                {"ok": True, "providers": [{"id": i, "name": n, "url": u} for i, n, u in AI_PROVIDERS]},
                ensure_ascii=False))
        if path == "/api/proxies":
            ctx = controller_ctx(eng.cfg)
            try:
                data = api(ctx, "GET", "/proxies", timeout=10).get("proxies", {})
            except Exception as exc:
                return self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
            names = [k for k, v in data.items()
                     if v.get("type") not in ("Selector", "URLTest", "Fallback", "Direct", "Reject", "Compatible")]
            return self._send(200, json.dumps({"ok": True, "proxies": names}, ensure_ascii=False))
        if path == "/api/presets/ai":
            return self._send(200, json.dumps({"ok": True, "domains": AI_DOMAINS},
                                              ensure_ascii=False))
        if path == "/api/routes":
            ctx = controller_ctx(eng.cfg)
            cur, uid = active_rules_uid(eng.cfg.get("clash_dir", ""))
            return self._send(200, json.dumps({
                "routes": eng.cfg.get("routes", []),
                "targets": list_targets(ctx),
                "rules_uid": uid,
                "active_profile": cur,
                "clash_dir": eng.cfg.get("clash_dir", ""),
            }, ensure_ascii=False))
        return self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            payload = {}

        if path == "/api/routes":
            routes = payload.get("routes")
            if isinstance(routes, list):
                clean = []
                for r in routes[:200]:
                    if not isinstance(r, dict):
                        continue
                    val = str(r.get("value") or "").strip()
                    tgt = str(r.get("target") or "").strip()
                    typ = str(r.get("type") or "DOMAIN-SUFFIX").strip().upper()
                    if val and tgt:
                        clean.append({"type": typ, "value": val, "target": tgt})
                self.engine.cfg["routes"] = clean
                save_config(self.engine.cfg)
            return self._send(200, json.dumps({"ok": True,
                                               "routes": self.engine.cfg.get("routes", [])},
                                              ensure_ascii=False))
        if path == "/api/subscribe/check":
            ok, info = fetch_subscription(str(payload.get("url") or "").strip())
            return self._send(200, json.dumps({"ok": ok, "info": info}, ensure_ascii=False))
        if path == "/api/regions/override":
            name = str(payload.get("name") or "").strip()
            region = str(payload.get("region") or "").strip()
            if not name:
                return self._send(400, json.dumps({"ok": False, "error": "缺少节点名"}, ensure_ascii=False))
            overrides = dict(self.engine.cfg.get("region_overrides") or {})
            if region:
                overrides[name] = region
            else:
                overrides.pop(name, None)
            self.engine.cfg["region_overrides"] = overrides
            save_config(self.engine.cfg)
            refresh_region_state(self.engine.cfg)
            return self._send(200, json.dumps({"ok": True, "overrides": overrides}, ensure_ascii=False))
        if path == "/api/vpn":
            res = vpn_action(str(payload.get("name") or ""), str(payload.get("action") or ""))
            return self._send(200, json.dumps(res, ensure_ascii=False))
        if path == "/api/vpn/create":
            name = str(payload.get("name") or "").strip()
            server = str(payload.get("server") or "").strip()
            kind = str(payload.get("type") or "IKEv2")
            if not name or not server:
                return self._send(400, json.dumps({"ok": False, "error": "需要名称和服务器地址"}, ensure_ascii=False))
            try:
                data = build_vpn_mobileconfig(name, kind, server,
                                              str(payload.get("account") or ""),
                                              str(payload.get("password") or ""),
                                              str(payload.get("secret") or ""))
            except Exception as exc:
                return self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
            out = os.path.join(tempfile.gettempdir(), "autonode-vpn-%d.mobileconfig" % int(time.time()))
            with open(out, "wb") as fh:
                fh.write(data)
            os.chmod(out, 0o600)
            subprocess.run(["open", out], capture_output=True)
            log("[VPN] 已生成配置描述文件：%s（等待系统确认安装）" % out)
            return self._send(200, json.dumps({"ok": True, "file": out}, ensure_ascii=False))
        if path == "/api/vpn/keep":
            name = str(payload.get("name") or "").strip()
            enabled = bool(payload.get("enabled"))
            keep = [n for n in (self.engine.cfg.get("vpn_keep") or []) if n != name]
            if enabled and name:
                keep.append(name)
            self.engine.cfg["vpn_keep"] = keep
            save_config(self.engine.cfg)
            log("[VPN] %s 保持连接：%s" % (name, "开" if enabled else "关"))
            return self._send(200, json.dumps({"ok": True, "keep": keep}, ensure_ascii=False))
        if path == "/api/groups/create":
            name = str(payload.get("name") or "").strip()
            members = [str(m) for m in (payload.get("members") or []) if str(m).strip()]
            if not name or len(members) < 1:
                return self._send(400, json.dumps({"ok": False, "error": "需要名称和至少一个成员"},
                                                  ensure_ascii=False))
            cur, guid = active_groups_uid(self.engine.cfg.get("clash_dir", ""))
            if not guid:
                return self._send(400, json.dumps({"ok": False, "error": "当前订阅没有「分组」模板，无法创建"},
                                                  ensure_ascii=False))
            custom = [g for g in self.engine.cfg.get("custom_groups", []) if g.get("name") != name]
            custom.append({"name": name, "members": members})
            try:
                written = write_groups(self.engine.cfg["clash_dir"], guid, custom)
            except Exception as exc:
                return self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
            self.engine.cfg["custom_groups"] = custom
            save_config(self.engine.cfg)
            threading.Thread(target=restart_verge, daemon=True).start()
            log("创建分组 %s（成员 %d 个），等待内核重启" % (name, len(members)))
            return self._send(200, json.dumps({"ok": True, "file": written, "restarting": True},
                                              ensure_ascii=False))
        if path == "/api/groups/add":
            g = self.engine.add_group(str(payload.get("name") or ""))
            return self._send(200, json.dumps({"ok": bool(g),
                                               "group": ({"id": g["id"], "label": g["label"]} if g else None)},
                                              ensure_ascii=False))
        if path == "/api/groups/remove":
            ok = self.engine.remove_group(str(payload.get("id") or ""))
            return self._send(200, json.dumps({"ok": ok}, ensure_ascii=False))
        if path == "/api/service":
            action = str(payload.get("action") or "")
            if action not in ("stop", "restart"):
                return self._send(400, json.dumps({"ok": False, "error": "unknown action"}))
            return self._send(200, json.dumps(service_control(action), ensure_ascii=False))
        if path == "/api/groups/rescan":
            added = rescan_groups(self.engine)
            return self._send(200, json.dumps({"ok": True, "added": added}, ensure_ascii=False))
        if path == "/api/routes/apply":
            cur, uid = active_rules_uid(self.engine.cfg.get("clash_dir", ""))
            if not uid:
                return self._send(400, json.dumps(
                    {"ok": False, "error": "当前订阅没有「规则」模板，无法写入"}, ensure_ascii=False))
            try:
                written = write_rules(self.engine.cfg["clash_dir"], uid,
                                      self.engine.cfg.get("routes", []))
            except Exception as exc:
                return self._send(500, json.dumps({"ok": False, "error": str(exc)},
                                                  ensure_ascii=False))
            threading.Thread(target=restart_verge, daemon=True).start()
            return self._send(200, json.dumps({"ok": True, "file": written},
                                              ensure_ascii=False))
        if path == "/api/sitecheck":
            gid = payload.get("id")
            url = (payload.get("url") or "").strip()
            if not url:
                return self._send(400, json.dumps({"ok": False, "error": "url required"}))
            if self.engine.site.get("running"):
                return self._send(200, json.dumps({"ok": True, "already": True}))
            threading.Thread(target=site_check, args=(self.engine, gid, url),
                             daemon=True).start()
            return self._send(200, json.dumps({"ok": True}))
        if path == "/api/switch":
            return self._send(200, json.dumps(
                switch_group_node(self.engine, payload.get("id"), payload.get("name")),
                ensure_ascii=False))
        if path == "/api/run":
            gid = payload.get("id")
            for rid, runner in self.engine.runners.items():
                if gid in (None, "", rid):
                    runner.run(block=False)
            return self._send(200, json.dumps({"ok": True}))
        if path == "/api/config":
            gid = payload.get("id")
            patch = payload.get("patch") or {}
            updated = self.engine.update_group(gid, patch)
            return self._send(200, json.dumps({"ok": bool(updated), "config": updated}, ensure_ascii=False))
        return self._send(404, json.dumps({"error": "not found"}))


# ------------------------------------------------------------------ 入口

def main(argv):
    if IS_WIN and getattr(sys, "frozen", False) and "--installed" not in argv:
        windows_self_install()
        return 0
    engine = Engine()

    if "--once" in argv or "--dry-run" in argv:
        target = None
        for a in argv:
            if a in ("--once", "--dry-run"):
                continue
            target = a
        out = []
        for gid, runner in engine.runners.items():
            if target and target not in (gid, runner.cfg.get("group")):
                continue
            out.append(run_group(engine, runner.cfg, dry_run="--dry-run" in argv))
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if "--serve" in argv:
        Handler.engine = engine
        port = int(engine.cfg["port"])
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        except OSError as exc:
            log("控制台启动失败（端口 %d）：%s" % (port, exc))
            return 1
        log("控制台已启动：http://127.0.0.1:%d（分组：%s）"
            % (port, "、".join(g["label"] for g in engine.cfg["groups"])))
        engine.start()
        threading.Thread(target=vpn_watchdog, args=(engine,), daemon=True).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        return 0

    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
