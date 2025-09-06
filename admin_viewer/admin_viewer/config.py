# -*- coding: utf-8 -*-
import os

APP_TITLE = "애드민 리포트 뷰어"
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".adminviewer_cache")
SETTINGS_PATH = os.path.join(CACHE_DIR, "settings.json")

HEADER_LABELS = {
    "No": "No",
    "place_id": "업체ID",
    "company_name": "업체명",
    "pub_date": "발행일",
    "title": "포스팅제목",
    "post_url": "포스팅URL",
}
DEFAULT_VIEW_COLS = ["place_id", "company_name", "pub_date", "title", "post_url"]
