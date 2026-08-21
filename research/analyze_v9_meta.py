from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import requests

EPISODES = [
    94310456, 94355263, 94437841, 94439800, 94450041, 94450953,
    94458225, 94478362, 94568538, 94617605, 94636231, 94711805,
    94726918,
]
CANDIDATES = ["unseen_current", "cok", "sota_claude"]
HORIZONS = [1, 2, 3, 6, 12, 24, 48, 72]


def download_replay(ep: int, cache: Path) -> dict[str, Any]:
    cache.mkdir(parents=True, exist_ok=True)
    p = cache / f"{ep}.json"
    if not p.exists():
        u = f"https://www.kaggle.com/competitions/episodes/{ep}/replay.json"
        r = requests.get(u, timeout=90)
        r.raise_for_status()
        p.write_text(json.dumps(r.json()), encoding="utf-8")
    return json.loads(p.read_text(encoding="utf-8"))


def candidate_rows(root: Path) -> dict[tuple[int, int, str], dict[str, Any]]:
    out: dict[tuple[int, int, str], dict[str, Any]] = {}
    for cand in CANDIDATES:
        paths = list((root / cand).rglob("newest.json"))
        if len(paths) != 1:
            raise RuntimeError(f"{cand}: newest.json count={len(paths)}")
        data = json.loads(paths[0].read_text(encoding="utf-8"))
        rows = data["results"]["newest_holdout"]["replaced_team_opponent"]
        for row in rows:
            key = (int(row["episode_id"]), int(row["candidate_seat"]), cand)
            out[key] = row
    return out


def tile_signature(tile: Any) -> tuple[Any, ...]:
    if tile is None:
        return ("EMPTY",)
    if tile == "LOCKED":
        return ("LOCKED",)
    if not isinstance(tile, dict):
        return (str(tile),)
    return (
        tile.get("kind"), tile.get("crop"), tile.get("animal"),
        bool(tile.get("watered_today", False)),
        bool(tile.get("fed_today", False)),
        bool(tile.get("cared_today", False)),
        int(tile.get("yield_units", 0) or 0),
    )


def public_fingerprint(replay: dict[str, Any], recorded_opp_seat: int, horizon: int) -> tuple[Any, ...]:
    idx = min(horizon, len(replay["steps"]) - 1)
    obs = replay["steps"][idx][recorded_opp_seat]["observation"]
    farm = obs["farms"][recorded_opp_seat]
    tiles = farm.get("tiles") or []
    counts = Counter(tile_signature(t) for row in tiles for t in row)
    positions = [tuple(farm.get("farmer") or (-1, -1))]
    positions.extend(sorted(tuple(x) for x in (farm.get("hands") or [])))
    compact_counts = tuple(sorted((repr(k), int(v)) for k, v in counts.items() if k != ("LOCKED",)))
    return (
        round(float(farm.get("money", 0.0)), 3),
        len(farm.get("hands") or []),
        tuple(sorted(farm.get("unlocked_quadrants") or [])),
        tuple(positions),
        compact_counts,
        tuple(obs.get("town", {}).get("unlocked_shops") or []),
    )


def dist(a: tuple[Any, ...], b: tuple[Any, ...]) -> float:
    # Intentionally coarse/public: economy, labour, land, layout, shops.
    score = abs(float(a[0]) - float(b[0])) / 500.0
    score += 2.0 * abs(int(a[1]) - int(b[1]))
    score += 3.0 * (a[2] != b[2])
    score += 0.25 * abs(len(a[3]) - len(b[3]))
    score += 1.5 * (a[4] != b[4])
    score += 4.0 * (a[5] != b[5])
    return score


def choose_label(rows: dict[tuple[int, int, str], dict[str, Any]], ep: int, seat: int) -> str:
    return max(
        CANDIDATES,
        key=lambda c: (
            bool(rows[(ep, seat, c)]["win"]),
            float(rows[(ep, seat, c)]["margin"]),
        ),
    )


def score_choices(rows: dict[tuple[int, int, str], dict[str, Any]], choices: dict[tuple[int, int], str]) -> dict[str, Any]:
    selected = [rows[(ep, seat, choices[(ep, seat)])] for ep in EPISODES for seat in (0, 1)]
    wins = sum(bool(r["win"]) for r in selected)
    margins = [float(r["margin"]) for r in selected]
    return {
        "wins": wins,
        "n": len(selected),
        "win_rate": wins / len(selected),
        "mean_margin": statistics.mean(margins),
        "min_margin": min(margins),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact-root", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=Path("artifacts/meta-replays"))
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    rows = candidate_rows(args.artifact_root)
    replays = {ep: download_replay(ep, args.cache) for ep in EPISODES}
    recorded_opp = {}
    for ep, replay in replays.items():
        names = list(replay["info"].get("TeamNames") or [])
        target = names.index("Matsu") if names.count("Matsu") == 1 else names.index("tetsuya")
        recorded_opp[ep] = 1 - target

    single = {}
    for c in CANDIDATES:
        single[c] = score_choices(rows, {(ep, s): c for ep in EPISODES for s in (0, 1)})

    oracle_choices = {(ep, s): choose_label(rows, ep, s) for ep in EPISODES for s in (0, 1)}
    oracle = score_choices(rows, oracle_choices)

    horizon_reports = {}
    for h in HORIZONS:
        fps = {ep: public_fingerprint(replays[ep], recorded_opp[ep], h) for ep in EPISODES}
        # Leave-one-episode-out nearest public opening; seat is respected.
        choices = {}
        for ep in EPISODES:
            for seat in (0, 1):
                train = [x for x in EPISODES if x != ep]
                nearest = min(train, key=lambda x: (dist(fps[ep], fps[x]), abs(x - ep)))
                choices[(ep, seat)] = choose_label(rows, nearest, seat)
        loo = score_choices(rows, choices)

        # Exact public-state bucket majority, reported only as an upper diagnostic.
        buckets = defaultdict(list)
        for ep in EPISODES:
            buckets[fps[ep]].append(ep)
        collision_count = sum(len(v) > 1 for v in buckets.values())
        horizon_reports[str(h)] = {
            "loo_nearest": loo,
            "unique_fingerprints": len(buckets),
            "collision_buckets": collision_count,
            "choices": {f"{ep}:{s}": choices[(ep, s)] for ep in EPISODES for s in (0, 1)},
        }

    matrix = []
    for ep in EPISODES:
        for seat in (0, 1):
            matrix.append({
                "episode": ep,
                "seat": seat,
                "best": oracle_choices[(ep, seat)],
                "candidates": {
                    c: {
                        "win": bool(rows[(ep, seat,c)]["win"]),
                        "margin": float(rows[(ep,seat,c)]["margin"]),
                    }
                    for c in CANDIDATES
                },
            })

    report = {
        "single": single,
        "oracle": oracle,
        "oracle_choices": {f"{ep}:{s}": oracle_choices[(ep, s)] for ep in EPISODES for s in (0, 1)},
        "horizons": horizon_reports,
        "matrix": matrix,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
