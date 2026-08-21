from __future__ import annotations

import copy
import hashlib
import json
import statistics
import time
from pathlib import Path
from typing import Any

import requests
from kaggle_environments import make

EPISODES = [
    94310456, 94355263, 94437841, 94439800, 94450041, 94450953,
    94458225, 94478362, 94568538, 94617605, 94636231, 94711805,
    94726918,
]
ALIASES = ("Matsu", "tetsuya")
PASS = {"farmer": ["PASS"], "hands": [], "market": []}


def get_value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def load_agent(path: Path):
    namespace: dict[str, Any] = {}
    source = path.read_text(encoding="utf-8")
    exec(compile(source, str(path), "exec"), namespace)
    agent = namespace.get("agent")
    if not callable(agent):
        agent = [value for value in namespace.values() if callable(value)][-1]
    return agent


def recorded_agent(replay: dict[str, Any], seat: int):
    actions = [step[seat].get("action") for step in replay["steps"]]

    def agent(obs: Any, configuration: Any = None):
        step = int(get_value(obs, "step", 0) or 0)
        return copy.deepcopy(actions[min(step + 1, len(actions) - 1)] or PASS)

    return agent


def candidate_agent(path: Path, timing: dict[str, float]):
    base = load_agent(path)

    def agent(obs: Any, configuration: Any = None):
        started = time.perf_counter()
        try:
            try:
                return base(obs, configuration)
            except TypeError:
                return base(obs)
        finally:
            elapsed = time.perf_counter() - started
            timing["calls"] = timing.get("calls", 0.0) + 1.0
            timing["sum"] = timing.get("sum", 0.0) + elapsed
            timing["max"] = max(timing.get("max", 0.0), elapsed)

    return agent


def download(episode_id: int, cache: Path):
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"{episode_id}.json"
    if not path.exists():
        response = requests.get(
            f"https://www.kaggle.com/competitions/episodes/{episode_id}/replay.json",
            timeout=90,
        )
        response.raise_for_status()
        path.write_bytes(response.content)
    return json.loads(path.read_text(encoding="utf-8"))


def target_seat(replay: dict[str, Any]) -> int:
    teams = list(replay["info"].get("TeamNames") or [])
    for alias in ALIASES:
        if teams.count(alias) == 1:
            return teams.index(alias)
    raise RuntimeError(f"No unique target team in {teams}")


def main() -> None:
    candidate_path = Path("artifacts/v21_main.py")
    cache = Path("artifacts/replays")
    rows = []
    for index, episode_id in enumerate(EPISODES, 1):
        print(f"{index}/{len(EPISODES)} episode={episode_id}", flush=True)
        replay = download(episode_id, cache)
        seat = target_seat(replay)
        opponent = 1 - seat
        timing: dict[str, float] = {}
        agents = [None, None]
        agents[seat] = candidate_agent(candidate_path, timing)
        agents[opponent] = recorded_agent(replay, opponent)
        configuration = dict(replay.get("configuration") or {})
        configuration["seed"] = int(replay["info"]["seed"])
        env = make("kaggriculture", configuration=configuration, debug=True)
        env.run(agents)
        terminal = env.steps[-1]
        rewards = [state.reward for state in terminal]
        statuses = [state.status for state in terminal]
        valid = statuses == ["DONE", "DONE"] and all(value is not None for value in rewards)
        candidate_reward = rewards[seat]
        opponent_reward = rewards[opponent]
        row = {
            "episode_id": episode_id,
            "teams": replay["info"].get("TeamNames"),
            "candidate_seat": seat,
            "candidate_reward": candidate_reward,
            "opponent_reward": opponent_reward,
            "margin": None if not valid else float(candidate_reward) - float(opponent_reward),
            "win": bool(valid and float(candidate_reward) > float(opponent_reward)),
            "valid": valid,
            "statuses": statuses,
            "max_call_ms": 1000.0 * timing.get("max", 0.0),
        }
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    valid_rows = [row for row in rows if row["valid"]]
    margins = [float(row["margin"]) for row in valid_rows]
    wins = sum(bool(row["win"]) for row in valid_rows)
    report = {
        "candidate_sha256": hashlib.sha256(candidate_path.read_bytes()).hexdigest(),
        "episodes": EPISODES,
        "rows": rows,
        "summary": {
            "comparisons": len(rows),
            "valid": len(valid_rows),
            "wins": wins,
            "win_rate": wins / max(1, len(valid_rows)),
            "mean_margin": statistics.mean(margins) if margins else None,
            "median_margin": statistics.median(margins) if margins else None,
            "min_margin": min(margins) if margins else None,
            "max_margin": max(margins) if margins else None,
            "max_call_ms": max((row["max_call_ms"] for row in rows), default=0.0),
        },
    }
    Path("artifacts/v21-target-seat.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary = report["summary"]
    markdown = (
        "# V21 newest target-seat holdout\n\n"
        f"- Wins: {summary['wins']}/{summary['valid']} "
        f"({100.0 * summary['win_rate']:.2f}%)\n"
        f"- Mean margin: {summary['mean_margin']:.1f}\n"
        f"- Minimum margin: {summary['min_margin']:.1f}\n"
        f"- Invalid: {summary['comparisons'] - summary['valid']}\n"
        f"- Max call: {summary['max_call_ms']:.3f} ms\n"
    )
    Path("artifacts/v21-target-seat.md").write_text(markdown, encoding="utf-8")
    print(markdown, flush=True)


if __name__ == "__main__":
    main()
