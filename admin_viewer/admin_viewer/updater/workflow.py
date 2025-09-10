# -*- coding: utf-8 -*-
from __future__ import annotations
import os
import sys
import threading
import subprocess
from pathlib import Path
from typing import Callable

import tkinter as tk
from tkinter import ttk, messagebox

from ..version import __version__
from ..config import APP_TITLE  # noqa: F401
from .logging_utils import _icon_path, ulog  # console_open 호출 제거
from .releases import (
    fetch_releases,
    pick_best_release,
    parse_semver,
    extract_version_from_asset_name,
)
from .download import download_resumable


# -------------------- UI 유틸 (완전 비가시 루트) --------------------
def _with_temp_root(fn: Callable[[], None]) -> None:
    """메시지박스용 루트를 완전 비가시로 생성."""
    root = tk.Tk()
    try:
        root.withdraw()
        try:
            root.overrideredirect(True)
            root.attributes("-alpha", 0.0)
            root.attributes("-toolwindow", True)
            root.attributes("-topmost", True)
        except Exception:
            pass
        fn.__globals__["root"] = root
        fn()
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def _ask_yesno(title: str, message: str) -> bool:
    ans = {"ok": False}

    def inner():
        ans["ok"] = messagebox.askyesno(title, message, parent=root)

    _with_temp_root(inner)
    return bool(ans["ok"])


class _ProgressDialog:
    """다운로드 진행창 (필요할 때만 표시)."""
    def __init__(self, title: str, message: str, determinate: bool = True):
        self.root = tk.Tk()
        try:
            self.root.title(title)
            self.root.attributes("-topmost", True)
            self.root.geometry("420x130+220+170")
            self.root.resizable(False, False)
            ic = _icon_path()
            if ic and ic.exists():
                try:
                    self.root.iconbitmap(default=str(ic))
                except Exception:
                    pass
        except Exception:
            pass

        frm = ttk.Frame(self.root, padding=10)
        frm.pack(fill="both", expand=True)

        self.lbl = ttk.Label(frm, text=message)
        self.lbl.pack(side="top", anchor="w", pady=(0, 8))

        mode = "determinate" if determinate else "indeterminate"
        self.pb = ttk.Progressbar(frm, orient="horizontal", mode=mode, length=360)
        self.pb.pack(side="top", fill="x")

        if not determinate:
            try:
                self.pb.start(10)
            except Exception:
                pass

        self.note = ttk.Label(frm, text="잠시만 기다려 주세요…", foreground="#666")
        self.note.pack(side="top", anchor="w", pady=(8, 0))

        try:
            self.root.update()
        except Exception:
            pass

    def set_fraction(self, frac: float):
        try:
            self.pb["value"] = max(0, min(100, frac * 100.0))
            self.root.update_idletasks()
        except Exception:
            pass

    def set_text(self, text: str):
        try:
            self.lbl.configure(text=text)
            self.root.update_idletasks()
        except Exception:
            pass

    def set_note(self, text: str):
        try:
            self.note.configure(text=text)
            self.root.update_idletasks()
        except Exception:
            pass

    def switch_to_indeterminate(self):
        try:
            self.pb.stop()
            self.pb.configure(mode="indeterminate")
            self.pb.start(10)
            self.root.update_idletasks()
        except Exception:
            pass

    def close(self):
        try:
            self.root.destroy()
        except Exception:
            pass


# -------------------- 파일/프로세스 유틸 --------------------
def _current_binary_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return Path(sys.argv[0]).resolve()


def _schedule_self_delete(target: Path, delay_seconds: int = 3) -> None:
    """Windows에서 자기 자신을 삭제하도록 예약."""
    if os.name != "nt":
        return
    cmd = (
        'cmd.exe /c start "" /min cmd.exe /c '
        f'"ping -n {max(2, delay_seconds)} 127.0.0.1 > nul & del /q \"{str(target)}\""'  # noqa: E501
    )
    try:
        subprocess.Popen(cmd, shell=True)
    except Exception as e:
        ulog(f"자기삭제 스케줄 실패: {e}")


# -------------------- 메인 엔트리 --------------------
def check_on_startup(auto_launch_new: bool = True) -> None:
    """
    앱 시작 시 업데이트 확인.
    - 최신이면 팝업/콘솔 아무것도 띄우지 않음.
    - 새 버전 존재 시에만 예/아니오 확인 → 다운로드 진행창 표시.
    """
    ulog("업데이트 확인 시작")

    # 1) 릴리스 조회
    try:
        releases = fetch_releases(timeout=10)
    except Exception as e:
        ulog(f"릴리스 불러오기 실패: {e}")
        return

    rel = pick_best_release(releases)
    if not rel:
        # 릴리스가 없으면 조용히 종료
        return

    tag_name = (rel.get("tag_name") or "").strip()
    tag_ver = tag_name.lstrip("vV") if parse_semver(tag_name) else None

    # 다운로드 대상으로 쓸 EXE 자산 선택
    best_asset = None
    for a in (rel.get("assets") or []):
        nm = a.get("name") or ""
        if nm.lower().endswith(".exe"):
            best_asset = a
            break

    if not best_asset:
        ulog("릴리스에 규칙에 맞는 EXE 자산이 없음")
        return

    remote_version = extract_version_from_asset_name(best_asset.get("name", "")) or tag_ver
    if not remote_version or not parse_semver(remote_version):
        ulog("원격 버전 파싱 실패 (자산명/태그 둘 다 실패)")
        return

    # 최신이면 조용히 종료 (팝업/콘솔 없음)
    if parse_semver(__version__) >= parse_semver(remote_version):
        ulog(f"최신 상태: 로컬 {__version__} >= 원격 {remote_version}")
        return

    ulog(f"새 버전 발견: 원격 {remote_version}, 로컬 {__version__}")

    # 2) 사용자 동의(완전 비가시 루트)
    def _ask():
        return _ask_yesno(
            "업데이트 확인",
            f"새 버전이 있습니다.\n현재: v{__version__}\n최신: v{remote_version}\n\n지금 업데이트하시겠습니까?",
        )

    ok = False

    def _ask_with_root():
        nonlocal ok
        ok = _ask()

    _with_temp_root(_ask_with_root)
    if not ok:
        ulog("사용자가 업데이트를 취소함")
        return

    # 3) 다운로드 (진행창)
    dlg = _ProgressDialog(
        title="업데이트 다운로드",
        message=f"새 버전(v{remote_version}) 내려받는 중…",
        determinate=True,
    )

    def _on_progress(frac: float, read: int, total: int):
        try:
            if total > 0:
                dlg.set_fraction(frac)
                dlg.set_note(f"{read/1024/1024:.1f}MB / {total/1024/1024:.1f}MB")
            else:
                dlg.set_note(f"{read/1024/1024:.1f}MB 다운로드 중… (크기 미상)")
        except Exception:
            pass

    def _on_indeterminate():
        try:
            dlg.switch_to_indeterminate()
            dlg.set_note("서버가 파일 크기를 제공하지 않습니다… 잠시만요")
        except Exception:
            pass

    ex = {"err": None}

    def worker():
        try:
            asset_url = best_asset.get("browser_download_url") or best_asset.get("url")
            if not asset_url:
                raise RuntimeError("자산 URL이 없음")

            # 순환 import 회피: 여기서 베이스 디렉토리 가져옴
            from .logging_utils import _base_dir

            tmp_target = _base_dir() / f"admin_viewer_{remote_version}.download"
            download_resumable(
                asset_url,
                tmp_target,
                timeout=300,
                progress_cb=_on_progress,
                on_indeterminate=_on_indeterminate,
                tries=3,
            )

            # 4) 완료 처리: 새 exe로 배치
            new_exe = _base_dir() / f"admin_viewer-{remote_version}.exe"
            if new_exe.exists():
                try:
                    new_exe.unlink()
                except Exception:
                    pass
            tmp_target.rename(new_exe)
            ulog(f"다운로드 완료 → {new_exe}")

            # 5) 완료 안내(완전 비가시 루트 사용)
            def _done_alert():
                messagebox.showinfo(
                    "다운로드 완료",
                    f"새 버전 파일이 준비되었습니다:\n{new_exe}\n\n확인을 누르면 새 버전을 실행합니다.",
                    parent=root,
                )

            _with_temp_root(_done_alert)

            # 6) 새 EXE 실행 + 자기자신 삭제 예약 + 종료
            if auto_launch_new and new_exe.suffix.lower() == ".exe":
                try:
                    old_exe = _current_binary_path() if getattr(sys, "frozen", False) else None
                    subprocess.Popen([str(new_exe)])
                    if old_exe and old_exe.exists():
                        _schedule_self_delete(old_exe, delay_seconds=3)
                    os._exit(0)
                except Exception as e:
                    ulog(f"새 EXE 실행 실패: {e}")

        except Exception as e:
            ex["err"] = e
        finally:
            try:
                dlg.close()
            except Exception:
                pass

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    try:
        dlg.root.mainloop()
    except Exception:
        pass

    if ex["err"]:
        ulog(f"업데이트 처리 실패: {ex['err']}")
