from __future__ import annotations

import argparse
import copy
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import benchmark_v21 as bench

PASS = {"farmer": ["PASS"], "hands": [], "market": []}
ITEMS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER")
CROPS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON")
ANIMALS = ("GOOSE", "COW", "SHEEP")
SHOPS = ("BAKERY", "PIZZA_SHOP", "BRUNCH_SPOT", "YARN_STORE", "ICE_CREAM_SHOP", "PET_CAFE", "SMOOTHIE_SHOP", "FARMERS_MARKET")


def call_agent(fn: Callable[..., dict[str, Any]], obs: Any, configuration: Any) -> dict[str, Any]:
    try:
        out = fn(obs, configuration)
    except TypeError:
        out = fn(obs)
    return copy.deepcopy(out if isinstance(out, dict) else PASS)


def numeric_map(obj: Any) -> dict[str, float]:
    if not isinstance(obj, dict):
        return {}
    result = {}
    for key, value in obj.items():
        try:
            result[str(key)] = float(value or 0)
        except Exception:
            result[str(key)] = 0.0
    return result


def farm_features(prefix: str, farm: Any, out: dict[str, float]) -> None:
    farm = farm if isinstance(farm, dict) else {}
    out[f"{prefix}.money"] = float(farm.get("money", 0) or 0)
    out[f"{prefix}.hands"] = float(len(farm.get("hands", []) or []))
    out[f"{prefix}.hires_today"] = float(farm.get("hires_today", 0) or 0)
    out[f"{prefix}.lands"] = float(len(farm.get("unlocked_quadrants", []) or []))
    positions = [farm.get("farmer")] + list(farm.get("hands", []) or [])
    xs, ys = [], []
    for p in positions:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            xs.append(float(p[0])); ys.append(float(p[1]))
    out[f"{prefix}.pos_x_mean"] = sum(xs) / max(1, len(xs))
    out[f"{prefix}.pos_y_mean"] = sum(ys) / max(1, len(ys))
    out[f"{prefix}.pos_x_span"] = (max(xs) - min(xs)) if xs else 0.0
    out[f"{prefix}.pos_y_span"] = (max(ys) - min(ys)) if ys else 0.0
    counts = Counter()
    yield_sum = watered = unwatered = fed = unfed = cared = uncared = fertilizer = 0.0
    for row in farm.get("tiles", []) or []:
        for tile in row or []:
            if tile is None:
                counts["EMPTY"] += 1
            elif tile == "LOCKED":
                counts["LOCKED"] += 1
            elif isinstance(tile, dict):
                kind = str(tile.get("kind") or "DICT")
                counts[kind] += 1
                crop = tile.get("crop")
                animal = tile.get("animal")
                if crop: counts[f"CROP:{crop}"] += 1
                if animal: counts[f"ANIMAL:{animal}"] += 1
                try: yield_sum += float(tile.get("yield_units", 0) or 0)
                except Exception: pass
                if kind == "PLANT":
                    if tile.get("watered_today"): watered += 1
                    else: unwatered += 1
                if animal:
                    if tile.get("fed_today"): fed += 1
                    else: unfed += 1
                    if tile.get("cared_today"): cared += 1
                    else: uncared += 1
                    fertilizer += float(bool(tile.get("fertilizer_available")))
    for key in ("EMPTY", "LOCKED", "WEED", "PLANT", "COOP", "PASTURE"):
        out[f"{prefix}.tile.{key}"] = float(counts[key])
    for crop in CROPS:
        out[f"{prefix}.crop.{crop}"] = float(counts[f"CROP:{crop}"])
    for animal in ANIMALS:
        out[f"{prefix}.animal.{animal}"] = float(counts[f"ANIMAL:{animal}"])
    out[f"{prefix}.yield_sum"] = yield_sum
    out[f"{prefix}.watered"] = watered
    out[f"{prefix}.unwatered"] = unwatered
    out[f"{prefix}.fed"] = fed
    out[f"{prefix}.unfed"] = unfed
    out[f"{prefix}.cared"] = cared
    out[f"{prefix}.uncared"] = uncared
    out[f"{prefix}.fertilizer_available"] = fertilizer


def extract_features(obs: Any) -> dict[str, float]:
    get = bench.get_value
    pid = int(get(obs, "player", 0) or 0)
    farms = list(get(obs, "farms", []) or [])
    me = farms[pid] if pid < len(farms) else {}
    opp = farms[1 - pid] if len(farms) >= 2 else {}
    out: dict[str, float] = {
        "seat": float(pid),
        "step": float(get(obs, "step", 0) or 0),
        "day": float(get(obs, "day", 0) or 0),
        "hour": float(get(obs, "hour", 0) or 0),
    }
    farm_features("self", me, out)
    farm_features("opp", opp, out)
    out["diff.money"] = out["self.money"] - out["opp.money"]
    out["diff.hands"] = out["self.hands"] - out["opp.hands"]
    out["diff.lands"] = out["self.lands"] - out["opp.lands"]
    market = get(obs, "market", {}) or {}
    prices = numeric_map(market.get("prices", {}) if isinstance(market, dict) else {})
    inventory = numeric_map(market.get("inventory", {}) if isinstance(market, dict) else {})
    for item in ITEMS:
        out[f"price.{item}"] = prices.get(item, 0.0)
        out[f"market_inventory.{item}"] = inventory.get(item, 0.0)
    town = get(obs, "town", {}) or {}
    shops = list(town.get("unlocked_shops", []) or []) if isinstance(town, dict) else []
    sc = Counter(shops)
    out["shop_count"] = float(len(shops))
    for shop in SHOPS:
        out[f"shop.{shop}"] = float(sc[shop])
    private = get(obs, "private", {}) or {}
    shed = numeric_map(private.get("shed", {}) if isinstance(private, dict) else {})
    seeds = numeric_map(private.get("seeds", {}) if isinstance(private, dict) else {})
    invs = private.get("inventories", []) if isinstance(private, dict) else []
    carried = Counter()
    for inv in invs or []:
        for item, value in numeric_map(inv).items(): carried[item] += value
    for item in ITEMS + ANIMALS:
        out[f"shed.{item}"] = shed.get(item, 0.0)
        out[f"carried.{item}"] = float(carried[item])
    for crop in CROPS:
        out[f"seed.{crop}"] = seeds.get(crop, 0.0)
    return out


def run_one(replay: dict[str, Any], candidate_seat: int, opponent_seat: int, anchor_path: Path, suffix_path: Path, decision: int) -> dict[str, Any]:
    anchor = bench.load_candidate(anchor_path)
    suffix = anchor if suffix_path.resolve() == anchor_path.resolve() else bench.load_candidate(suffix_path)
    captured: dict[str, float] = {}
    timing = {"max": 0.0, "sum": 0.0, "calls": 0.0}

    def hybrid(obs: Any, configuration: Any = None) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            step = int(bench.get_value(obs, "step", 0) or 0)
            anchor_action = call_agent(anchor, obs, configuration)
            if suffix is anchor:
                suffix_action = anchor_action
            else:
                suffix_action = call_agent(suffix, obs, configuration)
            if step == decision and not captured:
                captured.update(extract_features(obs))
            return anchor_action if step < decision else suffix_action
        finally:
            elapsed = time.perf_counter() - started
            timing["max"] = max(timing["max"], elapsed)
            timing["sum"] += elapsed
            timing["calls"] += 1.0

    opponent = bench.recorded_agent(replay, opponent_seat)
    agents = [hybrid, opponent] if candidate_seat == 0 else [opponent, hybrid]
    rewards, statuses = bench.run_agents(replay, agents)
    cr, orun = rewards[candidate_seat], rewards[1 - candidate_seat]
    valid = statuses == ["DONE", "DONE"] and cr is not None and orun is not None
    return {
        "candidate_seat": candidate_seat,
        "opponent_recorded_seat": opponent_seat,
        "candidate_reward": cr,
        "opponent_reward": orun,
        "margin": None if not valid else float(cr) - float(orun),
        "win": bool(valid and float(cr) > float(orun)),
        "valid": valid,
        "statuses": statuses,
        "max_call_ms": 1000.0 * timing["max"],
        "mean_call_ms": 1000.0 * timing["sum"] / max(1.0, timing["calls"]),
        "features": captured,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--anchor", type=Path, required=True)
    ap.add_argument("--suffix", type=Path, required=True)
    ap.add_argument("--suffix-name", required=True)
    ap.add_argument("--decision", type=int, required=True)
    ap.add_argument("--groups", nargs="+", default=["public_v18_live", "mid_teacher_holdout"])
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    rows = []
    for group in args.groups:
        episodes = bench.EPISODE_GROUPS[group]
        for index, episode_id in enumerate(episodes, 1):
            print(f"[{group}] {index}/{len(episodes)} episode={episode_id}", flush=True)
            replay = bench.download_replay(episode_id, args.cache)
            opponent_seat = bench.choose_replaced_opponent(replay, group)
            for seat in (0, 1):
                row = run_one(replay, seat, opponent_seat, args.anchor, args.suffix, args.decision)
                row.update({"episode_id": episode_id, "group": group, "suffix": args.suffix_name, "decision": args.decision, "teams": list(replay["info"].get("TeamNames") or [])})
                rows.append(row)
    valid = [r for r in rows if r["valid"]]
    result = {
        "anchor": str(args.anchor),
        "suffix": args.suffix_name,
        "decision": args.decision,
        "groups": args.groups,
        "summary": {
            "comparisons": len(rows),
            "valid": len(valid),
            "wins": sum(r["win"] for r in valid),
            "win_rate": sum(r["win"] for r in valid) / max(1, len(valid)),
            "mean_margin": sum(r["margin"] for r in valid) / max(1, len(valid)),
            "max_call_ms": max((r["max_call_ms"] for r in rows), default=0.0),
        },
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps(result["summary"], indent=2), flush=True)


if __name__ == "__main__":
    main()
