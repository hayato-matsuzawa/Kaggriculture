from __future__ import annotations

import benchmark_v21 as benchmark

# Keep the newest period completely outside model fitting.
benchmark.EPISODE_GROUPS = {
    key: value
    for key, value in benchmark.EPISODE_GROUPS.items()
    if key in ("public_v18_live", "mid_teacher_holdout")
}

if __name__ == "__main__":
    benchmark.main()
