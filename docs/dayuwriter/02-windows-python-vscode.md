# 02 Windows、Conda 与 VS Code 环境

## 1. 项目目录

在 VS Code 中打开：

```text
C:\Users\Administrator\Desktop\20260725DaZiJJJ\agribotzhnysysv1\.worktrees\dayuwriter-recovery-execution
```

PowerShell 命令：

```powershell
code C:\Users\Administrator\Desktop\20260725DaZiJJJ\agribotzhnysysv1\.worktrees\dayuwriter-recovery-execution
```

## 2. Conda 环境

环境名称：

```text
dayuwriter-control
```

解释器位置：

```text
C:\Users\Administrator\.conda\envs\dayuwriter-control\python.exe
```

环境文件：`environment/dayuwriter-control.yml`。

已安装的主要依赖：

```text
Python 3.11.15
pyserial 3.5
pytest 9.1.1
```

## 3. VS Code 解释器设置

1. 按 `Ctrl+Shift+P`；
2. 选择 `Python: Select Interpreter`；
3. 选择 `dayuwriter-control`，或者输入上述解释器绝对路径；
4. 打开新的 VS Code 终端。

激活和验证：

```powershell
conda activate dayuwriter-control
python --version
python -c "import serial; print(serial.__version__)"
```

## 4. 运行离线测试

```powershell
pytest tests/dayuwriter -q
```

截至 2026-07-26，完整套件结果为：

```text
85 passed
```

这些测试使用假串口和假时钟，不会连接 COM3，也不会移动机器。

## 5. 启动交互控制台

硬件前提：

- 机器物理对准 P0；
- USB 和 12 V 正确连接；
- 笔尖处于安全高度；
- 微雕管家、UGS 和其他串口程序全部关闭。

运行：

```powershell
python -m communication.dayuwriter.grbl_console --port COM3
```

命令：

```text
status
where
jog X 5 100
jog Y -5 100
jog Z -1 50
goto 50 30 100
goto 0 0 100
help
quit
```

当前 `Z+` 向下，`Z-` 向上。

## 6. 单次命令行控制

仅执行一次相对微动：

```powershell
python -m communication.dayuwriter.grbl_jog `
  --port COM3 `
  --axis X `
  --distance 5 `
  --feed 100
```

单次 CLI 会重新打开串口，可能触发 Arduino/GRBL 复位。需要连续坐标时，必须使用交互控制台或在同一个 `GrblController` 上连续调用。

## 7. 常见 VS Code 问题

### 找不到 communication 包

确认 VS Code 打开的是执行 worktree 根目录，而不是桌面上层目录或主仓库的计划分支。

### 找不到 serial

确认选择的是 `dayuwriter-control` 解释器，并执行：

```powershell
conda activate dayuwriter-control
python -c "import serial"
```

### COM3 被占用

关闭微雕管家、UGS、Arduino 串口监视器和其他 Python 控制程序。Windows 通常不允许两个程序同时独占 COM3。
