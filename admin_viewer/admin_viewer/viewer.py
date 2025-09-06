import tkinter as tk
from tkinter import filedialog, ttk, simpledialog, messagebox
import pandas as pd
from admin_viewer.data_loader import load_from_drive

APP_TITLE = "애드민 리포트 뷰어"

class ViewerApp(tk.Tk):
    def __init__(self, version: str):
        super().__init__()
        self.version = version
        self.title(f"{APP_TITLE} v{version}")
        self.geometry("1200x800")
        self.df = None

        self._build_menu()

        # 검색창
        search_frame = tk.Frame(self)
        search_frame.pack(fill="x", padx=5, pady=5)
        tk.Label(search_frame, text="검색:").pack(side="left")
        self.search_var = tk.StringVar()
        search_entry = tk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side="left", fill="x", expand=True)
        tk.Button(search_frame, text="검색", command=self.apply_search).pack(side="left", padx=5)

        # Treeview
        self.tree = ttk.Treeview(self)
        self.tree.pack(expand=True, fill="both")

    def _build_menu(self):
        menubar = tk.Menu(self)

        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="파일 열기", command=self.open_file)
        filemenu.add_command(label="Google Drive 동기화", command=self.sync_from_drive)
        filemenu.add_command(label="Excel로 내보내기", command=self.export_excel)
        filemenu.add_separator()
        filemenu.add_command(label="종료", command=self.quit)
        menubar.add_cascade(label="파일", menu=filemenu)

        self.config(menu=menubar)

    def open_file(self):
        path = filedialog.askopenfilename(filetypes=[("Parquet", "*.parquet"), ("CSV", "*.csv"), ("Excel", "*.xlsx")])
        if not path: return
        if path.endswith(".parquet"):
            self.df = pd.read_parquet(path)
        elif path.endswith(".csv"):
            self.df = pd.read_csv(path)
        elif path.endswith(".xlsx"):
            self.df = pd.read_excel(path)
        self.show_dataframe(self.df)

    def sync_from_drive(self):
        file_id = simpledialog.askstring("API / 파일ID / 공유링크", "API URL 또는 manifest 파일 ID/공유링크를 입력하세요.")
        if not file_id:
            return
        try:
            self.df = load_from_drive(file_id)
            self.show_dataframe(self.df)
        except Exception as e:
            messagebox.showerror("에러", f"Drive 동기화 실패: {e}")

    def show_dataframe(self, df: pd.DataFrame):
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = list(df.columns)
        self.tree["show"] = "headings"
        for col in df.columns:
            self.tree.heading(col, text=col)
        for _, row in df.iterrows():
            self.tree.insert("", "end", values=list(row))

    def apply_search(self):
        if self.df is None: return
        keyword = self.search_var.get().strip()
        if keyword == "":
            self.show_dataframe(self.df)
            return
        filtered_df = self.df[self.df.apply(lambda r: r.astype(str).str.contains(keyword).any(), axis=1)]
        self.show_dataframe(filtered_df)

    def export_excel(self):
        if self.df is None:
            messagebox.showwarning("경고", "내보낼 데이터가 없습니다.")
            return
        save_path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")])
        if save_path:
            self.df.to_excel(save_path, index=False)
            messagebox.showinfo("완료", f"Excel 파일 저장됨:\n{save_path}")
