# -*- coding: utf-8 -*-
"""Ren'Py 工具箱：RPA 解包 + 资源扫描，双标签页统一 GUI。"""
import ctypes
from ctypes import wintypes
import os
import queue
import struct
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from tkinterdnd2 import DND_FILES, TkinterDnD

from rpa_unpacker_core import SUPPORTED_EXT, load_config, save_config, run_one
from scanner_core import human_size, scan_tree

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except Exception:
        pass

APP_TITLE = "Ren'Py 工具箱"
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"


def copy_files_to_clipboard(paths, status_setter=None, show_success=True):
    """CF_HDROP 格式写入剪贴板，资源管理器可粘贴。"""
    try:
        payload = ("\0".join(os.path.abspath(p) for p in paths) + "\0\0").encode("utf-16-le")
        data = struct.pack("<IiiII", 20, 0, 0, 0, 1) + payload
        u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
        k32.GlobalAlloc.restype = wintypes.HGLOBAL
        k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        k32.GlobalLock.restype = ctypes.c_void_p
        k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        u32.SetClipboardData.restype = wintypes.HANDLE
        u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        if not u32.OpenClipboard(0):
            messagebox.showerror(APP_TITLE, "无法打开剪贴板")
            return
        try:
            u32.EmptyClipboard()
            hmem = k32.GlobalAlloc(0x0002, len(data))
            if not hmem:
                messagebox.showerror(APP_TITLE, "GlobalAlloc 失败")
                return
            ptr = k32.GlobalLock(hmem)
            if not ptr:
                k32.GlobalFree(wintypes.HGLOBAL(hmem))
                messagebox.showerror(APP_TITLE, "GlobalLock 失败")
                return
            ctypes.memmove(ptr, data, len(data))
            k32.GlobalUnlock(hmem)
            if not u32.SetClipboardData(15, hmem):
                k32.GlobalFree(wintypes.HGLOBAL(hmem))
                messagebox.showerror(APP_TITLE, "写入剪贴板失败")
                return
        finally:
            u32.CloseClipboard()
        msg = f"已复制 {len(paths)} 个项目到剪贴板，可在资源管理器 Ctrl+V 粘贴。"
        if status_setter:
            status_setter(msg)
        if show_success:
            messagebox.showinfo(APP_TITLE, msg)
    except Exception as e:
        messagebox.showerror(APP_TITLE, f"复制到剪贴板时出错: {e}")


class RPAUnpackerTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.files = []
        self.working = False
        self.log_queue = queue.Queue()
        self._after_id = None
        self.cfg = load_config()
        self._build()
        self._pump()

    def _build(self):
        ttk.Label(self, text="RPA 解包", font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w", padx=12, pady=(12, 6))
        ttk.Label(self, text="把 .rpa / .rpi 文件拖进下方区域，或点“选择文件”。先 unrpa，失败自动 rpycdec 兜底。",
                  wraplength=760, foreground="#555555").pack(anchor="w", padx=12)

        drop = tk.Frame(self, bg="#F4F6F8", highlightthickness=2,
                        highlightbackground="#B9C4CE", highlightcolor="#3A7BD5")
        drop.pack(fill="x", padx=12, pady=10, ipady=10)
        self.drop_hint = tk.Label(drop, text="把文件拖到这里", bg="#F4F6F8", fg="#5F6B76",
                                  font=("Microsoft YaHei UI", 11))
        self.drop_hint.pack(expand=True, fill="both", pady=18)
        drop.drop_target_register(DND_FILES)
        drop.dnd_bind("<<Drop>>", self._on_drop)
        self.drop_hint.drop_target_register(DND_FILES)
        self.drop_hint.dnd_bind("<<Drop>>", self._on_drop)

        self.listbox = tk.Listbox(self, height=5, font=("Consolas", 9))
        self.listbox.pack(fill="x", padx=12, pady=(0, 8))

        cfg_box = ttk.LabelFrame(self, text="输出位置", padding=(10, 6, 10, 8))
        cfg_box.pack(fill="x", padx=12, pady=(0, 8))
        out_row = ttk.Frame(cfg_box)
        out_row.pack(fill="x")
        self.out_var = tk.StringVar(value=self.cfg.get("output_dir", ""))
        ttk.Entry(out_row, textvariable=self.out_var).pack(side="left", fill="x", expand=True)
        ttk.Button(out_row, text="浏览", command=self._pick_out).pack(side="left", padx=(6, 0))
        self.sub_var = tk.BooleanVar(value=self.cfg.get("use_subfolder", False))
        ttk.Checkbutton(cfg_box, text="按归档名建子文件夹", variable=self.sub_var).pack(anchor="w", pady=(6, 0))

        btn_row = ttk.Frame(self)
        btn_row.pack(fill="x", padx=12, pady=(0, 8))
        ttk.Button(btn_row, text="选择文件", command=self._pick_files).pack(side="left")
        ttk.Button(btn_row, text="清空列表", command=self._clear).pack(side="left", padx=(6, 0))
        ttk.Button(btn_row, text="开始解包", command=self._start).pack(side="left", padx=(6, 0))

        self.log = tk.Text(self, height=12, state="disabled", wrap="word", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def _on_drop(self, event):
        paths = self.app.tk.splitlist(event.data)
        self._add_files(paths)

    def _pick_files(self):
        files = filedialog.askopenfilenames(filetypes=[("RPA/RPI 归档", "*.rpa *.rpi"), ("所有文件", "*.*")])
        if files:
            self._add_files(files)

    def _add_files(self, paths):
        for p in paths:
            if os.path.splitext(p)[1].lower() in SUPPORTED_EXT and p not in self.files:
                self.files.append(p)
        self._refresh_list()

    def _refresh_list(self):
        self.listbox.delete(0, "end")
        for p in self.files:
            self.listbox.insert("end", p)

    def _clear(self):
        self.files.clear()
        self._refresh_list()

    def _pick_out(self):
        d = filedialog.askdirectory()
        if d:
            self.out_var.set(d)

    def _emit(self, text):
        self.log_queue.put(text)

    def _log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _pump(self):
        try:
            while True:
                self._log(self.log_queue.get_nowait())
        except queue.Empty:
            pass
        self._after_id = self.after(100, self._pump)

    def _start(self):
        if self.working or not self.files:
            return
        self.cfg["output_dir"] = self.out_var.get()
        self.cfg["use_subfolder"] = self.sub_var.get()
        save_config(self.cfg)
        self.working = True
        targets = list(self.files)
        threading.Thread(target=self._worker, args=(targets,), daemon=True).start()

    def _worker(self, targets):
        for path in targets:
            run_one(path, self._emit, self.cfg["output_dir"], self.cfg["use_subfolder"])
        self._emit("全部完成")
        self.working = False


class AssetScannerTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self._scan_thread = None
        self._queue = queue.Queue()
        self._dir_map = {}
        self._pkg_map = {}
        self._closed = False
        self._build()
        self.after(100, self._poll)

    def _build(self):
        ttk.Label(self, text="资源包扫描", font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w", padx=12, pady=(12, 6))
        ttk.Label(self, text="拖入游戏文件夹，自动分析目录大小并探测 RPA / ZIP 资源包。",
                  foreground="#555555").pack(anchor="w", padx=12)

        drop = tk.Frame(self, bg="#F4F6F8", highlightthickness=2,
                        highlightbackground="#B9C4CE", highlightcolor="#3A7BD5")
        drop.pack(fill="x", padx=12, pady=10, ipady=10)
        self.drop_hint = tk.Label(drop, text="把文件夹拖到这里", bg="#F4F6F8", fg="#5F6B76",
                                  font=("Microsoft YaHei UI", 11))
        self.drop_hint.pack(expand=True, fill="both", pady=18)
        drop.drop_target_register(DND_FILES)
        drop.dnd_bind("<<Drop>>", self._on_drop)
        self.drop_hint.drop_target_register(DND_FILES)
        self.drop_hint.dnd_bind("<<Drop>>", self._on_drop)

        self.status_var = tk.StringVar(value="等待拖入文件夹...")
        ttk.Label(self, textvariable=self.status_var, anchor="w").pack(fill="x", padx=12, pady=(0, 6))

        paned = tk.PanedWindow(self, orient="vertical", sashwidth=6, sashrelief="raised", bg="#cbd5e0")
        paned.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        tree_frame = tk.Frame(paned)
        cols = ("size", "files", "pkgs")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="tree headings")
        self.tree.heading("#0", text="名称")
        self.tree.heading("size", text="大小")
        self.tree.heading("files", text="文件数")
        self.tree.heading("pkgs", text="资源包")
        self.tree.column("#0", width=520)
        self.tree.column("size", width=110, anchor="e")
        self.tree.column("files", width=80, anchor="e")
        self.tree.column("pkgs", width=80, anchor="e")
        self._setup_tree_style()
        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Button-3>", self._on_tree_menu)
        paned.add(tree_frame, stretch="always", minsize=200)

        pkg_frame = tk.Frame(paned)
        pcols = ("fmt", "path", "size", "imgs", "vids", "auds", "note")
        self.pkg_tree = ttk.Treeview(pkg_frame, columns=pcols, show="headings")
        for cid, text, w in (
            ("fmt", "格式", 80), ("path", "路径", 380), ("size", "大小", 90),
            ("imgs", "图片", 60), ("vids", "视频", 60), ("auds", "音频", 60),
            ("note", "备注", 160),
        ):
            self.pkg_tree.heading(cid, text=text)
            self.pkg_tree.column(cid, width=w, anchor="w" if cid in ("path", "note") else "e")
        psb = ttk.Scrollbar(pkg_frame, orient="vertical", command=self.pkg_tree.yview)
        self.pkg_tree.configure(yscrollcommand=psb.set)
        psb.pack(side="right", fill="y")
        self.pkg_tree.pack(fill="both", expand=True)
        self.pkg_tree.bind("<Button-3>", self._on_pkg_menu)
        self.pkg_tree.bind("<Double-1>", self._show_pkg_detail)
        paned.add(pkg_frame, stretch="always", minsize=160)

    def _setup_tree_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", font=("Microsoft YaHei UI", 10), rowheight=24, indent=28)
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"))
        style.map("Treeview", background=[("selected", "#dd6b20")], foreground=[("selected", "white")])
        self.tree.tag_configure("root", background="#1e3a5f", foreground="white",
                                font=("Microsoft YaHei UI", 10, "bold"))
        depth_bg = ("#9db8d6", "#b4c9e0", "#c8d8ea", "#d9e5f2",
                    "#e7eff7", "#f1f6fb", "#f8fbfe", "#ffffff")
        for i, bg in enumerate(depth_bg, 1):
            self.tree.tag_configure(f"d{i}", background=bg)
        self.tree.tag_configure("haspkg", foreground="#c53030",
                                font=("Microsoft YaHei UI", 10, "bold"))

    def _on_drop(self, event):
        path = event.data.strip().strip("{}")
        if os.path.isdir(path):
            self._start_scan(path)
        else:
            self.status_var.set("请拖入文件夹")

    def _start_scan(self, folder):
        if self._scan_thread and self._scan_thread.is_alive():
            return
        for item in self.tree.get_children():
            self.tree.delete(item)
        for item in self.pkg_tree.get_children():
            self.pkg_tree.delete(item)
        self._dir_map.clear()
        self._pkg_map.clear()
        self.status_var.set(f"扫描中: {folder}")
        self._scan_thread = threading.Thread(target=self._scan_worker, args=(folder,), daemon=True)
        self._scan_thread.start()

    def _scan_worker(self, folder):
        try:
            root_node, packages = scan_tree(folder)
            self._queue.put(("done", root_node, packages))
        except Exception as e:
            self._queue.put(("error", f"{type(e).__name__}: {e}"))

    def _poll(self):
        if self._closed:
            return
        try:
            while True:
                msg = self._queue.get_nowait()
                if msg[0] == "done":
                    self._fill_tree(msg[1])
                    self._fill_packages(msg[2])
                    total = msg[1]
                    self.status_var.set(
                        f"完成: {total.path}  总大小 {human_size(total.total_size)}"
                        f"  文件 {total.file_count} 个  资源包 {len(msg[2])} 个")
                elif msg[0] == "error":
                    self.status_var.set(f"扫描出错: {msg[1]}")
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _fill_tree(self, node, parent="", depth=0):
        is_root = parent == ""
        mark = "" if is_root else (CIRCLED[depth - 1] + " " if depth <= 10 else f"[{depth}] ")
        label = mark + node.name + "/"
        if node.perm_error:
            label += " [无权限]"
        if node.packages:
            label += f"   ◀ {len(node.packages)} 个资源包"
        tags = ["root"] if is_root else [f"d{min(depth, 8)}"]
        if node.packages and not is_root:
            tags.append("haspkg")
        item = self.tree.insert(
            parent, "end", text=label,
            values=(human_size(node.total_size), node.file_count, len(node.packages)),
            tags=tags, open=True)
        self._dir_map[item] = node.path
        for child in node.children:
            self._fill_tree(child, parent=item, depth=depth + 1)

    def _fill_packages(self, packages):
        packages = sorted(packages, key=lambda p: p.file_size, reverse=True)
        for pkg in packages:
            note = pkg.error if pkg.error else (f"共 {pkg.entry_count} 项" if pkg.entry_count else "")
            item = self.pkg_tree.insert("", "end", values=(
                pkg.fmt, pkg.path, human_size(pkg.file_size),
                pkg.image_count, pkg.video_count, pkg.audio_count, note))
            self._pkg_map[item] = pkg

    def _popup(self, event, tree, make_items):
        iid = tree.identify_row(event.y)
        if not iid:
            return
        tree.selection_set(iid)
        menu = tk.Menu(self, tearoff=0)
        for text, cmd in make_items(iid):
            menu.add_command(label=text, command=cmd)
        menu.tk_popup(event.x_root, event.y_root)

    def _on_tree_menu(self, event):
        def items(iid):
            path = self._dir_map.get(iid)
            if not path:
                return []
            return [
                ("打开目录", lambda: os.startfile(path)),
                ("复制绝对路径", lambda: self._copy_text(path)),
                ("复制文件夹", lambda: copy_files_to_clipboard([path], self.status_var.set)),
            ]
        self._popup(event, self.tree, items)

    def _on_pkg_menu(self, event):
        def items(iid):
            pkg = self._pkg_map.get(iid)
            if not pkg:
                return []
            return [
                ("打开所在目录", lambda: os.startfile(os.path.dirname(pkg.path))),
                ("复制绝对路径", lambda: self._copy_text(pkg.path)),
                ("复制文件", lambda: copy_files_to_clipboard([pkg.path], self.status_var.set)),
                ("查看包内详情", lambda: self._show_pkg_detail(None)),
            ]
        self._popup(event, self.pkg_tree, items)

    def _copy_text(self, text):
        self.app.clipboard_clear()
        self.app.clipboard_append(text)
        self.status_var.set(f"已复制: {text}")

    def _show_pkg_detail(self, _event):
        sel = self.pkg_tree.selection()
        if not sel:
            return
        pkg = self._pkg_map.get(sel[0])
        if not pkg:
            return
        lines = [f"文件: {pkg.path}", f"格式: {pkg.fmt}   大小: {human_size(pkg.file_size)}"]
        if pkg.error:
            lines.append(f"索引解析失败: {pkg.error}")
        else:
            lines.append(
                f"共 {pkg.entry_count} 项 | 图片 {pkg.image_count} 个 "
                f"({human_size(pkg.image_bytes)}) | 视频 {pkg.video_count} 个 "
                f"({human_size(pkg.video_bytes)}) | 音频 {pkg.audio_count} 个 | "
                f"其他 {pkg.other_count} 个")
            if pkg.sample_names:
                lines.append("")
                lines.append("图片/视频示例:")
                lines.extend("  " + n for n in pkg.sample_names)
        messagebox.showinfo("资源包详情", "\n".join(lines))


class ToolkitApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("980x760")
        self.root.minsize(800, 600)
        if os.path.exists("app.ico"):
            self.root.iconbitmap("app.ico")
        self._closed = False
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        style = ttk.Style()
        style.theme_use("clam")

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)

        self.rpa_tab = RPAUnpackerTab(self.notebook, root)
        self.scan_tab = AssetScannerTab(self.notebook, root)
        self.notebook.add(self.rpa_tab, text=" RPA 解包 ")
        self.notebook.add(self.scan_tab, text=" 资源扫描 ")

    def _on_close(self):
        if self._closed:
            return
        self._closed = True
        self.rpa_tab._closed = True
        self.scan_tab._closed = True
        if self.rpa_tab._after_id:
            self.rpa_tab.after_cancel(self.rpa_tab._after_id)
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass
        threading.Timer(0.5, lambda: os._exit(0)).start()


def main():
    root = TkinterDnD.Tk()
    ToolkitApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
