# LOCAL JOB70 sampling variants

Separate LOCAL methods; author configuration is unidentified. These are not the author Table1 or a shared ranking.

Raw Fraction predictions remain unchanged. Positive-truth zero has q-error Infinity; unfinished queries remain null. Whole70 quantiles exist only when all70 complete. No floor1 is applied.

Physical scanned rows are unknown. Metadata, two full projection COPY passes, common SQL, online work and controller validation are charged separately. External command wall was not supplied; recorded client wall is not end-to-end latency.

## SRS

Scope: `LOCAL_JOB70_SRS_WOR_N1000`; n=1000.

Completed 70/70; unfinished 0; raw zero 70; infinite q-errors 70.

Whole70: `{"max": {"status": "INFINITE", "value": "Infinity"}, "median": {"status": "INFINITE", "value": "Infinity"}, "p90": {"status": "INFINITE", "value": "Infinity"}, "p95": {"status": "INFINITE", "value": "Infinity"}, "queries": 70}`

Conditional finite-only (explicit denominator): `{"max": null, "median": null, "p90": null, "p95": null, "queries": 0}`

Status counts: `{"COMPLETE_ZERO": 70}`

Costs: `{"admission_physical_validation_seconds": 7.274782200000001, "after_projection_seconds": 174.6362487, "all_online_queries_and_leaf_checkpoint_seconds": 19.823547899999994, "before_projection_seconds": 180.19456160000001, "binary_copy_bytes_both_passes": 3271486004, "binary_copy_calls": 12, "charged_logical_lookups": null, "collection_and_checkpoint_seconds": 391.46041169999995, "collection_seconds": 391.1897398, "common_recorded_sql_seconds": 16.531698700000028, "common_sql_roundtrips": 65, "end_to_end_latency_claimed": false, "external_command_wall_not_supplied": true, "external_command_wall_seconds": null, "fresh_postflight_physical_validation_seconds": 7.150356700000032, "id_attempts_total": 254036, "live_population_metadata_seconds": 16.506852199999997, "measured_client_wall_seconds_before_final_records": 414.835801, "method": "LOCAL_JOB70_SRS_WOR_N1000", "offline_math_prepublication_validation_seconds": 8.299679700000013, "online_query_sql_roundtrips": 4344, "online_query_wall_seconds": 15.374808900000005, "physical_rows_scanned": null, "physical_rows_scanned_unknown": true, "schema_sql": 36, "setup_identity_metadata_reset_sql": 17}`

## IBJS

Scope: `LOCAL_JOB70_IBJS_SQL_N1000_B100K`; n=1000; b=100000, adaptive stop-after-complete is a LOCAL fallback, not an identified author configuration.

Completed 70/70; unfinished 0; raw zero 13; infinite q-errors 13.

Whole70: `{"max": {"status": "INFINITE", "value": "Infinity"}, "median": {"status": "FINITE", "value": "361337617859440995681/247746898779015970600"}, "p90": {"status": "INFINITE", "value": "Infinity"}, "p95": {"status": "INFINITE", "value": "Infinity"}, "queries": 70}`

Conditional finite-only (explicit denominator): `{"max": {"status": "FINITE", "value": "3084475125/166236514"}, "median": {"status": "FINITE", "value": "39320582697/30808996250"}, "p90": {"status": "FINITE", "value": "126623173800902051/47438589270107500"}, "p95": {"status": "FINITE", "value": "14219276236324227892/3221815882639458125"}, "queries": 57}`

Status counts: `{"COMPLETE": 57, "ZERO_SAMPLE": 13}`

Costs: `{"admission_physical_validation_seconds": 6.4044478, "after_projection_seconds": 176.4081959, "all_online_queries_and_leaf_checkpoint_seconds": 58.98706779999998, "before_projection_seconds": 179.4712949, "binary_copy_bytes_both_passes": 3271486004, "binary_copy_calls": 12, "charged_logical_lookups": 425577, "collection_and_checkpoint_seconds": 431.7054508, "collection_seconds": 431.6745563, "common_recorded_sql_seconds": 16.62676060000003, "common_sql_roundtrips": 67, "end_to_end_latency_claimed": false, "external_command_wall_not_supplied": true, "external_command_wall_seconds": null, "fresh_postflight_physical_validation_seconds": 6.596136400000034, "id_attempts_total": 254036, "live_population_metadata_seconds": 16.59143320000001, "measured_client_wall_seconds_before_final_records": 465.7906188, "method": "LOCAL_JOB70_IBJS_SQL_N1000_B100K", "offline_math_prepublication_validation_seconds": 19.132681899999966, "online_query_sql_roundtrips": 6354, "online_query_wall_seconds": 47.31254569999987, "physical_rows_scanned": null, "physical_rows_scanned_unknown": true, "schema_sql": 36, "setup_identity_metadata_reset_sql": 19}`
