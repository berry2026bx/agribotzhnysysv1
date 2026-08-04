# DayuWriter 重启恢复、重标定与助手复盘手册

## 0. 本文的用途和结论边界

本文把三件事合并为一份可执行手册：

1. 电脑、写字机和 D435i A 重启后的完整恢复顺序。
2. 相机、写字机、参考板或纸面发生变化后的重标定规则。
3. 本次协作中助手造成的失误、项目暴露的经验，以及已采取的改进。

当前可重复的能力是：**在固定的 A4 参考板纸面内，显示红色方块的 P0-XY；在人工前提、范围限制和观察下，执行一次受限 XY 跟随，可选固定 1 mm Z+ 下落。**

它不是杂草识别系统、抓取系统、自动回零系统、可靠三维接触系统或无人值守作业系统。任何操作步骤都不能扩大这一结论。

## 1. 重启后必须重新确认的事实

重启不会改变项目代码，却会使下列运行事实不再自动成立：

| 项目 | 重启后为什么需要确认 | 确认方法 |
| --- | --- | --- |
| 机械 P0 | 写字机没有编码器和已验证的自动回零；GRBL MPos 不是物理测量 | 人工把笔尖对准 P0 |
| 写字机 COM 口 | Windows 会重新枚举 CH340，端口号不是永久编号 | 设备管理器或 PowerShell 查询 |
| D435i 会话 | RealSense 进程、USB 枚举和帧流会在重启后重建 | 启动一个新的 dashboard，等 `ready` |
| 视觉 P0 基线 | 即使参考板不变，重新取帧后的目标分割/纸面映射仍可能有小偏移 | 红方块放 P0，读出本次页面 X/Y |
| 运动许可 | 12 V、笔尖高度、路径、纸板和相机状态均为现场条件 | 每次动作前现场检查 |

参考板到写字机的物理登记可以在板、纸面、背板和 P0 都未改变时复用；这与机械 P0 和本次视觉基线仍需重新确认并不矛盾。

## 2. 重启后的完整运行流程

### 2.1 物理预检查：先不接 12 V

1. 将 D435i A 接到电脑的直连 USB 3.x 端口。相机序列号应为 `231122070403`。
2. 写字机 USB 可以接入；CNC V3 的 12 V 保持断开。
3. 关闭 RealSense Viewer、旧的视觉网页服务、UGS、微雕管家、Arduino 串口监视器和旧 Python 程序。
4. 确认 A4 六 ArUco 参考板固定、平整，纸面目标与板在同一平面；六个标记没有被笔架、胶带或物体遮挡。
5. 人工将笔尖准确对准纸上 P0。重启、断电、手推或疑似丢步后，这一步不能省略。

若发生机械碰撞、皮带/同步轮/丝杆改动或电机线拆装，除本节外还必须复查机械紧固并做 X/Y 小幅方向测试。

### 2.2 使用固定解释器，避免 Conda 初始化问题

下面路径是当前电脑的已验证环境。使用它可避免 PowerShell 中 `conda activate` 尚未初始化的问题。若项目被迁移到别处，只改 `$project`，不要修改代码中的端口或序列号。

```powershell
$project = 'C:\Users\Administrator\Desktop\20260725DaZiJJJ\agribotzhnysysv1\.worktrees\dayuwriter-recovery-execution'
$py = 'C:\Users\Administrator\.conda\envs\dayuwriter-control\python.exe'

Set-Location $project
& $py -c "import serial, numpy, pyrealsense2, cv2; assert hasattr(cv2, 'aruco'); print('environment OK')"
```

若这条导入检查失败，不连接真机运动；先按 [21-全新电脑部署指南](21-new-computer-deployment.md) 修复环境。

### 2.3 终端 A：启动 D435i 实时视觉页面

在项目根目录运行，保持该终端不关闭：

```powershell
& $py -m vision.realsense.live_red_target_dashboard `
  --serial 231122070403 `
  --aruco-reference-board `
  --reference-registration docs/dayuwriter/calibration/camera-a-a4-aruco-registration.json `
  --port 8765
```

浏览器打开 <http://127.0.0.1:8765/>。程序会丢弃启动帧并收集完整的参考板帧；此时不要晃动相机或纸板。

只有页面满足全部条件，才进入下一步：

```text
state: ready
error: null
visible_marker_ids: 0, 1, 2, 3, 4, 5
mean_error_mm <= 1.5
max_error_mm <= 3.0
motion_permission: display_only
```

`display_only` 是正确的安全状态：该网页没有 GRBL 或串口权限。若看到 `camera_error`、`reference_lost` 或 `calibration_rejected`，停止在视觉步骤处理，不要尝试运行写字机。

RealSense 运行遵循官方 `pyrealsense2` 生命周期：启动 pipeline 后取得帧、把深度对齐到彩色，结束或异常后释放 pipeline。实际操作上等价于：**Viewer 与 dashboard 不同时运行；相机断连后停止旧 dashboard，再只启动一个新 dashboard。** 参考：[官方 align-depth2color 示例](https://github.com/realsenseai/librealsense/blob/master/wrappers/python/examples/align-depth2color.py)。

### 2.4 记录本次视觉 P0 基线

1. 放置平整、非反光、约 `10 x 10 mm` 的红色方块，使其几何中心位于物理 P0。
2. 等页面稳定显示目标，记录画面侧栏的 X、Y，例如 `X=... mm, Y=... mm`。
3. 将这两个数称为本次 `baseline-x`、`baseline-y`。它们是视觉残余偏移，不是机械原点。

不要盲用历史示例 `1.927 / 0.169`。只有在相机、纸板、纸面和 P0 完全未改变时，它才可能仍接近可用；本流程仍要求每次重启后重新读取本次值。

### 2.5 终端 B：只读检查写字机，再做 5 mm 复验

在另一个终端中查询 Windows 当前端口：

```powershell
Get-CimInstance Win32_SerialPort |
  Select-Object DeviceID, Name, PNPDeviceID, Manufacturer
```

找到 `USB-SERIAL CH340 (COMx)`，把实际值写入变量，例如：

```powershell
$port = 'COM4'  # 仅示例；必须替换为当天查询到的 COMx
Set-Location $project
& $py -m communication.dayuwriter.grbl_monitor --port $port
```

点击监视器的“连接并读取状态”，确认真实 `TX ?` 和 `RX <Idle|...>`。这一步不需要 12 V，也不应移动机械。

随后才接通 12 V，并确认：笔尖悬空、X/Y 路径无障碍、皮带/丝杆/电机线正常、12 V 可立即拔下。只做一次受限 `X+5 mm` 或 `Y+5 mm`，确认：

```text
GRBL 接收命令：ok
运动结束：Idle
现场观察：方向和位移正确
```

完成后关闭监视器，释放 COM 口。**`grbl_monitor` 与 `visual_follow` 不能同时占用同一个 COM 口。**

### 2.6 终端 C：先预览视觉跟随，再执行一次 XY

把红方块移动到纸面内的目标位置，要求相对 P0 每轴不超过 `60 mm`。先执行预览：

```powershell
& $py -m communication.dayuwriter.visual_follow `
  --baseline-x <本次P0的X值> `
  --baseline-y <本次P0的Y值> `
  --feed 50
```

预览必须明确显示 `preview only; no serial port opened`，并且建议的 X/Y 方向与红方块的实际位置一致。预览不正确时，回到标定步骤，不执行。

只有满足下面现场条件才执行第一次真机 XY：笔尖仍在 P0、12 V 已接、笔尖悬空、往返路径净空、相机/板/纸面未移动、预览方向正确。

```powershell
& $py -m communication.dayuwriter.visual_follow `
  --port $port `
  --baseline-x <本次P0的X值> `
  --baseline-y <本次P0的Y值> `
  --feed 50 `
  --execute `
  --physical-preflight
```

该程序会将 XY 拆成不超过 5 mm 的小段，并等待每段最终 `Idle`。首次恢复不要直接选用高速度、连续跟随或 Z。

### 2.7 可选：固定 1 mm Z 下落和有限连续跟随

仅当第 2.6 节单次 XY 已正确时，才允许增加固定 `Z+1 mm`。当前约定中 `Z+` 向下；没有自动高度规划。

```powershell
& $py -m communication.dayuwriter.visual_follow `
  --port $port `
  --baseline-x <本次P0的X值> `
  --baseline-y <本次P0的Y值> `
  --feed 50 `
  --z-drop-mm 1 `
  --execute `
  --physical-preflight `
  --z-drop-preflight
```

有限连续跟随只执行 XY，并会在正常结束时返回已武装的 P0。先以一轮、低风险方式验证；`500 mm/min` 是当前已尝试的上限，不是永久安全额定值。

```powershell
& $py -m communication.dayuwriter.visual_follow `
  --port $port `
  --baseline-x <本次P0的X值> `
  --baseline-y <本次P0的Y值> `
  --continuous `
  --return-to-p0 `
  --hold-at-target-seconds 10 `
  --max-moves 1 `
  --max-observations 120 `
  --feed 500 `
  --execute `
  --physical-preflight
```

连续会话一旦出现相机、参考板、目标、串口或控制器错误，就不应假设会安全回到 P0。遇到机械风险，直接断开 12 V；不要把 `Ctrl+C` 或 GRBL 坐标显示当作物理急停或绝对位置证明。

## 3. 变化类型与正确重标定动作

| 发生的变化 | 是否重新人工对准机械 P0 | 是否重新登记 A4 板 | 是否重新记录视觉基线 | 是否可直接执行视觉动作 |
| --- | --- | --- | --- | --- |
| 仅重启电脑，板/纸/机构未动 | 是 | 否 | 是 | 仅在页面 `ready`、5 mm 复验和预览通过后 |
| 相机 A 仅改变角度/高度，A4 板相对写字机不动 | 是（若机器重启/断电） | 否 | 是 | 等六标记质量闸门重新通过 |
| 相机 USB 重插、dashboard 重启 | 是（若写字机也重启/断电） | 否 | 是 | 等新的 `ready`，不能沿用旧网页状态 |
| 板、纸、背板的高度/倾角或相对 P0 改变 | 是 | 是 | 是 | 重新登记和验证后才可 |
| P0 改点、笔架手推、断电或疑似丢步 | 是 | 若板相对 P0 改变则是 | 是 | 先做 5 mm 机械复验 |
| 写字机搬运、皮带/丝杆/电机线被动过 | 是 | 通常是，除非板与机器刚性整体未变且 X30/Y30 仍实测正确 | 是 | 先重新实测方向/小位移 |
| 换成 D435i B | 是 | 是 | 是 | A 的相机 artifact 不能复制给 B |
| 目标高于纸面、倾斜或需要抓取 | 不适用 | 平面板仍不足 | 不适用 | 否，需要另行完成三维外参、Z 安全与接触标定 |

### 3.1 相机角度或高度变化：为什么通常不需重新登记参考板

登记文件定义的是**A4 板与写字机 P0 的物理关系**。相机 A 换角度后，dashboard 会重新检测六个 ArUco 标记，并从当前图像恢复纸面映射；所以相机重装本身不等于板到写字机的几何变化。

正确流程是：固定相机 -> 六标记完整入镜 -> 启动新 dashboard -> 等 `ready` -> 红方块放 P0 记录新视觉基线 -> 预览 -> 小范围动作。

但若相机视角导致标记太小、反光、遮挡或误差超限，状态不会通过质量闸门。此时调整相机位置、照明或板平整度；不要通过放宽误差阈值来强行继续。

### 3.2 板或纸面变化：必须重新登记

参考板滑动、重印、折弯、翘起、放到不同高度、纸面目标不再与板共面，都会改变纸面坐标和写字机坐标的关系。此时按下面顺序做：

1. 用尺确认 100 mm 标尺实际为 `99-101 mm`，并将板固定到刚性平面。
2. 将笔尖对准板上的 P0 十字。
3. 做受限 `X+30 mm`，笔尖必须对准板上 `X+30` 十字；回 P0。
4. 做受限 `Y+30 mm`，笔尖必须对准板上 `Y+30` 十字；回 P0。
5. 固定板后，在网页勾选确认并点击 `Register board`。
6. 重新启动/等待 dashboard `ready`，红方块置于 P0 后记录新视觉基线。

注册按钮不会运动机构、发送 G-code 或自动建立 GRBL 原点；前三个物理检查不能省略。

## 4. 助手失误：明确责任和改进

### 4.1 我造成或放大的问题

| 我的失误 | 具体后果 | 应有做法 | 已采取改进 |
| --- | --- | --- | --- |
| 没有在早期就坚持固定尺寸标记、实测打印尺寸和参考板方案 | 使用手绘圆点、缩放错误的打印件，导致重复采集和无效标定 | 在第一次视觉标定前就要求固定方块、尺测和独立验证点 | 使用 A4 六 ArUco 板、100 mm 尺寸门槛和保留误差闸门 |
| 没有及时把屏幕 Y 方向、纸面 Y 方向与机械 Y+ 的区别讲清 | 出现坐标方向/板图案方向的困惑和返工 | 在装板前明确机械 X+/Y+ 与印刷坐标约定 | 标定手册已把 X+ 右、Y+ 上和屏幕坐标分开记录 |
| 反复要求确认、过度分阶段讨论 | 用户等待时间过长，简单控制任务推进慢 | 必要的硬件安全确认完成后直接做可逆小范围操作 | 后续使用固定检查表和命令，不把同一问题重复提问 |
| 测试设计曾带执行参数访问真实 COM4 | 发生非操作者意图的 X/Z 实机动作，是最严重的软件安全失误 | 单元测试必须默认注入假控制器，真机测试必须是独立入口 | 已改为 fake controller，并将连续分支置于真实执行分支之前 |
| dashboard 对断连相机没有自动恢复，且我没有提前把进程生命周期作为运行条件写清 | 网页仍在 `8765`，但页面 `camera_error`、无图像和坐标 | 将“端口在监听”与“相机可用”分开验证；断连后启动新会话 | 运行手册要求检查 `ready`、`error:null` 和六标记；失败复盘已记录此事件 |
| 文档同步滞后 | README 一度保留“D435i 未接入”的早期结论，与后续演示记录矛盾 | 每个硬件里程碑同时更新原始记录、摘要与索引 | 已新增 19-23 系列文档并在 README 索引 |

### 4.2 不是由我造成，但我应更早隔离和解释的现场问题

- CNC V3 的 12 V 端子接触不良，会造成 `ok` 但无真实运动。
- CH340 的 COM 编号会变化；历史 `COM3`、`COM4` 或 `COM11` 都不能代替当天设备枚举。
- RealSense 单像素深度为零、3D 预览稀疏、Viewer 占用相机和帧池耗尽属于不同问题，不能用一个“相机坏了”概括。
- Conda 环境目录存在不表示 pip 依赖完整；Windows 也可能阻断 Tkinter DLL。
- 无编码器、无已验证回零和 `Pn:P` 未排查意味着人工 P0 与 Z 限制仍是必要条件。

## 5. 今后所有项目可复用的经验

1. **先建立最小可验证链路。** 设备枚举、单轴运动、图像、坐标显示、单次有界动作应分开验收。
2. **把坐标系写成可观察事实。** 屏幕像素、相机米制 XYZ、纸面 P0-XY、GRBL MPos 不能混用。
3. **用物理尺和保留点验证标定。** 拟合点不等于验收点；打印尺寸、目标中心和共面关系必须实测。
4. **把失效条件编码和显示出来。** `camera_error`、`reference_lost`、越界目标和串口异常应撤销动作资格。
5. **真实硬件与自动化测试必须隔离。** 测试默认假设备；真实端口只能经明确的人工前提和执行标志打开。
6. **通信成功不等于物理成功。** `ok` 后仍需最终 `Idle` 和现场观察；软件位置不等于编码器测量。
7. **重启是一个新的实验会话。** 重建设备身份、P0、视觉基线和质量闸门，而不是复用昨天的页面、端口或坐标。

## 6. 相关记录

- [19-标定过程与经验](19-calibration-process-and-lessons.md)
- [20-项目全流程记录](20-project-end-to-end-record.md)
- [21-全新电脑部署指南](21-new-computer-deployment.md)
- [22-项目失败复盘与防复发记录](22-project-failure-postmortems.md)
- [17-视觉跟随首次操作](17-visual-follow-first-operation.md)

