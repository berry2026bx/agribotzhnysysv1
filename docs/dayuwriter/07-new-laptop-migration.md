# 07 新电脑部署与现场迁移手册

适用对象：把当前 DayuWriter 控制界面和写字机迁移到一台全新的 Windows 11 电脑，并在新电脑上重新完成一次真实连接和小幅运动验证。

本手册的目标是恢复可复现的软件和硬件基线，然后在最终相机位置完成相机 A 到 P0 的标定。它不授权检测结果直接驱动写字机。文中 `COMx` 是占位符，必须替换为新电脑实际识别到的端口，例如 `COM4`。

## 最短成功路径

第一次迁移只需要完成下面 8 步；相机和视觉标定放到写字机重新跑通之后：

1. 新电脑安装 Git、Miniconda/Anaconda、VS Code、VS Code Python 扩展和 CH340 驱动。
2. 克隆本仓库的 `codex/dayuwriter-recovery-execution` 分支。
3. 用 `environment/dayuwriter-control.yml` 创建 `dayuwriter-control` 环境。
4. 保持 12V 断开，只插写字机 USB，查出实际 `COMx`。
5. 断开其他串口软件；检查机械和 12V 极性；让笔架物理对准 P0。
6. 接 USB 后再接 12V，观察无异常，再启动可视化界面。
7. 点击“连接并读取状态”，确认真实 `RX` 状态帧和 `Idle`，这一步不会自动移动。
8. 确认笔尖悬空、空间足够后，只做一个受限的 `X/Y ±5 mm` 按钮动作，等待最终 `Idle` 并观察实机。

完成第 8 步，才算“新电脑已经跑通写字机”。

## 0. 先明确哪些内容可复用

### 可直接复用

- GitHub 分支 `codex/dayuwriter-recovery-execution` 中的控制、相机采集代码、测试和文档。
- 相机 A 的身份：Intel RealSense D435I，序列号 `231122070403`。
- 已验证的相机 A 采集记录：`baseline/2026-07-27-realsense-camera-a-capture.json`。
- 已验证的写字机方向和受限 XY 软件范围：`X[-190, 190]` mm、`Y[-90, 140]` mm。
- 人工 P0 标记的位置和机械接线状态，只要搬运中没有移动皮带、丝杆、同步轮或电机接线。

### 必须在新电脑重新确认

- D435i 是否枚举为序列号 `231122070403`，以及 RGB、Depth 和 USB 3.x 是否正常。
- CH340 写字机实际分配到的 COM 口。不要假设仍是 `COM3` 或 `COM4`。
- Windows 驱动、RealSense SDK、Conda 环境和 VS Code 解释器。
- 写字机 USB、CNC V3 `12-36V` 供电端子、皮带和线缆在搬运后是否正常。
- 每次打开 GRBL 控制台前，笔架是否物理对准人工 P0。

### 尚未完成，不能复用为已知结果

- 相机 A 到写字机 P0 坐标系的外参或平面单应性。
- 相机 A 的最终安装位置、相机视野、笔尖遮挡情况和标定误差。
- 目标检测、视觉到 XY 的人工确认运动、自动 XY、Z 轴三维定位。
- 相机 B 的任何标定结果。

换新电脑或移动相机前尚未进行 P0 标定，因此不会丢失已完成的视觉标定结果。相机一旦固定到新位置，随后得到的 P0 标定只对该固定姿态有效。

## 1. 搬运前断开顺序

1. 关闭 RealSense Viewer、Python 相机脚本、GRBL 控制台、UGS 和任何串口工具。
2. 拔掉 12V 电源适配器，确认 CNC V3 板的 12V 已断开。
3. 拔掉写字机 USB 和 D435i USB。
4. 拍照记录红色 CNC V3 板的 `12-36V` 正负极接线、XYZ 电机插头、皮带、同步轮顶丝和 Z 丝杆联轴器。
5. 搬运时不要拉扯同步带、丝杆、电机线或 D435i USB 接头。
6. 保留物理 P0 标记；P0 不是自动回零，也不是编码器反馈。

## 2. 新场地的物理布置

### 2.1 电脑和线缆

- 新笔记本放在写字机旁边，使 D435i 使用短的直连 USB 3.x 数据线。
- 不要先使用普通 USB 2.0 线、普通多级延长线、USB over Wi-Fi 或网络 USB 共享。
- 写字机 USB 和 D435i USB 都优先直连新笔记本；必要时使用质量可靠的 USB 3.x 扩展方案，但先验证 USB 3.x 枚举。
- 12V 只接 CNC V3 板上标有 `12-36V` 的端子，红线接 `+`、黑线接 `-`；Arduino UNO 圆孔不是电机供电入口。

### 2.2 相机的暂定视角

先不标定，也不需要先购买支架。用手持或临时支撑寻找视角即可，12V 保持断开。

- 不使用正面低位水平视角：它会把工作平面看成窄边，并被横梁和滑台遮挡。
- 不要求完全垂直俯视；第一版优先高位斜视。
- 初始位置：镜头高于笔尖工作平面约 `400-500 mm`，相对工作区中心前移或侧移约 `200-300 mm`。
- 初始角度：相机光轴与工作平面的夹角约 `45-60` 度，瞄准工作区中心。
- RGB 画面必须同时包含：工作平面大部分区域、P0 附近、有效 XY 四角附近、笔尖附近；四周留约 10-20% 余量。
- 最终标定前必须将相机锁死在刚性支架上。相机或支架发生移动后，P0 标定失效，必须重做。

## 3. 在新笔记本获取项目代码

先安装 Git for Windows、Miniconda 或 Anaconda、VS Code 的 Python 扩展。打开 PowerShell，执行：

```powershell
$dayuWorkspace = "$env:USERPROFILE\Documents\DayuWriter"
git clone --branch codex/dayuwriter-recovery-execution --single-branch `
  https://github.com/berry2026bx/agribotzhnysysv1.git `
  $dayuWorkspace
Set-Location $dayuWorkspace
git branch --show-current
git log -1 --oneline
code .
```

预期分支输出：

```text
codex/dayuwriter-recovery-execution
```

不要只复制某个 `.py` 文件，也不要复制当前电脑的 `.conda` 环境目录。环境必须由清单重新创建。

如果 `code` 命令不可用，直接打开 VS Code，选择“文件 → 打开文件夹”，打开上面 `$dayuWorkspace` 指向的目录即可。后续 PowerShell 命令必须在这个项目根目录执行；目录中应能看到 `communication`、`docs`、`environment` 和 `tests`。

## 4. 创建 Python 环境

在项目根目录执行：

```powershell
conda env create -f environment/dayuwriter-control.yml
conda activate dayuwriter-control
python --version
python -c "import serial, numpy, pyrealsense2 as rs; print(serial.__version__); print(numpy.__version__); print(rs.__file__)"
python -m pytest -q --basetemp .pytest_cache\new-laptop-tests
```

预期：Python 3.11、`pyserial`、`numpy`、`pyrealsense2` 均可导入，测试全部通过。测试不应打开 COM 口或移动写字机。若暂时只验证写字机，可以先执行 `python -c "import serial; print(serial.__version__)"`，RealSense 依赖仍建议按清单一次装齐。

在 VS Code 中选择解释器：

```text
dayuwriter-control
```

或选择该环境中 `python.exe` 的绝对路径。

## 4.1 启动当前三页可视化界面

当前界面是 Python/Tkinter 桌面程序，不是网页服务，不需要启动浏览器或 Node.js。它包含三个页面：`现场控制`、`通信入门`、`坐标入门`。

在 VS Code 的 PowerShell 终端执行：

```powershell
conda activate dayuwriter-control
$dayuWorkspace = "$env:USERPROFILE\Documents\DayuWriter"
Set-Location $dayuWorkspace
python -m communication.dayuwriter.grbl_monitor --port COMx
```

例如新电脑实际端口为 `COM7`，就执行：

```powershell
python -m communication.dayuwriter.grbl_monitor --port COM7
```

启动程序只创建窗口，不会因为打开窗口而发送运动指令。窗口中的“串口”指标、连接提示和通信说明会使用命令行传入的实际端口。只有点击“连接并读取状态”后，程序才打开串口并执行首次只读 `?` 查询；连接成功后，动作按钮才会解锁。

演示时可以按这个因果顺序操作：

```text
点击连接并读取状态
  → CALL：Python 调用 status()
  → TX：发送 ?（只读查询，不移动）
  → RX：收到 <Idle|MPos:...|FS:...|Pn:...>
  → 点击一个受限 X/Y 按钮
  → CALL → TX $J=G91 G21 ... → RX ok
  → TX ? / RX Jog（运动中）
  → RX Idle（GRBL 报告控制周期结束）
```

`ok` 仅表示 GRBL 接受了文本；必须同时看到最终 `Idle`，并在现场观察真实机构运动。关闭窗口后，程序会释放串口；若端口仍被占用，检查是否还有旧的控制台、UGS、Arduino 串口监视器或 Python 进程。

## 5. 安装并验证 RealSense

1. 从官方 librealsense/RealSense SDK 发布页安装与当前实验匹配的 Windows SDK。当前已验证电脑使用 Viewer/SDK 2.58.1；先保持同一版本，避免无必要的软件变量。
2. 只连接 D435i A 到新笔记本的 USB 3.x 接口。
3. 打开 RealSense Viewer，确认：

```text
Name: Intel RealSense D435I
Serial: 231122070403
USB: 3.x
RGB: 可打开
Stereo Module / Depth: 可打开
```

4. 记录新电脑实际显示的 USB 类型、SDK 版本和相机固件版本。
5. 不因 Viewer 弹窗直接升级固件。相机已在固件 `5.13.0.55` 上完成 RGB/深度 Python 采集；升级必须是单独的、可回退评估步骤。
6. 关闭 Viewer，避免其独占相机，然后在项目根目录运行：

```powershell
python -m vision.realsense.camera_probe `
  --serial 231122070403 `
  --output docs\dayuwriter\baseline\realsense-camera-a-new-laptop.json `
  --save-frames docs\dayuwriter\baseline\realsense-camera-a-new-laptop-frames
```

该命令只读取指定相机，不会打开 COM 口或发送 GRBL 指令。JSON 中的点是相机坐标，单位为米；它不是 P0 机械坐标，不能用于移动。

官方 SDK 的关键含义：对齐后深度应读取到彩色图像坐标系；`get_distance()` 返回米；`rs2_deproject_pixel_to_point()` 输出相机坐标系中的米值，坐标轴为 +X 向右、+Y 向下、+Z 向前。

## 6. 新电脑重新识别写字机

### 6.1 USB-only 基线

1. 保持 12V 断开，只连接写字机 USB。
2. 在设备管理器或 PowerShell 中读取实际端口：

```powershell
Get-CimInstance Win32_SerialPort |
  Select-Object DeviceID, Name, PNPDeviceID, Manufacturer
```

3. 记录出现的 `USB-SERIAL CH340 (COMx)`。`COMx` 必须替换下面所有示例的端口。
4. 若设备不存在或有黄色警告，先解决 CH340 驱动；不要通 12V 或发送 GRBL 指令。

### 6.2 机械和供电复查

断开所有电源，确认：

```text
皮带与同步轮顶丝正常
Z 丝杆和联轴器正常
XYZ 电机插头正常
12V 红黑线在 CNC V3 的 12-36V 端子上，极性正确
笔尖悬空，远离纸面、底座与机械边界
12V 断电位置可立即触及
```

### 6.3 重新建立 P0 与短距离复验

1. 关闭所有可能占用串口的软件，包括 UGS、Arduino 串口监视器和旧 Python 程序。
2. 让笔架物理对准 P0 标记。移动、断电、重新插 USB 或可能丢步后，都不能把 GRBL 的显示坐标当作 P0 真值。
3. 接 USB 后接 12V，观察无自发运动、异响、发热、气味、火花。
4. 使用真实 COM 口启动控制台：

```powershell
python -m communication.dayuwriter.grbl_console --port COMx
```

5. 先输入 `status`，确认状态正常，再在笔尖悬空、空间足够、12V 可立即断开的条件下做一次小幅 XY 复验：

```text
jog X 5 100
jog Y 5 100
```

每次指令都等待最终 `Idle` 并观察实机。`ok` 仅表示 GRBL 接受指令，不证明机构已经完成真实运动。

已验证方向：X+ 向右、Y+ 向前、Z+ 向下。Z 轴仍没有可靠的软件工作范围，视觉阶段禁止自动 Z 移动。

## 7. 什么时候开始 P0 平面标定

只有同时满足以下条件才开始：

```text
相机 A 已固定在最终刚性位置
RGB 能看见工作平面、P0、笔尖附近和有效区域边缘
相机 USB 3.x 与 Python 只读采集已经成功
写字机已在新电脑上以真实 COM 口完成小幅 XY 复验
笔尖已物理对准 P0
```

下一步将采集至少 9 个已知 P0 XY 点（四角附近、边缘和中心），每个点记录像素、深度、相机三维坐标和机械 P0 坐标。拟合使用的点与验证点必须分开，并报告验证点平均误差和最大误差。误差未通过前，只显示预测坐标，不允许视觉自动移动。

## 8. 常见问题

### RealSense Viewer 能开，Python 报设备忙

先关闭 Viewer、其他 Python 相机脚本和所有可能占用 D435i 的程序；再执行 `camera_probe`。

### Viewer 显示 USB 不是 3.x

更换到笔记本直接 USB 3.x 接口，使用短的、支持 SuperSpeed 数据的线缆。不要用仅充电线或普通 USB 2.0 Micro-B 线。

### Python 找不到 `pyrealsense2`

确认 VS Code/终端使用 `dayuwriter-control`，再重新执行第 4 节的环境创建命令。

### 写字机 COM 口和旧电脑不同

这是正常的。以新电脑设备管理器的 `COMx` 为准，修改命令参数，不修改代码中的历史端口值来强行匹配。

### GRBL 返回 `ok`，机构不移动

优先检查 CNC V3 的 `12-36V` 端子接线和 12V 适配器，而不是刷固件、改 `$100/$101/$102` 或重复发送运动命令。

## 9. 新场地完成检查表

```text
[ ] Git 分支正确，离线测试全部通过
[ ] 相机 A 序列号为 231122070403，USB 3.x、RGB 和 Depth 正常
[ ] Python 相机只读采集 JSON 已生成
[ ] 写字机实际 COM 口已记录
[ ] 12V、皮带、丝杆、线缆已复查
[ ] 笔架已物理对准 P0
[ ] 小幅 X/Y 实机复验完成，最终状态 Idle
[ ] 相机已处于最终固定位置，工作平面可见
[ ] 才可以开始相机 A 到 P0 的九点标定
```

## 10. 证据与限制

- 本手册中的历史设备记录来自当前实验电脑。新电脑的驱动、COM 口、USB 模式和相机枚举必须重新实测。
- 相机 A 可复用代码和身份，但不能与相机 B 共用标定文件。
- 视觉检测框中心、相机三维点和 P0 坐标不是同一坐标系；没有经验证的坐标变换时，禁止发送写字机运动命令。
- 参考文档：`01-hardware-recovery.md` 至 `06-d435i-vision-roadmap.md`、`baseline/2026-07-27-realsense-camera-a.md`。
