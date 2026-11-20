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
自带 DRC，再从 **View Test Points → View Layout** 打开版图查看。示例还包含可正常生成
版图、但预期无法通过 DRC 的 0.2 µm 栅长边界，用于检查失败结果流程。

激活 PDK 后，左侧会以 PDK 名称为根节点，按 PCell 在 PDK 内的实际源码路径展示默认全部展开的树状结构。`sky130A` 的注册名称直接列在根节点下，名称后的括号显示源码文件名，悬停可查看完整路径。右侧保留 KLayout 声明的完整参数列表，隐藏和只读参数仅供查看。选择 PCell 后，右侧的 **Default** 和 **Range / Choices** 均可直接编辑；后者支持 `min=1, max=10`、`choices=['A', 'B']` 或 `1..10`。因此，当静态扫描无法解析 PDK 源码中的动态默认值时，可以在生成测试点前手工填写正确的数值。未填写的未知默认值不会再以空字符串传给 KLayout，而是从参数字典中省略，让 PCell 使用自身的运行时默认值。扫描器会为源码中没有约束的参数根据已解析默认值补充一组保守的布尔、整数或浮点候选值。点击 **Automatic Test Points Generation** 会读取右侧当前默认值，生成测试点和对应的 GDS。**View Test Points** 中可以查看参数、版图缩略图和 **View Layout**。修改默认值后可重新生成。未设置的参数由 KLayout 使用库默认值，隐藏或只读参数不参与配置。

**DRC** 检查已经生成的 GDS。Sky130A 使用 Magic，其他 PDK 仍使用 KLayout 规则文件。检查结果和 PDF 汇总可在 **DRC Results** 查看，底部 **Output** 会显示每组版图的生成路径及 DRC 结果。

## 生成 Sky130A NMOS

激活 `sky130A` 并选择 `nfet`。点击 **Automatic Test Points Generation** 后，GDS 和实际生效的参数 JSON 会保存到 `output/verification/run-*/`。确认版图后点击 **DRC**。请确保兼容该 PDK 的 Magic 已在 `PATH` 中。Magic 会在同一目录写出 `*_drc.txt` 和 `*_magic.log`。应用优先使用 PDK 的 `libs.tech/magic/sky130A.magicrc`，并根据导入位置设置 `PDK_ROOT`。如果没有原版 rcfile，则使用工程的 `config/sky130A.magicrc`。

从工程根目录也可以单独生成 GDS：

```bash
python scripts/generate_sky130_nmos.py --pdk "$SKY130_KLAYOUT" --w 0.42 --l 0.15 --nf 1 --output output/nmos.gds
```

`SKY130_KLAYOUT` 通常指向 `sky130A/libs.tech/klayout`。脚本也接受 `sky130A` 根目录或其 `libs.tech/klayout/python` 子目录。在界面导入这三个目录时，应用会按 Sky130A 安装根目录保存 PDK。脚本和应用共用 Sky130A 的兼容处理，参数配置位于 `config/sky130_nmos.json`。请使用已安装兼容版本 `gdsfactory` 和 `kfactory` 的 Python 环境。命令同时写出 `output/nmos.json`，记录请求值和实例化后的实际参数。`--m` 只记录到 JSON。

也可以检查命令行生成的 `output/nmos.gds`。设置 `PDK_ROOT` 为包含 `sky130A` 的目录后，在工程根目录运行：

```bash
magic -dnull -noconsole -rcfile "$PDK_ROOT/sky130A/libs.tech/magic/sky130A.magicrc" scripts/run_nmos_drc.tcl
```

脚本默认读取顶层单元 `NMOS_TOP`，将报告写到 `output/nmos_drc.txt`。

## Sky130A NFET 和 PFET 的 LVS 与 RCX

选择 `nfet` 或 `pfet`，生成测试点和 GDS 后，点击 **LVS** 或 **RCX**。两项检查都使用已有版图，可以独立运行。

- **LVS** 用 Magic 生成提取网表，并按该测试点实际生效的型号、宽度、长度和指数量生成独立参考网表。随后调用 `netgen-lvs`，使用导入 PDK 的 `libs.tech/netgen/sky130A_setup.tcl` 比较。**LVS Results** 显示比对和属性差异。自动参考支持普通单指和多指 NFET、PFET，要求无体端接触、保护环和交错指。
- **RCX** 用 Magic 提取寄生电容和电阻。**RCX Results** 显示预期型号、MOS 实例数和 R/C 元件数。`PASS_BASIC` 表示提取网表中找到了预期型号，R 或 C 的数量可以为零。

请确保 `magic` 和 `netgen-lvs` 已在 `PATH` 中。生成的 SPICE 和日志保存在本次 GDS 所在目录的 `lvs/<版图名>/` 和 `rcx/<版图名>/` 下。

若要从工程根目录检查默认的 `output/nmos.gds`，使用前面同样的 `PDK_ROOT`：

```bash
rcfile="$PDK_ROOT/sky130A/libs.tech/magic/sky130A.magicrc"
magic -dnull -noconsole -rcfile "$rcfile" scripts/extract_nmos_lvs.tcl
netgen-lvs -batch lvs "output/lvs/nmos_extracted.spice NMOS_TOP" "config/nmos_reference.spice NMOS_TOP" "$PDK_ROOT/sky130A/libs.tech/netgen/sky130A_setup.tcl" "output/lvs/nmos_lvs.log"
magic -dnull -noconsole -rcfile "$rcfile" scripts/extract_nmos_rcx.tcl
python scripts/check_nmos_rcx.py
```

## Sky130A 自定义 CMOS 反相器

激活含有 `nfet` 和 `pfet` 的 Sky130A 后，在 **Custom PCells** 中选择 `cmos_inverter`。它是应用提供的组合器件，原厂的 18 个 PCell 仍按库注册结果显示。默认各用一个单指 1.8 V NFET 和 PFET，宽度为 0.42 µm，长度为 0.15 µm。可编辑 `wn`、`ln`、`wp`、`lp`，尺寸按 0.005 µm 工艺网格输入。

**Automatic Test Points Generation** 生成 GDS，**View Test Points** 可预览。两管共栅接 `A`，共漏接 `Y`，源极和体端接各自的 `VDD` 或 `VSS`。**DRC** 检查整个版图，**LVS** 用独立参考网表核对两个器件和四个端口，**RCX** 提取器件与互连寄生参数。沿用 Sky130A 的 Magic 和 Netgen 配置。

Sky130A 的 `nfet`、`pfet` 和 `cmos_inverter` 各生成两个测试点。第一组使用当前参数，初始为器件默认参数。第二组额外将 `metal1_test_width` 设为 0.035 µm，加入一块与电路隔离的 0.035 × 0.500 µm Metal1 矩形，预期触发 DRC 的 `met1.6` 最小面积规则。**View Test Points** 会标出预期 DRC 结果，**DRC Results** 显示实测结果。这个负例针对 DRC，晶体管接线保持原样。

### 手动测试点与参数回调

在右侧修改 **Default** 后，应用调用 PCell 的参数回调和校正逻辑。回调给出提示或系统修正了参数时，界面会弹出 **PCell Callback**，并显示生效值。例如 Sky130A `nfet` 的 `l=0.10 µm` 会校正为 `0.15 µm`。点击 **Manual Test Points Generation** 会以当前生效值生成并追加一个测试点。手动点在 **View Test Points** 中标为 **Manual**，重新生成自动用例时仍会保留。

## 工程内置的 domestic180 PDK

在 **PDK Manager → Import PDK...** 选择 `pdks/domestic180` 并激活 **domestic180**。它包含 180 nm 的 `nmos`、`pmos` 和四端口 `inverter`，支持自动和手动生成版图、GDS 预览及 DRC、LVS 和 RCX。规则、层定义和寄生估算说明见 [domestic180 文档](pdks/domestic180/README.md)。

## 命令行运行和结果对照

先激活运行平台时使用的 Python 虚拟环境。Sky130A 需要同一套 PDK，且 `magic` 和 `netgen-lvs` 位于 `PATH`。domestic180 使用应用内的 KLayout Python 后端。

```bash
# 查看可用器件
scripts/run_pcell.sh --pdk "$SKY130A_ROOT" --list

# 生成与界面相同的自动用例，并运行支持的检查
scripts/run_pcell.sh --pdk "$SKY130A_ROOT" --pcell cmos_inverter
scripts/run_pcell.sh --pdk pdks/domestic180 --pcell inverter

# 模拟界面参数修改，触发参数校正后生成一个手动用例
scripts/run_pcell.sh --pdk "$SKY130A_ROOT" --pcell nfet --case manual --set l=0.10

# 用界面实际生成的版图复跑。保留相邻的 .json 参数文件
scripts/run_pcell.sh --pdk "$SKY130A_ROOT" --pcell nfet --gds "$GDS_FILE"
```

也可用 `python scripts/run_pcell.py` 代替 Shell 入口。默认输出在 `output/cli/` 下，每次运行创建独立目录，写出 GDS、检查报告和 `summary.json`。可用 `--checks drc lvs` 只运行指定检查，用 `--case default` 或 `--case negative` 只运行一组。重跑界面中预期违反 DRC 的 GDS 时，使用 `--gds ... --case negative`。重跑 domestic180 的手动版图时，使用 `--gds ... --case manual --set KEY=VALUE` 提供实际生效的参数。命令退出码为 0 表示结果符合预期，包含预期的 DRC 违规。手动用例的退出码为 0 要求所选检查通过。

仅运行原生参数回调和校正，并将终端记录保存为 `callback.log`：

```bash
scripts/run_pcell.sh --pdk "$SKY130A_ROOT" --pcell nfet --case manual --set l=0.10 --callback-only
```

界面中修改参数时，同样的运行记录会出现在 **Console**。日志分别记录回调和校正两个阶段，保留 PDK 原有的标准输出和错误输出。

### 直接调用 Magic 与 Netgen

将 `GDS_FILE` 和 `REFERENCE_FILE` 分别设为要核对的界面 GDS 和对应检查生成的参考 SPICE 文件：

```bash
scripts/replay_sky130_native.sh "$SKY130A_ROOT" "$GDS_FILE" "$REFERENCE_FILE"
```

该脚本直接用现有的 `run_nmos_drc.tcl`、`extract_nmos_lvs.tcl` 和 `extract_nmos_rcx.tcl` 调用 Magic，并运行 `netgen-lvs -batch lvs`。原始 DRC 报告、LVS 日志和 RCX SPICE 位于 `output/cli/native-*/`。脚本退出成功表示命令完成，检查结论以原始报告为准。需要自动判读结果时，使用上面的 `run_pcell.sh`。

直接调用 Magic 时，`SKY130A_ROOT` 使用指向名为 `sky130A` 的安装目录的绝对路径。界面生成的顶层单元为 `VERIFY_TOP`。独立 NMOS 脚本生成的版图可在命令末尾传入 `NMOS_TOP`。Netgen 的原始日志中，连接匹配和器件属性错误可以同时出现，平台和命令行入口都会把属性错误判为 LVS 失败。

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
