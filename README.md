# PCell Auto Verify

PCell Auto Verify 是一个基于 PySide6 的 PDK/PCell 桌面管理工具原型。它可以导入本地 PDK、持久化导入结果、在多个 PDK 中唯一激活一个，并浏览插件扫描出的 PCell 与参数。

## 安装与运行

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
pcell-auto-verify
```

点击工具栏 **PDK Manager**，选择 **Import PDK...** 并指向 PDK 根目录。首版内置 `open-pdks` 插件，支持 fossi-foundation/open-pdks 源码树，以及含 `sky130`、`gf180mcu`、`ihp-sg13g2` 标识的安装树。插件静态扫描 Python PCell 定义，不会执行 PDK 中的代码。导入信息默认保存在系统应用数据目录下的 SQLite 数据库中。

## 开发

```bash
pip install pytest
pytest
```

新的 PDK 格式可通过实现 `PDKPlugin` 并注册到 `PluginRegistry` 扩展。

