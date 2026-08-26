#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""安全清理项目运行产物。

默认只预览；传入 ``--apply`` 才会真正删除。配置目录和源码永不在
清理目标中。.venv 属于可重建产物，默认一并清理；需要保留时传入
``--keep-venv``。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parent
RUNTIME_DIRS = ("logs", "reports", "data")
CACHE_DIR_NAMES = ("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache")
ROOT_ARTIFACTS = (".coverage", "coverage.xml")
PRESERVED_RUNTIME_NAMES = {".gitkeep"}


def _is_within_project(path: Path) -> bool:
    """拒绝删除项目目录以外或项目根目录本身的路径。"""
    resolved = path.resolve(strict=False)
    if resolved == PROJECT_ROOT:
        return False
    try:
        resolved.relative_to(PROJECT_ROOT)
        return True
    except ValueError:
        return False


def _walk_project() -> Iterable[Path]:
    """遍历项目，但跳过配置、版本库及虚拟环境。"""
    skipped = {"config", ".git", ".svn", ".venv", "venv", "env", "ENV"}
    for current, dirnames, filenames in os.walk(PROJECT_ROOT):
        current_path = Path(current)
        dirnames[:] = [name for name in dirnames if name not in skipped]
        for dirname in dirnames:
            yield current_path / dirname
        for filename in filenames:
            yield current_path / filename


def collect_targets(include_venv: bool = False) -> List[Path]:
    """只收集明确已知的可再生产物，不处理未知文件。"""
    targets: List[Path] = []

    for dirname in RUNTIME_DIRS:
        directory = PROJECT_ROOT / dirname
        if directory.is_dir():
            targets.extend(
                child for child in directory.iterdir()
                if child.name not in PRESERVED_RUNTIME_NAMES
            )

    for path in _walk_project():
        if path.is_dir() and path.name in CACHE_DIR_NAMES:
            targets.append(path)
        elif path.is_file() and path.suffix.lower() in {".pyc", ".pyo"}:
            targets.append(path)

    for filename in ROOT_ARTIFACTS:
        path = PROJECT_ROOT / filename
        if path.exists():
            targets.append(path)

    if include_venv:
        for dirname in (".venv", "venv", "env", "ENV"):
            path = PROJECT_ROOT / dirname
            if path.exists():
                targets.append(path)

    # 父目录已入选时，不再重复列出其中的子项。
    unique: List[Path] = []
    for target in sorted(set(targets), key=lambda item: (len(item.parts), str(item).lower())):
        if not _is_within_project(target):
            continue
        if any(parent == target or parent in target.parents for parent in unique):
            continue
        unique.append(target)
    return unique


def path_size(path: Path) -> int:
    try:
        if path.is_file() or path.is_symlink():
            return path.stat().st_size
        return sum(
            item.stat().st_size
            for item in path.rglob("*")
            if item.is_file() and not item.is_symlink()
        )
    except OSError:
        return 0


def format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def remove_target(path: Path) -> None:
    if not _is_within_project(path):
        raise ValueError(f"拒绝清理项目外路径: {path}")
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def _relaunch_outside_venv_if_needed(include_venv: bool) -> Optional[int]:
    """Windows 无法删除正在运行的 python.exe，必要时切到基础解释器。"""
    if not include_venv or os.environ.get("GOLD_CLEANUP_RELAUNCHED") == "1":
        return None

    executable = Path(sys.executable).resolve(strict=False)
    project_venvs = [PROJECT_ROOT / name for name in (".venv", "venv", "env", "ENV")]
    running_inside = any(
        venv.resolve(strict=False) == executable
        or venv.resolve(strict=False) in executable.parents
        for venv in project_venvs
    )
    if not running_inside:
        return None

    base_executable = Path(getattr(sys, "_base_executable", "")).resolve(strict=False)
    if not base_executable.is_file() or _is_within_project(base_executable):
        print("无法找到项目外的基础 Python，请退出虚拟环境后重新执行清理。")
        return 1

    env = os.environ.copy()
    env["GOLD_CLEANUP_RELAUNCHED"] = "1"
    result = subprocess.run(
        [str(base_executable), str(Path(__file__).resolve()), *sys.argv[1:]],
        cwd=str(PROJECT_ROOT),
        env=env,
        check=False,
    )
    return result.returncode


def main() -> int:
    # PowerShell 7 和 cleanup_windows.cmd 都使用 UTF-8；显式统一编码，
    # 避免 Windows 上中文预览出现乱码。
    if os.name == "nt":
        for stream in (sys.stdout, sys.stderr):
            reconfigure = getattr(stream, "reconfigure", None)
            if reconfigure:
                reconfigure(encoding="utf-8", errors="backslashreplace")

    parser = argparse.ArgumentParser(description="清理日志、报告、缓存和 Python 临时文件")
    parser.add_argument("--apply", action="store_true", help="实际执行；不加时仅预览")
    venv_group = parser.add_mutually_exclusive_group()
    venv_group.add_argument(
        "--keep-venv",
        action="store_true",
        help="保留虚拟环境；默认会把它作为可重建产物清理",
    )
    # 兼容旧命令；现在已经是默认行为。
    venv_group.add_argument("--include-venv", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    include_venv = not args.keep_venv
    if args.apply:
        relaunched_result = _relaunch_outside_venv_if_needed(include_venv)
        if relaunched_result is not None:
            return relaunched_result

    targets = collect_targets(include_venv)
    total_size = sum(path_size(path) for path in targets)

    print(f"项目目录: {PROJECT_ROOT}")
    print("始终保留: 源码、启动脚本、requirements、文档和 config 全部配置")
    print(f"清理目标: {len(targets)} 项，约 {format_size(total_size)}")
    for target in targets:
        print(f"  - {target.relative_to(PROJECT_ROOT)}")

    if not args.apply:
        print("\n当前为预览模式，未删除任何文件。确认后执行:")
        print("  python cleanup_project.py --apply")
        print("如需保留虚拟环境，请添加 --keep-venv。")
        return 0

    failures = []
    for target in targets:
        try:
            remove_target(target)
        except OSError as exc:
            failures.append((target, exc))

    # 保留运行目录本身，程序也能在清理后立即重新生成内容。
    for dirname in RUNTIME_DIRS:
        (PROJECT_ROOT / dirname).mkdir(exist_ok=True)

    if failures:
        print("\n部分文件未能清理，通常是程序仍在运行并占用了日志:")
        for path, exc in failures:
            print(f"  - {path.relative_to(PROJECT_ROOT)}: {exc}")
        return 1

    print(f"\n清理完成，已释放约 {format_size(total_size)}。")
    if include_venv:
        print("虚拟环境已清理；Windows 下请重新运行 setup_windows.cmd 后再启动。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
