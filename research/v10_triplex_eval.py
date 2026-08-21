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


def safe_call(fn: Callable[..., dict[str, Any]], obs: Any, configuration: Any) -> dict[str, Any]:
    try:
        try:
            out = fn(obs, configuration)
        except TypeError:
            out = fn(obs)
    except Exception:
        return copy.deepcopy(PASS)
    return copy.deepcopy(out) if isinstance(out, dict) else copy.deepcopy(PASS)


def normalize_farmer(action: dict[str, Any]) -> list[Any]:
    value = action.get("farmer", ["PASS"])
    return list(value) if isinstance(value, list) and value else ["PASS"]


def normalize_hands(action: dict[str, Any], obs: Any) -> list[list[Any]]:
    farms = list(bench.get_value(obs, "farms", []) or [])
    pid = int(bench.get_value(obs, "player", 0) or 0)
    hand_count = len((farms[pid] if pid < len(farms) else {}).get("hands", []) or [])
    source = action.get("hands", []) or []
    result: list[list[Any]] = []
    for i in range(hand_count):
        value = source[i] if i < len(source) else ["PASS"]
        result.append(list(value) if isinstance(value, list) and value else ["PASS"])
    return result


def normalize_market(action: dict[str, Any]) -> list[list[Any]]:
    source = action.get("market", []) or []
    return [list(x) for x in source[:10] if isinstance(x, list) and x]


def run_one(
    replay: dict[str, Any],
    candidate_seat: int,
    opponent_seat: int,
    paths: dict[str, Path],
    farmer_name: str,
    hands_name: str,
    market_name: str,
) -> dict[str, Any]:
    names = {farmer_name, hands_name, market_name}
    agents = {name: bench.load_candidate(paths[name]) for name in names}
    timing = {"max": 0.0, "sum": 0.0, "calls": 0.0}

    def composite(obs: Any, configuration: Any = None) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            proposals = {name: safe_call(fn, obs, configuration) for name, fn in agents.items()}
            return {
                "farmer": normalize_farmer(proposals[farmer_name]),
                "hands": normalize_hands(proposals[hands_name], obs),
                "market": normalize_market(proposals[market_name]),
            }
        finally:
            elapsed = time.perf_counter() - started
            timing["max"] = max(timing["max"], elapsed)
            timing["sum"] += elapsed
            timing["calls"] += 1.0

    opponent = bench.recorded_agent(replay, opponent_seat)
    lineup = [composite, opponent] if candidate_seat == 0 else [opponent, composite]
    rewards, statuses = bench.run_agents(replay, lineup)
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
    ap.add_argument("--unseen", type=Path, required=True)
    ap.add_argument("--cok", type=Path, required=True)
    ap.add_argument("--sota", type=Path, required=True)
    ap.add_argument("--farmer", required=True)
    ap.add_argument("--hands", required=True)
    ap.add_argument("--market", required=True)
    ap.add_argument("--groups", nargs="+", default=["newest_holdout"])
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    paths = {"unseen": args.unseen, "cok": args.cok, "sota": args.sota}

    rows = []
    for group in args.groups:
        for index, episode_id in enumerate(bench.EPISODE_GROUPS[group], 1):
            print(f"[{group}] {index}/{len(bench.EPISODE_GROUPS[group])} episode={episode_id}", flush=True)
            replay = bench.download_replay(episode_id, args.cache)
            opponent_seat = bench.choose_replaced_opponent(replay, group)
            for candidate_seat in (0, 1):
                row = run_one(replay, candidate_seat, opponent_seat, paths, args.farmer, args.hands, args.market)
                row.update({"group": group, "episode_id": episode_id, "farmer": args.farmer, "hands": args.hands, "market": args.market})
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
    result = {"farmer": args.farmer, "hands": args.hands, "market": args.market, "summary": summary, "rows": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
