import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Keep tests local, deterministic, and free of external API calls.
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_commercial.db")
os.environ.pop("OPENAI_API_KEY", None)
os.environ.setdefault("EMAIL_ANALYZE_INBOUND", "false")
os.environ.setdefault("EMAIL_AUTO_REPLY", "false")
