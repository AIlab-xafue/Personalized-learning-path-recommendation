#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 FILE_INDEX.md 是否覆盖了仓库里的每一个文件。

Verify that FILE_INDEX.md documents every file tracked in the repository.

用法 / Usage:
    python docs/check_file_index.py

退出码 / Exit codes:
    0  全部覆盖 / every file is documented
    1  有文件未被说明 / some files are undocumented
    2  无法读取文件清单 / cannot obtain the file list
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
INDEX = HERE / "FILE_INDEX.md"
ROOT = HERE.parent


def tracked_files():
    """优先用 git 列出被跟踪的文件；不在 git 环境时退回遍历目录。"""
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z"],
            capture_output=True, check=True,
        ).stdout.decode("utf-8")
        files = [f for f in out.split("\0") if f]
        if files:
            return files, "git ls-files"
    except (OSError, subprocess.CalledProcessError):
        pass

    skip = {".git", "__pycache__", ".venv", ".idea", "models"}
    files = []
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT)
        if any(part in skip for part in rel.parts):
            continue
        files.append(rel.as_posix())
    return sorted(files), "目录遍历 / directory walk"


def match_level(rel_path, text):
    """返回匹配层级：2=完整路径, 1=末两级, 0=文件名(且目录名出现), None=未匹配。"""
    parts = rel_path.split("/")
    if rel_path in text:
        return 2
    if len(parts) >= 2 and "/".join(parts[-2:]) in text:
        return 1
    if len(parts) >= 2:
        # 文件名与该文件所在目录名都出现，视为在该目录小节内被说明
        if parts[-1] in text and parts[-2] in text:
            return 0
        return None
    # 根目录文件：直接按文件名匹配
    return 0 if rel_path in text else None


def main():
    if not INDEX.exists():
        print("找不到 %s / missing: %s" % (INDEX, INDEX))
        return 2

    text = INDEX.read_text(encoding="utf-8")
    files, source = tracked_files()
    if not files:
        print("无法获取文件清单 / cannot obtain the file list")
        return 2

    missing, levels = [], {2: 0, 1: 0, 0: 0}
    for f in files:
        lv = match_level(f, text)
        if lv is None:
            missing.append(f)
        else:
            levels[lv] += 1

    print("文件清单来源 / source      : %s" % source)
    print("被跟踪的文件 / tracked files : %d" % len(files))
    print("完整路径匹配 / full path     : %d" % levels[2])
    print("末两级匹配   / last two      : %d" % levels[1])
    print("文件名+目录  / name + dir    : %d" % levels[0])
    print("-" * 52)

    if missing:
        print("未被说明的文件 / UNDOCUMENTED (%d):" % len(missing))
        for f in missing:
            print("  - %s" % f)
        print("\n请在 docs/FILE_INDEX.md 中补上这些条目。")
        print("Please add these entries to docs/FILE_INDEX.md.")
        return 1

    print("全部 %d 个文件均已在 FILE_INDEX.md 中说明。" % len(files))
    print("All %d files are documented." % len(files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
