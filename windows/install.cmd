@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title Autonode - 安装

set "DEST=%APPDATA%\autonode"
set "SRC=%~dp0"
set "PYVER=3.12.7"
set "PYURL=https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-amd64.exe"

echo.
echo ============================================
echo  Autonode - Windows 安装
echo ============================================
echo.

rem ---------- 兼容性信息 ----------
for /f "delims=" %%v in ('powershell -NoProfile -Command "(Get-CimInstance Win32_OperatingSystem).Caption" 2^>nul') do set "OSNAME=%%v"
if not defined OSNAME set "OSNAME=%OS%"
echo  系统      : %OSNAME%
echo  架构      : %PROCESSOR_ARCHITECTURE%
echo  兼容性    : 需要 Windows 10/11 + 64 位；Python ^>= 3.8
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" (
  set "PYURL=https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-arm64.exe"
  echo  安装包    : ARM64 版本
) else (
  echo  安装包    : x64 版本
)
if /i "%PROCESSOR_ARCHITECTURE%"=="x86" (
  echo.
  echo  [!] 检测到 32 位系统，本工具未针对 32 位打包，建议换 64 位系统。
  echo.
)
echo.

rem ---------- 检测 Python ----------
echo ==^> 检测 Python
set "PY="
for %%C in (py python python3) do (
  if not defined PY (
    %%C -c "import sys;sys.exit(0 if sys.version_info[0]==3 else 1)" >nul 2>&1 && set "PY=%%C"
  )
)

if defined PY (
  for /f "delims=" %%V in ('%PY% -c "import sys;print(sys.version.split()[0])" 2^>nul') do set "PYFOUND=%%V"
  echo     已安装 Python !PYFOUND!  ^(命令: %PY%^)
) else (
  echo     未检测到 Python 3，开始自动安装 ...
  echo     将下载: %PYURL%
  echo     安装方式: 当前用户、静默、自动加入 PATH
  echo.

  where winget >nul 2>&1
  if !errorlevel! equ 0 (
    echo     [1/2] 尝试 winget ...
    winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
  ) else (
    echo     [1/2] 没有 winget，直接下载官方安装包 ...
  )

  rem winget 失败或不可用时，走官方安装包
  set "NEED_INSTALL=1"
  for %%D in (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%PROGRAMFILES%\Python312\python.exe"
    "%PROGRAMFILES%\Python311\python.exe"
  ) do (
    if exist %%D set "NEED_INSTALL="
  )

  if defined NEED_INSTALL (
    echo     [2/2] 下载并静默安装 Python %PYVER% ...
    powershell -NoProfile -Command "Invoke-WebRequest -Uri '%PYURL%' -OutFile '%TEMP%\python-setup.exe'" 2>nul
    if exist "%TEMP%\python-setup.exe" (
      "%TEMP%\python-setup.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_launcher=1
      del /q "%TEMP%\python-setup.exe" >nul 2>&1
    ) else (
      echo     [!] 下载失败
    )
  )

  rem 再找一遍
  for %%D in (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%PROGRAMFILES%\Python312\python.exe"
    "%PROGRAMFILES%\Python311\python.exe"
  ) do (
    if not defined PY if exist %%D set "PY=%%~D"
  )
  for %%C in (py python) do (
    if not defined PY (
      %%C -c "import sys;sys.exit(0 if sys.version_info[0]==3 else 1)" >nul 2>&1 && set "PY=%%C"
    )
  )
)

if not defined PY (
  echo.
  echo  [!] 自动安装未能完成。
  echo      请手动安装 Python 3.8+ 后重新运行： https://www.python.org/downloads/windows/
  echo      安装时务必勾选 "Add python.exe to PATH"
  echo.
  pause
  exit /b 1
)

for /f "delims=" %%V in ('%PY% -c "import sys;print(sys.version.split()[0])" 2^>nul') do set "PYFOUND=%%V"
for /f "delims=" %%P in ('%PY% -c "import sys;print(sys.executable)" 2^>nul') do set "PYPATH=%%P"

echo.
echo ==^> 部署程序
if not exist "%DEST%" mkdir "%DEST%"
copy /Y "%SRC%autonode.py" "%DEST%\autonode.py" >nul
if errorlevel 1 (
  echo     复制失败，请把整个文件夹解压后再运行本脚本
  pause
  exit /b 1
)

for /f "delims=" %%P in ('%PY% -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))"') do set "PYW=%%P"
if not exist "%PYW%" set "PYW=%PY%"

echo ==^> 创建开机自启与桌面快捷方式
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws=New-Object -ComObject WScript.Shell;" ^
  "$s=$ws.CreateShortcut([IO.Path]::Combine([Environment]::GetFolderPath('Startup'),'Autonode.lnk'));" ^
  "$s.TargetPath='%PYW%';$s.Arguments='\"%DEST%\autonode.py\" --serve';$s.WorkingDirectory='%DEST%';$s.WindowStyle=7;$s.Save();" ^
  "$u=[IO.Path]::Combine([Environment]::GetFolderPath('Desktop'),'Clash 节点控制台.url');" ^
  "Set-Content -Path $u -Value '[InternetShortcut]','URL=http://127.0.0.1:8765' -Encoding ASCII"

echo ==^> 启动服务
start "" "%PYW%" "%DEST%\autonode.py" --serve
timeout /t 3 >nul
start "" "http://127.0.0.1:8765/"

echo.
echo ============================================
echo  安装完成
echo    Python : %PYFOUND%  (%PYPATH%)
echo    程序   : %DEST%\autonode.py
echo    配置   : %DEST%\config.json
echo    控制台 : http://127.0.0.1:8765
echo.
echo  关闭窗口不会停止后台服务；
echo  要彻底停止请运行 uninstall.ps1
echo ============================================
echo.
pause
