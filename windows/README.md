# Autonode —— Windows

## 一步安装

双击 **`install.cmd`**（或右键 → 以管理员身份运行，非必须）。

它会：

1. 显示**兼容性信息**：系统版本、架构（x64 / ARM64）、所需 Python 版本
2. **检测 Python 3**
3. 没有就**自动安装**：
   - 优先 `winget install Python.Python.3.12`
   - 没有 winget 时，下载 python.org 官方安装包静默安装（当前用户、自动加 PATH）
4. 部署到 `%APPDATA%\autonode`
5. 建开机自启快捷方式 + 桌面「Clash 节点控制台」快捷方式
6. 启动后台服务并打开浏览器

装完窗口里会汇总：Python 版本与路径、程序位置、控制台地址。

> 兼容性：Windows 10/11 64 位，Python ≥ 3.8。32 位系统会提示但不建议使用。

## 可选：做成单文件 exe（分发给没装 Python 的人）

在**有 Python 的 Windows** 上跑一次：

```powershell
powershell -ExecutionPolicy Bypass -File build-exe.ps1
```

得到 `dist\Autonode.exe`。这个 exe **自带 Python 运行时**，双击即安装：

- 首次运行 → 复制自己到 `%APPDATA%\autonode\Autonode.exe`
- 建开机自启 + 桌面快捷方式
- 以 `--installed --serve` 启动自己
- 弹出**安装信息框**（系统版本、架构、安装位置、控制台地址）

因为内置了运行时，这条路径**不需要检测或安装 Python**。

> PyInstaller 不能跨平台编译，exe 必须在 Windows 上生成，macOS 做不出来。
> 未签名的 exe 首次运行会触发 SmartScreen，「更多信息 → 仍要运行」即可。

## 卸载

```powershell
powershell -ExecutionPolicy Bypass -File uninstall.ps1
```

删除自启与桌面快捷方式、结束进程；配置与日志保留在 `%APPDATA%\autonode`。

## 功能

| 功能 | Windows |
|---|---|
| 分组选优、手动切节点、锁定 | ✅ |
| 站点诊断 | ✅ |
| 分流规则 | ✅（写入 Verge 配置目录，需 Clash Verge） |
| 订阅导入 | ✅（Verge 用 deep link，其它客户端复制链接） |
| 退出 / 重启服务 | ✅（直接结束进程） |
| 开机自启 | ✅（启动文件夹快捷方式） |
| TUN / 系统代理 | 由 Clash 客户端负责，本工具不碰 |
