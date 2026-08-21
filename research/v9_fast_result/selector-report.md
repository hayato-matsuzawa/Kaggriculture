# Kaggriculture V9 selector training

No newest-holdout row was loaded. Hyperparameters selected by bidirectional era transfer, grouped episode CV, and temporal block CV.

- Winner: `d1:constant(candidate=0)`
- Decision step: 1
- Training samples: 94
- Training episodes: 47

## Cross-validation folds

| Fold | Wins | N | Win rate | Mean margin | Min margin |
|---|---:|---:|---:|---:|---:|
| public_to_mid | 23 | 40 | 57.50% | 7221.6 | -22109.0 |
| mid_to_public | 54 | 54 | 100.00% | 38894.3 | 14033.0 |
| episode_cv_0 | 19 | 20 | 95.00% | 37119.4 | -5056.0 |
| episode_cv_1 | 16 | 20 | 80.00% | 25031.2 | -22109.0 |
| episode_cv_2 | 14 | 18 | 77.78% | 11775.2 | -16493.0 |
| episode_cv_3 | 14 | 18 | 77.78% | 17774.6 | -10815.0 |
| episode_cv_4 | 14 | 18 | 77.78% | 34124.9 | -10574.0 |
| public_v18_live_early_to_late | 16 | 16 | 100.00% | 22809.8 | 14033.0 |
| public_v18_live_late_to_early | 38 | 38 | 100.00% | 45666.7 | 14360.0 |
| mid_teacher_holdout_early_to_late | 8 | 12 | 66.67% | -1141.2 | -22109.0 |
| mid_teacher_holdout_late_to_early | 15 | 28 | 53.57% | 10805.8 | -16493.0 |
