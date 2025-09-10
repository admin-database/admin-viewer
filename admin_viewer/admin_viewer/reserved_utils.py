# -*- coding: utf-8 -*-
"""
예약발행 파싱 및 한국표준시(KST) 현재시각 유틸
- 외부 시간 소스: worldtimeapi.org → naver.com Date 헤더 → 로컬 KST fallback
- 예약 문자열 파서: '예약:YYYY년MM월DD일 HH시MM분/URL'
"""
from __future__ import annotations
import re
import requests
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Tuple, Optional

KST = ZoneInfo("Asia/Seoul")

RESERVE_RE = re.compile(
    r"""^예약:
        (?P<y>\d{4})년(?P<m>\d{2})월(?P<d>\d{2})일
        \s*(?P<h>\d{2})시(?P<min>\d{2})분
        /(?P<url>https?://\S+)$
    """,
    re.X
)

def get_kst_now() -> datetime:
    """
    한국표준시(KST) 기준 현재 시각 반환.
    1) worldtimeapi.org → 2) naver.com Date 헤더(UTC) → 3) 로컬시각 KST 변환
    """
    # 1) worldtimeapi.org
    try:
        r = requests.get("https://worldtimeapi.org/api/timezone/Asia/Seoul", timeout=5)
        r.raise_for_status()
        dt_str = (r.json() or {}).get("datetime")
        if dt_str:
            return datetime.fromisoformat(dt_str).astimezone(KST)
    except Exception:
        pass

    # 2) naver.com HTTP Date (UTC)
    try:
        r = requests.head("https://www.naver.com", timeout=5, allow_redirects=True)
        date_hdr = r.headers.get("Date")
        if date_hdr:
            # 예: Mon, 08 Sep 2025 01:23:45 GMT
            utc = datetime.strptime(date_hdr, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)
            return utc.astimezone(KST)
    except Exception:
        pass

    # 3) fallback: 로컬시각을 KST로
    return datetime.now(tz=KST)

def parse_reserved_info(cell: str) -> Tuple[Optional[datetime], Optional[str]]:
    """
    '예약:YYYY년MM월DD일 HH시MM분/URL' → (KST datetime, URL) 반환. 실패 시 (None, None).
    """
    if not cell:
        return None, None
    m = RESERVE_RE.match(str(cell).strip())
    if not m:
        return None, None
    try:
        y = int(m.group("y")); mth = int(m.group("m")); d = int(m.group("d"))
        h = int(m.group("h")); mi = int(m.group("min"))
        dt = datetime(y, mth, d, h, mi, tzinfo=KST)
        url = m.group("url")
        return dt, url
    except Exception:
        return None, None
