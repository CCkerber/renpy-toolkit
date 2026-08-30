# -*- coding: utf-8 -*-
"""
Ren'Py 资源包扫描核心模块（无第三方依赖，可独立被 GUI / CLI 调用）

功能：
1. 递归统计目录树大小
2. 按文件头魔数识别资源包：RPA-2.0 / RPA-3.0 / RPA-3.2 / ZIP（含伪装扩展名）
3. 解析 RPA 索引 / ZIP 名单，按扩展名归类图片 / 视频 / 音频资源
"""
import os
import re
import sys
import zlib
import pickle
import zipfile
from dataclasses import dataclass, field

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors="replace")
    except Exception:
        pass

# ------------------------- 资源格式归类 -------------------------
IMAGE_EXTS = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tga", ".tif", ".tiff",
    ".dds", ".psd", ".svg", ".ico", ".avif", ".jxl", ".heic", ".exr", ".hdr",
}
VIDEO_EXTS = {
    ".mp4", ".mkv", ".webm", ".avi", ".mov", ".wmv", ".flv", ".m4v", ".mpg",
    ".mpeg", ".ts", ".3gp", ".ogv", ".m2ts",
}
AUDIO_EXTS = {
    ".ogg", ".mp3", ".wav", ".flac", ".opus", ".aac", ".m4a", ".wma", ".aiff",
}


def classify_ext(ext: str) -> str:
    ext = ext.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    return "other"


# ------------------------- 数据结构 -------------------------
@dataclass
class PackageInfo:
    """一个探测到的资源包"""
    path: str                      # 绝对路径
    fmt: str                       # RPA-2.0 / RPA-3.0 / RPA-3.2 / ZIP / ZIP?
    file_size: int = 0
    entry_count: int = 0
    image_count: int = 0
    video_count: int = 0
    audio_count: int = 0
    other_count: int = 0
    image_bytes: int = 0
    video_bytes: int = 0
    error: str = ""                # 索引解析失败原因（空 = 正常）
    sample_names: list = field(default_factory=list)  # 图片/视频示例文件名


@dataclass
class DirNode:
    """目录树节点"""
    path: str
    name: str
    total_size: int = 0
    file_count: int = 0
    children: list = field(default_factory=list)      # list[DirNode]
    packages: list = field(default_factory=list)      # list[PackageInfo] 本目录直属
    perm_error: bool = False                          # 无权限读取


# ------------------------- RPA 索引解析 -------------------------
_RPA2_RE = re.compile(rb"^RPA-2\.0\s+([0-9a-fA-F]+)\s*$")
_RPA3_RE = re.compile(rb"^RPA-3\.0\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s*$")
_RPA32_RE = re.compile(rb"^RPA-3\.2\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s*$")


def _parse_rpa_index(path: str):
    """解析 RPA 索引，返回 (fmt, index_dict) 或抛出异常。
    index_dict: {name: [(offset, size[, prefix]), ...]}（未异或还原，size 仅供统计参考）
    """
    with open(path, "rb") as f:
        header = f.readline()
        m = _RPA2_RE.match(header)
        if m:
            offset = int(m.group(1), 16)
            f.seek(offset)
            return "RPA-2.0", pickle.loads(zlib.decompress(f.read()))
        m = _RPA3_RE.match(header) or _RPA32_RE.match(header)
        if m:
            fmt = "RPA-3.2" if header.startswith(b"RPA-3.2") else "RPA-3.0"
            offset = int(m.group(1), 16)
            key = int(m.group(2), 16)
            f.seek(offset)
            raw_index = pickle.loads(zlib.decompress(f.read()))
            index = {}
            for name, entries in raw_index.items():
                fixed = []
                for e in entries:
                    if len(e) >= 2:
                        fixed.append((e[0] ^ key, e[1] ^ key) + tuple(e[2:]))
                index[name] = fixed
            return fmt, index
    raise ValueError("not a supported RPA archive")


def _stats_from_names(names_with_size, pkg: PackageInfo):
    """按文件名归类统计。names_with_size: list[(name, size_or_None)]"""
    for name, size in names_with_size:
        ext = os.path.splitext(name)[1]
        kind = classify_ext(ext)
        pkg.entry_count += 1
        if kind == "image":
            pkg.image_count += 1
            pkg.image_bytes += size or 0
            if len(pkg.sample_names) < 8:
                pkg.sample_names.append(name)
        elif kind == "video":
            pkg.video_count += 1
            pkg.video_bytes += size or 0
            if len(pkg.sample_names) < 8:
                pkg.sample_names.append(name)
        elif kind == "audio":
            pkg.audio_count += 1
        else:
            pkg.other_count += 1


def probe_package(path: str) -> "PackageInfo | None":
    """探测单个文件是否为资源包；不是则返回 None。"""
    try:
        size = os.path.getsize(path)
    except OSError:
        return None
    if size < 8:
        return None
    try:
        with open(path, "rb") as f:
            magic = f.read(8)
    except OSError:
        return None

    if magic.startswith(b"RPA-"):
        pkg = PackageInfo(path=path, fmt="RPA", file_size=size)
        try:
            fmt, index = _parse_rpa_index(path)
            pkg.fmt = fmt
            _stats_from_names([(n, (ents[0][1] if ents and len(ents[0]) > 1 else None))
                               for n, ents in index.items()], pkg)
        except Exception as e:
            pkg.error = f"index parse failed: {type(e).__name__}: {e}"
        return pkg

    if magic[:4] == b"PK\x03\x04" or magic[:4] == b"PK\x05\x06":
        pkg = PackageInfo(path=path, fmt="ZIP", file_size=size)
        try:
            with zipfile.ZipFile(path) as zf:
                infos = zf.infolist()
                _stats_from_names([(i.filename, i.file_size) for i in infos if not i.is_dir()], pkg)
        except Exception as e:
            pkg.fmt = "ZIP?"
            pkg.error = f"zip open failed: {type(e).__name__}: {e}"
        return pkg

    return None


# ------------------------- 目录树扫描 -------------------------
_SCAN_EXTS = {".rpa", ".rpi", ".dat", ".bin", ".pak", ".zip", ".arc", ".res", ".rpac"}
# 扩展名不在名单内的也会抽查文件头（防伪装），但只读前 8 字节，代价极低


def scan_tree(root: str):
    """扫描目录树，返回 (DirNode, all_packages)。"""
    root = os.path.abspath(root)
    all_packages = []

    def _walk(dirpath: str) -> DirNode:
        node = DirNode(path=dirpath, name=os.path.basename(dirpath) or dirpath)
        try:
            entries = list(os.scandir(dirpath))
        except OSError:
            node.perm_error = True
            return node
        for ent in entries:
            try:
                if ent.is_symlink() or ent.is_junction():
                    continue
                if ent.is_dir(follow_symlinks=False):
                    child = _walk(ent.path)
                    node.children.append(child)
                    node.total_size += child.total_size
                    node.file_count += child.file_count
                elif ent.is_file(follow_symlinks=False):
                    try:
                        fsize = ent.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
                    node.total_size += fsize
                    node.file_count += 1
                    ext = os.path.splitext(ent.name)[1].lower()
                    if ext in _SCAN_EXTS or fsize >= 16:
                        pkg = probe_package(ent.path)
                        if pkg is not None:
                            node.packages.append(pkg)
                            all_packages.append(pkg)
            except OSError:
                continue
        node.children.sort(key=lambda c: c.total_size, reverse=True)
        node.packages.sort(key=lambda p: p.file_size, reverse=True)
        return node

    root_node = _walk(root)
    return root_node, all_packages


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            if unit == "B":
                return f"{n} B"
            return f"{n:.1f} {unit}"
        n /= 1024
