# GitHub Zero-Beginner Guide for Project Members

本文件是给从未使用过 GitHub 的成员看的操作指南。先按“网页上传方式”完成第一次提交，后续熟悉后再学习 Git 命令和 Pull Request。

仓库地址：

```text
https://github.com/berry2026bx/agribotzhnysysv1
```

## 1. 本仓库是做什么的

本仓库用于统一保存团队项目资料，不再把代码、文档、测试记录、图纸和学习笔记散放在个人电脑、U 盘或聊天群里。

需要放入仓库的内容包括：

- 学习笔记
- 通讯协议资料
- PLC 点位表、寄存器表和测试记录
- ROS2/Gazebo 学习记录和代码
- CAD、仿真、样机结构说明
- 数据采集和标注说明
- 周报、测试记录、问题清单
- 后续软著、专利、论文和开题报告材料

## 2. 第一次使用前要做什么

### 第一步：登录 GitHub

打开：

```text
https://github.com
```

使用自己的 GitHub 账号登录。

### 第二步：接受仓库邀请

仓库管理员邀请你之后，GitHub 通常会通过网页通知或邮箱发送邀请。

你需要点击：

```text
Accept invitation
```

接受邀请后，你才可以向仓库上传文件。

### 第三步：打开团队仓库

打开：

```text
https://github.com/berry2026bx/agribotzhnysysv1
```

如果能看到 `README.md`、`docs/`、`plc/`、`communication/`、`ros2_ws/` 等目录，说明进入正确仓库。

## 3. 每个目录应该放什么

| 目录 | 应该上传的内容 |
| --- | --- |
| `docs/` | 项目说明、任务安排、学习路线、规则文档 |
| `communication/` | 串口、RS485、Modbus、CAN、TCP/UDP、MQTT 学习笔记和示例 |
| `plc/` | PLC 基础资料、I/O 点位表、寄存器表、接线记录、测试记录 |
| `ros2_ws/` | ROS2 学习笔记、节点代码、话题/服务示例、Gazebo 说明 |
| `firmware/` | STM32、Arduino、ESP32 等下位机代码 |
| `cad/` | CAD 模型说明、结构方案、BOM、截图索引 |
| `simulation/` | Gazebo 场景、URDF/SDF 模型说明、仿真记录 |
| `datasets/` | 数据采集说明、图像标注规范、样例数据说明 |
| `reports/` | 个人周报、测试记录、问题清单、阶段汇报 |
| `tests/` | 测试脚本、测试数据说明、联调记录 |
| `patents/` | 专利材料草稿和附图索引 |
| `software_copyright/` | 软著材料、截图、源码节选说明 |
| `papers/` | 论文题目、摘要、提纲、图表和初稿 |
| `open_reports/` | 开题报告材料 |

## 4. 最简单上传方式：网页上传

适合第一次使用 GitHub 的同学。

### 操作步骤

1. 打开仓库页面：

```text
https://github.com/berry2026bx/agribotzhnysysv1
```

2. 点击自己负责的目录。例如：

```text
communication
plc
ros2_ws
cad
datasets
reports
```

3. 点击页面右上方：

```text
Add file
```

4. 点击：

```text
Upload files
```

5. 把要上传的文件拖进去。

6. 在页面下方找到提交说明框。

7. 写一句清楚的提交说明，例如：

```text
docs: add weekly report
comm: add modbus learning notes
plc: add io map template
ros2: add topic learning notes
cad: add prototype structure notes
data: add annotation rules
test: add plc test record
```

8. 点击：

```text
Commit changes
```

完成后，仓库页面会显示你刚上传的文件。

## 5. 第一次每个人要上传什么

第一次不要追求复杂，先完成一次有效提交。

可选任务：

- 上传一份学习笔记
- 上传一份测试记录
- 上传一个模板文件
- 上传一份接口表
- 上传一份数据采集说明
- 上传一份 CAD 或仿真说明
- 上传一份周报

建议文件名格式：

```text
方向-内容-日期.md
```

示例：

```text
modbus-learning-notes-20260705.md
plc-io-map-template-20260705.md
ros2-topic-notes-20260705.md
weekly-report-20260705.md
```

如果不熟悉 Markdown，也可以先上传 `.docx`、`.txt`、`.pdf` 或图片说明，但后续建议逐步改为 Markdown 文档。

## 6. 提交说明怎么写

提交说明用于告诉别人你这次改了什么。不要只写“更新”“作业”“提交”。

推荐格式：

```text
类型: 具体做了什么
```

常用类型：

| 类型 | 用途 | 示例 |
| --- | --- | --- |
| `docs` | 文档、笔记、周报、说明 | `docs: add weekly report` |
| `comm` | 通讯协议资料 | `comm: add modbus notes` |
| `plc` | PLC 资料 | `plc: add register table template` |
| `ros2` | ROS2 资料或代码 | `ros2: add topic demo notes` |
| `firmware` | 下位机代码 | `firmware: add serial demo` |
| `cad` | 结构设计和 CAD | `cad: add prototype notes` |
| `sim` | 仿真资料 | `sim: add gazebo notes` |
| `data` | 数据和标注说明 | `data: add annotation rules` |
| `test` | 测试记录 | `test: add communication test record` |
| `fix` | 修正错误 | `fix: correct register address` |

## 7. 公开仓库禁止上传什么

本仓库是公开仓库，所有人都可能看到内容。禁止上传：

- GitHub 密码、邮箱验证码、Token、SSH 私钥
- 手机号、身份证号、家庭地址等个人隐私
- 服务器密码、数据库密码、设备公网 IP
- 未经允许公开的专利核心细节
- 大量原始视频、大量图片或超大数据集
- 未经授权的第三方资料

如果文件很大，例如视频、大量图片、完整数据集，先放到指定网盘或服务器，仓库里只写说明和索引。

## 8. 上传前自查

上传前检查 5 件事：

1. 文件是否放在正确目录。
2. 文件名是否能看懂。
3. 提交说明是否清楚。
4. 文件里是否包含密码、手机号、验证码、私钥等敏感信息。
5. 文件是否太大。

## 9. 后续进阶：使用 Git 命令

第一次可以先用网页上传。后续需要正式写代码时，再学习 Git 命令。

### 克隆仓库

```bash
git clone https://github.com/berry2026bx/agribotzhnysysv1.git
cd agribotzhnysysv1
```

### 更新本地仓库

```bash
git pull origin main
```

### 创建自己的分支

```bash
git checkout -b your-task-branch
```

### 提交修改

```bash
git add .
git commit -m "docs: add learning notes"
```

### 推送到 GitHub

```bash
git push origin your-task-branch
```

推送后，在 GitHub 页面创建 Pull Request，等待审核合并。

## 10. 遇到问题怎么办

如果遇到问题，先截图，并说明：

- 你在哪个页面操作
- 你点击了什么
- 出现了什么提示
- 你准备上传哪个文件

不要反复乱点，也不要把同一文件重复上传很多次。

## 11. 本周最低要求

每位成员至少完成一次有效提交。

最低标准：

```text
1 个文件 + 1 条清楚的提交说明
```

推荐提交位置：

```text
reports/
communication/
plc/
ros2_ws/
cad/
datasets/
```

完成第一次提交后，仓库管理员会根据提交记录、文件内容和测试记录进行检查。
