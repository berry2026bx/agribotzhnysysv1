# DayuWriter 写字机恢复与视觉改造文档

这套文档记录 2026-07-26 在 Windows 11 新电脑上恢复 DayuWriter/CoreXY 写字机、建立 Python 控制、完成基础标定并准备接入 Intel RealSense D435i 的全过程。

文档采用证据优先原则：现场观察、设备输出和代码测试属于已验证事实；历史对话中的端口、固件和参数只作为线索，不直接当作当前事实。

## 当前结论

- Windows 当前识别设备为 `USB-SERIAL CH340 (COM3)`。
- 当前实际固件为 `Grbl 1.1f kvenjoy.com.20170131`，不是历史记录中的 1.1h。
- 12 V 电机电源必须接红色 CNC V3 板的 `12-36V` 端子，不能只接 Arduino UNO 圆形电源孔。
- X、Y、Z 三轴均已实际运动。
- X/Y/Z 距离参数在当前测量精度下正确，未修改 `$100/$101/$102`。
- 已建立人工物理参考点 P0 和 Python XY 安全范围。
- 已实现相对微动、持续连接控制台、`where`、`goto` 和越界保护。
- 当前无自动回零；启动控制台前必须把机构物理对准 P0。
- 当前 `Z+` 向下、`Z-` 向上，Z 轴尚未建立软件边界。
- 状态持续显示 `Pn:P`，表示探针输入有效；原因尚未最终确认。
- D435i 尚未接入和标定，视觉坐标不能直接用于运动。

## 推荐阅读顺序

1. [01-硬件恢复与接线](01-hardware-recovery.md)
2. [02-Windows、Conda 与 VS Code 环境](02-windows-python-vscode.md)
3. [03-Python 控制代码与 GRBL 通信原理](03-python-grbl-control.md)
4. [04-坐标系、P0 与机械标定](04-coordinate-calibration.md)
5. [05-日常操作与故障排查](05-operation-troubleshooting.md)
6. [06-D435i 视觉改造路线](06-d435i-vision-roadmap.md)

## 原始证据

`baseline/` 保存设备身份、GRBL 原始输出、三轴观察、Python 实机测试和标定记录。原始记录不应被后续总结替代。

## 代码入口

- `communication/dayuwriter/grbl_console.py`：交互控制台
- `communication/dayuwriter/grbl_controller.py`：持久串口与状态机
- `communication/dayuwriter/grbl_protocol.py`：GRBL 命令校验和编码
- `communication/dayuwriter/workspace.py`：P0 坐标解析和 XY 安全范围
- `tests/dayuwriter/`：离线测试

## 当前仓库位置

```text
C:\Users\Administrator\Desktop\20260725DaZiJJJ\agribotzhnysysv1\.worktrees\dayuwriter-recovery-execution
```

当前开发分支：`codex/dayuwriter-recovery-execution`。
