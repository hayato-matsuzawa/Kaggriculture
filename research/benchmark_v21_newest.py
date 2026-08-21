from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchmark_v21 as benchmark

benchmark.EPISODE_GROUPS = {
    "newest_holdout": [
        94310456, 94355263, 94437841, 94439800, 94450041, 94450953,
        94458225, 94478362, 94568538, 94617605, 94636231, 94711805,
        94726918,
    ]
}

if __name__ == "__main__":
    benchmark.main()
