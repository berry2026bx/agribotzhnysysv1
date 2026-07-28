# 全新 Windows 11 电脑运行 DayuWriter 可视化界面

适用对象：一台没有项目代码、没有 Conda 环境、没有 CH340 驱动的新 Windows 11 电脑。

目标：在不改动任何控制代码的前提下，启动 `grbl_monitor.py` 的三页可视化界面，并在连接写字机后看到真实的 Python 调用、TX、RX、GRBL 状态和 MPos 坐标。

本手册不包含相机标定、目标检测或自动运动。新电脑的 COM 端口、驱动状态和物理 P0 必须重新确认，不能照搬旧电脑记录。

## 最简单：不连接写字机，只展示界面

这 4 步只用于给人展示界面、通信链路图和协议说明。**不需要连接写字机 USB，不需要安装 CH340 驱动，也不要接 12V 电源。**

1. 在新电脑安装 Git for Windows 和 Miniconda。
2. 打开“Anaconda Prompt”。
3. 逐行粘贴下面命令：

```bat
cd /d %USERPROFILE%\Documents
git clone --branch codex/dayuwriter-recovery-execution --single-branch https://github.com/berry2026bx/agribotzhnysysv1.git DayuWriter
cd /d %USERPROFILE%\Documents\DayuWriter
conda create -n dayuwriter-control python=3.11 pyserial pytest -y
conda activate dayuwriter-control
python -m communication.dayuwriter.grbl_monitor --port DEMO
```

4. 窗口打开后，只浏览“现场控制、通信入门、坐标入门”三个页面。**不要点击“连接并读取状态”。**

`DEMO` 只是一个占位名字，表示“当前没有接真实写字机”。当前程序不会在打开窗口时访问串口；只有点击连接按钮才会尝试打开 `--port` 后面的名称。

这种离线展示会显示完整的 Python → pySerial → USB-UART/CH340 → GRBL → STEP/DIR → A4988 → 电机链路图和协议说明，但不会生成伪造的“实时串口数据”。真实的 TX/RX、MPos 和坐标轨迹仍然只在连接真实设备后显示。

## 1. 先理解成功标准

完成下列两级验证即可。

### A. 软件界面已运行（不接写字机也可完成）

```text
[ ] 能打开 DayuWriter 现场控制窗口
[ ] 窗口顶部显示命令行传入的 COMx
[ ] 可以阅读“现场控制、通信入门、坐标入门”三个页面
[ ] 运行监视器测试通过
```

### B. 写字机已重新连接（需要 USB；小幅移动还需要 12V）

```text
[ ] 设备管理器显示 USB-SERIAL CH340 (COMx)
[ ] 点击“连接并读取状态”后，界面出现真实 CALL、TX ?、RX <...> 记录
[ ] 界面显示 GRBL 状态和 MPos
[ ] 仅在机械检查完成后，才做一次受限 X/Y 5 mm 动作
```

`COMx` 是占位符，必须替换为新电脑当前识别到的实际端口，例如 `COM4` 或 `COM7`。端口编号是 Windows 分配的设备地址，不是 GRBL 固件版本，也不是写字机永久编号。

## 2. 需要准备的东西

### 软件

1. Git for Windows。
2. Miniconda 或 Anaconda。
3. VS Code 与 Microsoft Python 扩展。
4. CH340 Windows 驱动。若设备管理器没有正常出现 `USB-SERIAL CH340 (COMx)`，从 [WCH 官方 CH341SER 驱动页](https://www.wch-ic.com/downloads/CH341SER_EXE.html) 下载并安装；不要从不明驱动站下载。

### 硬件

1. DayuWriter 的 USB 数据线。
2. 12V 适配器，仅在准备验证电机动作时连接。
3. 能立刻拔掉的 12V 电源插头。

首次软件部署不需要 12V，也不需要连接相机。

## 3. 获取项目代码

打开 PowerShell。下面命令会把仓库放到新电脑当前用户的“文档”目录；不需要复制旧电脑的 `.conda` 文件夹。

```powershell
$dayuWorkspace = Join-Path $env:USERPROFILE "Documents\DayuWriter"
git clone --branch codex/dayuwriter-recovery-execution --single-branch `
  https://github.com/berry2026bx/agribotzhnysysv1.git `
  $dayuWorkspace
Set-Location $dayuWorkspace
git branch --show-current
git log -1 --oneline
```

预期分支：

```text
codex/dayuwriter-recovery-execution
```

在 VS Code 中打开项目：

```powershell
code $dayuWorkspace
```

如果 PowerShell 提示 `code` 不是命令，打开 VS Code，选择“文件 → 打开文件夹”，选择 `$dayuWorkspace` 对应的目录。后续所有终端命令都必须在该项目根目录执行；根目录应包含 `communication`、`docs`、`environment` 和 `tests`。

## 4. 建立 Python 环境

### 推荐：完整项目环境

该方式同时安装后续 RealSense 代码所需依赖。新电脑在项目根目录执行：

```powershell
conda env create -f environment\dayuwriter-control.yml
conda activate dayuwriter-control
python --version
python -c "import serial; print('pyserial', serial.__version__)"
python -m pytest tests/dayuwriter/test_grbl_monitor.py -q
```

预期：Python 版本为 3.11，`pyserial` 可导入，监视器测试通过。测试使用假串口，不会打开 COM 口，也不会移动写字机。

### 仅为运行可视化界面的最小环境

如果完整环境在 `pyrealsense2` 安装阶段失败，而当前目标只是运行可视化界面，可改用下面最小环境。不要在同一环境里混用两套安装命令。

```powershell
conda create -n dayuwriter-control python=3.11 pyserial pytest -y
conda activate dayuwriter-control
python -m pytest tests/dayuwriter/test_grbl_monitor.py -q
```

此最小环境足以运行 `communication.dayuwriter.grbl_monitor`。后续要使用 D435i 时，删除或更新该环境并回到完整清单：

```powershell
conda env update -n dayuwriter-control -f environment\dayuwriter-control.yml --prune
```

### 在 VS Code 选择正确解释器

1. 按 `Ctrl+Shift+P`。
2. 运行 `Python: Select Interpreter`。
3. 选择名称为 `dayuwriter-control` 的解释器。
4. 打开一个新的 VS Code PowerShell 终端，执行：

```powershell
conda activate dayuwriter-control
python -c "import sys, serial; print(sys.executable); print(serial.__version__)"
```

`sys.executable` 必须位于 `dayuwriter-control` 环境中。若报 `No module named serial`，说明 VS Code 使用了 base Python 或系统 Python，而不是项目环境。

## 5. 第一次只打开界面（不连硬件）

可视化界面是 Tkinter 桌面程序，不是网页，不需要浏览器、Node.js 或本地服务器。先任选一个占位端口启动窗口，例如 `COM4`：

```powershell
conda activate dayuwriter-control
Set-Location $dayuWorkspace
python -m communication.dayuwriter.grbl_monitor --port COM4
```

此时程序只创建窗口，不会打开 `COM4`，不会发送指令，也不会移动写字机。只有点击界面的“连接并读取状态”后，程序才会打开传入端口。

应能看到：

```text
现场控制：Python → pySerial → Windows COMx → CH340 → GRBL → STEP/DIR → A4988 → 机械机构
通信入门：COMx、CH340、USB-UART、G-code/Jog、TX/RX、状态帧的解释
坐标入门：MPos、人工 P0、X/Y/Z 正方向和软件边界
```

关闭窗口可直接关闭程序。该窗口关闭后会释放已经打开的串口。

## 6. 让新电脑识别写字机 USB

### 6.1 先只接 USB，12V 保持断开

1. 拔掉写字机 12V 适配器，确认 CNC V3 板的 `12-36V` 端子没有外部供电。
2. 只把写字机 USB 连接到新电脑。
3. 打开“设备管理器 → 端口（COM 和 LPT）”，或在 PowerShell 执行：

```powershell
Get-CimInstance Win32_SerialPort |
  Select-Object DeviceID, Name, PNPDeviceID, Manufacturer
```

4. 找到类似下面的一行：

```text
DeviceID : COMx
Name     : USB-SERIAL CH340 (COMx)
```

5. 记录真实端口，例如 `COM7`。

当前实验电脑曾验证过 `COM4`，但这不是新电脑的默认端口。换 USB 插口、换电脑、重装驱动后，编号可能改变。

### 6.2 没有 CH340 设备时

1. 拔插 USB，观察设备管理器是否变化。
2. 更换一根确定支持数据传输的 USB 线与一个直连 USB 接口。
3. 安装第 2 节所列 WCH 官方驱动，重启 Windows 后重新插 USB。
4. 若出现黄色警告或仍未显示 CH340，不要接 12V，不要尝试发送 GRBL 指令。

## 7. 启动真实端口并读取状态

先关闭所有可能占用端口的软件：微雕管家、UGS、Arduino 串口监视器、旧的 Python 控制程序、另一份可视化界面。Windows 串口通常只能被一个程序独占打开。

使用第 6 节得到的真实端口启动。例如新电脑显示 `COM7`：

```powershell
conda activate dayuwriter-control
Set-Location $dayuWorkspace
python -m communication.dayuwriter.grbl_monitor --port COM7
```

注意：端口参数显示什么，窗口顶部就显示什么。程序不会猜测或自动替换 `COMx`。

点击“连接并读取状态”后，程序会：

```text
1. 用 pySerial 打开 COM7，参数为 115200 baud、8-N-1、无流控。
2. 等待约 2 秒，让 Arduino/GRBL 串口启动稳定。
3. 清空已有输入缓冲。
4. 发送 GRBL 实时状态查询字节 ?。
5. 等待并显示真实 RX 状态帧，例如 <Idle|MPos:...>。
```

`?` 是只读状态查询，不是移动命令。打开一个新的串口会话可能导致 Arduino/GRBL 复位或其显示坐标重新开始解释；本机没有编码器与自动回零。因此，连接成功只能证明通信正常，不能自行证明物理笔架就在 P0。

界面中应依次出现真实记录：

```text
CALL  GrblController.open(port='COM7')
CALL  GrblController.status()
TX    ?
RX    <Idle|MPos:...>
```

若出现 `failed to open GRBL port`，优先检查端口是否写对、其他软件是否占用端口、CH340 驱动是否正常。不要通过不断重试运动按钮来解决连接问题。

## 8. 仅在需要验证机械时接 12V

本节不是“运行界面”的前置条件；它只用于验证新电脑可以真实控制写字机。

在接 12V 前确认：

```text
[ ] CNC V3 的 12-36V 接线端子：红线接 +，黑线接 -
[ ] 笔尖悬空，没有压在纸面、底座或机械边界上
[ ] X/Y/Z 都留有足够运动余量
[ ] 皮带、同步轮顶丝、丝杆联轴器和 XYZ 电机插头未因搬运松动
[ ] 12V 插头可随时拔掉
[ ] 笔架已物理对准人工 P0 标记
```

随后接入 12V，观察没有自发运动、异响、焦味、冒烟或火花。回到可视化界面，先确认读取状态仍为正常状态；再只点击一次 X 或 Y 的 `±5 mm` 按钮。

一次可信的移动证据必须包括：

```text
TX $J=G91 G21 ...      电脑确实写出 Jog 指令
RX ok                  GRBL 接受了该行，不等于完成
RX <Jog|...>（可能出现）GRBL 报告运动中
RX <Idle|MPos:...>     GRBL 报告控制周期结束
现场肉眼观察            机构确实按正确方向位移
```

`MPos` 是 GRBL 的内部位置记录，不是编码器实测。断电、手推、重插 USB、复位或疑似丢步后，都要重新将笔架物理对准 P0，再解释坐标。

## 9. 常见问题速查

| 现象 | 首先检查 | 不要做 |
| --- | --- | --- |
| `conda` 不是命令 | 从 Anaconda Prompt 打开项目，或重新安装/初始化 Conda | 把 Python 包安装到不确定的系统 Python |
| `No module named serial` | `conda activate dayuwriter-control` 后再运行；检查 VS Code 解释器 | 在 base 环境盲目安装多个 pyserial |
| 窗口显示 COM4，但设备管理器是 COM7 | 关闭窗口，用 `--port COM7` 重新启动 | 修改代码把 COM4 写死 |
| `failed to open GRBL port` | 端口拼写、其他串口软件、CH340 驱动、USB 数据线 | 同时打开 UGS、Arduino 监视器和本界面 |
| 有 `RX ok`，电机不动 | 12V 是否真正接到 CNC V3 的 `12-36V` 端子 | 仅因 `ok` 就重刷固件或改 GRBL 参数 |
| 有状态帧但坐标不可信 | 重新物理对齐 P0 | 把 MPos 当成绝对机械真值 |
| 界面打不开 | 在项目根目录运行命令；确认 `python -m pytest tests/dayuwriter/test_grbl_monitor.py -q` 通过 | 从 `communication\dayuwriter` 子目录直接运行脚本 |

## 10. 每次重启后的最短操作

```powershell
conda activate dayuwriter-control
Set-Location "$env:USERPROFILE\Documents\DayuWriter"
python -m communication.dayuwriter.grbl_monitor --port COMx
```

把 `COMx` 换成设备管理器当前显示的真实端口。若只演示通信界面，不点击“连接并读取状态”，则不会打开串口；若需要读取实时数据，先关闭其他串口软件，再点击连接。

## 11. 相关文档

- [07-新电脑部署与现场迁移](07-new-laptop-migration.md)：相机、写字机迁移与 P0 标定的完整路线。
- [02-Windows、Conda 与 VS Code 环境](02-windows-python-vscode.md)：当前环境与 VS Code 的细节。
- [03-Python 控制代码与 GRBL 通信原理](03-python-grbl-control.md)：控制模块与协议基础。
- [05-日常操作与故障排查](05-operation-troubleshooting.md)：常规现场故障处理。

## 12. 本文依据与限制

- 当前开发分支：`codex/dayuwriter-recovery-execution`。
- 当前实验电脑的已验证记录显示 CH340 曾使用 `COM4` 完成小幅 X 轴往返；该记录不能替代新电脑上的端口和运动验证。
- 可视化程序 `communication/dayuwriter/grbl_monitor.py` 在用户点击连接前不创建 `GrblWorker`，因此不打开串口；连接后显示的是实际 TraceEvent，而不是模拟通信。
- `ok` 仅表示 GRBL 接受指令；最终 `Idle` 与现场观察才是一次移动完成的必要证据。
