# 05 日常操作与故障排查

## 1. 每次启动前

1. 检查同步带、导轨、丝杆和电机线；
2. 确认 12 V 端子压紧；
3. 笔尖或工具保持安全悬空；
4. 机构物理对准 P0；
5. USB 连接电脑，12 V 连接 CNC V3；
6. 关闭所有其他串口程序；
7. 在 VS Code 激活 `dayuwriter-control`；
8. 启动交互控制台；
9. 先执行 `status` 和 `where`；
10. 第一次只做小距离运动。

## 2. 推荐操作会话

```powershell
conda activate dayuwriter-control
python -m communication.dayuwriter.grbl_console --port COM3
```

```text
status
where
jog X 1 50
goto 10 10 100
goto 0 0 100
quit
```

## 3. 正常输出

```text
connected: <Idle|MPos:0.000,0.000,0.000|...>
accepted: ok
final: <Idle|MPos:...>
```

软件成功不等于机械成功。第一次测试、维修后测试和标定测试都需要现场观察。

## 4. 软件坐标变化但电机不动

优先检查：

1. 12 V 是否接在 CNC V3 的 `12-36V` 端子；
2. 端子螺丝是否压紧；
3. 适配器是否实际输出约 12 V；
4. A4988 是否正确插入；
5. 电机四线插头是否松动。

本项目曾因 12 V 端子接触不良出现“GRBL 返回 ok、MPos 更新，但电机无声无动作”。

## 5. COM3 打不开

可能原因：

- 微雕管家、UGS 或 Arduino 串口监视器占用端口；
- USB 线松动；
- Windows 给设备分配了新的 COM 号；
- CH340 设备异常。

先在设备管理器重新确认端口，不要硬编码历史 COM11。

## 6. MPos 每次从零开始

打开串口可能让 Arduino/GRBL 复位。单次 `grbl_jog` 每次都会重新打开端口，所以物理位移会累计，而每次输出可能重新从零计算。

需要连续坐标时使用 `grbl_console`，不要反复启动单次 CLI。

## 7. goto 被拒绝

检查目标：

```text
X 必须在 [-190, 190]
Y 必须在 [-90, 140]
速度必须 <= 100 mm/min
```

程序在发送任何运动前检查最终目标，但当前没有对中途障碍物做路径规划。

## 8. Z 方向

当前：

```text
Z+ 向下
Z- 向上
```

在 Z 上下边界未标定前，只使用低速小距离点动。不要让视觉程序自动发送 Z 运动。

## 9. 紧急情况

- 机械即将碰撞：立即切断 12 V；
- 软件卡死：切断 12 V，再关闭程序；
- 不要把 `Ctrl-X` 当成硬件急停；
- 断电后重新使用前，必须重新对准 P0。

## 10. 禁止直接运行的历史脚本

以下历史脚本包含硬编码 COM11、自动 G92、自动运动、参数写入或无截止等待等问题，不能直接用于当前机器：

```text
dazij_allcode/aceshi.py
dazij_allcode/bzhongjian.py
dazij_allcode/c.py
dazij_allcode/d.py
dazij_allcode/verify_basic.py
dazij_allcode/calibrate_camera.py
dazij_allcode/full_loop.py
```

UGS 本地包也没有完成官方哈希核对，当前恢复和控制不依赖它。
