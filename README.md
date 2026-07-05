# agribotzhnysysv1

An open training and collaboration repository for an agricultural robotics and intelligent control project.

This repository is used to organize learning notes, experiment records, source code, interface documents, simulation assets, test reports, and early-stage project outputs related to agricultural robots, PLC control, communication protocols, ROS2/Gazebo, embedded systems, sensor data, computer vision, CAD modeling, and research documentation.

## Project Scope

The repository focuses on the following work areas:

- Git and GitHub collaboration practice
- Communication protocols such as serial communication, RS485, Modbus, CAN, TCP/UDP, and MQTT
- PLC control, I/O mapping, register tables, safety logic, and actuator control
- ROS2 workspace organization, topics, services, launch files, robot control, and navigation
- Gazebo simulation, URDF/SDF models, digital prototypes, and test scenes
- Embedded firmware examples for common microcontroller platforms
- Agricultural perception datasets, image annotation rules, and sensor data records
- CAD models, mechanical structure notes, BOM files, and prototype documentation
- Weekly reports, test records, issue tracking, and project review materials
- Draft materials for software copyright, patents, papers, and opening reports

## Repository Structure

| Path | Purpose |
| --- | --- |
| `docs/` | Project rules, task planning, Git workflow, equipment notes, and learning roadmaps |
| `plc/` | PLC programs, I/O maps, Modbus register tables, wiring notes, and safety logic |
| `communication/` | Serial, RS485, Modbus, CAN, TCP/UDP, MQTT notes and demos |
| `ros2_ws/` | ROS2 workspace, packages, nodes, launch files, navigation, and control code |
| `firmware/` | Embedded firmware examples and lower-level controller code |
| `cad/` | CAD models, structure notes, BOM files, and mechanical design records |
| `simulation/` | Gazebo worlds, URDF/SDF models, simulation scripts, and scene notes |
| `datasets/` | Dataset notes, image annotation rules, sample data descriptions, and data indexes |
| `reports/` | Weekly reports, test records, issue lists, and review notes |
| `patents/` | Patent draft materials and figure indexes |
| `software_copyright/` | Software copyright draft materials, screenshots, and version notes |
| `papers/` | Paper topics, outlines, figures, drafts, and experiment notes |
| `open_reports/` | Opening report drafts and supporting materials |
| `tests/` | Communication tests, PLC tests, ROS2 tests, and integration test records |

## Current Tasks

The current stage is mainly for repository setup and basic collaboration practice.

Each project member should:

1. Accept the repository invitation if collaborator access is required.
2. Learn how to use GitHub web upload or basic Git commands.
3. Submit at least one useful file, such as a learning note, test record, code demo, interface table, CAD note, dataset note, or weekly report.
4. Put files into the correct directory.
5. Use clear commit messages.
6. Avoid uploading private, sensitive, or oversized files.

Suggested first submissions:

| Area | Suggested Submission |
| --- | --- |
| Communication | Basic notes or demos for serial, Modbus, CAN, TCP/UDP, or MQTT |
| PLC | I/O map template, register table template, wiring notes, or basic control notes |
| ROS2 | Workspace notes, topic/service examples, launch notes, or navigation learning notes |
| Vision and Data | Dataset collection notes, annotation rules, or sample data descriptions |
| CAD and Simulation | CAD modeling notes, prototype structure notes, URDF/SDF notes, or Gazebo notes |
| Reports | Weekly report, test record, problem list, or review summary |

## How to Upload Files

### Option 1: Upload on GitHub Web

This is the easiest method for beginners.

1. Open this repository on GitHub.
2. Enter the directory that matches your work area, such as `communication/`, `plc/`, `ros2_ws/`, `cad/`, `datasets/`, or `reports/`.
3. Click `Add file`.
4. Click `Upload files`.
5. Drag files into the page.
6. Write a clear commit message.
7. Click `Commit changes`.

### Option 2: Upload with Git Commands

Clone the repository:

```bash
git clone <repository-url>
cd agribotzhnysysv1
```

Create a personal working branch:

```bash
git checkout -b your-branch-name
```

After adding or editing files:

```bash
git add .
git commit -m "docs: add learning notes"
git push origin your-branch-name
```

Then open a Pull Request on GitHub for review and merge.

## Commit Message Rules

Use this format:

```text
type: short description
```

Common prefixes:

| Prefix | Meaning | Example |
| --- | --- | --- |
| `docs` | Documentation, notes, plans, and rules | `docs: add weekly report template` |
| `comm` | Communication protocol notes and demos | `comm: add modbus tcp notes` |
| `plc` | PLC files, I/O maps, register tables, and control notes | `plc: add io map template` |
| `ros2` | ROS2 packages, nodes, launch files, and navigation notes | `ros2: add topic demo notes` |
| `firmware` | Embedded firmware and lower-level controller code | `firmware: add serial demo` |
| `cad` | CAD models and mechanical design notes | `cad: add prototype structure notes` |
| `sim` | Simulation models, scenes, and scripts | `sim: add gazebo scene notes` |
| `data` | Dataset notes, annotation rules, and sample data indexes | `data: add annotation rules` |
| `test` | Test scripts and test records | `test: add plc actuator test record` |
| `fix` | Fixes and corrections | `fix: correct register description` |

## Weekly Review Checklist

Weekly review should focus on:

1. Whether each work area has new commits.
2. Whether submitted files are placed in the correct directory.
3. Whether notes, code, diagrams, or records are understandable.
4. Whether tests or experiments include date, device, method, result, and known issues.
5. Whether important outputs can support later reports, papers, software copyright, or patent drafts.

## Public Repository Safety Rules

This is a public repository. Do not upload:

- Passwords, verification codes, tokens, private keys, or secret files
- Personal identity information, phone numbers, addresses, or private contact details
- Server passwords, database passwords, device public IPs, or private network credentials
- Confidential patent details that are not approved for public release
- Large raw videos, large image folders, or oversized datasets
- Files copied from third parties without permission or proper attribution

For large files, store them in a separate approved storage location and only keep an index or description in this repository.

---

<details>
<summary>中文说明（点击展开）</summary>

# agribotzhnysysv1

这是一个面向农业机器人与智能控制项目的公开训练协作仓库。

本仓库用于统一整理学习笔记、实验记录、代码、接口文档、仿真资源、测试报告和阶段性成果材料。主要方向包括农业机器人、PLC 控制、通讯协议、ROS2/Gazebo、嵌入式系统、传感器数据、视觉识别、CAD 建模和科研材料整理。

## 项目范围

本仓库主要包含以下内容：

- Git 与 GitHub 协作训练
- 串口、RS485、Modbus、CAN、TCP/UDP、MQTT 等通讯协议
- PLC 控制、I/O 点位表、寄存器表、安全逻辑和执行机构控制
- ROS2 工作空间、话题、服务、launch、机器人控制和导航
- Gazebo 仿真、URDF/SDF 模型、数字样机和测试场景
- 常见下位机平台的固件示例
- 农业感知数据集、图像标注规则和传感器数据记录
- CAD 模型、结构设计说明、BOM 和样机文档
- 周报、测试记录、问题清单和阶段验收材料
- 软著、专利、论文和开题报告的草稿材料

## 当前任务

当前阶段以仓库搭建和基础协作为主。

每位成员需要：

1. 接受仓库协作邀请。
2. 学会使用 GitHub 网页上传或基础 Git 命令。
3. 至少提交一份有效文件，例如学习笔记、测试记录、代码示例、接口表、CAD 说明、数据集说明或周报。
4. 将文件放到对应目录。
5. 提交信息要写清楚。
6. 不上传隐私、敏感或超大文件。

## 上传方式

### 方式一：网页上传

1. 打开 GitHub 仓库页面。
2. 进入对应目录，例如 `communication/`、`plc/`、`ros2_ws/`、`cad/`、`datasets/` 或 `reports/`。
3. 点击 `Add file`。
4. 点击 `Upload files`。
5. 拖入文件。
6. 写清楚提交说明。
7. 点击 `Commit changes`。

### 方式二：Git 命令上传

```bash
git clone <repository-url>
cd agribotzhnysysv1
git checkout -b your-branch-name
```

修改或新增文件后：

```bash
git add .
git commit -m "docs: add learning notes"
git push origin your-branch-name
```

然后在 GitHub 页面创建 Pull Request，审核后合并。

## 公开仓库注意事项

本仓库是公开仓库，禁止上传：

- 密码、验证码、Token、私钥等敏感信息
- 身份证号、手机号、地址等个人隐私
- 服务器密码、数据库密码、设备公网 IP 等信息
- 未经允许公开的专利核心内容
- 大量原始视频、大量图片或超大数据集
- 未经授权的第三方资料

大文件应放在单独的合规存储位置，仓库中只保存说明或索引。

</details>
