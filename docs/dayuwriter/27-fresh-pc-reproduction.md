# DayuWriter 全新 Windows 电脑复刻手册

## 0. 目标与原则

这份手册将代码、Python 环境、D435i A、CH340 写字机、A4 参考板和受监督视觉跟随复刻到新电脑。成功不是“安装完成”，而是按顺序得到可验证证据：

```text
代码版本和依赖导入
-> 离线测试
-> D435i Viewer RGB/Depth
-> Python dashboard ready
-> CH340 只读状态
-> 5 mm 实机运动
-> 红方块 P0-XY 显示
-> 一轮移动/停留/返回 P0
```

新电脑绝不能继承旧电脑的 COM 编号、PowerShell 环境路径、运行进程、相机占用状态或 P0 视觉基线。A4 板的物理登记记录可以随代码带来，但仅在同一台相机、同一块未改变的板和同一机械纸面关系下，且重新验证通过时才可用。

## 1. 安装项目外部软件

1. 安装 Git for Windows；若项目通过压缩包复制，也应至少保留包含 `.git` 的正式仓库副本，以便检查版本和更新。
2. 安装 Anaconda 或 Miniconda。项目目标是 Python `3.11`。
3. 安装 VS Code 及 Microsoft Python 扩展。
4. 从 Intel RealSense 官方 librealsense 发布页安装 Windows 版 RealSense SDK 2.0 / Viewer。不要因为 Viewer 显示提示就自动更新 D435i 固件；先记录现有版本并验证采集。
5. 仅当设备管理器不能正常识别写字机时，从 WCH 官方来源安装 CH340/CH341SER 驱动。驱动安装后重新插写字机 USB。

硬件首次验证应使用 D435i 的短 USB 3.x 数据线直连电脑，避免仅充电线、USB 2.0 延长线或未供电集线器。写字机首次设备识别时 12 V 保持断开。

## 2. 获取确定的项目版本

在 Anaconda Prompt 或已初始化的 PowerShell 中执行：

```powershell
$destination = Join-Path $env:USERPROFILE 'Documents\DayuWriter'
git clone --branch codex/dayuwriter-recovery-execution --single-branch `
  https://github.com/berry2026bx/agribotzhnysysv1.git `
  $destination
Set-Location $destination
git branch --show-current
git log -1 --oneline
code .
```

应看到分支 `codex/dayuwriter-recovery-execution`。如果目录已存在，先执行 `git status`，确认没有需要保留的未提交文件后才执行 `git pull --ff-only`。

如果 PowerShell 显示 `Run 'conda init' before 'conda activate'`，最简单的临时处理是使用 Anaconda Prompt；长期处理是在 Anaconda Prompt 中运行一次 `conda init powershell`，关闭并重新打开 PowerShell。不要因提示而删除已存在的环境。

## 3. 创建与修复 Python 环境

在项目根目录执行：

```powershell
conda env create -f environment\dayuwriter-control.yml
conda activate dayuwriter-control
python -c "import sys, serial, numpy, pyrealsense2 as rs, cv2; assert hasattr(cv2, 'aruco'); print(sys.executable); print('pyserial', serial.__version__); print('numpy', numpy.__version__); print('pyrealsense2', rs.__file__); print('opencv', cv2.__version__)"
```

环境文件需要 Python 3.11、`pyserial`、`pytest`、NumPy、`pyrealsense2` 与 `opencv-contrib-python`。`opencv-contrib-python` 必须提供 `cv2.aruco`；不要同时混装 `opencv-python`、`opencv-contrib-python` 和 headless 变体。

### 3.1 如果 Conda 停在 pip 依赖阶段

曾出现环境目录已创建但 NumPy 尚未装入的情况。先确认没有另一个终端同时在安装，再执行：

```powershell
conda activate dayuwriter-control
python -m pip install --only-binary=:all: --timeout 60 --retries 2 `
  numpy pyserial pytest pyrealsense2 "opencv-contrib-python>=4.13,<4.14"
```

重复上面的导入检查。若环境已能激活但 PowerShell 弹出 Base 的激活信息，以 `python -c "import sys; print(sys.executable)"` 的实际路径为准，不要猜测当前环境是否完整。

在 VS Code 按 `Ctrl+Shift+P`，选择 `Python: Select Interpreter`，选中 `dayuwriter-control` 对应的 Python 3.11 解释器。

## 4. 先做离线代码验收

下列命令不应打开 COM 口、D435i 或电机：

```powershell
$testTemp = Join-Path $env:USERPROFILE 'pytest-temp\dayuwriter-tests'
New-Item -ItemType Directory -Force (Split-Path $testTemp) | Out-Null
python -m pytest -q -p no:cacheprovider --basetemp $testTemp
```

过去 Windows 上默认 pytest 缓存目录曾导致无关的中断；关闭 cache provider 并显式指定用户可写临时目录是稳定的替代方式。测试通过仅证明代码逻辑；它不证明新电脑的相机、串口、供电或机械运动。

可选的无硬件演示：

```powershell
python -m communication.dayuwriter.grbl_monitor --port DEMO
```

`DEMO` 只是桌面教学界面的离线占位名，不会产生真实 TX/RX/MPos，也不等于写字机连接。

## 5. 先验证 D435i A，不接写字机 12 V

1. 只连接 D435i A 的 USB 3.x 数据线；先不要接写字机 USB 和 12 V。
2. 打开 RealSense Viewer，核对型号、序列号、USB 类型，并分别打开 RGB 与 Depth/Stereo 流。
3. 记录相机序列号、固件、Viewer/SDK 版本和 USB 类型。不要立即更新固件。
4. **关闭 Viewer**。Viewer 与 Python pipeline 并发会导致相机占用或帧超时。
5. 运行只读 Python 探测：

```powershell
python -m vision.realsense.camera_probe `
  --serial <Viewer 中实际序列号> `
  --output docs\dayuwriter\baseline\camera-new-pc.json `
  --save-frames docs\dayuwriter\baseline\camera-new-pc-frames
```

相机 XYZ 的单位是米，且是相机坐标，不是写字机 P0-XY。`depth=0` 表示该像素没有有效深度，不是整台相机必然损坏；项目探测程序会搜索邻近有效深度样本。`Frame didn't arrive within 5000` 常见于 Viewer/旧 Python 进程占用、USB/线缆不稳定，或错误地长期保留 frameset。先释放相机、重新插直连 USB 3.x、再只启动一个采集程序。

## 6. 部署写字机：先 USB、后 12 V

### 6.1 得到新电脑实际 COMx

保持 12 V 断开，接入写字机 USB：

```powershell
Get-CimInstance Win32_SerialPort |
  Select-Object DeviceID, Name, PNPDeviceID, Manufacturer
```

记录当天 `USB-SERIAL CH340 (COMx)`。不要把本项目历史的 `COM3`、`COM4` 或任何截图中的端口号写死。

关闭所有其他串口程序后执行：

```powershell
python -m communication.dayuwriter.grbl_monitor --port COMx
```

点击“连接并读取状态”，应看到实际 `TX ?` 与 `RX <...>`。这一阶段无需也不应有 12 V 或电机运动。

### 6.2 最小真机验证

确认笔尖悬空、机构无障碍、12 V 正确接入 CNC V3 的 `12-36V` 端子、可立即断电、P0 已人工对准。接通 12 V 后只做一次 `+5 mm` X 或 Y 检查。必须记录：命令、`ok`、最终 `Idle` 和人眼看到的方向/位移。成功后人工回 P0。

## 7. 在新电脑恢复 A4 参考板与网页

如果参考板、背板、纸面、P0 和写字机之间的物理关系与旧部署完全没有变化，可保留仓库中的参考登记文件，但仍需新启动 dashboard、六标记质量检查、P0 基线和 5 mm 复验。

如果相机、板、纸、P0 或写字机被移动，按 [25-几何变化重标定手册](25-geometry-change-recalibration-runbook.md) 重新登记；换 D435i B 时尤其不能使用 A 的相机标定或注册结果作为已验证事实。

关闭 Viewer 后：

```powershell
python -m vision.realsense.live_red_target_dashboard `
  --serial <本机验证的 D435i 序列号> `
  --aruco-reference-board `
  --reference-registration docs/dayuwriter/calibration/camera-a-a4-aruco-registration.json `
  --port 8765
```

打开 <http://127.0.0.1:8765/>。只有 `ready`、六 ID 完整、平均误差 `<=1.5 mm`、最大误差 `<=3.0 mm` 时才放红方块并记录本次 P0 视觉基线。之后使用 [24-不依赖 Codex 的代码操作手册](24-standalone-code-operation.md) 的预览和有限一轮命令。

## 8. 新电脑成功的交接包

新电脑第一次现场成功后，至少保留并提交：

```text
camera-new-pc.json 与保存帧
Viewer 型号/序列号/USB 类型记录
CH340 查询输出与实际 COMx
5 mm 运动的命令、Idle 和现场观察
dashboard ready 的截图（含六个标记与误差）
P0 红方块页面截图、浮点 baselineX/baselineY
一次预览和一轮实际视觉跟随的终端输出
```

这些文件使“新电脑已复刻”成为可核查的实验状态，而不只是安装完成的口头结论。
