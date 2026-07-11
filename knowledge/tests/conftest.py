"""테스트 부트스트랩 — rootdir 가 knowledge/ 라도 `rag`·`core`·`schemas` 를 import 하도록
knowledge 디렉터리를 sys.path 에 넣는다.
"""
import sys
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent
if str(KNOWLEDGE_DIR) not in sys.path:
    sys.path.insert(0, str(KNOWLEDGE_DIR))
