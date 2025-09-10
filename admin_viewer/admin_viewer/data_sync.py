# -*- coding: utf-8 -*-
from __future__ import annotations
import json
from io import BytesIO
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd
import requests

from .helpers import is_url
from .drive import drive_download_url, extract_drive_file_id

ProgressCB = Callable[[int, int, str, str], None]  # done, total, label, note

def _load_manifest(raw: str) -> Dict:
    """raw가 URL/공유링크/fileId 모두일 수 있음. manifest(JSON) dict를 반환."""
    if is_url(raw):
        fid = extract_drive_file_id(raw)
        if fid:
            r = requests.get(drive_download_url(fid), timeout=60)
            r.raise_for_status()
            return r.json()
        else:
            r = requests.get(raw, timeout=60)
            r.raise_for_status()
            payload = r.json()
            if isinstance(payload, dict) and "files" in payload:
                return payload
            # nested에서 manifest id 뽑기
            for k in ("manifest_file_id","manifest_id","file_id","id"):
                v = payload.get(k)
                if isinstance(v, str) and v.strip():
                    rr = requests.get(drive_download_url(v.strip()), timeout=60)
                    rr.raise_for_status()
                    return rr.json()
            data = payload.get("data", {})
            if isinstance(data, dict):
                for k in ("manifest_file_id","manifest_id","file_id","id"):
                    v = data.get(k)
                    if isinstance(v, str) and v.strip():
                        rr = requests.get(drive_download_url(v.strip()), timeout=60)
                        rr.raise_for_status()
                        return rr.json()
            raise RuntimeError("API 응답에서 manifest 파일 정보를 찾지 못했습니다.")
    else:
        r = requests.get(drive_download_url(raw), timeout=60)
        r.raise_for_status()
        return r.json()

def _read_frame_from_local(path: str) -> pd.DataFrame:
    low = path.lower()
    if low.endswith(".parquet") or low.endswith(".parq"):
        return pd.read_parquet(path)
    if low.endswith(".csv"):
        try:
            return pd.read_csv(path)
        except UnicodeDecodeError:
            return pd.read_csv(path, encoding="cp949")
    # 확장자 없으면 parquet 우선, 실패 시 csv
    try:
        return pd.read_parquet(path)
    except Exception:
        return pd.read_csv(path, encoding="utf-8", errors="ignore")

def fetch_and_parse_manifest(
    raw: str,
    *,
    cache_dir: str,
    default_view_cols: List[str],
    progress_cb: Optional[ProgressCB] = None,
):
    """매니페스트를 읽고 파일들을 다운로드/파싱해 뷰에 맞춘 DF와 날짜 범위를 반환."""
    # 1) manifest
    if progress_cb: progress_cb(0, -1, "매니페스트 불러오는 중…", "")
    manifest = _load_manifest(raw)
    files = manifest.get("files", []) if isinstance(manifest, dict) else []
    if not files:
        raise RuntimeError("manifest에 files가 없습니다.")

    # 2) 총 용량
    total_size = 0
    sizes_known = True
    for f in files:
        sz = int(f.get("size") or 0)
        if sz > 0:
            total_size += sz
        else:
            sizes_known = False
    if progress_cb:
        if sizes_known and total_size > 0:
            progress_cb(0, total_size, "다운로드 준비 중…", "")
        else:
            progress_cb(0, -1, "다운로드 준비 중…", "파일 크기 정보가 없어 대략적인 진행만 표시됩니다.")

    # 3) 다운로드/파싱
    frames = []
    downloaded_acc = 0
    for idx, f in enumerate(files, start=1):
        fid = f.get("fileId"); name = f.get("name")
        if not fid or not name:
            continue

        url = drive_download_url(fid)
        with requests.get(url, stream=True, timeout=300) as r:
            r.raise_for_status()
            local_path = f"{cache_dir}/{name}"
            with open(local_path, "wb") as fp:
                read = 0
                for ch in r.iter_content(chunk_size=1024*256):
                    if not ch:
                        continue
                    fp.write(ch)
                    read += len(ch)
                    if progress_cb:
                        if sizes_known and total_size > 0:
                            progress_cb(downloaded_acc + read, total_size,
                                        f"[{idx}/{len(files)}] {name} 다운로드 중…",
                                        f"{(downloaded_acc+read)/1024/1024:.1f}MB / {total_size/1024/1024:.1f}MB")
                        else:
                            progress_cb(downloaded_acc + read, -1,
                                        f"[{idx}/{len(files)}] {name} 다운로드 중…",
                                        f"{read/1024/1024:.1f}MB 수신")
        downloaded_acc += read
        if progress_cb:
            if sizes_known and total_size > 0:
                progress_cb(downloaded_acc, total_size,
                            f"[{idx}/{len(files)}] {name} 다운로드 완료",
                            f"{downloaded_acc/1024/1024:.1f}MB / {total_size/1024/1024:.1f}MB")
            else:
                progress_cb(downloaded_acc, -1,
                            f"[{idx}/{len(files)}] {name} 다운로드 완료",
                            f"누적 {downloaded_acc/1024/1024:.1f}MB")

        if progress_cb: progress_cb(downloaded_acc, total_size if sizes_known else -1,
                                    f"[{idx}/{len(files)}] {name} 파싱 중…", "")
        frames.append(_read_frame_from_local(local_path))

    if not frames:
        raise RuntimeError("가져온 데이터가 없습니다.")

    df = pd.concat(frames, ignore_index=True)
    if "pub_date" in df.columns:
        df["pub_date"] = pd.to_datetime(df["pub_date"], errors="coerce")

    view_cols = [c for c in default_view_cols if c in df.columns]
    view_df = df[view_cols].copy() if view_cols else df.copy()

    vr = manifest.get("view_range", {}) if isinstance(manifest, dict) else {}
    return view_df, vr.get("min_date"), vr.get("max_date"), {
        "version": manifest.get("version"),
        "schema": manifest.get("schema"),
        "file_count": len(files),
        "total_size": (total_size if sizes_known else None)
    }
