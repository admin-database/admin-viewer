import requests
import os, sys, subprocess
import tkinter as tk
from tkinter import messagebox
from admin_viewer.__version__ import __version__

# GitHub main 브랜치에 올려둔 latest_version.json URL
LATEST_VERSION_URL = "https://raw.githubusercontent.com/<username>/<repo>/main/latest_version.json"

def check_update(root: tk.Tk):
    try:
        resp = requests.get(LATEST_VERSION_URL, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        latest = data.get("version")
        url = data.get("download_url")

        if latest and url and latest > __version__:
            if messagebox.askyesno("업데이트", f"새 버전 {latest}이 있습니다. 다운로드할까요?"):
                download_and_run(root, url, latest)
    except Exception as e:
        print(f"[ERROR] 업데이트 확인 실패: {e}")

def download_and_run(root, url, latest):
    out_name = f"admin_viewer_v{latest}.exe"
    out_path = os.path.join(os.getcwd(), out_name)

    r = requests.get(url, stream=True)
    r.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)

    messagebox.showinfo("완료", f"새 버전 {latest} 다운로드 완료!\n곧 새 버전을 실행합니다.")
    subprocess.Popen([out_path], shell=True)
    root.quit()
    sys.exit(0)
