# -*- coding: utf-8 -*-
import os, json, platform, shutil, webbrowser
from datetime import datetime
import hashlib
import pandas as pd
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import tkinter.font as tkfont

from .version import __version__
from .config import APP_TITLE, CACHE_DIR, SETTINGS_PATH, DEFAULT_VIEW_COLS, HEADER_LABELS
from .helpers import autosize_excel, parse_id_list, sanitize_component, is_url
from . import ui
from .ui_progress import parse_with_popup
from .parser_runner import load_manifest  # 매니페스트 선확인용


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

        # 엑셀 저장 버튼 옆 '제공 기간' 라벨
        self.lbl_range_var = tk.StringVar(value="")
        self.lbl_range = None
        # 파싱 시 제공된 기간 저장(조회 시 건수만 덧붙임)
        self._provided_range = ("", "")  # (start_txt, end_txt)

        os.makedirs(CACHE_DIR, exist_ok=True)
        self._load_settings()

        # UI 생성 (self.tree, self.status, self.combo, self.combo_var, self.btn_export, self.toolbar 등)
        ui.build_ui(self)

        # 업체 선택 전 접근 방지: 엑셀 비활성화
        try:
            self.btn_export.configure(state="disabled")
        except Exception:
            pass

        # 툴바에 '제공' 라벨 부착
        self._init_range_label()

    # ---------- settings ----------
    def _load_settings(self):
        try:
            if os.path.isfile(SETTINGS_PATH):
                with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                self.api_input.set(cfg.get("last_api", ""))
                self._last_sig = cfg.get("last_manifest_sig", "")
        except:
            self._last_sig = ""

    def _save_settings(self):
        try:
            cfg = {
                "last_api": self.api_input.get().strip(),
                "last_manifest_sig": getattr(self, "_last_sig", "")
            }
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except:
            pass

    # ---------- 엑셀 옆 '제공' 라벨 ----------
    def _init_range_label(self):
        try:
            parent = getattr(self, "toolbar", None)
            if parent is None:
                return
            if self.lbl_range is None:
                self.lbl_range = ttk.Label(parent, textvariable=self.lbl_range_var)
                self.lbl_range.pack(side="left", padx=(6, 0))
        except Exception:
            pass

    def _update_range_label(self, s_txt: str, e_txt: str, count: int | None = None):
        """
        파싱 직후: count=None → '제공: 시작 ~ 종료'만
        조회 후: count=int → '제공: … / N건'
        """
        text = ""
        if s_txt or e_txt:
            text = f"제공: {s_txt} ~ {e_txt}" if (s_txt and e_txt) else f"제공: {s_txt or e_txt}"
        if count is not None:
            text = (text + " / " if text else "") + f"{count:,}건"
        try:
            self.lbl_range_var.set(text)
            if self.lbl_range is None:
                self._init_range_label()
        except Exception:
            pass

    # ---------- 콤보 완전 비활성화 ----------
    def _disable_combo(self):
        """콤보를 완전 비활성화 + 목록 숨김 + 선택값 비움."""
        self.combo_items = []
        self.combo_map = {}
        try:
            self.combo.configure(state="disabled", values=[])
        except Exception:
            pass
        self.combo_var.set("")

    # ---------- API 입력 받고 실행 ----------
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

    # ---------- 파싱 실행 ----------
    def sync_data(self):
        manifest_src = self.api_input.get().strip()
        if not manifest_src:
            messagebox.showwarning("경고", "API 또는 manifest 파일 ID/공유링크를 입력하세요.", parent=self)
            return

        # 0) 매니페스트 선확인
        try:
            manifest = load_manifest(manifest_src)
            new_sig = self._signature_of_manifest(manifest)
        except Exception as e:
            messagebox.showerror("에러", f"매니페스트 로드 실패: {e}", parent=self)
            return

        # 변경 없음 → 팝업 없이 상태만 갱신
        if self._last_sig and new_sig == self._last_sig:
            if self.df_all.empty:
                parse_with_popup(self, manifest_src, on_done=self._after_parse, show_result=False)
            else:
                vr = manifest.get("view_range", {}) or {}
                s_txt = (vr.get("min_date") or "").strip()
                e_txt = (vr.get("max_date") or "").strip()
                self._provided_range = (s_txt, e_txt)
                self._update_range_label(s_txt, e_txt)  # 총량 감춤
                if s_txt or e_txt:
                    self.status.set(f"변경 없음: 기간 {s_txt} ~ {e_txt}")
                else:
                    self.status.set("변경 없음")
            return

        # 1) 변경 있음 → 진행 팝업(결과 팝업 없음)
        parse_with_popup(self, manifest_src, on_done=self._after_parse, show_result=False)

    def _signature_of_manifest(self, manifest: dict) -> str:
        """manifest 핵심 값(version, schema, files[name/size/fileId])으로 해시 생성"""
        try:
            ver = str(manifest.get("version", ""))
            sch = str(manifest.get("schema", ""))
            files = manifest.get("files", []) or []
            core = {
                "version": ver,
                "schema": sch,
                "files": [
                    {"name": f.get("name", ""),
                     "size": int(f.get("size") or 0),
                     "fileId": f.get("fileId", "")}
                    for f in files
                ]
            }
            dump = json.dumps(core, ensure_ascii=False, sort_keys=True).encode("utf-8")
            return hashlib.sha256(dump).hexdigest()
        except Exception:
            return ""

    def _after_parse(self, res):
        """
        parse_with_popup 의 on_done 콜백.
        res: ParseResult(df, start_date, end_date, meta)
        """
        # 1) DataFrame 반영
        df = res.df.copy()
        view_cols = [c for c in DEFAULT_VIEW_COLS if c in df.columns]
        self.df_all = df[view_cols].copy() if view_cols else df.copy()

        # 2) 상태 초기화 (테이블 비우기, 엑셀 비활성화, 콤보 비활성화)
        self.render_table(pd.DataFrame())
        self.last_filtered = pd.DataFrame()
        self.selected_ids.clear()
        self.last_ids = set()
        self.last_sdt = None
        self.last_edt = None
        self._disable_combo()
        try:
            self.btn_export.configure(state="disabled")
        except Exception:
            pass

        # 3) 콤보 목록만 내부에 준비(화면은 비활성화 상태 유지)
        if "place_id" in self.df_all.columns:
            all_ids = [str(x) for x in self.df_all["place_id"].astype(str).dropna().unique()]
            items, mapping = [], {}
            if "company_name" in self.df_all.columns:
                tmp = (self.df_all[["place_id","company_name"]]
                       .dropna()
                       .astype({"place_id": str, "company_name": str})
                       .drop_duplicates(subset=["place_id"]))
                for pid, cname in tmp.itertuples(index=False):
                    label = f"{pid} - {cname}"
                    items.append(label); mapping[label] = str(pid)
            else:
                for pid in all_ids:
                    items.append(pid); mapping[pid] = pid
            self.combo_items = items
            self.combo_map = mapping
            self.status.set("동기화 완료: 업체ID를 선택/등록하기 전에는 데이터를 표시하지 않습니다.")
        else:
            self.status.set("동기화 완료: place_id 컬럼이 없어 업체 선택 기능을 사용할 수 없습니다.")

        # 4) 엑셀 옆 라벨에 '제공: 시작 ~ 종료'만 표시(총량 감춤)
        s_txt = (res.start_date or "").strip() if res else ""
        e_txt = (res.end_date or "").strip() if res else ""
        if not (s_txt or e_txt) and "pub_date" in self.df_all.columns:
            try:
                p = pd.to_datetime(self.df_all["pub_date"], errors="coerce")
                if not p.isna().all():
                    s = p.min(); e = p.max()
                    s_txt = s.strftime("%Y-%m-%d"); e_txt = e.strftime("%Y-%m-%d")
            except Exception:
                pass
        self._provided_range = (s_txt, e_txt)
        self._update_range_label(s_txt, e_txt)  # count 없이 호출
        if s_txt or e_txt:
            self.status.set(f"동기화 완료: 기간 {s_txt} ~ {e_txt}")

        # 5) manifest 서명 저장(다음 비교용)
        self._last_sig = self._signature_of_manifest({
            "version": res.meta.get("version"),
            "schema": res.meta.get("schema"),
            "files": [{"name":"", "size": res.meta.get("total_size") or 0, "fileId": ""}]
        }) or self._last_sig
        self._save_settings()

    # ---------- 표 렌더/정렬/필터 ----------
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
            messagebox.showwarning("경고", "인식된 업체ID가 없습니다.", parent=self)
            return
        self.selected_ids = ids

        if self.df_all.empty or "place_id" not in self.df_all.columns:
            self._reset_combo()
            return

        df_ids = self.df_all[self.df_all["place_id"].astype(str).isin(ids)].copy()
        if "company_name" in df_ids.columns:
            items = ["전체(선택된)"]; mapping = {}
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
            # ID 없으면 접근 불가: 표시/엑셀 모두 비활성
            self.last_filtered = pd.DataFrame()
            self.render_table(self.last_filtered)
            self.status.set("조회: 업체ID 미지정 — 데이터를 표시하지 않습니다.")
            try:
                self.btn_export.configure(state="disabled")
            except Exception:
                pass
            # 라벨은 제공기간만 유지(건수 미표시)
            self._update_range_label(*self._provided_range)
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

        # 엑셀 활성화 + 라벨에 '… / N건' 추가
        try:
            self.btn_export.configure(state="normal")
        except Exception:
            pass
        self._update_range_label(*self._provided_range, count=len(df))

        range_txt = ""
        if sdt or edt:
            s_txt = sdt.strftime("%Y-%m-%d") if sdt else "…"
            e_txt = edt.strftime("%Y-%m-%d") if edt else "…"
            range_txt = f" / 기간 {s_txt} ~ {e_txt}"
        ids_txt = f" / 업체ID {', '.join(sorted(map(str, ids)))[:80]}..." if ids else " / 전체"
        self.status.set(f"조회 조건 적용{range_txt}{ids_txt}")

    # ---------- 엑셀 내보내기 ----------
    def export_excel(self):
        if self.last_filtered.empty:
            messagebox.showwarning("경고","저장할 조회 결과가 없습니다. 먼저 [조회하기]를 실행해 주세요.", parent=self)
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
        messagebox.showinfo("완료", f"엑셀 저장 완료:\n{os.path.basename(f)}", parent=self)

    # ---------- 링크 오버레이/오픈 ----------
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
