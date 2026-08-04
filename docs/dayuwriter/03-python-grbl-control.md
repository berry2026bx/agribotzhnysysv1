# 03 Python 控制代码与 GRBL 通信原理

## 1. 总体调用链

```text
用户输入
  -> grbl_console.py
  -> workspace.py 检查坐标
  -> grbl_protocol.py 校验并编码命令
  -> grbl_controller.py 管理 pySerial
  -> COM3 / CH340
  -> Arduino / GRBL
  -> A4988
  -> 步进电机
```

## 2. 四个核心模块

### grbl_console.py

负责：

- 解析 `status/jog/where/goto/help/quit`；
- 保持一个控制器会话；
- 在运动前检查 XY 目标；
- 把长距离 `goto` 拆成多个安全微动；
- 显示最终原始状态。

### grbl_controller.py

负责：

- 用 115200、8-N-1 打开串口；
- 使用有限读写超时；
- 等待 Arduino 可能发生的启动复位；
- 发送状态查询和点动命令；
- 区分命令接受与机械规划完成；
- 在异常和正常退出时关闭串口。

### grbl_protocol.py

负责：

- 只允许 X/Y/Z；
- 单段距离限制为 0.001 至 5 mm；
- XY 速度不超过 100 mm/min；
- Z 速度不超过 50 mm/min；
- 强制加入 `G21`，防止继承英寸模式；
- 使用固定小数格式，避免 GRBL 不接受的科学计数法。

### workspace.py

负责：

- 解析 `<...|MPos:x,y,z|...>`；
- 检查 P0 坐标目标是否越界；
- 将长距离拆成不超过 5 mm 的分段。

## 3. 串口打开

控制器通过 pySerial 使用：

```python
serial.Serial(
    port="COM3",
    baudrate=115200,
    bytesize=serial.EIGHTBITS,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    timeout=0.2,
    write_timeout=1.0,
    xonxoff=False,
    rtscts=False,
    dsrdtr=False,
)
```

打开此类 Arduino 串口可能触发复位，所以程序等待约 2 秒并清空启动期间的旧输入。打开串口本身不会发送运动命令。

## 4. 实时状态查询

Python 发送一个字节：

```python
b"?"
```

`?` 是 GRBL 实时命令，不加换行。典型返回：

```text
<Idle|MPos:10.000,20.000,0.000|FS:0,0|Pn:P>
```

字段解释：

- `Idle`：控制器当前空闲；
- `MPos`：GRBL 根据已发脉冲估计的机器位置；
- `FS`：当前进给和主轴速度；
- `Pn:P`：探针输入有效。

`MPos` 不是编码器测量值。电机断电、卡住或丢步时，GRBL 仍可能更新 MPos。

## 5. 点动命令

输入：

```text
jog X 5 100
```

编码结果：

```gcode
$J=G91 G21 X5 F100
```

解释：

- `$J=`：GRBL 1.1 点动；
- `G91`：相对坐标；
- `G21`：毫米；
- `X5`：X 正方向 5 mm；
- `F100`：100 mm/min。

通信状态机：

```text
发送 ?
  -> 必须收到 Idle
发送 $J=...
  -> 必须收到 ok
循环发送 ?
  -> 可能先收到 Jog/Run
  -> 最终必须收到 Idle
```

`ok` 只表示 GRBL 接受并解析了命令，不表示机械运动已经完成，更不表示现场一定产生位移。

## 6. goto 绝对坐标

输入：

```text
goto 50 30 100
```

处理过程：

1. 查询当前 MPos；
2. 检查目标是否位于 X/Y 安全范围；
3. 计算 X 和 Y 的相对差值；
4. 分成每段不超过 5 mm；
5. 先完成 X，再完成 Y；
6. 每段都等待 `ok` 和最终 `Idle`。

因此当前 `goto` 走的是轴向折线路径，不是同时插补的直线或对角线。对于未来视觉定位到点，这通常足够；如果工具轨迹必须是直线，需要另行设计受限的 XY 联动命令。

## 7. 自己编写控制脚本

```python
from communication.dayuwriter.grbl_controller import GrblController
from communication.dayuwriter.grbl_protocol import JogCommand

with GrblController("COM3") as robot:
    print(robot.status().raw)
    print(robot.jog(JogCommand("X", 5, 100)).final_status.raw)
    print(robot.jog(JogCommand("Y", -5, 100)).final_status.raw)
```

不要绕过 `GrblController` 直接拼接来自相机或网络的 G-code。坐标必须先经过数值类型、有限值和工作范围验证。

## 8. 当前代码限制

- P0 不会自动寻找；
- Z 没有软件上下限；
- `goto` 仅支持 XY；
- 没有连续轨迹规划；
- 没有运动队列取消按钮或物理急停输入；
- 没有读取电机实际位置的编码器；
- 相机坐标转换尚未实现。
