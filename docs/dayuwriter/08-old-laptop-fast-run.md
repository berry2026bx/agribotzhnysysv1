# 08 旧笔记本最快运行清单

目标：在以前使用过、基本环境已存在的 Windows 笔记本上，最快重新运行：D435i A 的 Python 采集、DayuWriter 的 Python 控制台和实时监控器。

本清单不进行相机安装、P0 标定、目标检测或自动运动。

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
python -c "import serial, numpy, pyrealsense2; print('Python environment OK')"
```

出现 `Python environment OK` 后继续。

只有上一步报错时才执行以下恢复命令：

```powershell
conda env update -n dayuwriter-control -f environment/dayuwriter-control.yml
conda activate dayuwriter-control
python -c "import serial, numpy, pyrealsense2; print('Python environment OK')"
```

如果电脑没有 `dayuwriter-control` 环境：

```powershell
conda env create -f environment/dayuwriter-control.yml
conda activate dayuwriter-control
```

## 3. 运行 D435i A

1. 先只连接 D435i A；写字机 12V 保持断开。
2. 打开 RealSense Viewer，确认：

```text
Name: Intel RealSense D435I
Serial Number: 231122070403
USB: 3.x
RGB: 可打开
Stereo Module / Depth: 可打开
```

3. 关闭 RealSense Viewer。
4. 在同一个 PowerShell、项目根目录运行：

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

## 7. 最快完成状态

完成以下项目即可停止：

```text
[ ] 相机 A Viewer 的 RGB/Depth 正常
[ ] camera_probe 已生成 JSON
[ ] 新电脑实际 COM 口已确认
[ ] Python 控制台已完成 X/Y 正负 5 mm 往返
[ ] 实时协议监控器已能连接
```

此时，“刚刚已经完成的全部能力”已在旧笔记本恢复。相机最终视角确定并固定后，再开始 P0 平面标定。
