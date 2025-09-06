# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk

def build_ui(app):
    top = ttk.Frame(app); top.pack(fill="x", padx=10, pady=8)

    ttk.Button(top, text="시작", command=app._prompt_api_then_sync).pack(side="left", padx=4)

    ttk.Label(top, text="업체ID:").pack(side="left", padx=(20,0))
    app.search_var = tk.StringVar()
    ttk.Entry(top, textvariable=app.search_var, width=18).pack(side="left", padx=4)

    ttk.Button(top, text="업체 일괄 등록", command=app.prompt_id_list).pack(side="left", padx=(10,4))

    ttk.Label(top, text="업체 선택:").pack(side="left", padx=(14,0))
    app.combo_var = tk.StringVar()
    app.combo = ttk.Combobox(top, textvariable=app.combo_var, width=28, state="disabled")
    app.combo.bind("<<ComboboxSelected>>", app.on_combo_select)
    app.combo.pack(side="left", padx=4)

    ttk.Label(top, text="시작:").pack(side="left", padx=(20,0))
    try:
        from tkcalendar import DateEntry
        app.start_cal = DateEntry(top, date_pattern="yyyy-mm-dd", width=12)
        app.start_cal.pack(side="left", padx=4)
        app.end_cal = DateEntry(top, date_pattern="yyyy-mm-dd", width=12)
        ttk.Label(top, text="끝:").pack(side="left", padx=(10,0))
        app.end_cal.pack(side="left", padx=4)
        app._use_calendar = True
    except Exception:
        app._use_calendar = False
        app.start_var = tk.StringVar()
        app.end_var = tk.StringVar()
        ttk.Entry(top, textvariable=app.start_var, width=12).pack(side="left", padx=4)
        ttk.Label(top, text="끝:").pack(side="left", padx=(10,0))
        ttk.Entry(top, textvariable=app.end_var, width=12).pack(side="left", padx=4)

    ttk.Button(top, text="조회하기", command=app.apply_filter).pack(side="left", padx=8)
    ttk.Button(top, text="엑셀 저장", command=app.export_excel).pack(side="left", padx=4)

    app.status = tk.StringVar(value="[시작]을 눌러 API(또는 manifest 파일 ID/공유링크)를 입력하고 데이터를 동기화하세요.")
    ttk.Label(top, textvariable=app.status).pack(side="left", padx=8, fill="x", expand=True)

    frame = ttk.Frame(app); frame.pack(fill="both", expand=True, padx=10, pady=8)
    app.tree = ttk.Treeview(frame, columns=(), show="headings", selectmode="none")
    vs = ttk.Scrollbar(frame, orient="vertical", command=app.tree.yview)
    hs = ttk.Scrollbar(frame, orient="horizontal", command=app.tree.xview)
    app.tree.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
    app.tree.pack(side="left", fill="both", expand=True)
    vs.pack(side="right", fill="y")
    hs.pack(side="bottom", fill="x")

    style = ttk.Style(app.tree)
    try:
        style.theme_use("clam")
    except:
        pass
    style.configure("Treeview", rowheight=26)

    app.tree.bind("<Double-1>", app._on_tree_double_click)
    app.tree.bind("<Motion>", app._on_tree_motion)
    app.tree.bind("<Leave>", app._on_tree_leave)
    app.tree.bind("<Button-1>", app._on_tree_click_any)
    app.tree.bind("<Configure>", lambda e: app._hide_overlay())
    app.tree.bind("<MouseWheel>", lambda e: app._hide_overlay())
    app.tree.bind("<Button-4>",  lambda e: app._hide_overlay())
    app.tree.bind("<Button-5>",  lambda e: app._hide_overlay())
