# 完整复现阶段：可公开的派生结果

**整篇论文仍未完成。** 本页是已验证部分的协作快照。

来源状态时间：2026-10-30T15:20:44.514793+00:00

作者Table1数值与本地重跑各有evidence标签；配置、样本和尾部误差有差异，不能互相替代。
公开工作负载为683条，其中4--6表413条；作者200条具体成员未找到。
Flights为本地生成的1B母体；DBEst仅4类SQL/20K拟合，八类不支持，未做等预算或延迟排名。
CI仅一次样本，少于10行的组排除，不能解读为重复抽样覆盖率校准。

只发布派生表图。原始数据、模型、运行环境、PDF和大输出保存在本地，不随仓库分发。

## 表格和图

- [fullpaper_cardinality_table1.csv](fullpaper_cardinality_table1.csv)
- [fullpaper_cardinality_studies.csv](fullpaper_cardinality_studies.csv)
- [fullpaper_cardinality_groups.csv](fullpaper_cardinality_groups.csv)
- [fullpaper_cardinality_temporal_population_fractions.csv](fullpaper_cardinality_temporal_population_fractions.csv)
- [fullpaper_cardinality_inference_variant_changes.csv](fullpaper_cardinality_inference_variant_changes.csv)
- [fullpaper_cardinality_table1_comparison.png](fullpaper_cardinality_table1_comparison.png)
- [fullpaper_cardinality_sample_size_study.png](fullpaper_cardinality_sample_size_study.png)
- [fullpaper_cardinality_budget_study.png](fullpaper_cardinality_budget_study.png)
- [fullpaper_cardinality_generalization.png](fullpaper_cardinality_generalization.png)
- [fullpaper_cardinality_cpp_latency.png](fullpaper_cardinality_cpp_latency.png)
- [fullpaper_cardinality_temporal_updates.png](fullpaper_cardinality_temporal_updates.png)
- [fullpaper_flights_query_summary.csv](fullpaper_flights_query_summary.csv)
- [fullpaper_flights_all_groups.csv](fullpaper_flights_all_groups.csv)
- [fullpaper_flights_flights_relative_error.png](fullpaper_flights_flights_relative_error.png)
- [fullpaper_flights_flights_ci_half_width.png](fullpaper_flights_flights_ci_half_width.png)
- [fullpaper_flights_comparison_query_comparison.csv](fullpaper_flights_comparison_query_comparison.csv)
- [fullpaper_flights_comparison_flights_partial_baselines.png](fullpaper_flights_comparison_flights_partial_baselines.png)

## 当前阶段状态

| 阶段 | 状态 |
| --- | --- |
| paper_and_public_input_audit | INPUT_AUDIT_PASS_WITH_GAPS |
| independent_70_truths_and_postgres_11_5 | PASS |
| rdc_n100000_b0p0 | PASS_LOCAL_VARIANT |
| joblight_single_n10000000 | PASS_LOCAL_VARIANT |
| paper_proxy_joblight_rdc_n10000000_b0p5 | PASS_LOCAL_VARIANT |
| public_scale_rdc_n100000_b0p0 | PASS_LOCAL_VARIANT |
| public_scale_rdc_n10000000_b0p5 | PASS_LOCAL_VARIANT |
| cpp_existing_model_correctness | PASS |
| flights_source_5m | PASS |
| flights_streaming_golden_200k | PASS |
| flights_1b_generated | PASS_ORIGINAL_SCALE_GENERATION |
| ssb_sf500_generated | PARTIAL_CHECKPOINT |
| mscn_100_epochs | PASS_LOCAL_TABLE1_RERUN |
| mscn_rebuilt_consistent_sample_generalization | PASS_SEALED_REBUILT_100_EPOCHS_LOCAL_WORKLOAD |
| cpp_5spn_public_workload | PASS |
| cpp_6spn_paper_proxy_v2 | PASS_SEALED_LOCAL_PUBLIC_WORKLOAD |
| cpp_canonical_v3 | PASS_READ_ONLY_CURRENT_CANONICAL_NATIVE_AUDIT |
| dbest_1b_bounded_original_engine | PASS_WITH_GAPS |
| paper_exact_200_query_binding | OPEN_SOURCE_GAP |
| figure5_original_synthetic_database | OPEN_SOURCE_GAP |
| all_original_comparison_implementations | OPEN_SOURCE_GAP |
| figure7_exact_author_config | OPEN_SOURCE_GAP |
| flights_1b_rspn_aqp_and_ci | PASS_SEALED_ORIGINAL_SCALE_LOCAL_EXPERIMENT |
| independent_public_683_truths | PASS_LOCAL_COUNTS_WITH_PUBLISHED_INPUT_DIFFERENCES |
| flights_original_baseline_comparisons | PENDING |
| ssb_aqp_and_baselines | PENDING |
| ssb_confidence_intervals | PENDING |
| dbest_wavelet_microbenchmarks | PENDING |

完整协议、恢复门禁与组员分工见[运行指南](../../docs/FULL_RUNNING_GUIDE.md)。
本快照的输入与工件SHA见[摘要](fullpaper_summary.json)。
