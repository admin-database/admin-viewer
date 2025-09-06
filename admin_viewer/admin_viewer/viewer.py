# -*- coding: utf-8 -*-
import os, json, platform, shutil, webbrowser
from datetime import datetime
import pandas as pd
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import tkinter.font as tkfont

from .version import __version__
from .config import APP_TITLE, CACHE_DIR, SETTINGS_PATH, DEFAULT_VIEW_COLS, HEADER_LABELS
from .helpers import autosize_excel, parse_id_list, sanitize_component, is_url
from .drive import drive_download_url, extract_drive_file_id
from . import ui

class ViewerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE}  v{__version__}")
        try:
            self.state("zoomed")
        except:
            self.geometry("1280x760")

        self.api_input = tk.StringVar()
        self.df_all = pd.DataFrame()
        self.last_filtered = pd.DataFrame()
        self.selected_ids = []
        self.combo_items = []
        self.combo_map = {}
        self.sort_reverse = {}
        self.last_ids = set()
        self.last_sdt = None
        self.last_edt = None

        self._overlay = None
        self._overlay_font = None
        self._overlay_url = None

        os.makedirs(CACHE_DIR, exist_ok=True)
        self._load_settings()

        ui.build_ui(self)

    def _load_settings(self):
        try:
            if os.path.isfile(SETTINGS_PATH):
                with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                self.api_input.set(cfg.get("last_api", ""))
        except:
            pass

    def _save_settings(self):
        try:
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump({"last_api": self.api_input.get().strip()}, f, ensure_ascii=False, indent=2)
        except:
            pass

    def _prompt_api_then_sync(self):
        initial = self.api_input.get().strip()
        val = simpledialog.askstring(
            "API / 파일ID / 공유링크",
            "API URL 또는 manifest 파일 ID/공유링크를 입력하세요.",
            initialvalue=initial,
            parent=self
        )
        if not val:
            return
        self.api_input.set(val.strip())
        self._save_settings()
        self.sync_data()

    def sync_data(self):
        import requests
        raw = self.api_input.get().strip()
        if not raw:
            messagebox.showwarning("경고", "API 또는 manifest 파일 ID/공유링크를 입력하세요.")
            return
        try:
            manifest = None
            if is_url(raw):
                fid = extract_drive_file_id(raw)
                if fid:
                    manifest = requests.get(drive_download_url(fid), timeout=60).json()
                else:
                    resp = requests.get(raw, timeout=60)
                    resp.raise_for_status()
                    payload = resp.json()
                    if isinstance(payload, dict) and "files" in payload:
                        manifest = payload
                    else:
                        mid = self._extract_manifest_id(payload)
                        if not mid:
                            raise ValueError("API 응답에서 manifest_file_id를 찾지 못했습니다.")
                        manifest = requests.get(drive_download_url(mid), timeout=60).json()
            else:
                manifest = requests.get(drive_download_url(raw), timeout=60).json()
        except Exception as e:
            messagebox.showerror("에러", f"API 호출 실패\n{e}")
            return

        files = manifest.get("files", []) if isinstance(manifest, dict) else []
        if not files:
            messagebox.showwarning("경고","manifest에 files가 없습니다.")
            return

        frames=[]
        for f in files:
            fid = f.get("fileId"); name = f.get("name")
            if not fid or not name:
                continue
            try:
                local_path = os.path.join(CACHE_DIR, name)
                r = requests.get(drive_download_url(fid), timeout=120)
                r.raise_for_status()
                with open(local_path, "wb") as fp:
                    fp.write(r.content)
                frames.append(pd.read_parquet(local_path))
            except Exception as e:
                messagebox.showwarning("알림", f"{name} 받기 실패: {e}")

        if not frames:
            messagebox.showwarning("경고","가져온 데이터가 없습니다.")
            return

        df = pd.concat(frames, ignore_index=True)
        if "pub_date" in df.columns:
            df["pub_date"] = pd.to_datetime(df["pub_date"], errors="coerce")

        view_cols = [c for c in DEFAULT_VIEW_COLS if c in df.columns]
        self.df_all = df[view_cols].copy()

        self.render_table(pd.DataFrame())
        self.last_filtered = pd.DataFrame()
        self.selected_ids.clear()
        self.last_ids = set()
        self.last_sdt = None
        self.last_edt = None
        self._reset_combo()

        vr = manifest.get("view_range", {})
        self.status.set(f"동기화 완료: 기간 {vr.get('min_date')} ~ {vr.get('max_date')}")

    def _extract_manifest_id(self, payload: dict):
        if not isinstance(payload, dict):
            return None
        for k in ("manifest_file_id", "manifest_id", "file_id", "id"):
            if isinstance(payload.get(k), str) and payload[k].strip():
                return payload[k].strip()
        data = payload.get("data", {})
        if isinstance(data, dict):
            for k in ("manifest_file_id", "manifest_id", "file_id", "id"):
                if isinstance(data.get(k), str) and data[k].strip():
                    return data[k].strip()
        return None

    def render_table(self, df: pd.DataFrame):
        self.tree.delete(*self.tree.get_children())
        self._hide_overlay()

        if df.empty:
            self.tree["columns"] = ()
            return

        data_cols = list(df.columns)
        cols = ["No"] + data_cols
        self.tree["columns"] = cols

        for c in cols:
            head = HEADER_LABELS.get(c, c)
            if c == "No":
                self.tree.heading(c, text=head)
                w = 60; anchor = "center"
            else:
                self.tree.heading(c, text=head, command=lambda _c=c: self.sort_by_column(_c))
                if c == "post_url":
                    w = 380; anchor = "w"
                elif c == "title":
                    w = 320; anchor = "w"
                elif c in ("place_id", "company_name", "pub_date"):
                    w = 110 if c == "pub_date" else (140 if c == "company_name" else 90)
                    anchor = "center"
                else:
                    w = 120; anchor = "w"
            self.tree.column(c, width=w, anchor=anchor)

        for no, row in enumerate(df.itertuples(index=False), start=1):
            vals = [str(no)]
            for v in row:
                if isinstance(v, pd.Timestamp):
                    vals.append(v.strftime("%Y-%m-%d"))
                else:
                    vals.append("" if (pd.isna(v) if isinstance(v, float) else v is None) else str(v))
            self.tree.insert("", "end", values=vals)

    def sort_by_column(self, col: str):
        if self.last_filtered.empty or col == "No":
            return
        reverse = self.sort_reverse.get(col, False)
        if col != "pub_date" and "pub_date" in self.last_filtered.columns:
            self.last_filtered = self.last_filtered.sort_values(
                by=[col, "pub_date"], ascending=[not reverse, True], na_position='last'
            )
        else:
            self.last_filtered = self.last_filtered.sort_values(
                by=col, ascending=not reverse, na_position='last'
            )
        self.sort_reverse[col] = not reverse
        self.render_table(self.last_filtered)

    def _reset_combo(self):
        self.combo_items = []
        self.combo_map = {}
        self.combo.configure(state="disabled", values=[])
        self.combo_var.set("")

    def prompt_id_list(self):
        txt = simpledialog.askstring(
            "업체 일괄 등록",
            "업체ID를 콤마, 공백, 줄바꿈으로 구분해 입력하세요.\n예) 123,456 789",
            parent=self
        )
        if txt is None:
            return
        ids = parse_id_list(txt)
        if not ids:
            messagebox.showwarning("경고", "인식된 업체ID가 없습니다.")
            return
        self.selected_ids = ids

        if self.df_all.empty or "place_id" not in self.df_all.columns:
            self._reset_combo()
            return

        df_ids = self.df_all[self.df_all["place_id"].astype(str).isin(ids)].copy()
        if "company_name" in df_ids.columns:
            items = ["전체(선택된)"]
            mapping = {}
            for pid, cname in (
                df_ids[["place_id","company_name"]]
                .dropna()
                .drop_duplicates(subset=["place_id"])
                .itertuples(index=False)
            ):
                label = f"{pid} - {cname}"
                items.append(label)
                mapping[label] = str(pid)
            self.combo_items = items
            self.combo_map = mapping
            self.combo.configure(state="readonly", values=items)
            self.combo_var.set("전체(선택된)")
        else:
            items = ["전체(선택된)"] + [str(x) for x in ids]
            mapping = {str(x): str(x) for x in ids}
            self.combo_items = items
            self.combo_map = mapping
            self.combo.configure(state="readonly", values=items)
            self.combo_var.set("전체(선택된)")

    def on_combo_select(self, _evt=None):
        sel = self.combo_var.get().strip()
        self.apply_filter(force_sel=sel)

    def apply_filter(self, force_sel: str | None = None):
        if self.df_all.empty:
            return

        df = self.df_all.copy()

        ids_from_button = set(self.selected_ids) if self.selected_ids else set()
        q = self.search_var.get().strip()
        ids_from_input = set(parse_id_list(q)) if q else set()

        if ids_from_input:
            ids = ids_from_input
        else:
            ids = ids_from_button
            sel = force_sel or self.combo_var.get().strip()
            if sel and sel != "전체(선택된)":
                pid = self.combo_map.get(sel)
                if pid:
                    ids = {pid}

        sdt = edt = None
        try:
            if getattr(self, "_use_calendar", False):
                sdt = self.start_cal.get_date()
                edt = self.end_cal.get_date()
            else:
                s_raw = getattr(self, "start_var", tk.StringVar()).get().strip()
                e_raw = getattr(self, "end_var", tk.StringVar()).get().strip()
                sdt = datetime.strptime(s_raw, "%Y-%m-%d").date() if s_raw else None
                edt = datetime.strptime(e_raw, "%Y-%m-%d").date() if e_raw else None
        except:
            pass

        if not ids:
            self.last_filtered = pd.DataFrame()
            self.last_ids = set()
            self.last_sdt = sdt
            self.last_edt = edt
            self.render_table(self.last_filtered)
            self.status.set("업체 ID를 지정해야 조회할 수 있습니다.")
            return

        df = df[df["place_id"].astype(str).isin(ids)]
        if "pub_date" in df.columns:
            if sdt:
                df = df[df["pub_date"] >= pd.to_datetime(sdt)]
            if edt:
                df = df[df["pub_date"] <= pd.to_datetime(edt)]

        self.last_filtered = df
        self.last_ids = set(ids)
        self.last_sdt = sdt
        self.last_edt = edt
        self.render_table(df)

        range_txt = ""
        if sdt or edt:
            s_txt = sdt.strftime("%Y-%m-%d") if sdt else "…"
            e_txt = edt.strftime("%Y-%m-%d") if edt else "…"
            range_txt = f" / 기간 {s_txt} ~ {e_txt}"
        ids_txt = f" / 업체ID {', '.join(sorted(map(str, ids)))[:80]}..." if ids else ""
        self.status.set(f"조회 조건 적용{range_txt}{ids_txt}")

    def export_excel(self):
        if self.last_filtered.empty:
            messagebox.showwarning("경고","저장할 조회 결과가 없습니다. 먼저 [조회하기]를 실행해 주세요.")
            return

        df = self.last_filtered.copy()
        if "pub_date" in df.columns:
            df["pub_date"] = pd.to_datetime(df["pub_date"], errors="coerce").dt.strftime("%Y-%m-%d")

        sdt = self.last_sdt
        edt = self.last_edt
        if not sdt or not edt:
            try:
                p = pd.to_datetime(self.last_filtered["pub_date"], errors="coerce")
                if not sdt: sdt = p.min().date() if not p.isna().all() else None
                if not edt: edt = p.max().date() if not p.isna().all() else None
            except:
                pass
        s_txt = (sdt.strftime("%Y-%m-%d") if sdt else "시작없음")
        e_txt = (edt.strftime("%Y-%m-%d") if edt else "마감없음")

        title_name = ""
        try:
            all_ids = set(self.df_all["place_id"].astype(str).unique()) if "place_id" in self.df_all.columns else set()
            ids = self.last_ids
            if ids and all_ids and ids == all_ids:
                title_name = "전체"
            else:
                if "company_name" in self.last_filtered.columns:
                    names = [x for x in self.last_filtered["company_name"].dropna().astype(str).unique() if x.strip()]
                    if len(names) == 0:
                        title_name = "선택"
                    elif len(names) == 1:
                        title_name = names[0]
                    else:
                        title_name = f"{names[0]}외"
                else:
                    pids = [x for x in self.last_filtered["place_id"].astype(str).unique()]
                    if len(pids) == 0:
                        title_name = "선택"
                    elif len(pids) == 1:
                        title_name = pids[0]
                    else:
                        title_name = f"{pids[0]}외"
        except:
            title_name = "선택"

        fname = f"애드민_리포트_{sanitize_component(title_name)}_{s_txt}_{e_txt}.xlsx"
        f = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel","*.xlsx")],
            initialfile=fname
        )
        if not f:
            return

        df.to_excel(f, index=False)
        try:
            autosize_excel(f)
        except:
            pass
        messagebox.showinfo("완료", f"엑셀 저장 완료:\n{os.path.basename(f)}")

    def _on_tree_double_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        col_id = self.tree.identify_column(event.x)
        row_id = self.tree.identify_row(event.y)
        if not col_id or not row_id:
            return
        try:
            col_index = int(col_id.replace('#','')) - 1
        except:
            return
        cols = list(self.tree["columns"])
        if not (0 <= col_index < len(cols)) or cols[col_index] != "post_url":
            return
        url = str(self.tree.item(row_id).get("values", [])[col_index]).strip()
        if url.lower().startswith("http"):
            self._open_in_chrome(url)

    def _on_tree_motion(self, event):
        region = self.tree.identify("region", event.x, event.y)
        col_id = self.tree.identify_column(event.x)
        row_id = self.tree.identify_row(event.y)
        if region != "cell" or not col_id or not row_id:
            self._hide_overlay(); return
        try:
            col_index = int(col_id.replace('#','')) - 1
        except:
            self._hide_overlay(); return

        cols = list(self.tree["columns"])
        if not (0 <= col_index < len(cols)) or cols[col_index] != "post_url":
            self._hide_overlay(); return

        values = self.tree.item(row_id).get("values", [])
        if col_index >= len(values):
            self._hide_overlay(); return
        url = str(values[col_index]).strip()
        if not url.lower().startswith("http"):
            self._hide_overlay(); return

        bbox = self.tree.bbox(row_id, col_id)
        if not bbox:
            self._hide_overlay(); return
        x, y, w, h = bbox

        if self._overlay is None:
            base_font = tkfont.nametofont("TkDefaultFont")
            self._overlay_font = base_font.copy()
            self._overlay_font.configure(underline=True)
            self._overlay = tk.Label(self.tree, fg="blue", bg=self.tree.cget("background"),
                                     font=self._overlay_font, cursor="hand2", anchor="w")
            self._overlay.bind("<Button-1>", lambda e: self._open_in_chrome(self._overlay_url))
            self._overlay.bind("<Double-1>", lambda e: self._open_in_chrome(self._overlay_url))

        self._overlay_url = url
        self._overlay.configure(text=url)
        self._overlay.place(x=x+2, y=y, width=w-4, height=h)
        self.tree.configure(cursor="hand2")

    def _on_tree_leave(self, _evt=None):
        self._hide_overlay()

    def _on_tree_click_any(self, _evt=None):
        self._hide_overlay()

    def _hide_overlay(self):
        if self._overlay is not None:
            self._overlay.place_forget()
        self.tree.configure(cursor="")

    def _open_in_chrome(self, url:str):
        opened = False
        try:
            controller = None
            candidates = []
            if platform.system() == "Windows":
                candidates = [
                    os.path.expandvars(r"%ProgramFiles%/Google/Chrome/Application/chrome.exe"),
                    os.path.expandvars(r"%ProgramFiles(x86)%/Google/Chrome/Application/chrome.exe"),
                    os.path.expandvars(r"%LocalAppData%/Google/Chrome/Application/chrome.exe"),
                ]
            elif platform.system() == "Darwin":
                candidates = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
            else:
                for name in ("google-chrome", "chrome", "chromium", "chromium-browser"):
                    p = shutil.which(name)
                    if p:
                        candidates.append(p)

            chrome_path = next((p for p in candidates if p and os.path.exists(p)), None)
            if chrome_path:
                webbrowser.register('chrome', None, webbrowser.BackgroundBrowser(chrome_path))
                controller = webbrowser.get('chrome')
            else:
                try:
                    controller = webbrowser.get('chrome')
                except:
                    controller = None

            if controller:
                controller.open(url, new=2)
                opened = True
        except:
            pass
        if not opened:
            webbrowser.open(url, new=2)
