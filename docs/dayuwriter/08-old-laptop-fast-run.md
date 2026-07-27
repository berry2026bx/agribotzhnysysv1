# 08 旧笔记本最快运行清单

目标：在以前使用过、基本环境已存在的 Windows 笔记本上，最快重新运行 DayuWriter 的 Python 控制台和实时监控器，并尽可能检查 D435i A。最终的相机标定和视觉自动运动在另一台电脑上完成。

本清单不进行相机安装、P0 标定、目标检测或自动运动。

## 版本分工

- 旧电脑已有 RealSense Viewer `2.50.0`：可用于查看相机是否能枚举、RGB/Depth 是否能打开；它不是当前 Python 采集验证使用的 `pyrealsense2 2.58.x`。
- 旧电脑：优先恢复写字机 Python 控制和监控；只有在 `pyrealsense2` 已能导入时才运行相机 Python 采集。
- 后续标定/视觉自动运动的电脑：安装与项目清单匹配的 `pyrealsense2 2.58.x` 和对应的 RealSense SDK/Viewer（当前基线为 SDK 2.58.1），再运行相机采集、P0 标定和视觉控制。
- 2.50.0 与 2.58.x 版本不一致不代表一定不能打开相机，但不能把旧 Viewer 的显示结果当作当前 Python 管线已验证。

## 1. 获取最新代码

打开 PowerShell，始终使用一份新的代码目录：

```powershell
$dayuDir = "$env:USERPROFILE\Documents\agribotzhnysysv1-dayuwriter"
git clone --branch codex/dayuwriter-recovery-execution --single-branch `
  https://github.com/berry2026bx/agribotzhnysysv1.git `
  $dayuDir
Set-Location $dayuDir
```

若提示该目录已经存在，使用新的目录名后重试，例如：

```powershell
$dayuDir = "$env:USERPROFILE\Documents\agribotzhnysysv1-dayuwriter-2"
git clone --branch codex/dayuwriter-recovery-execution --single-branch `
  https://github.com/berry2026bx/agribotzhnysysv1.git `
  $dayuDir
Set-Location $dayuDir
```

确认目录正确：

```powershell
git branch --show-current
Get-ChildItem communication, vision, environment, docs
```

预期分支：

```text
codex/dayuwriter-recovery-execution
```

## 2. 启用已有 Python 环境

在项目根目录执行：

```powershell
conda activate dayuwriter-control
python -c "import serial, numpy; print('Writer Python environment OK')"
```

出现 `Writer Python environment OK` 后继续。

只有上一步报错时才执行以下恢复命令：

```powershell
conda env update -n dayuwriter-control -f environment/dayuwriter-control.yml
conda activate dayuwriter-control
python -c "import serial, numpy; print('Writer Python environment OK')"
```

如果电脑没有 `dayuwriter-control` 环境：

```powershell
conda env create -f environment/dayuwriter-control.yml
conda activate dayuwriter-control
```

## 3. 旧电脑检查 D435i A（可选）

1. 先只连接 D435i A；写字机 12V 保持断开。
2. 打开已有的 RealSense Viewer `2.50.0`，确认：

```text
Name: Intel RealSense D435I
Serial Number: 231122070403
USB: 3.x
RGB: 可打开
Stereo Module / Depth: 可打开
```

3. 关闭 RealSense Viewer。
4. 检查旧电脑是否已有 Python RealSense 包：

```powershell
python -c "import pyrealsense2 as rs; print(rs.__file__)"
```

5. 如果上一步成功，在同一个 PowerShell、项目根目录运行：

```powershell
python -m vision.realsense.camera_probe `
  --serial 231122070403 `
  --output docs\dayuwriter\baseline\realsense-camera-a-old-laptop.json `
  --save-frames docs\dayuwriter\baseline\realsense-camera-a-old-laptop-frames
```

预期输出：

```text
Read-only baseline written to ...realsense-camera-a-old-laptop.json
```

此步骤完成后，D435i A 的 Python 采集已恢复。不要让 Viewer 和该 Python 命令同时运行。

如果旧电脑没有 `pyrealsense2`，不要为了这一步强行混装旧 Viewer 2.50.0 和新 Python SDK；先完成写字机控制，后续在另一台电脑按项目清单安装匹配的 2.58.x 环境。

## 4. 识别写字机 COM 口

1. 写字机 12V 保持断开。
2. 连接写字机 USB。
3. 在 PowerShell 运行：

```powershell
Get-CimInstance Win32_SerialPort |
  Select-Object DeviceID, Name, PNPDeviceID, Manufacturer
```

4. 找到 `USB-SERIAL CH340 (COMx)`，把实际端口记为 `COMx`。

不要假设新电脑上仍是 `COM3` 或 `COM4`。

## 5. 运行写字机 Python 控制台

先完成以下实物检查：

```text
[ ] 笔架物理对准 P0 标记
[ ] 笔尖悬空
[ ] X/Y/Z 有移动空间
[ ] 12V 电源线已接在 CNC V3 的 12-36V 端子
[ ] 12V 断电位置可立即触及
[ ] UGS、Arduino 串口监视器、旧 Python 控制程序均已关闭
```

接上 12V。将下面的 `COMx` 替换为第 4 节发现的实际端口：

```powershell
python -m communication.dayuwriter.grbl_console --port COMx
```

在控制台依次输入：

```text
status
where
jog X 5 100
jog X -5 100
jog Y 5 100
jog Y -5 100
quit
```

每次 `jog` 后确认实机运动，并等待状态回到 `Idle`。发现无运动、碰撞、持续振动、异响、发热、气味或火花时，立即断开 12V，不再发送命令。

已验证方向：`X+` 向右、`Y+` 向前、`Z+` 向下。现在不要通过视觉自动移动 Z。

## 6. 运行实时协议监控器

确认第 5 节控制台已经输入 `quit` 并关闭。串口一次只能由一个程序独占。

```powershell
python -m communication.dayuwriter.grbl_monitor --port COMx
```

在打开的窗口中连接写字机，使用小幅 X/Y 按钮，并查看实际 Python 调用、TX、RX 和最终状态。不要同时打开 GRBL 控制台。

## 7. 后续标定/视觉电脑的最低要求

在另一台电脑上进行标定和视觉自动运动时，重新执行：

```text
安装/确认 RealSense SDK 2.58.1（或与环境清单匹配的 2.58.x）
克隆同一 GitHub 分支
创建或更新 dayuwriter-control 环境
确认 D435i A 序列号 231122070403
运行 camera_probe
连接写字机并确认新电脑实际 COM 口
固定相机后重新做 P0 多点标定
先显示预测坐标，再人工确认 XY，最后才考虑自动 XY
```

旧电脑上的相机 Viewer 截图、中心像素深度和设备身份记录可以作为参考；它们不是新场地的相机到 P0 标定结果。相机或写字机在另一台电脑上的物理位置改变后，必须在最终位置重新标定。

## 8. 最快完成状态

完成以下项目即可停止：

```text
[ ] （可选）旧电脑相机 A Viewer 的 RGB/Depth 正常
[ ] （可选）旧电脑 camera_probe 已生成 JSON
[ ] 新电脑实际 COM 口已确认
[ ] Python 控制台已完成 X/Y 正负 5 mm 往返
[ ] 实时协议监控器已能连接
```

完成前四项中的写字机部分后，旧笔记本的基础运行已恢复；相机标定和视觉自动运动留到另一台电脑。
