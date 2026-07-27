# 07 新笔记本与新场地迁移手册

适用对象：已完成 DayuWriter 基础恢复、Python 控制和 RealSense D435i A 只读采集后，准备在另一台 Windows 11 笔记本与更大场地继续实验。

本手册的目标是恢复可复现的软件和硬件基线，然后在最终相机位置完成相机 A 到 P0 的标定。它不授权检测结果直接驱动写字机。

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

## 4. 创建 Python 环境

在项目根目录执行：

```powershell
conda env create -f environment/dayuwriter-control.yml
conda activate dayuwriter-control
python --version
python -c "import serial, numpy, pyrealsense2 as rs; print(serial.__version__); print(numpy.__version__); print(rs.__file__)"
python -m pytest -q --basetemp .pytest_cache\new-laptop-tests
```

预期：Python 3.11、`pyserial`、`numpy`、`pyrealsense2` 均可导入，测试全部通过。测试不应打开 COM 口或移动写字机。

在 VS Code 中选择解释器：

```text
dayuwriter-control
```

或选择该环境中 `python.exe` 的绝对路径。

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
