# -*- coding: utf-8 -*-
"""
진행 팝업 + 백그라운드 파싱 실행
- parse_with_popup(parent, manifest_src, on_done=None, *, show_result=False)
"""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable


class _ProgressDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, title: str = "작업 진행 중"):
        super().__init__(parent)
        self.transient(parent)
        self.title(title)
        self.resizable(False, False)

        self._label = ttk.Label(self, text="준비 중…", anchor="w")
        self._label.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")

        self._note = ttk.Label(self, text="", anchor="w")
        self._note.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="ew")

        self._pb = ttk.Progressbar(self, mode="indeterminate", length=300)
        self._pb.grid(row=2, column=0, padx=16, pady=(0, 16), sticky="ew")
        self._pb.start(10)

        self.columnconfigure(0, weight=1)
        self.protocol("WM_DELETE_WINDOW", self._on_close_blocked)

        # 포커스/모달
        self.grab_set()
        self.focus_force()

    # ---- 외부에서 호출하는 업데이트 API
    def set_total(self, total: int):
        try:
            total = int(total)
        except Exception:
            total = -1
        if total and total > 0:
            self._pb.config(mode="determinate", maximum=total, value=0)
        else:
            self._pb.config(mode="indeterminate")
            self._pb.start(10)

    def set_progress(self, done: int, total: int, label: str):
        try:
            total = int(total)
        except Exception:
            total = -1
        if total and total > 0:
            if str(self._pb.cget("mode")) != "determinate":
                self._pb.config(mode="determinate", maximum=total, value=0)
            self._pb["value"] = max(0, min(done, total))
        else:
            if str(self._pb.cget("mode")) != "indeterminate":
                self._pb.config(mode="indeterminate")
                self._pb.start(10)
        self._label.configure(text=label or "")

    def set_note(self, note: str):
        self._note.configure(text=note or "")

    def close(self):
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    def _on_close_blocked(self):
        # 진행 중 닫기 방지
        pass


def parse_with_popup(
    parent: tk.Misc,
    manifest_src: str,
    on_done: Optional[Callable[[Optional[object]], None]] = None,
    *,
    show_result: bool = False,
):
    """
    진행 팝업을 띄우고, 백그라운드에서 파싱을 실행한다.
    - manifest_src: 매니페스트 URL/Drive 공유링크/파일 ID 등
    - on_done(result): 완료 시 콜백 (GUI 스레드에서 호출)
    - show_result: True면 성공 메시지를 간단히 표시
    """
    # ※ 순환 임포트 방지: 함수 내부에서 지연 임포트
    from .parser_runner import parse_all, ManifestError, ProgressCB  # type: ignore

    dlg = _ProgressDialog(parent, title="데이터 파싱 중")

    # GUI 업데이트용 콜백
    def progress_cb(done: int, total: int, label: str):
        try:
            dlg.set_progress(done, total, label)
        except tk.TclError:
            pass  # 창이 닫힌 경우 등

    result_holder = {"result": None, "error": None}

    def worker():
        try:
            result_holder["result"] = parse_all(manifest_src, progress_cb=progress_cb)
        except ManifestError as e:
            result_holder["error"] = e
        except Exception as e:
            result_holder["error"] = e
        finally:
            dlg.after(0, _finish)

    def _finish():
        dlg.close()
        err = result_holder["error"]
        res = result_holder["result"]
        if err is not None:
            messagebox.showerror("실패", f"파싱 중 오류가 발생했습니다.\n{err}")
            if on_done:
                on_done(None)
            return
        if show_result:
            messagebox.showinfo("완료", "파싱을 완료했습니다.")
        if on_done:
            on_done(res)

    th = threading.Thread(target=worker, daemon=True)
    th.start()
    return dlg
