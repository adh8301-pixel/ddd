"""Vercel 서버리스 함수 진입점. 모든 요청을 Flask 앱으로 넘긴다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402

app = create_app()
