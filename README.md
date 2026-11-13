# Autonode

<p align="center">
  <img src="assets/icon-256.png" width="120" alt="Autonode">
</p>

<p align="center">
  给 Clash 系客户端用的「节点自动选优 + AI 通道保活」小工具。
  <br>
  本地网页控制台，零依赖，不碰系统网络配置。
</p>

---

## 它解决什么问题

- **AI 站点对 IP 敏感**：ChatGPT / Claude / Gemini 会查 IP 异常，频繁换节点容易掉登录态
- **24×7 挂着不想手动切**：节点挂了要能自动兜底，但不能因为"另一个节点快 20ms"就乱换
- **出问题要能定位**：哪个站点打不开、哪些节点能打开、现在走的哪条线

Autonode 的思路是：**稳定优先于快**。AI 分组「粘滞」，只在验证失败时才换；通用分组才按延迟择优。

## 特性

- 🔁 **分组自动选优**：定时测延迟，在勾选的地区里挑最优，带防抖避免来回切
- 🧲 **AI 通道**：独立角色，验证通过就绝不换节点（避免 IP 漂移触发风控）
- 🔀 **分流规则**：域名 / IP 段 / 进程名 → 直连、拒绝或指定分组，一键写入 Clash Verge
- 🔍 **站点诊断**：打不开某站时，一键测出哪些节点能开，直接切过去
- 📥 **订阅导入**：粘贴订阅链接，校验后交给客户端导入
- 🖥 **本地控制台**：`http://127.0.0.1:8765`，可安装成桌面应用

## 支持的客户端

| 客户端 | 支持情况 |
|---|---|
| Clash Verge / Clash Verge Rev | 完整（unix socket、分流规则、订阅 deep link） |
| ClashX / Stash / Clash for Windows / mihomo | 节点管理与诊断（自动探测 TCP 9090/9091/9097/9099） |

## 快速开始

**macOS**

```bash
bash install.sh
```

或从 [Releases](https://github.com/shwenyu/Autonode/releases/latest) 下载
`Autonode-<version>.pkg`（未签名，首次需右键 → 打开）。

> 安装包不进仓库，只作为 Release 资产提供；仓库里只有源码和构建脚本。

**Windows**

双击 `windows/install.cmd`：自动检测 Python，缺失时用 winget / 官方安装包自动装好，然后部署、创建开机自启与桌面快捷方式。

想要不依赖 Python 的单文件 exe：在 Windows 上运行 `windows/build-exe.ps1`（PyInstaller，自带运行时）。

详细说明见 [windows/README.md](windows/README.md)。

## 工作原理

```
Clash 客户端 (mihomo 内核)
        ▲  unix socket / TCP + secret
        │
   Autonode ── 定时测速 ──▶ 选择一个节点
        │
        └── 本地 HTTP 控制台 (127.0.0.1:8765)
```

Autonode 不实现代理，只通过 mihomo 的 **external-controller** 读取分组、测速、切换节点。
系统代理 / TUN 由 Clash 客户端负责——这样不需要 root helper，也不会和客户端抢网络配置。

## 数据位置

| 平台 | 位置 |
|---|---|
| macOS | `~/.config/autonode/` + `~/Library/LaunchAgents/com.autonode.plist` |
| Windows | `%APPDATA%\autonode\` + 启动文件夹快捷方式 |

只读客户端接口，不上传任何数据。唯一的网络请求是测速地址（默认 gstatic）和你主动填写的订阅链接。

## 常见问题

**端口 8765 被占用** → 改 `config.json` 里的 `port`，重启服务。

**分流规则应用失败** → 当前订阅在 Clash Verge 里没有启用「规则」增强模板。

**AI 分组老是不换节点** → 这是设计如此（粘滞）。它的验证地址默认是 `chatgpt.com`，验证失败才会换。

**ClashX / Stash 连不上** → 在客户端里打开 `external-controller`，把端口和 secret 填进 `config.json`。

## 发布新版本

打 tag 即触发 GitHub Actions，自动构建两套安装包并上传到 Release：

```bash
git tag v1.1.1
git push origin v1.1.1
```

工作流见 [`.github/workflows/release.yml`](.github/workflows/release.yml)：

- **macOS**：`pkgbuild` 生成 `Autonode-<version>.pkg`（postinstall 会为当前用户铺好配置和 LaunchAgent）
- **Windows**：PyInstaller 生成 `Autonode.exe`（自带运行时），连同安装脚本打包成 `autonode-windows-<version>.zip`
- 两个 job 都用 `softprops/action-gh-release` 上传到同名 Release

> 产物未签名：macOS 需要右键打开，Windows 会触发 SmartScreen。

## 开发

```bash
python3 autonode.py --serve     # 后台 + 控制台
python3 autonode.py --once      # 跑一轮
python3 autonode.py --dry-run   # 只测速不切换
```

单文件、纯标准库，Python ≥ 3.8。

## 许可证

MIT
