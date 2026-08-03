# PCell Auto Verify

PCell Auto Verify 是一个基于 PySide6 的 PDK/PCell 桌面管理工具原型。它可以导入本地 PDK、持久化导入结果、在多个 PDK 中唯一激活一个，并浏览插件扫描出的 PCell 与参数。

## 安装与运行

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
python main.py
```

安装会同时引入 PCell 实例化所需的 NumPy。验证时，应用会将当前 Python
环境的包搜索路径传给 KLayout 的嵌入式 Python，因此应从安装依赖时使用的
虚拟环境启动。安装后仍可使用 `pcell-auto-verify` 命令启动。

点击工具栏 **PDK Manager**，选择 **Import PDK...** 并指向 PDK 根目录。首版内置 `open-pdks` 插件，支持 fossi-foundation/open-pdks 源码树，以及含 `sky130`、`gf180mcu`、`ihp-sg13g2` 标识的安装树。插件静态扫描 Python PCell 定义，不会执行 PDK 中的代码。导入信息默认保存在系统应用数据目录下的 SQLite 数据库中。

导入名为 `gf180mcuA` 的 PDK 时，程序还会在列表最前面加入一个
`GF180MCUANMOS` 入门 PCell。它提供栅宽和栅长参数，并生成包含 COMP、Poly2、
Nplus、接触孔及源漏 Metal1 的 NMOS 版图，可用于第一次生成测试点、运行 PDK
自带 DRC，再从 **DRC Results → Open Layout** 打开版图查看。示例还包含可正常生成
版图、但预期无法通过 DRC 的 0.2 µm 栅长边界，用于检查失败结果流程。

激活 PDK 后，左侧会以 PDK 名称为根节点，按 PCell 在 PDK 内的实际源码路径展示默认全部展开的树状结构。选择 PCell 后，右侧的 **Range / Choices** 可直接编辑，支持 `min=1, max=10`、`choices=['A', 'B']` 或 `1..10`。扫描器会为源码中没有约束的参数根据默认值补充一组保守的布尔、整数或浮点候选值。点击 **Generate Test Points** 只会取每个参数候选范围的首、尾边界值并进行组合，从而减少需要 DRC 的组数；组合超过 200 条时仍会均匀抽样为 200 条。生成结果可通过 **View Test Points** 查看。

**Verify** 会用 KLayout 实例化每一个测试点，查找当前 PDK 中的第一个 `*.lydrc`（其次是 `*.drc`）规则文件并执行 DRC。对于 GF180 这类由 `run_drc.py` 启动的宏，会直接执行其独立 DRC 规则文件，避免 KLayout 的嵌入式 Python 还需单独安装 `docopt`。程序会同时传入规则文件常见的 `topcell`、`cell_name` 和 `cell` 顶层单元参数。底部 **Output** 显示逐条 PASS/FAIL 及汇总；完成后右上角 **DRC Results** 按钮可查看所有参数和错误信息，点击 **Open Layout** 可在 KLayout 中检查对应的通过或未通过版图。若未安装 `klayout`、PCell 无法实例化或 PDK 中没有规则文件，测试会明确标为失败而不会误报通过。

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
