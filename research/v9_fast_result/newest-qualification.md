# Kaggriculture V21 cross-era benchmark

Candidate SHA-256: `231d5a5e1ea5328a857da873bd8df863fd5ca634fff5c6afe13d929cda78cb9b`
Engine: `1.32.7`

## Summary

| Group | Opponent selection | Wins | Valid | Win rate | Mean margin | Min margin |
|---|---|---:|---:|---:|---:|---:|
| newest_holdout | replaced_team_opponent | 18 | 26 | 69.23% | 18726.5 | -19028.0 |
| newest_holdout | recorded_winner | 16 | 26 | 61.54% | 19906.6 | -19028.0 |

## Integrity

- Exact replay reproductions: 13 / 13
- Invalid candidate comparisons: 0
- Maximum observed candidate call: 187.713 ms

The recorded opponent action stream is open-loop after the candidate changes the game state. This is a reproducible regression and adversarial benchmark, not a direct live-ladder probability estimate.
