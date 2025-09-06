# -*- coding: utf-8 -*-
import re

def drive_download_url(file_id: str) -> str:
    return f"https://drive.google.com/uc?export=download&id={file_id}"

def extract_drive_file_id(s: str) -> str | None:
    if not s:
        return None
    m = re.search(r"/file/d/([A-Za-z0-9_-]+)", s)
    if m: return m.group(1)
    m = re.search(r"[?&]id=([A-Za-z0-9_-]+)", s)
    if m: return m.group(1)
    return None
