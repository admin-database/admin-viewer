# -*- coding: utf-8 -*-
from __future__ import annotations
import time, requests
from pathlib import Path
from typing import Callable

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .logging_utils import ulog

def _make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=5, read=5, connect=5,
        backoff_factor=0.8,
        status_forcelist=[429, 500, 502, 503, 504],
        raise_on_status=False,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update({"User-Agent": "admin-viewer-updater/1.0"})
    return s

def download_resumable(
    url: str,
    dst: Path,
    timeout: int = 120,
    progress_cb: Callable[[float, int, int], None] | None = None,  # (frac, read, total)
    on_indeterminate: Callable[[], None] | None = None,
    tries: int = 3,
) -> None:
    """
    Resumable download:
    - .part 임시 파일 사용
    - Range 이어받기
    - 416/401/403/404/5xx 대응
    """
    tmp = dst.with_suffix(dst.suffix + ".part")
    sess = _make_session()
    last_err = None

    def existing_size() -> int:
        try:
            return tmp.stat().st_size if tmp.exists() else 0
        except Exception:
            return 0

    def probe_head() -> tuple[int|None, str|None]:
        try:
            r = sess.head(url, allow_redirects=True, timeout=timeout)
            total = int(r.headers.get("Content-Length") or 0) or None
            etag = r.headers.get("ETag")
            return total, etag
        except Exception:
            return None, None

    total_remote, etag = probe_head()

    for attempt in range(1, tries + 1):
        try:
            start = existing_size()
            headers = {"Accept": "application/octet-stream"}
            if start > 0:
                if etag:
                    headers["If-Range"] = etag
                headers["Range"] = f"bytes={start}-"
                ulog(f"[다운로드] 이어받기 시도 (start={start})")

            with sess.get(url, headers=headers, stream=True, allow_redirects=True, timeout=timeout) as r:
                status = r.status_code
                ulog(f"[다운로드] 응답 코드: {status}, 최종 URL: {r.url}")

                if status == 416:
                    ulog("[다운로드] 416 → 부분 파일 삭제 후 재시작")
                    try:
                        if tmp.exists(): tmp.unlink()
                    except Exception:
                        pass
                    raise RuntimeError("HTTP 416")

                if status in (401, 403, 404):
                    raise RuntimeError(f"HTTP {status}")

                r.raise_for_status()

                try:
                    cl = int(r.headers.get("Content-Length") or 0)
                except Exception:
                    cl = 0

                if total_remote:
                    total = total_remote
                else:
                    total = (start + cl) if (status == 206 and cl > 0) else (cl or None)

                if total is None and on_indeterminate:
                    on_indeterminate()

                mode = "ab" if (status == 206 and start > 0) else "wb"
                read = start
                chunk = 1024 * 256
                last_log = time.time()
                t0 = time.time()

                with open(tmp, mode) as f:
                    for ch in r.iter_content(chunk_size=chunk):
                        if not ch:
                            continue
                        f.write(ch)
                        read += len(ch)

                        now = time.time()
                        if now - last_log >= 1.0:
                            if total and total > 0:
                                frac = read / total
                                if progress_cb: progress_cb(frac, read, total)
                                ulog(f"[다운로드] 진행 {read}/{total} bytes ({frac*100:.1f}%)")
                            else:
                                if progress_cb: progress_cb(0.0, read, 0)
                                ulog(f"[다운로드] 진행 {read} bytes (총 크기 미상)")
                            last_log = now

                if total and read < total:
                    raise RuntimeError(f"Incomplete download: {read}/{total}")

                try:
                    if dst.exists(): dst.unlink()
                except Exception:
                    pass
                tmp.rename(dst)
                ulog(f"[다운로드] 완료: {dst} (총 {read} bytes, 경과 {time.time()-t0:.1f}s)")
                return

        except Exception as e:
            last_err = e
            ulog(f"[다운로드] 실패(시도 {attempt}/{tries}): {e}")
            time.sleep(min(5, 1 + attempt))

    raise last_err or RuntimeError("다운로드 실패 (모든 재시도 소진)")
