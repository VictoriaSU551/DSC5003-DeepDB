"""Score frozen rebuilt MSCN predictions against SQL-verified local truths.

Independent permanent entry; never loads a model or invokes inference. The
original SHA-frozen trainer, result script and published artifacts are retained.
"""
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

DIRECTORY = ROOT / "output/full/mscn/rebuilt_seed1/results"


def record(path):
    path = Path(path).resolve()
    return dict(path=path.relative_to(ROOT).as_posix(), bytes=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def validate_identity(prediction, truth, group, index, samples_sha256):
    """Require the exact original query, sample identity and integer estimate."""
    sql_sha = hashlib.sha256(truth["query"].encode()).hexdigest()
    if (prediction["group"] != group or truth["group"] != group
            or int(prediction["query_no"]) != index or int(truth["query_no"]) != index
            or prediction["query"] != truth["query"]
            or prediction["source_sql_sha256"] != sql_sha
            or prediction["samples_manifest_sha256"] != samples_sha256
            or int(prediction["cardinality_true"]) != int(truth["cardinality_published"])):
        raise ValueError("Preserved prediction query/truth/sample identity differs")
    estimate = int(prediction["cardinality_predict"])
    if estimate < 1:
        raise ValueError("Preserved MSCN estimate must be a positive integer")
    return estimate


def run(directory=DIRECTORY):
    directory = Path(directory)
    evaluation_path = directory / "evaluation.json"
    if not evaluation_path.is_file():
        raise ValueError("100-epoch published evaluation must be committed before local scoring")
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    if (evaluation["status"] != "REBUILT_PUBLIC_WORKLOAD_EVALUATION_COMPLETE"
            or evaluation["completed_epochs"] != 100 or evaluation["queries"] != 753):
        raise ValueError("100-epoch published evaluation is incomplete")
    import full_mscn as frozen
    frozen.verify_records(evaluation["artifacts"], directory)
    import full_local_truth_eval as local
    report_path = ROOT / "output/full/results/grouped_truth_discrepancies.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if (report["status"] != "PASS_LOCAL_COUNTS_WITH_PUBLISHED_INPUT_DIFFERENCES"
            or report["queries"] != 683 or report["published_matches"] != 609
            or report["independent_SQL_confirmed_differences"] != 74
            or report["original_published_inputs_unchanged"] is not True):
        raise ValueError("Independent local truth SQL audit is incomplete")
    truth_path = ROOT / report["local_truth_path"]
    if record(truth_path)["sha256"] != report["local_truth_sha256"]:
        raise ValueError("Independent truth artifact changed")
    truth_rows = local.read_csv(truth_path)
    truths = {(row["group"], int(row["query_no"])): row for row in truth_rows}
    if len(truth_rows) != 683 or len(truths) != 683:
        raise ValueError("Duplicate or incomplete local truth query keys")
    source_paths = [evaluation_path, report_path, truth_path, Path(__file__),
                    directory / "binding.json", directory / "model_state.pt",
                    ROOT / "data/mscn/rebuilt/manifest.json",
                    ROOT / "data/mscn/rebuilt/workloads/public-grouped.joint.jsonl",
                    ROOT / "code/full_local_truth_eval.py",
                    ROOT / "code/full_evaluation.py", ROOT / "code/full_inventory.py"]
    all_rows, groups, seen = [], {}, set()
    for tables in range(3, 7):
        for predicates in range(1, 6):
            group = "{}_{}_SPN".format(tables, predicates)
            path = directory / (group + ".csv")
            source_paths.append(path)
            predictions = local.read_csv(path)
            aligned_truths = []
            for index, prediction in enumerate(predictions):
                key = (group, index)
                if key in seen:
                    raise ValueError("Invalid or duplicate prediction key")
                truth = truths[key]
                validate_identity(prediction, truth, group, index, evaluation["samples_manifest_sha256"])
                seen.add(key)
                aligned_truths.append(truth)
            scores = local.align_and_score(predictions, aligned_truths)
            for prediction, score in zip(predictions, scores):
                estimate = int(prediction["cardinality_predict"])
                if float(estimate) != score["prediction"] or estimate < 1:
                    raise ValueError("Prediction changed during postprocessing")
                if not math.isclose(float(prediction["q_error"]), score["published_q_error"],
                                    rel_tol=1e-14, abs_tol=1e-14):
                    raise ValueError("Preserved published q-error is inconsistent")
                all_rows.append(dict(prediction, cardinality_true_published=score["published_truth"],
                    cardinality_true_local=score["local_truth"],
                    q_error_published=score["published_q_error"], q_error_local=score["local_q_error"]))
            groups[group] = dict(queries=len(scores),
                local=local.numeric_summary([row["local_q_error"] for row in scores]),
                published=local.numeric_summary([row["published_q_error"] for row in scores]))
    if seen != set(truths) or len(all_rows) != 683:
        raise ValueError("The full public workload is not aligned")
    changed = sum(row["cardinality_true_local"] != row["cardinality_true_published"] for row in all_rows)
    if changed != 74:
        raise ValueError("Local/published truth discrepancy count changed")
    sources = sorted((record(path) for path in source_paths), key=lambda row: row["path"])
    binding = local.binding_hash(dict(sources=sources, protocol="rebuilt_predictions_local_truth_only_v1"))
    receipt_path = directory / "evaluation_local_truth.json"
    if receipt_path.exists():
        previous = json.loads(receipt_path.read_text(encoding="utf-8"))
        if previous["binding_sha256"] != binding:
            raise ValueError("Existing local metrics bind different inputs; preserve and version explicitly")
        frozen.verify_records(previous["artifacts"], directory)
        return dict(previous, reused_verified_local_metrics=True)
    destination = directory / "local_truth_all_public_predictions.csv"
    temporary = destination.with_suffix(".csv.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(all_rows[0]))
        writer.writeheader()
        writer.writerows(all_rows)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(str(temporary), str(destination))
    def pooled(rows):
        return dict(queries=len(rows),
            local=local.numeric_summary([row["q_error_local"] for row in rows]),
            published=local.numeric_summary([row["q_error_published"] for row in rows]))
    result = dict(status="PASS_LOCAL_TRUTH_POSTPROCESSING", binding_sha256=binding, sources=sources,
        full_paper_reproduction_complete=False, queries=683, original_published_matches=609,
        SQL_confirmed_input_differences=74, predictions_recomputed=False, model_loaded=False,
        training_or_frozen_bitmaps_modified=False, original_evaluation_preserved=True,
        published_evaluation_sha256=record(evaluation_path)["sha256"],
        truth_report_sha256=record(report_path)["sha256"], local_truth_sha256=record(truth_path)["sha256"],
        samples_manifest_sha256=evaluation["samples_manifest_sha256"],
        checkpoint_sha256=evaluation["checkpoint"]["artifact"]["sha256"],
        groups=groups, public_3to6=pooled(all_rows),
        public_4to6=pooled([row for row in all_rows if int(row["group"][0]) >= 4]),
        figure8_public_groups=[dict(tables=tables, predicates=predicates,
            **groups["{}_{}_SPN".format(tables, predicates)])
            for tables in (4, 5, 6) for predicates in range(1, 6)],
        job_light_scope="No replacement local JOB truth supplied; original 70-query published evaluation retained",
        source_code="Permanent full_mscn_local_truth entry plus sealed root align_and_score/numeric_summary helpers",
        artifacts=[dict(path=destination.name, bytes=destination.stat().st_size,
                        sha256=record(destination)["sha256"])])
    frozen.atomic_json(receipt_path, result)
    return result


if __name__ == "__main__":
    result = run()
    print(json.dumps(dict(status=result["status"], queries=result["queries"],
        reused=result.get("reused_verified_local_metrics", False),
        public_3to6=result["public_3to6"], public_4to6=result["public_4to6"])))
