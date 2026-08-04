# YOLO 目标到 DayuWriter 的演示操作

本功能分成两个进程：D435i/YOLO 网页是 display-only，只显示图像和坐标；跟随进程在人工确认后才打开唯一 CH340 串口。网页本身不会运动。

## 已验证环境

dayuwriter-control 中已经验证 torch 2.13.0+cu126、GPU available True、NVIDIA GeForce RTX 3060、cv2 4.13.0、ArUco True、Ultralytics OK。

## 首次显示

先关闭 RealSense Viewer，确认相机 A 序列号 231122070403，模型文件例如 models/yolo11n.pt 已存在。12 V 可以先断开，写字机不需要运动。

在 VS Code 终端运行：

    conda activate dayuwriter-control
    Set-Location C:\Users\Administrator\Desktop\20260725DaZiJJJ\agribotzhnysv1\.worktrees\dayuwriter-recovery-execution
    python -m vision.realsense.live_yolo_dashboard --serial 231122070403 --model models\yolo11n.pt --class-name bottle

浏览器打开 http://127.0.0.1:8765/。页面应显示 RGB、目标类别、置信度、像素中心、深度和相机 XYZ。六个 ArUco ID、参考板姿态和固定 P0 映射有效时，才会显示 machine_xy_mm；深度无效或参考板丢失时，坐标字段会隐藏，状态保持 display_only。

## 人工确认后的一次 XY 演示

只有同时满足以下条件才运行运动：笔尖物理位于固定 P0；12 V 接通；笔尖悬空；去目标和返回 P0 的完整 XY 路径净空；Z 方向有余量；相机、纸张和 ArUco 板未移动；Viewer 已关闭；页面显示请求类别、稳定相机 XYZ、reference_state=ready、mapping_state=available；系统只发现一个 CH340。

在同一个 VS Code 终端运行：

    python -m communication.dayuwriter.visual_follow --dashboard-url http://127.0.0.1:8765/state.json --class-name bottle --port COM4 --baseline-x 0 --baseline-y 0 --continuous --max-moves 1 --max-observations 120 --return-to-p0 --hold-at-target-seconds 10 --feed 500 --execute --physical-preflight

该命令使用固定物理 P0 (0,0)，不是把第一个 YOLO 目标当作原点。它先走 XY，停留 10 秒，再回到 P0；默认不下降 Z。只有 XY 经尺子和悬空测试正确后，才可另加 z-drop-mm 0.5 和 z-drop-preflight，最大 1 mm。

## 一键显示入口

    scripts\start_dayuwriter_yolo.cmd models\yolo11n.pt bottle 231122070403

该入口默认只启动显示页。停止时运行：

    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\stop_dayuwriter_yolo.ps1

停止运动可能让笔尖停在目标处；下一轮运动前必须重新物理确认 P0。不要用 Stop-Process -Name python，以免误杀其他项目。

## 相机或纸板移动后的处理

相机高度/角度、写字机位置、纸张或 ArUco 板改变后，旧姿态和旧机器映射立即失效。重新固定纸板，确认 P0，保证六个 ID 完整入镜，然后重新启动显示页，等待 reference_state=ready 和重投影误差合格，再进行无动力 XY 验证。不要修改 GRBL 坐标去补偿视觉误差。

## 故障边界

- yolo_dependency_missing：只补用户环境依赖，不关闭 Windows 安全防护。
- depth_invalid：保留图像和检测框，不发布 XYZ，不运动。
- reference_lost 或姿态移动：丢弃旧变换，不运动。
- 多个同类目标：当前实现选择置信度最高且面积次高者；正式杂草模型应增加明确目标选择策略。
- GRBL 超时或报错：停止当前周期，断开 12 V，并重新确认 P0。
