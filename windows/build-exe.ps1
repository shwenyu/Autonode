# 在 Windows 上生成单文件 exe（只需做一次）

前提：已安装 Python 3（https://www.python.org/downloads/windows/，安装时勾选 Add to PATH）。

在本目录打开 PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File build-exe.ps1
```

产物：`dist\Autonode.exe`（单文件，目标机器不需要装 Python）。

说明：

- 打包用的是 PyInstaller `--onefile --noconsole`，首次启动会比直接跑 .py 慢 1–2 秒（解压自身）。
- 未签名的 exe 可能被 Windows Defender/SmartScreen 拦一次，需要"仍要运行"。
- 如果杀软误报严重，改用 `--onedir`（生成文件夹，体积大一些但不自解压）。
- 代码里有 Windows 分支：控制器走 TCP 9090/9091/9097/9099，退出按钮直接结束进程（不依赖 launchctl）。
