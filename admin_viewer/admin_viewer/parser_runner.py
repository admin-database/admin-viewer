# -*- coding: utf-8 -*-
from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

import pandas as pd
import requests

from .helpers import is_url
from .drive import drive_download_url, extract_drive_file_id
# NOTE: normalize_reservations 는 parse_all 내부에서 지연 임포트 (순환/패키징 이슈 회피)

# 콜백: done(bytes), total(bytes or -1), label(str)
ProgressCB = Callable[[int, int, str], None]


class ManifestError(Exception):
    pass


@dataclass
class ParseResult:
    df: pd.DataFrame
    start_date: Optional[str]
    end_date: Optional[str]
    meta: Dict


def _load_manifest_from_id(fid: str) -> Dict:
    r = requests.get(drive_download_url(fid), timeout=60)
    r.raise_for_status()
    return r.json()


def load_manifest(src: str) -> Dict:
    """
    src가 URL/공유링크/fileId/직접 API URL 모두 가능.
    files 배열을 포함하는 manifest dict를 반환.
    """
    if is_url(src):
        fid = extract_drive_file_id(src)
        if fid:
            return _load_manifest_from_id(fid)
        r = requests.get(src, timeout=60)
        r.raise_for_status()
        payload = r.json()
        if isinstance(payload, dict) and "files" in payload:
            return payload
        # nested에서 manifest id 찾기
        for key in ("manifest_file_id", "manifest_id", "file_id", "id"):
            v = payload.get(key)
            if isinstance(v, str) and v.strip():
                return _load_manifest_from_id(v.strip())
        data = payload.get("data", {})
        if isinstance(data, dict):
            for key in ("manifest_file_id", "manifest_id", "file_id", "id"):
                v = data.get(key)
                if isinstance(v, str) and v.strip():
                    return _load_manifest_from_id(v.strip())
        raise ManifestError("API 응답에서 manifest 파일 정보를 찾지 못했습니다.")
    else:
        # fileId로 간주
        return _load_manifest_from_id(src)


def _read_frame(path: str) -> pd.DataFrame:
    low = path.lower()
    if low.endswith(".parquet") or low.endswith(".parq"):
        return pd.read_parquet(path)
    if low.endswith(".csv"):
        try:
            return pd.read_csv(path)
        except UnicodeDecodeError:
            return pd.read_csv(path, encoding="cp949")
    # 확장자 모호 시 parquet 우선, 실패하면 csv
    try:
        return pd.read_parquet(path)
    except Exception:
        return pd.read_csv(path, encoding="utf-8", errors="ignore")


def parse_all(manifest_src: str, *, progress_cb: Optional[ProgressCB] = None) -> ParseResult:
    """
    매니페스트 로드 → 파일 다운로드 → 파싱 → 예약 정규화 → 결과 반환
    """
    manifest = load_manifest(manifest_src)
    if not isinstance(manifest, dict) or not manifest.get("files"):
        raise ManifestError("manifest에 files가 없습니다.")

    files = manifest["files"]
    # 총 용량(있으면 determinate)
    total = 0
    sizes_known = True
    for f in files:
        sz = int(f.get("size") or 0)
        if sz > 0:
            total += sz
        else:
            sizes_known = False
    if progress_cb:
        if sizes_known and total > 0:
            progress_cb(0, total, "다운로드 준비 중…")
        else:
            progress_cb(0, -1, "다운로드 준비 중…")

    # 다운로드 + 파싱
    frames: List[pd.DataFrame] = []
    downloaded = 0
    for idx, f in enumerate(files, start=1):
        fid = f.get("fileId"); name = f.get("name")
        if not fid or not name:
            continue

        url = drive_download_url(fid)
        with requests.get(url, stream=True, timeout=300) as r:
            r.raise_for_status()
            local_path = name  # 동일 이름으로 저장
            read = 0
            with open(local_path, "wb") as fp:
                for ch in r.iter_content(chunk_size=256 * 1024):
                    if not ch:
                        continue
                    fp.write(ch)
                    read += len(ch)
                    if progress_cb:
                        if sizes_known and total > 0:
                            progress_cb(downloaded + read, total, f"[{idx}/{len(files)}] {name} 다운로드 중…")
                        else:
                            progress_cb(downloaded + read, -1, f"[{idx}/{len(files)}] {name} 다운로드 중…")
            downloaded += read
            if progress_cb:
                label = f"[{idx}/{len(files)}] {name} 다운로드 완료"
                progress_cb(downloaded, total if sizes_known else -1, label)

        if progress_cb:
            progress_cb(downloaded, total if sizes_known else -1, f"[{idx}/{len(files)}] {name} 파싱 중…")
        frames.append(_read_frame(local_path))

    if not frames:
        raise ManifestError("가져온 데이터가 없습니다.")

    df = pd.concat(frames, ignore_index=True)

    # 날짜 표준화(있을 경우)
    if "pub_date" in df.columns:
        df["pub_date"] = pd.to_datetime(df["pub_date"], errors="coerce")

    # ★ 항상 정규화 적용 — 지연 임포트(패키징/순환 회피)
    try:
        from .schedule_utils import normalize_reservations  # noqa: WPS433 (local import)
    except Exception:
        # 혹시라도 로딩 실패 시, 정규화 없이 통과(최소 동작 보장)
        normalize_reservations = lambda x: x  # type: ignore
    df = normalize_reservations(df)

    vr = manifest.get("view_range", {})
    meta = {
        "version": manifest.get("version"),
        "schema": manifest.get("schema"),
        "file_count": len(files),
        "total_size": (total if sizes_known else None),
    }
    return ParseResult(df=df, start_date=vr.get("min_date"), end_date=vr.get("max_date"), meta=meta)
