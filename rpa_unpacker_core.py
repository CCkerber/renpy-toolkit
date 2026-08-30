# -*- coding: utf-8 -*-
"""RPA 解包核心（从 rpa-unpacker 项目中提取，无 GUI 依赖）"""
import json
import os
import shutil
import sys
import traceback

from unrpa import UnRPA
from rpycdec import extract_rpa

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except Exception:
        pass

SUPPORTED_EXT = (".rpa", ".rpi")

CONFIG_DIR = os.path.join(
    os.environ.get("APPDATA") or os.path.expanduser("~"), "RenPyToolkit"
)
CONFIG_FILE = os.path.join(CONFIG_DIR, "rpa_config.json")


def load_config() -> dict:
    cfg = {"output_dir": "", "use_subfolder": False}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            for key in cfg:
                if key in data:
                    cfg[key] = data[key]
    except Exception:
        pass
    return cfg


def save_config(cfg: dict) -> None:
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def resolve_out_dir(archive_path: str, out_root: str, use_subfolder: bool) -> str:
    name = os.path.basename(archive_path)
    base = out_root.strip() if out_root and out_root.strip() else os.path.dirname(os.path.abspath(archive_path))
    if use_subfolder:
        return os.path.join(base, os.path.splitext(name)[0])
    return base


def _count_files(root_dir: str) -> int:
    total = 0
    for _dir, _sub, files in os.walk(root_dir):
        total += len(files)
    return total


def _index_file_count(archive_path: str):
    try:
        with open(archive_path, "rb") as f:
            return len(UnRPA(archive_path, verbosity=-1).get_index(f))
    except Exception:
        return None


def unpack_with_unrpa(archive_path: str, out_dir: str) -> None:
    UnRPA(
        archive_path,
        verbosity=-1,
        path=out_dir,
        mkdir=True,
        continue_on_error=True,
    ).extract_files()


def unpack_with_rpycdec(archive_path: str, out_dir: str) -> None:
    with open(archive_path, "rb") as f:
        extract_rpa(f, out_dir)


def run_one(archive_path: str, emit, out_root: str = "", use_subfolder: bool = False) -> bool:
    """解单个归档。先 unrpa，失败回退 rpycdec。返回是否成功。"""
    name = os.path.basename(archive_path)
    out_dir = resolve_out_dir(archive_path, out_root, use_subfolder)

    emit(">> %s" % name)
    if not os.path.isfile(archive_path):
        emit("  [X] 文件不存在，跳过")
        return False

    expected = _index_file_count(archive_path)
    if expected:
        emit("  索引登记 %d 个文件，输出到：%s" % (expected, out_dir))

    try:
        emit("  尝试 unrpa ...")
        unpack_with_unrpa(archive_path, out_dir)
        got = _count_files(out_dir)
        if got == 0:
            raise RuntimeError("解包完成但没写出任何文件")
        if expected and got < expected:
            emit("  [!] unrpa 解出 %d 个（少于索引的 %d 个），可能有文件损坏" % (got, expected))
        else:
            emit("  [OK] unrpa 成功，解出 %d 个文件" % got)
        return True
    except Exception as exc:
        emit("  [X] unrpa 失败：%s: %s" % (type(exc).__name__, exc))

    try:
        emit("  尝试 rpycdec 兜底 ...")
        unpack_with_rpycdec(archive_path, out_dir)
        got = _count_files(out_dir)
        if got == 0:
            raise RuntimeError("解包完成但没写出任何文件")
        emit("  [OK] rpycdec 成功，解出 %d 个文件" % got)
        return True
    except Exception as exc:
        emit("  [X] rpycdec 也失败：%s: %s" % (type(exc).__name__, exc))
        emit("  [X] 两道都没解开，放弃：%s" % name)
        emit("     " + traceback.format_exc().replace("\n", "\n     ").rstrip())
        return False
