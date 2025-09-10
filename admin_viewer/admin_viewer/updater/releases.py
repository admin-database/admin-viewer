# -*- coding: utf-8 -*-
from __future__ import annotations
import re, requests
from typing import Optional

from .logging_utils import ulog
from .config_bridge import GITHUB_USER, GITHUB_REPO  # 아래 파일 설명 참고

SEMVER_RE = re.compile(r"^\s*(\d+)\.(\d+)\.(\d+)\s*$")
ASSET_EXE_RE = re.compile(r".*\.exe$", re.I)

def parse_semver(s: str) -> Optional[tuple[int,int,int]]:
    m = SEMVER_RE.match(s or "")
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))

def extract_version_from_asset_name(name: str) -> Optional[str]:
    nums = re.findall(r"(\d+\.\d+\.\d+)", name or "")
    for n in nums:
        if parse_semver(n):
            return n
    return None

def fetch_releases(timeout: int = 10) -> list[dict]:
    ulog("릴리스 목록 조회 시도")
    url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/releases"
    r = requests.get(url, timeout=timeout, headers={"User-Agent":"admin-viewer-updater/1.0"})
    r.raise_for_status()
    items = r.json() or []
    ulog(f"릴리스 {len(items)}개 불러옴")
    return items

def pick_best_release(items: list[dict]) -> Optional[dict]:
    candidates: list[tuple[str, dict]] = []
    for rel in items:
        if rel.get("draft") or rel.get("prerelease"):
            continue
        tag = (rel.get("tag_name") or "").strip()
        tag_ver = tag.lstrip("vV") if parse_semver(tag.lstrip("vV")) else None

        assets = rel.get("assets") or []
        asset_ver = None
        for a in assets:
            ver = extract_version_from_asset_name(a.get("name", ""))
            if ver:
                asset_ver = ver
                break

        ver = asset_ver or tag_ver
        if ver and parse_semver(ver):
            candidates.append((ver, rel))

    if not candidates:
        ulog("선택 가능한 릴리스가 없음 (draft/prerelease 필터링 또는 버전 파싱 실패)")
        return None

    candidates.sort(key=lambda x: parse_semver(x[0]), reverse=True)
    best = candidates[0][1]
    ulog(f"최신 릴리스 선정: tag={best.get('tag_name')}, name={best.get('name')}")
    return best
