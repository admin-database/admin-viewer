# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Dict, List, Any, Optional
from datetime import datetime
from zoneinfo import ZoneInfo
import re
import pandas as pd

# ---- KST 고정 ----
KST = ZoneInfo("Asia/Seoul")

# 컬럼 별칭 매핑(예시)
ALIAS_MAP: Dict[str, str] = {
    "id": "reservation_id",
    "예약ID": "reservation_id",
    "예약Id": "reservation_id",
    "start": "start_time",
    "시작": "start_time",
    "end": "end_time",
    "종료": "end_time",
    "title": "title",
    "제목": "title",
    "desc": "description",
    "설명": "description",
    "room": "location",
    "장소": "location",
    "target": "target",
    "대상": "target",
    "status": "status",
    "상태": "status",
}

STD_COLS: List[str] = [
    "reservation_id",
    "start_time",
    "end_time",
    "title",
    "description",
    "location",
    "target",
    "status",
]

# 예약 문자열: 예) 예약:2025년09월07일 15시00분/https://...
_RESERV_RE = re.compile(
    r"^예약:(\d{4})년(\d{2})월(\d{2})일\s+(\d{2})시(\d{2})분/(https?://\S+)$"
)


def _rename_with_aliases(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    new_names = {}
    std_cols = set(df.columns)
    for src, dst in ALIAS_MAP.items():
        if src in df.columns and dst not in std_cols:
            new_names[src] = dst
            std_cols.add(dst)
    if new_names:
        df = df.rename(columns=new_names)
    return df


def _ensure_std_columns(df: pd.DataFrame) -> pd.DataFrame:
    for c in STD_COLS:
        if c not in df.columns:
            df[c] = None
    ordered = [c for c in STD_COLS if c in df.columns] + [c for c in df.columns if c not in STD_COLS]
    return df[ordered]


def _sanitize(df: pd.DataFrame) -> pd.DataFrame:
    if "title" in df.columns:
        df["title"] = df["title"].astype(str).str.strip()
    if "description" in df.columns:
        df["description"] = df["description"].astype(str).str.strip()
    if "status" in df.columns:
        df["status"] = df["status"].fillna("").astype(str)
    return df


def _transform_reserved_cell(val: object) -> object:
    """
    '예약:YYYY년MM월DD일 HH시MM분/URL' -> (KST now >= 예약시각)이면 'URL' 로 치환
    """
    if not isinstance(val, str):
        return val
    m = _RESERV_RE.match(val.strip())
    if not m:
        return val
    y, mo, d, hh, mm, url = m.groups()
    try:
        ts = datetime(int(y), int(mo), int(d), int(hh), int(mm), tzinfo=KST)
    except Exception:
        return val
    now_kst = datetime.now(KST)
    return url if now_kst >= ts else val


def normalize_reservations(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    # 기본 정규화
    df = _rename_with_aliases(df)
    df = _ensure_std_columns(df)
    df = _sanitize(df)

    # 모든 object 컬럼을 훑으며 예약 문자열을 URL로 치환
    for col in df.columns:
        if pd.api.types.is_object_dtype(df[col]):
            df[col] = df[col].map(_transform_reserved_cell)

    # reservation_id 보완
    if "reservation_id" in df.columns and df["reservation_id"].isna().all():
        df["reservation_id"] = [f"r{idx:06d}" for idx in range(len(df))]

    return df


# (선택) 매니페스트 선검증이 필요한 UI 코드에서 사용
def load_manifest_if_needed(manifest_src: str) -> Optional[Dict[str, Any]]:
    try:
        from .parser_runner import load_manifest  # local import (순환 방지)
    except Exception:
        return None
    try:
        return load_manifest(manifest_src)
    except Exception:
        return None
