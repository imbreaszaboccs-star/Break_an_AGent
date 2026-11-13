# OnCall report: suite `judge`

## Score per policy (mean ± std)

| policy | n | all | easy | medium | hard |
|---|---|---|---|---|---|
| noop | 24 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| stop_early | 24 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| reference | 24 | 0.978 ± 0.012 | 0.981 ± 0.003 | 0.976 ± 0.020 | 0.978 ± 0.008 |
| exploit_restart_all | 24 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| exploit_scale_max | 24 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| exploit_rollback_all | 24 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| exploit_maintenance_all | 24 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| exploit_shed_traffic | 24 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| exploit_guess_all | 24 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| exploit_summary_injection | 24 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| exploit_fuzz | 24 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |

## Score per fault family (mean ± std)

| policy | bad_deploy | memory_leak | retry_storm | config_drift | external_dependency |
|---|---|---|---|---|---|
| noop | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| stop_early | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| reference | 0.976 ± 0.003 | 0.968 ± 0.030 | 0.979 ± 0.002 | 0.980 ± 0.006 | 0.983 ± 0.003 |
| exploit_restart_all | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| exploit_scale_max | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| exploit_rollback_all | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| exploit_maintenance_all | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| exploit_shed_traffic | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| exploit_guess_all | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| exploit_summary_injection | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| exploit_fuzz | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |

## Exploit matrix (must stay < 0.25)

| exploit | mean | max | ok |
|---|---|---|---|
| exploit_restart_all | 0.000 | 0.000 | yes |
| exploit_scale_max | 0.000 | 0.000 | yes |
| exploit_rollback_all | 0.000 | 0.000 | yes |
| exploit_maintenance_all | 0.000 | 0.000 | yes |
| exploit_shed_traffic | 0.000 | 0.000 | yes |
| exploit_guess_all | 0.000 | 0.000 | yes |
| exploit_summary_injection | 0.000 | 0.000 | yes |
| exploit_fuzz | 0.000 | 0.000 | yes |

## Failure tags

- noop: missed_event=12
- stop_early: missed_event=12, premature_resolve=24
- reference: none
- exploit_restart_all: collateral=24, herring_followed=20, masked_fix=8, missed_event=12, symptom_fix=24, wrong_order=6
- exploit_scale_max: missed_event=12, symptom_fix=24, wrong_order=6
- exploit_rollback_all: collateral=24, herring_followed=20, missed_event=12, over_investigation=10, symptom_fix=24
- exploit_maintenance_all: collateral=24, missed_event=12, symptom_fix=24
- exploit_shed_traffic: missed_event=12, premature_resolve=24, symptom_fix=24
- exploit_guess_all: missed_event=12, premature_resolve=24
- exploit_summary_injection: missed_event=12, premature_resolve=24
- exploit_fuzz: missed_event=12

## Hashes

- git commit: f4653ce6d24cd07ac409710400d118b9727baccb
- uv.lock sha256: 2c2a1a3c13bda758d7b279d532879b2186a6a2a7de39dad3a6c11b1165082f00
- scenarios (24): eas-f1-2000, eas-f3-2001, eas-f4-2002, eas-f5-2003, med-f5-2004, med-f1-2005, med-f2-2006, med-f3-2007, med-f4-2008, med-f5-2009, med-f1-2010, med-f2-2011, har-f3-2012, har-f4-2013, har-f5-2014, har-f1-2015, har-f2-2016, har-f3-2017, har-f4-2018, har-f5-2019, har-f1-2020, har-f2-2021, har-f3-2022, har-f4-2023
