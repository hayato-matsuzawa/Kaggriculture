# Kaggriculture V21 cross-era benchmark

Candidate SHA-256: `ff598e7b4421d98bd8e28df9a383ec54e6040b94cdd57ef6f1d13cc673960710`
Engine: `1.32.7`

## Summary

| Group | Opponent selection | Wins | Valid | Win rate | Mean margin | Min margin |
|---|---|---:|---:|---:|---:|---:|
| newest_holdout | replaced_team_opponent | 18 | 26 | 69.23% | 18726.5 | -19028.0 |
| newest_holdout | recorded_winner | 16 | 26 | 61.54% | 19906.6 | -19028.0 |

## Integrity

- Exact replay reproductions: 13 / 13
- Invalid candidate comparisons: 0
- Maximum observed candidate call: 216.248 ms

The recorded opponent action stream is open-loop after the candidate changes the game state. This is a reproducible regression and adversarial benchmark, not a direct live-ladder probability estimate.
