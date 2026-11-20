# Autonode 数据结构与运行时层级

> 对应版本：v3.0.0
> 本文只描述「数据从哪里来、存在哪里、怎么流动」，不涉及 UI 细节。

## 1. 运行形态

```
launchd (com.autonode)
  └── /usr/bin/python3 ~/.config/autonode/autonode.py --serve
        ├── HTTP 控制台  127.0.0.1:8765   （无鉴权，仅本机）
        ├── Runner×N     每组一个调度线程（按 interval 触发 run_group）
        ├── vpn_watchdog 系统 VPN 保活（60s）
        ├── traffic_sampler  会话流量累计（2s）
        └── sub_poller   订阅可用性轮询（600s）
```

数据不落数据库，只有三类持久化介质：

| 介质 | 位置 | 内容 |
|---|---|---|
| 配置 | `~/.config/autonode/config.json` | 用户设置（见 §4） |
| 日志 | `~/.config/autonode/pick.log`（512KB 轮转） | 运行记录 |
| 备份 | `profiles.yaml.bak-autonode` 等 | 切换订阅前的快照 |

## 2. 三个数据源（只读）

```
┌─────────────────────────────┐
│ A. Clash Verge 文件层        │  ~/Library/Application Support/
│                             │    io.github.clash-verge-rev.clash-verge-rev/
│  profiles.yaml              │  ← 订阅清单：current + items[uid/type/name/url/extra]
│  profiles/<uid>.yaml        │  ← 每个订阅的节点定义（name/server/...）
│  profiles/<uid>.yaml        │  ← rules / proxies / groups 模板（prepend/append/delete）
│  clash-verge.yaml           │  ← 生成的运行配置（只读参考）
└─────────────────────────────┘
             │ 读
┌─────────────────────────────┐
│ B. mihomo 控制器            │  unix: /var/run/clash-verge-service/users/501/verge-mihomo.sock
│                             │  tcp : 9090/9097/9091/9099/9093/6170（带 secret 时 Bearer）
│  GET /version /configs      │  状态、TUN、端口、mode
│  GET /proxies /proxies/{n}  │  分组与节点、当前选择
│  GET /proxies/{n}/delay     │  单节点测速
│  GET /connections           │  活动连接（含 process、规则、出口链）
│  PUT /proxies/{n}           │  切换节点（唯一的写操作）
└─────────────────────────────┘
             │ 读
┌─────────────────────────────┐
│ C. macOS 系统层             │
│  route -n get default       │  默认路由（判断 TUN/系统 VPN 是否接管）
│  ifconfig / scutil --nc     │  隧道接口、系统 VPN 服务
│  lsof -iTCP                 │  按进程的连接数（无 Clash 时兜底）
│  nettop -J bytes_in/out     │  按进程累计流量
│  ps -axo comm               │  运行中的 VPN 客户端
│  preferences.plist          │  VPN 服务定义（scutil 看不到时兜底）
└─────────────────────────────┘
```

## 3. 一次「自动选优」的数据流

```
Runner(定时)
   │
   ▼
run_group(engine, group)
   ├─ evaluate()
   │    ├─ GET /proxies/{group}          → all[]、now
   │    ├─ 过滤 is_node + region_priority
   │    ├─ 并发 GET /proxies/{n}/delay    → 基础延迟
   │    ├─ [可选] 串行验证 verify_url     → 目标可用性
   │    └─ 返回 (current, current_ms, candidates[], flag, total_nodes)
   ├─ 阈值判断 floor = min(min_healthy, max(1, total//2))
   ├─ 防抖判断 keep = current_ms <= best_ms*keep_factor + keep_offset
   └─ [必要时] PUT /proxies/{group} {"name": ...}
            │
            ▼
      Runner.status（内存） → GET /api/status → 前端
```

## 4. config.json 字段树

```jsonc
{
  // —— 连接与身份 ——
  "socket": "…/verge-mihomo.sock",   // 控制器 unix socket
  "api_host": "127.0.0.1",           // TCP 兜底
  "api_port": 9090,
  "api_secret": "",
  "clash_dir": "…/clash-verge-rev",  // Verge 配置目录
  "port": 8765,                      // 本控制台端口
  "enabled": true,

  // —— 分组（Runner 的配置来源）——
  "groups": [
    {
      "id": "main",                  // 本地标识
      "label": "♻️ 手动选择节点",     // 显示名
      "group": "♻️ 手动选择节点",     // mihomo 分组名（唯一真身）
      "role": "general",             // ai | general（ai 走粘滞策略）
      "enabled": true,
      "interval_seconds": 300,
      "test_url": "https://www.gstatic.com/generate_204",
      "timeout_ms": 3000,
      "min_healthy": 3,              // 会被池子大小自适应下调
      "keep_factor": 1.3,            // 防抖系数
      "keep_offset_ms": 30,          // 防抖偏移
      "regions": ["日本","新加坡","美国"],
      "verify_url": "",              // 目标验证地址（空=关闭）
      "verify_top": 0,
      "verify_mode": "lazy",
      "verify_good_ms": 2000,
      "verify_timeout_ms": 8000,
      "verify_gap_seconds": 1.5,
      "manual_hold_seconds": 1800,   // 手动切换后锁定时长
      "max_workers": 8
    }
  ],

  // —— 分流（写入 Verge 的 rules 模板）——
  "routes": [
    { "type": "DOMAIN-SUFFIX", "value": "openai.com", "target": "🧲 AI" }
  ],

  // —— 自建分组（写入 Verge 的 groups 模板）——
  "custom_groups": [
    { "name": "AI-Claude", "members": ["lite-美国01", "pro-日本03"] }
  ],

  // —— 地区识别 ——
  "region_overrides": { "节点A": "日本" },
  "region_choices": ["日本","新加坡","…","未知"],

  // —— 系统 VPN ——
  "vpn_keep": ["Aida"],              // 需要保活的系统 VPN 名
  "vpn_interval": 60,

  // —— 订阅健康 ——
  "sub_health": {
    "RMWAJGSLqny0": {
      "samples": [ { "t": 1763…, "ok": true, "ms": 1006, "bytes": 88000, "nodes": 115, "code": 200 } ]
    }
  },
  "sub_poll_interval": 600
}
```

## 5. 运行时内存状态（不持久化）

| 变量 | 归属 | 生命周期 |
|---|---|---|
| `Engine.cfg` | 服务 | 进程存活期，变更时 save_config |
| `Engine.runners[gid]` | 服务 | 每个分组一个，含 `status` 与 `manual_epoch` |
| `SESSION_TRAFFIC` / `_CONN_LAST` | 服务 | 会话流量累计，**进程退出即清零** |
| `_REGION_STATE` | 服务 | overrides + name→server 映射 |
| `OV_RESULT` | 前端 | 每个分组最近一次测速结果 |
| `STATUS` / `ROUTES` / `RT_TARGETS` | 前端 | 当前页面的数据快照 |

## 6. API 一览

| 方法 | 路径 | 数据源 |
|---|---|---|
| GET | `/api/status` | Runner 内存 + 控制器活性 |
| GET | `/api/overview` | 控制器 /configs、/connections + 系统路由 |
| GET | `/api/regions/unknown` | 控制器 /proxies |
| GET | `/api/apps` | 控制器 /connections；无 Clash 时 lsof + nettop |
| GET | `/api/latency?id=` | 串行 3 次 /proxies/{node}/delay |
| GET | `/api/net-latency` | 系统直连 HTTPS 探测 |
| GET | `/api/vpn` | scutil / preferences.plist / route / lsof |
| GET | `/api/subscriptions` | profiles.yaml + sub_health |
| GET | `/api/routes` | 控制器 /proxies（目标）+ 配置文件（规则） |
| GET | `/api/tun` | 控制器 /configs |
| GET | `/api/presets/ai`、`/ai-providers` | 常量表 |
| POST | `/api/run`、`/api/switch`、`/api/config` | 控制器 PUT + config.json |
| POST | `/api/routes`、`/api/routes/apply` | rules 模板 → 重启 Verge |
| POST | `/api/groups/create`、`/add`、`/remove`、`/rescan` | groups 模板 / config.json |
| POST | `/api/subscriptions/poll`、`/activate` | 网络探测 / profiles.yaml |
| POST | `/api/service`、`/update/apply` | launchd / 下载安装 |
| POST | `/api/vpn`、`/vpn/keep`、`/vpn/create` | scutil / config / .mobileconfig |

## 7. 页面 → 数据映射

```
概览      → /api/overview (+ /api/latency | /api/net-latency)
分组      → /api/status、/api/groups/*、/api/config、/api/switch
分流规则  → /api/routes、/api/routes/apply
应用      → /api/apps
TUN       → /api/tun、/api/routes（进程规则）
VPN       → /api/vpn、/api/vpn/keep、/api/vpn/create、/api/vpn/open
订阅      → /api/subscriptions、/api/subscribe/check
```

## 8. 硬约束（设计前提）

1. **一个订阅生效**：mihomo 只加载 `profiles.yaml.current` 指向的订阅，其它订阅的分组在运行配置里不存在。跨订阅分流 = 切换订阅 + 重启 Verge。
2. **TUN 是全局的**：没有"部分 TUN"，只能靠规则或 `route-exclude-address` 收敛影响面。
3. **NE 应用不可控**：aTrust / EasyConnect / Shadowrocket 由 Apple 的 Network Extension 管理，只能感知状态与端口，无法代为登录或开关。
4. **写 Verge 的模板文件必须在客户端退出时进行**，否则会被它退出时覆盖。
