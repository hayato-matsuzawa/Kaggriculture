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


def get_step(obs: Any) -> int:
    raw = bench.get_value(obs, "step", None)
    if raw is not None:
        return int(raw or 0)
    return int(bench.get_value(obs, "day", 0) or 0) * 24 + int(bench.get_value(obs, "hour", 0) or 0)


def load_fixed_route(path: Path, label: str, decision_step: int) -> Callable[..., dict[str, Any]]:
    namespace: dict[str, Any] = {}
    source = path.read_text(encoding="utf-8")
    exec(compile(source, str(path), "exec"), namespace)
    base_selector = namespace.get("_v7_route_label")
    if not callable(base_selector):
        raise RuntimeError("COK route selector not found")

    def selector(obs: Any) -> str:
        if get_step(obs) < decision_step:
            return str(base_selector(obs))
        return label

    namespace["_v7_route_label"] = selector
    agent = namespace.get("agent")
    if not callable(agent):
        raise RuntimeError("agent not found")
    return agent


def safe_call(fn: Callable[..., dict[str, Any]], obs: Any, configuration: Any) -> dict[str, Any]:
    try:
        try:
            out = fn(obs, configuration)
        except TypeError:
            out = fn(obs)
    except Exception:
        return copy.deepcopy(PASS)
    return copy.deepcopy(out) if isinstance(out, dict) else copy.deepcopy(PASS)


def run_one(replay: dict[str, Any], candidate_seat: int, opponent_seat: int, path: Path, label: str, decision_step: int) -> dict[str, Any]:
    candidate = load_fixed_route(path, label, decision_step)
    timing = {"max": 0.0, "sum": 0.0, "calls": 0.0}

    def timed(obs: Any, configuration: Any = None) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            return safe_call(candidate, obs, configuration)
        finally:
            elapsed = time.perf_counter() - started
            timing["max"] = max(timing["max"], elapsed)
            timing["sum"] += elapsed
            timing["calls"] += 1.0

    opponent = bench.recorded_agent(replay, opponent_seat)
    agents = [timed, opponent] if candidate_seat == 0 else [opponent, timed]
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
    ap.add_argument("--candidate", type=Path, required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--decision-step", type=int, default=72)
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
                row = run_one(replay, candidate_seat, opponent_seat, args.candidate, args.label, args.decision_step)
                row.update({"group": group, "episode_id": episode_id, "label": args.label, "decision_step": args.decision_step})
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
    result = {"label": args.label, "decision_step": args.decision_step, "summary": summary, "rows": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
