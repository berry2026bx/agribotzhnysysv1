# DayuWriter 全新 Windows 11 电脑部署指南

本指南用于把当前项目完整部署到一台新的 Windows 11 电脑：写字机 Python 控制、D435i A 采集、A4 ArUco 纸面标定、实时红方块坐标显示，以及受限视觉跟随程序。它不假设新电脑会复用旧电脑的 `COM` 编号、USB 状态、Conda 路径或相机占用状态。

## 0. 成功标准与安全边界

按下列顺序验收，前一层未通过时不进入后一层：

```text
代码与 Python 环境 -> 离线测试 -> D435i 只读采集 -> CH340 只读状态
-> 5 mm 实机 XY -> 参考板 ready -> 红方块坐标显示 -> 受限视觉跟随
```

只有最后两项需要相机和纸板；只有“5 mm 实机 XY”及之后需要接 12 V。任何 USB 重插、12 V 断开、笔架手推、相机/纸板/P0 改变或疑似丢步后，停止自动动作并重新建立相应的物理基准。

## 1. 准备软件与硬件

### 软件

1. Git for Windows。
2. Anaconda 或 Miniconda。
3. VS Code 与 Microsoft Python 扩展。
4. Intel RealSense SDK 2.0 for Windows（已验证工作机使用 Viewer 2.58.1）。从 [librealsense 官方发布页](https://github.com/IntelRealSense/librealsense/releases) 获取，不因安装器提示而直接升级 D435i 固件。
5. 仅当设备管理器未正常识别写字机时，从 [WCH 官方 CH341SER 页面](https://www.wch-ic.com/downloads/CH341SER_EXE.html) 安装 CH340 驱动。

### 硬件

- DayuWriter USB 数据线和 D435i A 的短 USB 3.x 数据线。D435i 必须直连电脑的 USB 3.x 端口进行首次验证，不使用仅充电线或普通 USB 2.0 延长线。
- D435i A：序列号应为 `231122070403`。
- 固定到写字机纸面 P0 的 A4 六 ArUco 参考板。若重新打印，必须用 [a4-aruco-v3-300dpi.png](reference-board/a4-aruco-v3-300dpi.png) 实际尺寸打印，并测量 100 mm 标尺为 `99-101 mm`。
- 写字机 12 V 电源。电机电源只能接红色 CNC V3 的 `12-36V` 端子，红线接 `+`、黑线接 `-`；不要把 UNO 圆孔当作电机供电接口。

## 2. 获取代码并在 VS Code 打开

打开 **Anaconda Prompt** 或已经完成 Conda 初始化的 PowerShell：

```powershell
$dayuWorkspace = Join-Path $env:USERPROFILE 'Documents\DayuWriter'
git clone --branch codex/dayuwriter-recovery-execution --single-branch `
  https://github.com/berry2026bx/agribotzhnysysv1.git `
  $dayuWorkspace
Set-Location $dayuWorkspace
git branch --show-current
git log -1 --oneline
code .
```

预期分支是 `codex/dayuwriter-recovery-execution`。若电脑已存在此目录，进入目录后执行 `git status`，确认不会覆盖自己的未提交修改，再执行 `git pull --ff-only`。不要复制旧电脑的 `.conda` 目录，也不要只复制单个 Python 文件。

若 PowerShell 报 `Run 'conda init' before 'conda activate'`，在 Anaconda Prompt 执行一次：

```bat
conda init powershell
```

关闭并重新打开 PowerShell；或者直接继续使用 Anaconda Prompt。已有提示符显示 `(dayuwriter-control)` 时，用下面的 `python -c` 确认解释器，不要因为另一条初始化信息而盲目反复创建环境。

## 3. 创建并验证 Python 环境

在项目根目录执行：

```powershell
conda env create -f environment\dayuwriter-control.yml
conda activate dayuwriter-control
python -c "import sys, serial, numpy, pyrealsense2 as rs, cv2; assert hasattr(cv2, 'aruco'); print(sys.executable); print('pyserial', serial.__version__); print('numpy', numpy.__version__); print('pyrealsense2', rs.__file__); print('opencv', cv2.__version__)"
```

`environment/dayuwriter-control.yml` 当前指定 Python 3.11、pyserial、pytest、NumPy、`pyrealsense2` 和 `opencv-contrib-python`。使用 contrib 轮子是因为项目需要 `cv2.aruco`；同一个环境只保留一种 OpenCV wheel，不要同时安装 `opencv-python`、`opencv-contrib-python` 和 headless 变体。

若首次 `conda env create` 停在 pip 依赖阶段，先确认没有另一个终端同时安装该环境。网络恢复后，在已创建的同名环境中补齐依赖：

```powershell
conda activate dayuwriter-control
python -m pip install --only-binary=:all: --timeout 60 --retries 2 `
  numpy pyserial pytest pyrealsense2 "opencv-contrib-python>=4.13,<4.14"
```

重复运行上一段导入检查。它成功前，不连接任何真机。VS Code 中执行 `Ctrl+Shift+P` -> `Python: Select Interpreter`，选择 `dayuwriter-control`；终端中 `sys.executable` 必须来自该环境。

## 4. 先完成离线验证

下列测试使用假设备，不应打开 COM 口、相机或电机：

```powershell
$testTemp = Join-Path $env:USERPROFILE 'pytest-temp\dayuwriter-tests'
New-Item -ItemType Directory -Force (Split-Path $testTemp) | Out-Null
python -m pytest -q -p no:cacheprovider --basetemp $testTemp
```

若测试通过，先可启动不连硬件的 GRBL 教学界面：

```powershell
python -m communication.dayuwriter.grbl_monitor --port DEMO
```

`DEMO` 只是离线占位名。窗口可展示通信链路，但不创建真实串口活动，不能把它当作写字机连接测试。

## 5. 部署 D435i A：只读相机验证

1. 保持写字机 USB 和 12 V 均断开，只将 D435i A 直连 USB 3.x。
2. 打开 RealSense Viewer，确认名称为 `Intel RealSense D435I`、序列号为 `231122070403`、连接为 USB 3.x，并能分别打开 RGB 与 Stereo Module/Depth。
3. 记录 Viewer 显示的 SDK、固件和 USB 类型。不要因为 Viewer 提示就立即升级固件。
4. **关闭 Viewer** 和所有旧的 Python/浏览器仪表板进程，保证只有一个进程拥有相机。
5. 在项目根目录运行只读探测：

```powershell
python -m vision.realsense.camera_probe `
  --serial 231122070403 `
  --output docs\dayuwriter\baseline\camera-a-new-pc.json `
  --save-frames docs\dayuwriter\baseline\camera-a-new-pc-frames
```

输出 JSON 中的相机坐标为米，不是写字机 P0 坐标；该命令不打开 COM 口。若出现 `Frame didn't arrive within 5000`，先关闭 Viewer/旧 dashboard/其他 Python 相机进程，重新插到直连 USB 3.x，再只启动一次 `camera_probe`。深度值为 `0` 代表该像素没有有效深度，不能用于三维坐标计算。

## 6. 部署 DayuWriter：先 USB、后 12 V

### 6.1 识别 CH340

确认 12 V 断开，只接写字机 USB。运行：

```powershell
Get-CimInstance Win32_SerialPort |
  Select-Object DeviceID, Name, PNPDeviceID, Manufacturer
```

记录类似 `USB-SERIAL CH340 (COMx)` 的当前 `COMx`。不要把旧记录中的 `COM3` 或 `COM4` 写死到代码；新电脑、USB 插口和驱动都会改变端口编号。

关闭微雕管家、UGS、Arduino 串口监视器、旧控制台和另一份 `grbl_monitor`，因为串口只能由一个进程独占。使用实际端口启动：

```powershell
python -m communication.dayuwriter.grbl_monitor --port COMx
```

点击“连接并读取状态”。首次只发送实时 `?` 状态查询；界面应显示真实 `CALL`、`TX ?`、`RX <...>` 和 GRBL 状态。此步骤不运动。

### 6.2 5 mm 物理复验

在接 12 V 前确认：笔尖悬空、纸面和机械边界均无接触、皮带/同步轮/丝杆/XYZ 插头无松动、12 V 红黑线位于 CNC V3 的 `12-36V` 端子且极性正确、12 V 插头可立即拔下。将笔尖人工对准 P0。

接通 12 V 后观察无自发运动、异响、气味、火花或异常发热。只做一次 X 或 Y 的 `+5 mm` 按钮测试。成功证据需要：

```text
TX 的相对 Jog 命令
RX ok
最终 RX <Idle|...>
操作者看到笔架确实沿正确方向移动
```

`ok` 不等于物理完成；`MPos` 不是编码器位置。每次重新连接、断电或手推后，都要重新物理对准 P0。

## 7. 恢复 A4 参考板与实时坐标页面

参考板、背板和纸面若一直刚性固定到同一机械 P0，换电脑或仅重装相机不需要重画 P0；但必须让页面重新看见并验证六个标记。若板、纸面、P0 的相对位置、高度或倾角变化，先执行 [19-标定过程与经验](19-calibration-process-and-lessons.md) 第 4 节的 P0/X30/Y30 对齐和登记。

关闭 Viewer，固定 D435i A，使六个标记都清晰可见，然后启动：

```powershell
python -m vision.realsense.live_red_target_dashboard `
  --serial 231122070403 `
  --aruco-reference-board `
  --reference-registration docs/dayuwriter/calibration/camera-a-a4-aruco-registration.json `
  --port 8765
```

在浏览器打开 <http://127.0.0.1:8765/>。等待状态依次经过启动/收集，最终为 `ready`。运行条件是六 ID 完整、保留误差平均不超过 1.5 mm、最大不超过 3.0 mm；未达到时只处理相机、光照、遮挡和板固定，不发送写字机动作。页面始终是 `display_only`，没有 GRBL 串口权限。

将约 `10 x 10 mm`、平整、不反光的红方块放在纸面内。页面应在画面上显示检测框和 P0-XY。先把方块中心放在物理 P0，记录或刷新当前视觉基线；绝不复用相机、板或 P0 已改变时的旧基线。

## 8. 视觉跟随：先预览，再显式执行

仅在页面 `ready`、笔尖已物理对准 P0、12 V 接通、笔尖悬空、完整路径无障碍、相机/板/纸面未移动时，才允许考虑这一步。先预览，以下基线只是当前已记录示例：

```powershell
python -m communication.dayuwriter.visual_follow `
  --baseline-x 1.927 `
  --baseline-y 0.169
```

预览必须显示合理的目标、相对量和拟发送的 GRBL 分段，且明确为 preview。第一次执行只使用小距离 XY；需要固定 1 mm Z 下落时，再加入显式的 `--z-drop-mm 1`、`--execute`、`--physical-preflight` 和 `--z-drop-preflight`。完整边界和命令见 [17-visual-follow-first-operation.md](17-visual-follow-first-operation.md)。

不要将现有红方块演示当作杂草检测、抓取、三维目标高度控制或无人值守系统。任意相机帧超时、参考板丢失、红方块不在纸面、串口错误或动作异常，都应停止后续动作；机械紧急情况直接断开 12 V。

## 9. 日常启动最短清单

```powershell
conda activate dayuwriter-control
Set-Location "$env:USERPROFILE\Documents\DayuWriter"
python -m vision.realsense.live_red_target_dashboard --serial 231122070403 --aruco-reference-board --reference-registration docs/dayuwriter/calibration/camera-a-a4-aruco-registration.json --port 8765
```

另开一个终端，仅在需要写字机时启动：

```powershell
conda activate dayuwriter-control
Set-Location "$env:USERPROFILE\Documents\DayuWriter"
python -m communication.dayuwriter.grbl_monitor --port COMx
```

其中 `COMx` 永远以设备管理器当天读到的端口为准。相机页面和 GRBL 窗口可以并存，因为它们访问不同设备；同一台 D435i 或同一 COM 口不能同时被多个程序占用。

## 10. 交接记录

在新电脑的首次现场成功后，保存并提交：

- `camera-a-new-pc.json`、帧图和相机 Viewer 的型号/序列号/USB 记录。
- 当前 `USB-SERIAL CH340 (COMx)` 的设备管理器截图或文本输出。
- 5 mm XY 的命令、最终 `Idle` 与人工观察。
- 参考板 `ready` 状态的截图，包含六个标记和保留误差。
- P0 红方块的页面截图、视觉基线和一次预览输出。

这些记录让“在新电脑成功”成为可检查事实，而不是只依赖口头回忆。

