# DayuWriter 电脑和机器重启后的完整恢复手册

## 0. 重启意味着什么

重启不会删除代码，但会清除或改变运行时事实。最重要的是：本机没有编码器和已验证的自动回零，故重启后的 GRBL `MPos` 不能证明笔尖的物理位置。每次重启都应视为新的实验会话，按下面顺序恢复：

```text
环境 -> 相机身份和单独采集 -> 参考板 ready -> 机械 P0/CH340 身份
-> 5 mm 机械复验 -> 本次视觉 P0 基线 -> 预览 -> 受监督动作
```

在任一层失败时停在该层。不要用过去的 `COM4`、历史基线、浏览器旧页面或昨天的 `MPos` 跨过失败层。

## 1. 物理预检查：先不接 12 V

1. 写字机 12 V 保持断开；D435i 接直连 USB 3.x 数据口；写字机 USB 可接。
2. 确认 CNC V3 端子的 12 V 红线在 `+`、黑线在 `-`，线缆和 XYZ 电机插头没有松动。UNO 圆孔不是电机电源接口。
3. 关闭 RealSense Viewer、微雕管家、UGS、Arduino 串口监视器、旧 dashboard、旧 `visual_follow` 和旧 `grbl_monitor`。
4. 检查参考板平整且固定，红方块将放在同一纸面；六个标记应无遮挡。
5. 人工让笔尖准确对准纸上 P0。即使此时还未接 12 V，也必须完成这项物理复位。

若笔架被手推、皮带/丝杆改动、发生碰撞或有疑似丢步，除本手册外还需做机械方向和尺度复查；不要进入连续跟随。

## 2. 进入项目与验证环境

用固定解释器，不依赖当前 shell 是否已 `conda init`：

```powershell
$project = 'C:\Users\Administrator\Desktop\20260725DaZiJJJ\agribotzhnysysv1\.worktrees\dayuwriter-recovery-execution'
$py = 'C:\Users\Administrator\.conda\envs\dayuwriter-control\python.exe'
$cameraSerial = '231122070403'
Set-Location $project

& $py -c "import sys, serial, numpy, pyrealsense2 as rs, cv2; assert hasattr(cv2, 'aruco'); print(sys.executable); print('environment OK')"
```

若导入失败，停止并按 [27-全新电脑复刻手册](27-fresh-pc-reproduction.md) 修复环境。不要用系统 Python 或 Base Anaconda 继续，因为它们可能没有 `pyrealsense2` 或 `cv2.aruco`。

可用下面命令只读枚举相机身份；它不启动流：

```powershell
& $py -c "import pyrealsense2 as rs; c=rs.context(); print([(d.get_info(rs.camera_info.name), d.get_info(rs.camera_info.serial_number), d.get_info(rs.camera_info.usb_type_descriptor)) for d in c.devices])"
```

本部署的历史成功相机为 D435i A、序列号 `231122070403`、USB 3.x。若输出不同、为空或 USB 退化，先处理线缆/端口/设备身份，不能把命令中的序列号改成猜测值。

## 3. 启动一个新的 dashboard 会话

保持 Viewer 完全关闭。在终端 A 中运行：

```powershell
& $py -m vision.realsense.live_red_target_dashboard `
  --serial $cameraSerial `
  --aruco-reference-board `
  --reference-registration docs/dayuwriter/calibration/camera-a-a4-aruco-registration.json `
  --port 8765
```

浏览器打开 <http://127.0.0.1:8765/>。只在状态为 `ready`、`error: null`、六个 ID `0..5` 完整可见、平均误差 `<=1.5 mm`、最大误差 `<=3.0 mm` 时继续。

如 `8765` 已被旧进程占用，优先回到旧 dashboard 所在终端按 `Ctrl+C`。找不到终端时先确认占用者再停止，而不是盲目结束所有 Python：

```powershell
Get-NetTCPConnection -LocalPort 8765 -State Listen | Select-Object OwningProcess, LocalAddress, LocalPort
Get-Process -Id <上一步的 OwningProcess>
# 确认它确为旧 dashboard 后才执行： Stop-Process -Id <PID>
```

网页能打开却显示 `camera_error` 并不矛盾：HTTP 服务可以存活，而 D435i pipeline 已断连。停止旧 dashboard、关闭相机竞争进程、检查 USB 后只启动一次新会话。

## 4. 建立本次视觉基线

笔尖仍在人工 P0 时，红方块中心也放 P0。等页面显示稳定后，在终端 B 执行：

```powershell
$p0 = Invoke-RestMethod 'http://127.0.0.1:8765/state.json'
if ($p0.state -ne 'ready' -or $p0.mapping_state -ne 'available' -or $null -eq $p0.machine_xy_mm) {
  throw 'Dashboard not ready; no P0 baseline was recorded.'
}
$baselineX = [double]$p0.machine_xy_mm.x
$baselineY = [double]$p0.machine_xy_mm.y
"P0 baseline: X={0:F3}, Y={1:F3} mm" -f $baselineX, $baselineY
```

这些变量只在当前 PowerShell 会话有效。重启后重新读，不要从网页的整数显示或旧文档抄入。

## 5. 找到当天的 CH340 端口，并作读状态检查

仍保持 12 V 断开：

```powershell
Get-CimInstance Win32_SerialPort |
  Select-Object DeviceID, Name, PNPDeviceID, Manufacturer
```

找到 `USB-SERIAL CH340 (COMx)` 后赋值，例如：

```powershell
$port = 'COM4'  # 示例；替换为上述输出的实际 COMx
& $py -m communication.dayuwriter.grbl_monitor --port $port
```

在监视器点击“连接并读取状态”，确认 `TX ?` 和 `RX <Idle|...>`。这一步没有电机运动。完成后关闭监视器以释放 COM 口；dashboard 可保持运行，因为它只占用相机。

## 6. 接 12 V 后仅做一个 5 mm 复验

重新确认笔尖悬空、P0 准确、完整小路径无障碍，12 V 可立即断开。接通 12 V，观察没有自发运动或异常，再在监视器执行一次 `X+5 mm` 或 `Y+5 mm`。

只有同时看到 `ok`、最终 `Idle` 并且人眼确认方向/实际位移正确，才允许人工回到 P0 并进入下一步。若任一项失败，断 12 V 并排查供电、COM、驱动、A4988、电机线与机械；不做“多发几条命令试试”。

## 7. 预览和恢复一次受监督动作

红方块放到纸面内已知小偏移处，笔尖已经手动回 P0，才运行：

```powershell
& $py -m communication.dayuwriter.visual_follow `
  --baseline-x $baselineX `
  --baseline-y $baselineY `
  --feed 500
```

它必须打印合理的目标相对量和 `preview only; no serial port opened`。确认目标方向正确、12 V 接通、笔尖悬空、去目标和回 P0 的路径均净空、相机/板/纸没动后，再执行有限一轮：

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

该命令武装时不会对当前红方块移动；移动方块后才触发一次。完成时应物理回 P0。连续跟随过程中出现相机、参考板或串口错误时，程序不能保证自动回 P0；先断 12 V（如有机械风险）并重新从第 1 节开始。

## 8. 重启后的结束与留档

完成本次恢复后，建议保存：当前 CH340 输出、dashboard `ready` 状态截图、P0 视觉基线、5 mm 观察、预览输出和异常日志。它们证明的是“本次重启恢复成功”，而不是为下一次重启免除检查。

完整连续运行、一次 Z 下落和停止方法参见 [24-不依赖 Codex 的代码操作手册](24-standalone-code-operation.md)。如相机、参考板、纸面或 P0 改变，改用 [25-几何变化重标定手册](25-geometry-change-recalibration-runbook.md)，不要只重复本手册的重启步骤。
