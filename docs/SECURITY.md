# 安全自查报告

> 版本：v2.2.0-beta.3
> 范围：`autonode.py`（单文件服务 + 内置 Web 控制台）、安装脚本、打包产物
> 方法：静态代码审计 + 黑盒请求验证（本机）

## 1. 信任边界

```
用户 ──浏览器──▶ 127.0.0.1:8765 ──▶ Python 服务（用户权限）
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
             mihomo 控制器        Verge 配置文件        macOS 系统命令
             (unix socket)       (profiles/*.yaml)    (scutil/lsof/route…)
```

- 服务以**当前用户**运行，没有 root 权限（TUN/内核由 Clash 的 root 服务负责）
- 控制台只监听 `127.0.0.1`，不对外网暴露
- 最敏感的能力：切换节点、改分流规则、重启 Clash Verge、下载并安装 pkg

## 2. 已修复的问题

| 编号 | 级别 | 问题 | 修复 |
|---|---|---|---|
| S1 | **高** | 控制台无来源校验：恶意网页可用表单 POST 触发 `/api/service`、`/api/update/apply` 等 | 校验 `Host` 与 `Origin`，不匹配返回 403；请求体上限 1 MB |
| S2 | **高** | 订阅内容（机场可控制节点名）直接拼进 `innerHTML`，可注入脚本 → 控制台被接管后可操控代理 | 新增 `esc()`，对节点名/分组名/规则值/主机名等 20 处动态内容统一转义 |
| S3 | **中** | `apply_update` 接受任意 URL 下载并交给安装器（可被 XSS 或本地脚本利用安装任意 pkg） | 限制 https + `github.com` / `objects.githubusercontent.com`，且只接受 `.pkg/.zip` |
| S4 | **中** | `service_control` 通过 `/bin/sh -c` 拼接 label（本地文件可控） | 改为 `subprocess` 参数数组，无 shell |
| S5 | **中** | `update_group` 对 patch 值不校验，传入对象会让 `int()` 抛异常或写入脏数据 | 逐字段试归一化，失败则丢弃；实测非法 `interval_seconds` 被拒绝 |
| S6 | **中** | `Content-Length` 非数字导致处理器崩溃 | 解析失败返回 400，长度上限校验 |
| S7 | **低** | `/api/vpn/open` 接受任意 bundle id，可被用来启动任意应用 | 白名单：仅允许已发现的 VPN/企业客户端 |
| S8 | **低** | 生成的 `.mobileconfig`（含明文 VPN 密码）长期留在临时目录 | `chmod 600` + 90 秒后自动删除 |
| S9 | **低** | 多线程同时 `save_config` 会互相覆盖（曾导致订阅健康数据丢失） | 加 `RLock` 串行化写入 |
| S10 | **低** | `load_config()` 白名单读取，重启丢失大量配置 | 改为通用合并（功能 bug） |

## 3. 已验证的防御

```bash
# 伪造 Host（DNS rebinding 尝试）
curl -H "Host: evil.com" http://127.0.0.1:8765/api/status        → 403
# 跨站 Origin（CSRF 尝试）
curl -X POST -H "Origin: http://evil.com" … /api/run             → 403
# 超大请求体
curl -X POST --data-binary @1.1MB /api/run                       → 413
# 非数字 Content-Length
printf 'POST … Content-Length: abc' | nc 127.0.0.1 8765          → 400
# 非法 bundle
POST /api/vpn/open {"bundle":"com.apple.finder"}                 → 400 未知应用
# 非法配置值
POST /api/config {"patch":{"interval_seconds":{"x":1}}}          → 被丢弃，原值不变
```

## 4. 已知残余风险（接受 / 需注意）

| 编号 | 级别 | 说明 | 建议 |
|---|---|---|---|
| R1 | 中 | **无鉴权**：任何本机进程都能调用 API（浏览器侧已被 Origin 拦住） | 如需更高隔离，可加一次性 token（写入 config，页面注入） |
| R2 | 中 | **更新安装 = 管理员权限执行 pkg**：若 GitHub Release 被篡改，可提权 | 长期应校验签名/哈希；当前仅信任 github.com 域名 |
| R3 | 低 | `config.json` 中 `api_secret`、`vpn` 密码等为明文 | 文件权限 600；不建议在多用户机器使用 |
| R4 | 低 | 订阅链接以 HTTPS 拉取，未做证书固定 | 机场本身即信任源，风险与客户端一致 |
| R5 | 低 | 日志包含节点名/域名，未加密 | 仅本机；logs 轮转 512 KB |
| R6 | 低 | 写入 Verge 模板前若客户端未退出，可能被覆盖（数据一致性，非安全） | 已提供 `.bak`；切换订阅流程会先退出客户端 |

## 5. 攻击面清单

| 入口 | 输入 | 处理 |
|---|---|---|
| HTTP API | JSON body、query | Host/Origin 校验、大小限制、字段白名单、路径不可控 |
| 订阅链接 | 机场返回的 YAML/base64 | 仅解析计数与字节，不执行；节点名渲染前转义 |
| 节点名 / 分组名 | mihomo 返回值 | `esc()` 转义后进入 DOM |
| profiles.yaml | 本地文件（Verge 写） | 只读解析；写入前备份；uid 强校验 |
| 外部命令 | 全部为固定 argv | 无 shell 拼接（S4 已修） |
| 更新下载 | GitHub Release 资产 | 域名白名单 + 类型白名单 |

## 6. 复现测试

```bash
cd <repo> && python3 tests/test_dryrun.py && python3 tests/test_minhealthy.py
# 手动：
#   1. 用浏览器控制台执行 fetch 到 http://127.0.0.1:8765/api/run（会被 Origin 拦）
#   2. 尝试非法 bundle / 超大 body / 伪造 Host，见 §3
```
