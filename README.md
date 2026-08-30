# Ren'Py 工具箱

把两个 Ren'Py 相关的小工具合并成一个双标签页程序：

- **RPA 解包**：拖入 `.rpa` / `.rpi` 文件，优先用 `unrpa` 解包，失败自动回退 `rpycdec`；可设置输出目录和归档子文件夹。
- **资源扫描**：拖入游戏文件夹，显示目录树大小、探测 RPA-2.0/3.0/3.2/ZIP（含伪装扩展名），列出包内图片 / 视频 / 音频数量。

## 运行

双击 `run.bat`（使用项目内 venv，无需安装到系统）。

## 特性

- 统一窗口，双标签页切换
- 目录树自动展开，用 `①②③…` 圈号 + 行底色深度渐变标识父子层级
- 选中行使用橙色高亮，与层级蓝色区分
- 目录树 / 资源包均支持右键：打开目录、复制绝对路径、复制到剪贴板（可在资源管理器 Ctrl+V 粘贴）

## 打包（onedir）

```
venv\Scripts\python.exe -m PyInstaller --noconfirm --onedir --noconsole \
  --name RenPyToolkit --collect-all tkinterdnd2 toolkit_gui.py
```

产物约 35MB，整个文件夹拷贝即可绿色分发。

## 依赖

- Python 3.12（项目 venv 已内置）
- unrpa / rpycdec / tkinterdnd2（见 requirements.txt）
