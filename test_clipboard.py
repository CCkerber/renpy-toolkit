import os
import sys
import tempfile
import subprocess

sys.path.insert(0, os.path.dirname(__file__))
from toolkit_gui import copy_files_to_clipboard


def main():
    tmp = tempfile.mkdtemp(prefix="tk_clip_test_")
    target = os.path.join(tmp, "sample_game")
    os.makedirs(target, exist_ok=True)

    copy_files_to_clipboard([target], show_success=False)

    ps = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "(Get-Clipboard -Format FileDropList).FullName"],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    got = [l.strip() for l in ps.stdout.splitlines() if l.strip()]
    print("clipboard files:", got)
    norm_target = os.path.normpath(target).lower()
    if any(os.path.normpath(g).lower() == norm_target for g in got):
        print("PASSED")
        sys.exit(0)
    else:
        print("FAIL: clipboard does not contain the folder")
        sys.exit(1)


if __name__ == "__main__":
    main()
