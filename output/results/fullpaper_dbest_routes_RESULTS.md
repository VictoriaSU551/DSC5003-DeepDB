# Partial original DBEst Flights coverage

Historical four classes:76 native calls; new1D routes:99 calls/101 fit attempts. Export executes0 calls.

New native components:204; empty fixed-subset:103; fit errors:0; numerical-budget unsupported:2; numerical-validation failures:0; native errors/NULL/nonfinite:0/0/0.

F3.3 has matching evaluation SQL and is scored against its exact full-population truth, separately as a **LOCAL F3.3 variant** with a query-aware exact-year fitting prefilter. Its author prefilter configuration does not match; this is not recovered author configuration or a shared ranking. F5.2 is two SUM points with **no joint CI**. Empty fixed-subset, native unsupported/fit errors and missing groups remain gaps. Matched means are conditional; all-truth means stay null without complete finite coverage.

Metadata budget: old declared full-stream/count metadata or estimated state counts; new complete9,997,912 retained-category/non-NULL count/p metadata, with only20,000 unique fitting rows. Plug-in count uncertainty is not a query CI. Aggregate target answers are held out until evaluation. Author training configuration/full-paper completion remain false.

Truth SQL identity: the pinned V4 helper permits only the explicit source-bound query3 single-space literal alias for1B. Applied aliases: [{"actual_sql": "SELECT unique_carrier, COUNT(*) FROM flights WHERE origin_state_abr='LA' AND dest_state_abr='CA' GROUP BY unique_carrier;", "alias": "SOURCE_BOUND_QUERY3_SINGLE_SPACE", "expected_sql": "SELECT unique_carrier, COUNT(*) FROM flights WHERE origin_state_abr='LA' AND  dest_state_abr='CA' GROUP BY unique_carrier;", "query_name": "F2.2", "query_no": 3}]. No general SQL normalization or label rewriting occurs.

| Query | Scope | Finite matched / truth | All-nonzero-truth mean relative error |
| --- | --- | --- | --- |
| F1.1 | FROZEN_ORIGINAL_FOUR | 1/1 | 0.0007380091546170917 |
| F1.2 | FROZEN_ORIGINAL_FOUR | 1/1 | 0.09081640395385665 |
| F2.1 | NOT_DBEST_KDE_CATEGORY_LEARNING | 0/26 | None |
| F2.2 | NOT_DBEST_KDE_CATEGORY_LEARNING | 0/26 | None |
| F2.3 | NOT_DBEST_KDE_CATEGORY_LEARNING | 0/22 | None |
| F3.1 | FROZEN_ORIGINAL_FOUR | 22/22 | 0.25655683554235076 |
| F3.2 | ORIGINAL_1D_API_ROUTING_WITH_ESTIMATED_CATEGORY_METADATA | 10/53 | None |
| F4.1 | FROZEN_ORIGINAL_FOUR | 52/53 | None |
| F4.2 | UNSUPPORTED_MULTIDIMENSIONAL | 0/26 | None |
| F5.1 | ORIGINAL_1D_API_ROUTING_WITH_ESTIMATED_CATEGORY_METADATA | 12/22 | None |
| F5.2 | ORIGINAL_1D_API_ROUTING_WITH_ESTIMATED_CATEGORY_METADATA | 32/53 | None |

LOCAL F3.3 variant (evaluation SQL matches; author prefilter configuration does not match):

| Query | Scope | Finite matched / truth | All-nonzero-truth mean relative error |
| --- | --- | --- | --- |
| F3.3 | QUERY_AWARE_EXACT_YEAR_PREFILTER_VARIANT | 13/26 | None |
