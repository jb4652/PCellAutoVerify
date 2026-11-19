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

点击工具栏 **PDK Manager**，选择 **Import PDK...** 并指向 PDK 根目录。首版内置 `open-pdks` 插件，支持 fossi-foundation/open-pdks 源码树，以及含 `sky130`、`gf180mcu`、`ihp-sg13g2` 标识的安装树。导入其他 PDK 时，插件静态扫描 Python PCell 定义。导入信息默认保存在系统应用数据目录下的 SQLite 数据库中。

导入 `sky130A` 时，应用在独立 Python 进程中加载 `libs.tech/klayout/python/cells`，按 KLayout 库的实际注册名称列出 PCell。请使用可信的 PDK，并在应用使用的虚拟环境中安装该 PDK 所需的依赖（例如兼容版本的 `gdsfactory`）。旧导入记录可通过 **PDK Manager → Import PDK...** 重新选择原目录来刷新，原激活状态会保留。

导入名为 `gf180mcuA` 的 PDK 时，程序还会在列表最前面加入一个
`GF180MCUANMOS` 入门 PCell。它提供栅宽和栅长参数，并生成包含 COMP、Poly2、
Nplus、接触孔及源漏 Metal1 的 NMOS 版图，可用于第一次生成测试点、运行 PDK
自带 DRC，再从 **DRC Results → Open Layout** 打开版图查看。示例还包含可正常生成
版图、但预期无法通过 DRC 的 0.2 µm 栅长边界，用于检查失败结果流程。

激活 PDK 后，左侧会以 PDK 名称为根节点，按 PCell 在 PDK 内的实际源码路径展示默认全部展开的树状结构。`sky130A` 的注册名称直接列在根节点下，名称后的括号显示源码文件名，悬停可查看完整路径。右侧保留 KLayout 声明的完整参数列表，隐藏和只读参数仅供查看。选择 PCell 后，右侧的 **Default** 和 **Range / Choices** 均可直接编辑；后者支持 `min=1, max=10`、`choices=['A', 'B']` 或 `1..10`。因此，当静态扫描无法解析 PDK 源码中的动态默认值时，可以在生成测试点前手工填写正确的数值。未填写的未知默认值不会再以空字符串传给 KLayout，而是从参数字典中省略，让 PCell 使用自身的运行时默认值。扫描器会为源码中没有约束的参数根据已解析默认值补充一组保守的布尔、整数或浮点候选值。点击 **Generate Test Points** 会读取右侧当前默认值生成一组测试点。可在 **View Test Points** 中查看，修改默认值后可重新生成。未设置的参数由 KLayout 使用库默认值，隐藏或只读参数不参与配置。

**Verify** 会通过应用自身的 Python 解释器和 `klayout` Python 包实例化每一个测试点，使 PCell 可以使用应用环境中已安装的 NumPy 等二进制依赖；随后查找当前 PDK 中的第一个 `*.lydrc`（其次是 `*.drc`）规则文件并用 KLayout 执行 DRC。对于 GF180 这类由 `run_drc.py` 启动的宏，会直接执行其独立 DRC 规则文件，避免 KLayout 的嵌入式 Python 还需单独安装 `docopt`。程序会同时传入规则文件常见的 `topcell`、`cell_name` 和 `cell` 顶层单元参数。底部 **Output** 显示逐条 PASS/FAIL 及汇总；完成后右上角 **DRC Results** 按钮可查看所有参数和错误信息，点击 **Open Layout** 可在 KLayout 中检查对应的通过或未通过版图。若无法完成 DRC，结果会显示具体原因。

## 生成 Sky130A NMOS

启动应用并激活已导入的 `sky130A` 后，选择 `nfet`，依次点击 **Generate Test Points** 和 **Run Verify**。每次运行会在 `output/verification/run-*/` 保存 GDS、实际生效的参数 JSON，以及规则执行时生成的 DRC 报告。缺少 KLayout 命令行工具或规则文件时，仍会尝试生成 GDS，并说明 DRC 未运行。输出区会显示 GDS 的完整路径，DRC 结果中的 **View Layout** 在没有预览图时可以打开 GDS 或其所在目录。

从工程根目录也可以单独生成 GDS：

```bash
python scripts/generate_sky130_nmos.py --pdk "$SKY130_KLAYOUT" --w 0.42 --l 0.15 --nf 1 --output output/nmos.gds
```

`SKY130_KLAYOUT` 通常指向 `sky130A/libs.tech/klayout`。脚本也接受 `sky130A` 根目录或其 `libs.tech/klayout/python` 子目录。在界面导入这三个目录时，应用会按 Sky130A 安装根目录保存 PDK。脚本和应用共用 Sky130A 的兼容处理，参数配置位于 `config/sky130_nmos.json`。请使用已安装兼容版本 `gdsfactory` 和 `kfactory` 的 Python 环境。命令同时写出 `output/nmos.json`，记录请求值和实例化后的实际参数。`--m` 只记录到 JSON。

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
