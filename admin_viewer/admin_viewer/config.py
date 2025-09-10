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

# ===== GitHub Releases 기반 자동 업데이트 설정 =====
# 리포지토리: https://github.com/admin-database/admin-viewer
GITHUB_USER = "admin-database"
GITHUB_REPO = "admin-viewer"

# 릴리스 자산 파일명 규칙 (예: admin_viewer_v1.2.3.exe)
RELEASE_EXE_PREFIX = "admin_viewer_v"
RELEASE_EXE_SUFFIX = ".exe"

# 프리릴리스(베타/RC)까지 포함할지 여부
INCLUDE_PRERELEASE = False
