# DayuWriter 写字机恢复与视觉改造文档

这套文档记录从 2026-07-26 起在 Windows 11 上恢复 DayuWriter/CoreXY 写字机、建立 Python 控制、完成基础标定，并最终完成 D435i A 的纸面红方块显示与一次受监督的有界 XY/Z 演示。

文档采用证据优先原则：现场观察、设备输出和代码测试属于已验证事实；历史对话中的端口、固件和参数只作为线索，不直接当作当前事实。

## 初始恢复阶段结论

> 下列项目是 2026-07-26 恢复阶段的基线。后续相机、参考板和视觉跟随结果以 [15](15-camera-a-a4-aruco-high-resolution-live-validation.md)、[16](16-camera-a-p0-red-square-live-validation.md)、[17](17-visual-follow-first-operation.md)、[19](19-calibration-process-and-lessons.md) 和 [20](20-project-end-to-end-record.md) 为准。

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
- 该阶段 D435i 尚未接入和标定；后续记录已完成显示标定及一次受监督的受限运动验证，但没有形成无人值守视觉作业能力。

## 推荐阅读顺序

1. [01-硬件恢复与接线](01-hardware-recovery.md)
2. [02-Windows、Conda 与 VS Code 环境](02-windows-python-vscode.md)
3. [03-Python 控制代码与 GRBL 通信原理](03-python-grbl-control.md)
4. [04-坐标系、P0 与机械标定](04-coordinate-calibration.md)
5. [05-日常操作与故障排查](05-operation-troubleshooting.md)
6. [06-D435i 视觉改造路线](06-d435i-vision-roadmap.md)
7. [07-新电脑部署与现场迁移](07-new-laptop-migration.md)
8. [14-全新电脑运行可视化界面](14-new-pc-live-monitor.md)
9. [19-标定过程与经验](19-calibration-process-and-lessons.md)
10. [20-项目全流程记录](20-project-end-to-end-record.md)
11. [21-全新电脑部署指南](21-new-computer-deployment.md)
12. [22-项目失败复盘与防复发记录](22-project-failure-postmortems.md)

## 原始证据

`baseline/` 保存设备身份、GRBL 原始输出、三轴观察、Python 实机测试和标定记录。原始记录不应被后续总结替代。

## 代码入口

- `communication/dayuwriter/grbl_console.py`：交互控制台
- `communication/dayuwriter/grbl_controller.py`：持久串口与状态机
- `communication/dayuwriter/grbl_protocol.py`：GRBL 命令校验和编码
- `communication/dayuwriter/workspace.py`：P0 坐标解析和 XY 安全范围
- `communication/dayuwriter/grbl_monitor.py`：三页现场控制与通信可视化界面
- `tests/dayuwriter/`：离线测试

## 当前仓库位置

```text
C:\Users\Administrator\Desktop\20260725DaZiJJJ\agribotzhnysysv1\.worktrees\dayuwriter-recovery-execution
```

当前开发分支：`codex/dayuwriter-recovery-execution`。
