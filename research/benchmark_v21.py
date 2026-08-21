from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

import requests
from kaggle_environments import make

PASS_ACTION = {"farmer": ["PASS"], "hands": [], "market": []}

EPISODE_GROUPS: dict[str, list[int]] = {
    "public_v18_live": [
        90108945, 90109603, 90110271, 90110946, 90111614, 90112297,
        90112969, 90113641, 90114321, 90115006, 90115677, 90116362,
        90116405, 90117048, 90117722, 90118413, 90119117, 90119795,
        90120485, 90121168, 90121857, 90122540, 90123236, 90123284,
        90123938, 90124623, 90125302,
    ],
    "mid_teacher_holdout": [
        93893188, 93896734, 93920628, 93871017, 94100037, 94052517,
        94141444, 93880718, 94060491, 93917082, 93877159, 93921512,
        93895845, 94394862, 94394863, 93909122, 93866634, 93886088,
        93881606, 94176801,
    ],
    "newest_holdout": [
        94310456, 94355263, 94437841, 94439800, 94450041, 94450953,
        94458225, 94478362, 94568538, 94617605, 94636231, 94711805,
        94726918,
    ],
}

REPLACED_TEAM_ALIASES: dict[str, tuple[str, ...]] = {
    "public_v18_live": ("Touhidul Alam Seyam",),
    "mid_teacher_holdout": ("tetsuya",),
    "newest_holdout": ("Matsu", "tetsuya"),
}


def get_value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def load_candidate(path: Path) -> Callable[..., dict[str, Any]]:
    namespace: dict[str, Any] = {}
    source = path.read_text(encoding="utf-8")
    exec(compile(source, str(path), "exec"), namespace)
    agent = namespace.get("agent")
    if not callable(agent):
        callables = [value for value in namespace.values() if callable(value)]
        if not callables:
            raise RuntimeError(f"No callable agent in {path}")
        agent = callables[-1]
    return agent


def recorded_agent(replay: dict[str, Any], seat: int) -> Callable[..., dict[str, Any]]:
    actions = [step[seat].get("action") for step in replay["steps"]]

    def agent(obs: Any, configuration: Any = None) -> dict[str, Any]:
        step = int(get_value(obs, "step", 0) or 0)
        index = min(step + 1, len(actions) - 1)
        action = actions[index] or PASS_ACTION
        return copy.deepcopy(action)

    return agent


def timed_candidate(path: Path, timing: dict[str, float]) -> Callable[..., dict[str, Any]]:
    base = load_candidate(path)

    def agent(obs: Any, configuration: Any = None) -> dict[str, Any]:
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


def replay_configuration(replay: dict[str, Any]) -> dict[str, Any]:
    config = dict(replay.get("configuration") or {})
    config["seed"] = int(replay["info"]["seed"])
    config.setdefault("episodeSteps", 720)
    return config


def run_agents(
    replay: dict[str, Any],
    agents: list[Callable[..., dict[str, Any]]],
) -> tuple[list[float | None], list[str]]:
    env = make("kaggriculture", configuration=replay_configuration(replay), debug=True)
    env.run(agents)
    terminal = env.steps[-1]
    rewards = [state.reward for state in terminal]
    statuses = [state.status for state in terminal]
    return rewards, statuses


def download_replay(episode_id: int, cache_dir: Path) -> dict[str, Any]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{episode_id}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    url = f"https://www.kaggle.com/competitions/episodes/{episode_id}/replay.json"
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            response = requests.get(url, timeout=90)
            response.raise_for_status()
            replay = response.json()
            if int(replay["info"]["EpisodeId"]) != episode_id:
                raise RuntimeError("Episode ID mismatch")
            path.write_text(json.dumps(replay), encoding="utf-8")
            return replay
        except Exception as exc:  # pragma: no cover - network retry
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Unable to download episode {episode_id}: {last_error}")


def choose_replaced_opponent(
    replay: dict[str, Any],
    group: str,
) -> int:
    teams = list(replay["info"].get("TeamNames") or [])
    aliases = REPLACED_TEAM_ALIASES[group]
    for alias in aliases:
        if alias in teams and teams.count(alias) == 1:
            return 1 - teams.index(alias)
    rewards = replay.get("rewards") or [None, None]
    if all(value is not None for value in rewards):
        return 0 if float(rewards[0]) >= float(rewards[1]) else 1
    return 0


def choose_winner(replay: dict[str, Any]) -> int:
    rewards = replay.get("rewards") or [None, None]
    if all(value is not None for value in rewards):
        return 0 if float(rewards[0]) >= float(rewards[1]) else 1
    return 0


def compare_candidate(
    replay: dict[str, Any],
    candidate_path: Path,
    opponent_seat: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate_seat in (0, 1):
        timing: dict[str, float] = {}
        candidate = timed_candidate(candidate_path, timing)
        opponent = recorded_agent(replay, opponent_seat)
        agents = [candidate, opponent] if candidate_seat == 0 else [opponent, candidate]
        rewards, statuses = run_agents(replay, agents)
        candidate_reward = rewards[candidate_seat]
        opponent_reward = rewards[1 - candidate_seat]
        valid = statuses == ["DONE", "DONE"] and candidate_reward is not None and opponent_reward is not None
        rows.append(
            {
                "candidate_seat": candidate_seat,
                "opponent_recorded_seat": opponent_seat,
                "candidate_reward": candidate_reward,
                "opponent_reward": opponent_reward,
                "margin": None if not valid else float(candidate_reward) - float(opponent_reward),
                "win": bool(valid and float(candidate_reward) > float(opponent_reward)),
                "valid": valid,
                "statuses": statuses,
                "max_call_ms": 1000.0 * timing.get("max", 0.0),
                "mean_call_ms": 1000.0 * timing.get("sum", 0.0) / max(1.0, timing.get("calls", 0.0)),
            }
        )
    return rows


def validate_replay(replay: dict[str, Any]) -> dict[str, Any]:
    agents = [recorded_agent(replay, 0), recorded_agent(replay, 1)]
    rewards, statuses = run_agents(replay, agents)
    expected = replay.get("rewards") or [None, None]
    exact = all(
        expected[i] is not None
        and rewards[i] is not None
        and math.isclose(float(expected[i]), float(rewards[i]), abs_tol=1e-9)
        for i in (0, 1)
    )
    return {
        "exact": exact,
        "expected": expected,
        "observed": rewards,
        "statuses": statuses,
        "replay_module_version": replay.get("module_version"),
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [row for row in rows if row["valid"]]
    margins = [float(row["margin"]) for row in valid]
    return {
        "comparisons": len(rows),
        "valid": len(valid),
        "wins": sum(bool(row["win"]) for row in valid),
        "win_rate": sum(bool(row["win"]) for row in valid) / max(1, len(valid)),
        "mean_margin": statistics.mean(margins) if margins else None,
        "median_margin": statistics.median(margins) if margins else None,
        "min_margin": min(margins) if margins else None,
        "max_margin": max(margins) if margins else None,
        "max_call_ms": max((float(row["max_call_ms"]) for row in rows), default=0.0),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Kaggriculture V21 cross-era benchmark",
        "",
        f"Candidate SHA-256: `{report['candidate_sha256']}`",
        f"Engine: `{report['engine_version']}`",
        "",
        "## Summary",
        "",
        "| Group | Opponent selection | Wins | Valid | Win rate | Mean margin | Min margin |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for group, modes in report["summary"].items():
        for mode, summary in modes.items():
            lines.append(
                f"| {group} | {mode} | {summary['wins']} | {summary['valid']} | "
                f"{100.0 * summary['win_rate']:.2f}% | {summary['mean_margin']:.1f} | {summary['min_margin']:.1f} |"
            )
    lines.extend(
        [
            "",
            "## Integrity",
            "",
            f"- Exact replay reproductions: {report['integrity']['exact']} / {report['integrity']['checked']}",
            f"- Invalid candidate comparisons: {report['integrity']['invalid_candidate_comparisons']}",
            f"- Maximum observed candidate call: {report['integrity']['max_call_ms']:.3f} ms",
            "",
            "The recorded opponent action stream is open-loop after the candidate changes the game state. "
            "This is a reproducible regression and adversarial benchmark, not a direct live-ladder probability estimate.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=Path("artifacts/replays"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/v21-benchmark.json"))
    parser.add_argument("--markdown", type=Path, default=Path("artifacts/v21-benchmark.md"))
    args = parser.parse_args()

    import kaggle_environments

    candidate_sha = hashlib.sha256(args.candidate.read_bytes()).hexdigest()
    all_results: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    integrity_rows: list[dict[str, Any]] = []
    episode_metadata: list[dict[str, Any]] = []

    for group, episode_ids in EPISODE_GROUPS.items():
        for index, episode_id in enumerate(episode_ids, 1):
            print(f"[{group}] {index}/{len(episode_ids)} episode={episode_id}", flush=True)
            replay = download_replay(episode_id, args.cache)
            integrity = validate_replay(replay)
            integrity_rows.append({"episode_id": episode_id, "group": group, **integrity})
            teams = list(replay["info"].get("TeamNames") or [])
            episode_metadata.append(
                {
                    "episode_id": episode_id,
                    "group": group,
                    "teams": teams,
                    "recorded_rewards": replay.get("rewards"),
                    "module_version": replay.get("module_version"),
                }
            )
            selections = {
                "replaced_team_opponent": choose_replaced_opponent(replay, group),
                "recorded_winner": choose_winner(replay),
            }
            for mode, opponent_seat in selections.items():
                rows = compare_candidate(replay, args.candidate, opponent_seat)
                for row in rows:
                    row.update(
                        {
                            "episode_id": episode_id,
                            "group": group,
                            "mode": mode,
                            "teams": teams,
                        }
                    )
                all_results[group][mode].extend(rows)

    summary = {
        group: {mode: summarize(rows) for mode, rows in modes.items()}
        for group, modes in all_results.items()
    }
    flat_rows = [row for modes in all_results.values() for rows in modes.values() for row in rows]
    report = {
        "candidate": str(args.candidate),
        "candidate_sha256": candidate_sha,
        "engine_version": getattr(kaggle_environments, "__version__", "unknown"),
        "episode_groups": EPISODE_GROUPS,
        "episodes": episode_metadata,
        "integrity_rows": integrity_rows,
        "results": {group: dict(modes) for group, modes in all_results.items()},
        "summary": summary,
        "integrity": {
            "checked": len(integrity_rows),
            "exact": sum(bool(row["exact"]) for row in integrity_rows),
            "invalid_candidate_comparisons": sum(not bool(row["valid"]) for row in flat_rows),
            "max_call_ms": max((float(row["max_call_ms"]) for row in flat_rows), default=0.0),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.markdown.write_text(render_markdown(report), encoding="utf-8")
    print(render_markdown(report), flush=True)


if __name__ == "__main__":
    main()
