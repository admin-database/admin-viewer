# -*- coding: utf-8 -*-
"""
프로세스 단일 실행 가드.
- 기본: 로컬 루프백 소켓 바인딩으로 중복 실행 차단 (크로스플랫폼)
- 이미 실행 중이면 False를 반환하므로, 호출 측에서 메시지 띄우고 종료하면 됨.
- PyInstaller EXE/소스 실행 모두 동작.
"""

from __future__ import annotations
import socket
import hashlib

class SingleInstance:
    def __init__(self, app_key: str = "admin_viewer"):
        # app_key 기반으로 고유 포트 산출(충돌 최소화)
        h = int(hashlib.sha1(app_key.encode("utf-8")).hexdigest(), 16)
        self._port = 30000 + (h % 20000)  # 30000~49999 범위
        self._sock = None

    def acquire(self) -> bool:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", self._port))
            s.listen(1)
            self._sock = s  # 소켓을 쥐고 있어야 락 유지
            return True
        except Exception:
            # 이미 다른 프로세스가 바인딩 중(=실행 중)
            return False

    def release(self) -> None:
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass
        finally:
            self._sock = None
