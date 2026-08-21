# Kaggriculture V9 candidate screen

Qualification gate: **24/26 wins (92.31%)** on untouched newest holdout.

| Candidate | Wins | Valid | Win rate | Mean margin | Min margin | Max call ms |
|---|---:|---:|---:|---:|---:|---:|
| unseen_current | 18 | 26 | 69.23% | 18726.46153846154 | -19028.0 | 131.45182099998465 |
| cok | 16 | 26 | 61.54% | 24734.80769230769 | -43064.0 | 197.32459600004404 |
| sota_claude | 6 | 26 | 23.08% | 3002.0384615384614 | -35641.0 | 131.73864399999502 |
| unseen_v60 | 6 | 26 | 23.08% | -4558.692307692308 | -49809.0 | 90.96930100000122 |
| unseen_v52 | 6 | 26 | 23.08% | -5280.807692307692 | -51032.0 | 0.9811349999608865 |
| seyam_v21 | 4 | 26 | 15.38% | -1027.4615384615386 | -27442.0 | 194.8469550000027 |
| kirby | 0 | 26 | 0.00% | -121057.76923076923 | -196236.0 | 1.1254080000071554 |
| gnr_adaptive | 0 | 26 | 0.00% | -124280.88461538461 | -173025.0 | 89.91911699999378 |
| gnr_v2 | 0 | 26 | 0.00% | -124280.88461538461 | -173025.0 | 82.38990600000307 |
| simon | 0 | 26 | 0.00% | -125045.0 | -185593.0 | 129.85797700000035 |
| sota_gpt | 0 | 26 | 0.00% | -128081.88461538461 | -177618.0 | 142.65474399996947 |
| aral | 0 | 26 | 0.00% | -134242.88461538462 | -182430.0 | 0.6977689999985159 |
| deepesh | 0 | 0 | 0.00% | None | None | None |
| keyholder | 0 | 0 | 0.00% | None | None | None |
| v7_drive | 0 | 0 | 0.00% | None | None | None |
| zansued | 0 | 0 | 0.00% | None | None | None |

## Oracle coverage: replaced_team_opponent
- single: unseen_current=18/26; cok=16/26; unseen_v60=6/26; unseen_v52=6/26; sota_claude=6/26
- pairs: cok,unseen_current=23/26; sota_claude,unseen_current=20/26; unseen_current,unseen_v60=18/26; unseen_current,unseen_v52=18/26; sota_gpt,unseen_current=18/26
- triples: cok,sota_claude,unseen_current=25/26; cok,unseen_current,unseen_v60=23/26; cok,unseen_current,unseen_v52=23/26; cok,sota_gpt,unseen_current=23/26; cok,simon,unseen_current=23/26

## Oracle coverage: recorded_winner
- single: unseen_current=16/26; cok=13/26; unseen_v60=7/26; unseen_v52=7/26; sota_claude=6/26
- pairs: cok,unseen_current=22/26; sota_claude,unseen_current=18/26; seyam_v21,unseen_current=18/26; unseen_current,unseen_v60=17/26; unseen_current,unseen_v52=17/26
- triples: cok,sota_claude,unseen_current=24/26; cok,unseen_current,unseen_v60=22/26; cok,unseen_current,unseen_v52=22/26; cok,sota_gpt,unseen_current=22/26; cok,simon,unseen_current=22/26
