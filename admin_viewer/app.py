# app.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import traceback
import tkinter as tk
from tkinter import messagebox

from admin_viewer.single_instance import SingleInstance
from admin_viewer.viewer import ViewerApp
from admin_viewer.updater import check_on_startup


def main() -> None:
    # 단일 인스턴스 가드
    guard = SingleInstance("admin_viewer")
    if not guard.acquire():
        # 이미 실행 중 안내
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            messagebox.showinfo("안내", "애드민 리포트 뷰어가 이미 실행 중입니다.", parent=root)
        finally:
            try:
                root.destroy()
            except Exception:
                pass
        sys.exit(0)

    try:
        # 업데이트 확인 (최신이면 팝업 없음)
        try:
            check_on_startup(auto_launch_new=True)
        except Exception:
            pass  # 실패는 조용히 무시

        # ViewerApp은 tk.Tk를 상속 → 별도의 tk.Tk() 생성하지 말고 그냥 인스턴스화
        app = ViewerApp()
        app.mainloop()

    except Exception as e:
        # 예외 안내
        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            messagebox.showerror("오류", f"실행 중 오류가 발생했습니다.\n{e}\n\n{traceback.format_exc()}", parent=root)
        except Exception:
            traceback.print_exc(file=sys.stderr)
        finally:
            try:
                root.destroy()
            except Exception:
                pass
    finally:
        try:
            guard.release()
        except Exception:
            pass


if __name__ == "__main__":
    main()
