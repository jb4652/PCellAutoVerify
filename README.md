# PCell Auto Verify

PCell Auto Verify 是一个基于 PySide6 的 PDK/PCell 桌面管理工具原型。它可以导入本地 PDK、持久化导入结果、在多个 PDK 中唯一激活一个，并浏览插件扫描出的 PCell 与参数。

## 安装与运行

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
python main.py
```

安装后仍可使用 `pcell-auto-verify` 命令启动。

点击工具栏 **PDK Manager**，选择 **Import PDK...** 并指向 PDK 根目录。首版内置 `open-pdks` 插件，支持 fossi-foundation/open-pdks 源码树，以及含 `sky130`、`gf180mcu`、`ihp-sg13g2` 标识的安装树。插件静态扫描 Python PCell 定义，不会执行 PDK 中的代码。导入信息默认保存在系统应用数据目录下的 SQLite 数据库中。

激活 PDK 后，左侧会以 PDK 名称为根节点，按 PCell 在 PDK 内的实际源码路径展示默认全部展开的树状结构。选择 PCell 后，右侧的 **Range / Choices** 可直接编辑，支持 `min=1, max=10`、`choices=['A', 'B']` 或 `1..10`。点击 **Generate Test Points** 会生成基准点以及逐参数的边界/选项变化（避免全排列爆炸），再通过 **View Test Points** 查看结果。**Verify** 按钮会发出验证请求，为后续接入 KLayout DRC 等工具预留了信号；主界面底部的 **Output** 区域会以文字形式持续展示 PDK 加载、测试点生成和验证请求消息。没有范围时使用参数默认值。

## 开发

```bash
pip install pytest
pytest
```

## 目录结构

```text
main.py       # 直接运行的程序入口
core/         # 领域模型和应用初始化
database/     # SQLite 持久化
gui/          # PySide6 窗口与对话框
plugins/      # PDK 插件协议、实现和注册中心
tests/        # 自动化测试
```

各层通过公开的 `__init__.py` 接口协作，界面、数据库和扫描逻辑不再集中在同一包中。新的 PDK 格式可通过实现 `plugins.PDKPlugin` 并注册到 `plugins.PluginRegistry` 扩展。
