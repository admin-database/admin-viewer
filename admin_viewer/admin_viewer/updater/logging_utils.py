# -*- coding: utf-8 -*-
from __future__ import annotations
import os, sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import tkinter as tk
from tkinter import ttk

# 콘솔창 (업데이트 진행상황 가시화)
_console_root = None
_console_text = None

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]  # admin_viewer/ 아래 기준

def _icon_path() -> Optional[Path]:
    for cand in ("logo.ico", "Logo.ico", "icon.ico"):
        p = _base_dir() / cand
        if p.exists():
            return p
    return None

def log_path() -> Path:
    return _base_dir() / "log" / "updatelog.txt"

def ulog(msg: str) -> None:
    # 파일
    try:
        log_path().parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path(), "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass
    # 콘솔
    try:
        _console_append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    except Exception:
        pass

def console_open():
    global _console_root, _console_text
    if _console_root is not None:
        return
    try:
        _console_root = tk.Toplevel()
        _console_root.title("업데이트 진행 상황")
        _console_root.attributes("-topmost", True)
        _console_root.geometry("640x360+240+160")
        frm = ttk.Frame(_console_root, padding=8); frm.pack(fill="both", expand=True)
        _console_text = tk.Text(frm, height=12)
        _console_text.pack(fill="both", expand=True)
        ttk.Button(frm, text="닫기", command=_console_root.destroy).pack(side="right", pady=6)
        _console_root.update()
    except Exception:
        _console_root = None
        _console_text = None

def _console_append(line: str):
    if _console_root is None or _console_text is None:
        return
    try:
        _console_text.insert("end", line + "\n")
        _console_text.see("end")
        _console_root.update_idletasks()
    except Exception:
        pass
