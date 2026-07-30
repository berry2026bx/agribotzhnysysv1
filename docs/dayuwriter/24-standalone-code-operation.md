# DayuWriter 不依赖 Codex 的代码操作手册

## 0. 本手册解决什么问题

本手册说明如何只使用 PowerShell、Python 和浏览器运行现有系统：

```text
D435i A RGB/深度帧
-> A4 六 ArUco 标记恢复纸面 P0-XY
-> 网页显示红方块坐标
-> visual_follow 读取网页 state.json
-> 受限 GRBL 相对 XY Jog
-> 可选：固定 1 mm Z+ 下落（单次模式）
```

它不需要 Codex，也不需要网页给写字机发送指令。网页服务只读相机并提供 `state.json`；`communication.dayuwriter.visual_follow` 才会在具有 `--execute`、`--port` 和人工前提标志时打开串口。

当前已验证的是：平整纸面内的红色方块坐标显示，以及在有人观察、人工 P0 和受限工作区下的 XY 跟随。它不是杂草识别、抓取、自动回零、闭环定位、自动 Z 高度规划或无人值守系统。

## 日常入口：不用终端、不用 Codex

日常操作优先双击：

```text
scripts\start_dayuwriter_gui.cmd
```

它会打开一个中文桌面窗口。窗口里只有四个日常动作：启动可视化、从 P0 启动自动跟随、停止自动跟随、打开标定手册。以后不需要用 VS Code 任务、PowerShell 参数或 `.cmd` 的内部逻辑；它们仅保留给排错。

从 P0 自动跟随前，在窗口中勾选现场确认。程序会启动/复用可视化页面，等到六标记与红方块可用后，把当前红方块坐标记录为 P0，之后才等待红方块位置改变。每轮只做 XY：去目标、停 10 秒、返回 P0，不会自动下 Z。

## 1. 每次先建立本次会话的变量

在 PowerShell 打开项目根目录。以下项目路径、解释器路径、相机序列号和 `COM4` 是这台已部署电脑的已成功样例；端口、P0 视觉基线和现场状态不是永久事实。

```powershell
$project = 'C:\Users\Administrator\Desktop\20260725DaZiJJJ\agribotzhnysysv1\.worktrees\dayuwriter-recovery-execution'
$py = 'C:\Users\Administrator\.conda\envs\dayuwriter-control\python.exe'
$cameraSerial = '231122070403'
Set-Location $project

& $py -c "import sys, serial, numpy, pyrealsense2 as rs, cv2; assert hasattr(cv2, 'aruco'); print(sys.executable); print('environment OK')"
```

最后一行必须显示 `environment OK`。这比依赖 `conda activate` 更可靠，尤其是在 PowerShell 尚未执行 `conda init` 时。

## 2. 启动相机与坐标可视化页面

### 2.0 最快入口：双击或 VS Code 一键安全启动

仓库现在提供了一个**不会运动**的启动器。它会检查 Python 依赖、枚举 D435i、启动 dashboard、打开浏览器；若 Windows 只找到一个 CH340 端口，还会打开 GRBL 监视器，但监视器仍处于未连接状态。

双击 Windows 资源管理器中的：

```text
scripts\start_dayuwriter_session.cmd
```

或在 VS Code 打开仓库根目录，按 `Ctrl+Shift+P`，选择 `Tasks: Run Task`，再选择：

```text
DayuWriter: Safe start dashboard and monitor
```

它只做显示和待连接监视器，不运行 `visual_follow`，不传递 `--execute`，不发送 GRBL Jog，也不接通 12 V。启动后仍须依次按第 2.2、3、4、5 节确认相机质量、P0、串口、12 V 和路径，才能手动运行任何动作命令。

如果启动器提示端口 `8765` 已被占用，说明旧 dashboard 仍在运行；回到旧 dashboard 窗口按 `Ctrl+C` 后再启动。若检测到多个 CH340，脚本不会猜测 COM 口，而是只启动网页并打印候选端口；按第 4.1 节人工确认实际端口。

### 2.0.1 已武装自动连续跟随（明确区别于安全启动）

当且仅当操作者已经确认下列现场事实：笔尖物理在 P0、12 V 已接、笔尖悬空、完整去目标与回 P0 路径净空、相机/参考板/纸面未移动，并且**红方块中心目前正放在 P0**，可双击：

```text
scripts\start_dayuwriter_auto_follow.cmd
```

或在 VS Code 的 `Tasks: Run Task` 选择：

```text
DayuWriter: Arm automatic visual follow from P0
```

该启动器会：启动 dashboard，等待 `ready` 和有效红方块；读取当前浮点坐标为本次 P0 基线；自动发现唯一 CH340；然后在一个可见终端运行连续 XY 跟随。它不运动当前 P0 红方块，因为实际命令包含 `--wait-for-target-change`；只有自动跟随窗口已经显示“armed”后，把红方块移到新位置才会开始运动。

每一轮的行为是：新位置保持三帧稳定 -> XY 移到方块 -> 停 10 秒 -> XY 返回 P0 -> 等待下一次方块移动至少 1 mm。该入口不传递 `--z-drop-mm`，不会自动下 Z；仍保留 `X [-190,190] mm`、`Y [-90,140] mm` 和 `500 mm/min` 上限。按自动跟随终端的 `Ctrl+C` 停止；可能停在非 P0 位置，必须人工检查并重新对准 P0。

本启动器不能通过软件确认笔尖实际在 P0、12 V、净空或纸板是否被移动；`-ArmAtP0` 只是操作者对这些物理前提的明确声明，不是传感器验证。

### 2.1 物理和进程前提

1. 将 D435i A 直连 USB 3.x 数据口；A4 六 ArUco 参考板、纸面与红方块应处于同一平面。
2. 固定相机，确保六个 ID `0..5` 都完整、清晰入镜；不能被笔架、胶带或红方块遮挡。
3. 关闭 RealSense Viewer、旧 dashboard、`camera_probe` 和其他打开 D435i 的程序。一个相机采集会话只能由一个进程拥有。
4. 写字机可以不接 12 V。本步骤不打开 COM 口，也不可能产生运动。

在终端 A 执行：

```powershell
Set-Location $project
& $py -m vision.realsense.live_red_target_dashboard `
  --serial $cameraSerial `
  --aruco-reference-board `
  --reference-registration docs/dayuwriter/calibration/camera-a-a4-aruco-registration.json `
  --port 8765
```

浏览器打开 <http://127.0.0.1:8765/>。终端 A 必须保持运行；按 `Ctrl+C` 才会停止网页和释放相机。

### 2.2 可接受的页面状态

不要因网页能打开就认为相机可用。展开“诊断状态”，仅在以下条件同时成立时使用坐标：

```text
state: ready
error: null
reference.state: ready
visible_marker_ids: 0, 1, 2, 3, 4, 5
mean_error_mm <= 1.5
max_error_mm <= 3.0
motion_permission: display_only
```

`display_only` 是设计要求，不是故障：它明确证明网页没有 GRBL 或串口运动能力。若出现 `camera_error`、`reference_lost`、`calibration_rejected` 或没有红方块坐标，先停止在相机/标定层排查，绝不启动 `visual_follow`。

页面为了观感把坐标显示为整数，并在不超过 1.5 秒的短暂图像缺口中标为“显示上次有效坐标”。控制程序不读取这份页面缓存；它只接受新的 `state.json` 中 `ready`、`mapping_state: available` 和完整浮点坐标。

## 3. 记录本次 P0 视觉基线

每个运行会话都必须把笔尖**物理**对准纸面 P0。GRBL `MPos` 是开环控制器状态，不是编码器测量；重启、断电、USB 重插、手推笔架、碰撞或疑似丢步后都不能用旧 `MPos` 代替这一步。

1. 使笔尖悬空且准确对准纸上 P0。
2. 把平整、非反光、约 `10 mm x 10 mm` 的红方块几何中心放在同一 P0。
3. 等页面稳定为 `ready` 并显示方块。
4. 在另一个 PowerShell 终端读取未四舍五入的本次基线：

```powershell
$p0 = Invoke-RestMethod 'http://127.0.0.1:8765/state.json'
if ($p0.state -ne 'ready' -or $p0.mapping_state -ne 'available' -or $null -eq $p0.machine_xy_mm) {
  throw 'Dashboard is not ready; do not record a P0 baseline.'
}
$baselineX = [double]$p0.machine_xy_mm.x
$baselineY = [double]$p0.machine_xy_mm.y
"P0 visual baseline: X={0:F3} mm, Y={1:F3} mm" -f $baselineX, $baselineY
```

历史记录中的 `1.927 / 0.169` 或 `0 / 0` 只是过去某一会话的例子，不能替换这里的新读数。页面上显示 `+2 / +0` 也不能替换控制用的精确变量。

## 4. 查询写字机身份，并做一次最小机械复验

### 4.1 只读查询

先保持 12 V 断开，只接写字机 USB。关闭微雕管家、UGS、Arduino 串口监视器、旧 Python 控制台和另一个 `grbl_monitor`。运行：

```powershell
Get-CimInstance Win32_SerialPort |
  Select-Object DeviceID, Name, PNPDeviceID, Manufacturer
```

从输出中找到当天的 `USB-SERIAL CH340 (COMx)`，例如：

```powershell
$port = 'COM4'  # 仅当天查询到的示例，必须替换为实际 COMx
& $py -m communication.dayuwriter.grbl_monitor --port $port
```

在桌面窗口中只点击“连接并读取状态”，确认出现真实 `TX ?`、`RX <...>`，且没有报警。然后退出窗口释放 COM 口。`grbl_monitor` 与 `visual_follow` 不能同时占用同一个 COM 口。

### 4.2 接通 12 V 后的 5 mm 复验

接通前人工确认：笔尖悬空、路径无障碍、皮带/同步轮/丝杆/轴线完好、12 V 接在红色 CNC V3 的 `12-36V` 端子（红线 `+`、黑线 `-`），并能立即断开 12 V。笔尖先物理对准 P0。

接通后只做一个小幅 `X+5 mm` 或 `Y+5 mm` 检查，然后人工回到 P0。成功证据必须同时包含：

```text
GRBL 返回 ok
最后状态为 Idle
现场观察到方向正确、实际发生约 5 mm 位移
```

`ok` 只表示命令被接受，不是运动完成；`Idle` 也不能替代人眼检查。出现异响、碰撞、发热、烧焦气味、方向异常或未动时，立即断开 12 V，停止下一条命令。

## 5. 先预览，再执行一次红方块 XY 移动

把红方块移到参考板纸面内的一个小目标位置；笔尖必须重新在 P0，且相机、参考板、纸面在第 3 节之后未动。先运行不会打开串口的预览：

```powershell
& $py -m communication.dayuwriter.visual_follow `
  --baseline-x $baselineX `
  --baseline-y $baselineY `
  --feed 500
```

输出的 `proposed delta` 必须与目标相对 P0 的方向和大致距离一致，并显示 `preview only; no serial port opened`。不一致时只可回到第 2 或第 3 节，不得用试错运动“校正”。

仅在同一时刻确认“笔尖在 P0、12 V 已接、笔尖悬空、完整 XY 路径净空、相机/纸板未动”后，执行：

```powershell
& $py -m communication.dayuwriter.visual_follow `
  --port $port `
  --baseline-x $baselineX `
  --baseline-y $baselineY `
  --feed 500 `
  --execute `
  --physical-preflight
```

程序会把较长位移拆成相对 Jog 并等待每段完成。此次单次模式完成后不会自动回 P0；观察笔尖实际位置，必要时人工回 P0，再开始另一项实验。

## 6. 可选：一次 XY 后固定下落 1 mm

只有第 5 节的同一会话已正确完成，且确认**至少 1 mm 向下净空**时，才可使用：

```powershell
& $py -m communication.dayuwriter.visual_follow `
  --port $port `
  --baseline-x $baselineX `
  --baseline-y $baselineY `
  --feed 500 `
  --z-drop-mm 1 `
  --execute `
  --physical-preflight `
  --z-drop-preflight
```

当前机械约定中 `Z+` 向下。此命令不是抓取或高度闭环：它只在 XY 成功后尝试固定 `Z+1 mm`，且最大值被代码限制为 1 mm。`Pn:P` 探针输入仍未排除根因，不能把它用于自动探测或自动 Z 标定。

## 7. 连续红方块跟随：移动、停 10 秒、返回 P0

连续模式只执行 XY。它在每次新目标上连续取得 3 个稳定样本，移动到目标，停留 10 秒，按已知相对量返回启动时的 P0，再等待红方块位置至少改变 1 mm。正常循环不包含 Z 动作。

先做一次有限、可监督的会话：

```powershell
& $py -m communication.dayuwriter.visual_follow `
  --port $port `
  --baseline-x $baselineX `
  --baseline-y $baselineY `
  --continuous `
  --wait-for-target-change `
  --return-to-p0 `
  --hold-at-target-seconds 10 `
  --max-moves 1 `
  --max-observations 120 `
  --feed 500 `
  --execute `
  --physical-preflight
```

只有该一轮从 P0 到目标、停留、物理返回 P0 都正确时，才可在**可见终端**中启动持续观察模式：

```powershell
& $py -m communication.dayuwriter.visual_follow `
  --port $port `
  --baseline-x $baselineX `
  --baseline-y $baselineY `
  --continuous `
  --wait-for-target-change `
  --until-stopped `
  --return-to-p0 `
  --hold-at-target-seconds 10 `
  --feed 500 `
  --execute `
  --physical-preflight
```

`--until-stopped` 只移除普通会话的次数和时间上限；它没有移除实时画面、三帧稳定、P0 相对工作区或 `500 mm/min` 上限。当前代码仍拒绝 P0 相对 `X [-190, 190] mm`、`Y [-90, 140] mm` 之外的目标。这是依据曾手工测得余量设置的保护，不应为方便而删除。

## 8. 停止、故障和代码入口

- 正常停止连续跟随：在运行 `visual_follow` 的可见终端按 `Ctrl+C`。它可能中断在目标处，先人工检查并重新物理对准 P0。
- 机械紧急情况：先断开 12 V；不要等待网页或 Python 响应。
- 相机失帧/网页 `camera_error`：`Ctrl+C` 停 dashboard，关闭 Viewer 和其他相机进程，检查 USB 3.x 线后重新启动第 2 节；网页端口还在监听不代表相机链路有效。
- 串口占用：完全退出另一个串口程序后重新查询 `COMx`；不要让两个程序竞争同一端口。

主要代码职责如下，日后修改时不要把二者混合：

| 文件 | 职责 | 允许的硬件权限 |
| --- | --- | --- |
| `vision/realsense/live_red_target_dashboard.py` | D435i、ArUco、红色目标、网页与 `state.json` | 只打开相机；没有串口代码 |
| `vision/realsense/aruco_reference_board.py` | 参考板几何、注册记录、质量门槛 | 纯视觉/文件 |
| `communication/dayuwriter/visual_follow.py` | 读取严格的 `state.json`，生成或显式执行 XY/Z Jog | 仅带 `--execute` 时打开串口 |
| `communication/dayuwriter/grbl_controller.py` | 持久串口、GRBL `ok` 与最终状态等待 | 串口 |
| `communication/dayuwriter/workspace.py` | 分段与软件工作区检查 | 无硬件 |

离线测试不得连接真实 COM 口或 D435i：

```powershell
$testTemp = Join-Path $env:USERPROFILE 'pytest-temp\dayuwriter-tests'
New-Item -ItemType Directory -Force (Split-Path $testTemp) | Out-Null
& $py -m pytest -q -p no:cacheprovider --basetemp $testTemp
```

当前完整测试集验证代码逻辑，不是新的机械或标定证据。每次真机操作仍必须按本手册的当次物理前提执行。
