from __future__ import annotations

import argparse
import copy
import json
import statistics
import time
from pathlib import Path
from typing import Any, Callable

import benchmark_v21 as bench

PASS = {"farmer": ["PASS"], "hands": [], "market": []}


def call(fn: Callable[..., dict[str, Any]], obs: Any, configuration: Any) -> dict[str, Any]:
    try:
        try:
            out = fn(obs, configuration)
        except TypeError:
            out = fn(obs)
    except Exception:
        return copy.deepcopy(PASS)
    return copy.deepcopy(out) if isinstance(out, dict) else copy.deepcopy(PASS)


def normalize_workers(action: dict[str, Any], obs: Any) -> tuple[list[Any], list[list[Any]]]:
    farmer = action.get("farmer", ["PASS"])
    if not isinstance(farmer, list) or not farmer:
        farmer = ["PASS"]
    farms = list(bench.get_value(obs, "farms", []) or [])
    pid = int(bench.get_value(obs, "player", 0) or 0)
    hand_count = len((farms[pid] if pid < len(farms) else {}).get("hands", []) or [])
    source = action.get("hands", []) or []
    hands: list[list[Any]] = []
    for i in range(hand_count):
        value = source[i] if i < len(source) else ["PASS"]
        hands.append(value if isinstance(value, list) and value else ["PASS"])
    return farmer, hands


def normalize_market(action: dict[str, Any]) -> list[list[Any]]:
    orders = action.get("market", []) or []
    return [list(x) for x in orders[:10] if isinstance(x, list) and x]


def run_one(
    replay: dict[str, Any],
    candidate_seat: int,
    opponent_seat: int,
    worker_path: Path,
    market_path: Path,
) -> dict[str, Any]:
    worker = bench.load_candidate(worker_path)
    market = worker if worker_path.resolve() == market_path.resolve() else bench.load_candidate(market_path)
    timing = {"max": 0.0, "sum": 0.0, "calls": 0.0}

    def composite(obs: Any, configuration: Any = None) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            wa = call(worker, obs, configuration)
            ma = wa if market is worker else call(market, obs, configuration)
            farmer, hands = normalize_workers(wa, obs)
            return {"farmer": farmer, "hands": hands, "market": normalize_market(ma)}
        finally:
            elapsed = time.perf_counter() - started
            timing["max"] = max(timing["max"], elapsed)
            timing["sum"] += elapsed
            timing["calls"] += 1.0

    opponent = bench.recorded_agent(replay, opponent_seat)
    agents = [composite, opponent] if candidate_seat == 0 else [opponent, composite]
    rewards, statuses = bench.run_agents(replay, agents)
    cr, other = rewards[candidate_seat], rewards[1 - candidate_seat]
    valid = statuses == ["DONE", "DONE"] and cr is not None and other is not None
    return {
        "candidate_seat": candidate_seat,
        "opponent_recorded_seat": opponent_seat,
        "candidate_reward": cr,
        "opponent_reward": other,
        "margin": None if not valid else float(cr) - float(other),
        "win": bool(valid and float(cr) > float(other)),
        "valid": valid,
        "statuses": statuses,
        "max_call_ms": 1000.0 * timing["max"],
        "mean_call_ms": 1000.0 * timing["sum"] / max(1.0, timing["calls"]),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", type=Path, required=True)
    ap.add_argument("--market", type=Path, required=True)
    ap.add_argument("--worker-name", required=True)
    ap.add_argument("--market-name", required=True)
    ap.add_argument("--groups", nargs="+", default=["newest_holdout"])
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    rows = []
    for group in args.groups:
        for index, episode_id in enumerate(bench.EPISODE_GROUPS[group], 1):
            print(f"[{group}] {index}/{len(bench.EPISODE_GROUPS[group])} episode={episode_id}", flush=True)
            replay = bench.download_replay(episode_id, args.cache)
            opponent_seat = bench.choose_replaced_opponent(replay, group)
            for candidate_seat in (0, 1):
                row = run_one(replay, candidate_seat, opponent_seat, args.worker, args.market)
                row.update({
                    "group": group,
                    "episode_id": episode_id,
                    "worker": args.worker_name,
                    "market": args.market_name,
                })
                rows.append(row)

    summary = {}
    for group in args.groups:
        selected = [r for r in rows if r["group"] == group and r["valid"]]
        margins = [float(r["margin"]) for r in selected]
        summary[group] = {
            "wins": sum(bool(r["win"]) for r in selected),
            "valid": len(selected),
            "win_rate": sum(bool(r["win"]) for r in selected) / max(1, len(selected)),
            "mean_margin": statistics.mean(margins) if margins else None,
            "min_margin": min(margins) if margins else None,
            "max_call_ms": max((float(r["max_call_ms"]) for r in selected), default=0.0),
        }
    result = {
        "worker": args.worker_name,
        "market": args.market_name,
        "summary": summary,
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
