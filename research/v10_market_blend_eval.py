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
PRODUCTS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER")


def get_step(obs: Any) -> int:
    raw = bench.get_value(obs, "step", None)
    if raw is not None:
        return int(raw or 0)
    return int(bench.get_value(obs, "day", 0) or 0) * 24 + int(bench.get_value(obs, "hour", 0) or 0)


def safe_call(fn: Callable[..., dict[str, Any]], obs: Any, configuration: Any) -> dict[str, Any]:
    try:
        try:
            out = fn(obs, configuration)
        except TypeError:
            out = fn(obs)
    except Exception:
        return copy.deepcopy(PASS)
    return copy.deepcopy(out) if isinstance(out, dict) else copy.deepcopy(PASS)


def order_qty(order: Any) -> int:
    try:
        return max(0, int(order[2]))
    except Exception:
        return 0


def sell_map(action: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for order in action.get("market", []) or []:
        if isinstance(order, list) and len(order) >= 3 and order[0] == "SELL" and order[1] in PRODUCTS:
            out[order[1]] = out.get(order[1], 0) + order_qty(order)
    return out


def compose_market(obs: Any, base: dict[str, Any], overlay: dict[str, Any], mode: str) -> list[list[Any]]:
    base_orders = [list(x) for x in (base.get("market", []) or []) if isinstance(x, list) and x]
    non_sell = [x for x in base_orders if not (len(x) >= 1 and x[0] == "SELL")]
    base_sells, overlay_sells = sell_map(base), sell_map(overlay)
    quantities: dict[str, int] = {}
    for item in PRODUCTS:
        if mode == "replace":
            qty = overlay_sells.get(item, 0)
        elif mode == "max":
            qty = max(base_sells.get(item, 0), overlay_sells.get(item, 0))
        elif mode == "min_positive":
            values = [x for x in (base_sells.get(item, 0), overlay_sells.get(item, 0)) if x > 0]
            qty = min(values) if values else 0
        else:
            qty = base_sells.get(item, 0)
        if qty > 0:
            quantities[item] = qty

    private = bench.get_value(obs, "private", {}) or {}
    shed = bench.get_value(private, "shed", {}) or {}
    prices = bench.get_value(bench.get_value(obs, "market", {}) or {}, "prices", {}) or {}
    sells = []
    for item, qty in quantities.items():
        try:
            available = max(0, int(bench.get_value(shed, item, 0) or 0))
        except Exception:
            available = 0
        qty = min(qty, available)
        if qty > 0:
            sells.append(["SELL", item, qty])
    sells.sort(key=lambda x: float(bench.get_value(prices, x[1], 0) or 0) * int(x[2]), reverse=True)
    return (non_sell + sells)[:10]


def run_one(replay: dict[str, Any], candidate_seat: int, opponent_seat: int, base_path: Path, overlay_path: Path, mode: str, decision_step: int) -> dict[str, Any]:
    base = bench.load_candidate(base_path)
    overlay = bench.load_candidate(overlay_path)
    timing = {"max": 0.0, "sum": 0.0, "calls": 0.0}

    def candidate(obs: Any, configuration: Any = None) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            base_action = safe_call(base, obs, configuration)
            overlay_action = safe_call(overlay, obs, configuration)
            if get_step(obs) < decision_step:
                return base_action
            return {
                "farmer": list(base_action.get("farmer") or ["PASS"]),
                "hands": [list(x or ["PASS"]) for x in (base_action.get("hands") or [])],
                "market": compose_market(obs, base_action, overlay_action, mode),
            }
        finally:
            elapsed = time.perf_counter() - started
            timing["max"] = max(timing["max"], elapsed)
            timing["sum"] += elapsed
            timing["calls"] += 1.0

    opponent = bench.recorded_agent(replay, opponent_seat)
    agents = [candidate, opponent] if candidate_seat == 0 else [opponent, candidate]
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
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--overlay", type=Path, required=True)
    ap.add_argument("--base-name", required=True)
    ap.add_argument("--overlay-name", required=True)
    ap.add_argument("--mode", choices=["replace", "max", "min_positive"], required=True)
    ap.add_argument("--decision-step", type=int, required=True)
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
                row = run_one(replay, candidate_seat, opponent_seat, args.base, args.overlay, args.mode, args.decision_step)
                row.update({"group": group, "episode_id": episode_id})
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
    result = {"base":args.base_name,"overlay":args.overlay_name,"mode":args.mode,"decision_step":args.decision_step,"summary":summary,"rows":rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
