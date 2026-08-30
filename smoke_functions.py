# -*- coding: utf-8 -*-
"""功能冒烟：调用核心模块，不启 GUI。"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

# 1. 扫描
from scanner_core import scan_tree
node, pkgs = scan_tree(os.path.join(ROOT, "..", "renpy-asset-scanner", "sample_game"))
assert len(pkgs) >= 3, pkgs
print(f"scanner OK: dirs={1+sum(len(c.children) for c in node.children)} pkgs={len(pkgs)}")

# 2. 解包
from rpa_unpacker_core import run_one, SUPPORTED_EXT
samples = os.path.join(ROOT, "..", "rpa-unpacker", "test_samples")
archives = [os.path.join(samples, f) for f in sorted(os.listdir(samples))
            if os.path.splitext(f)[1].lower() in SUPPORTED_EXT and "broken" not in f]
assert archives, "no sample archives"
out_base = os.path.join(ROOT, "test_unpack_output")
os.makedirs(out_base, exist_ok=True)
log = []
ok = run_one(archives[0], lambda x: log.append(x), out_base, True)
assert ok, log
print(f"unpack OK: {archives[0]}")
print("FUNCTIONS PASSED")
