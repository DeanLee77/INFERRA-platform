import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = Path(__file__).with_name("retrieval_source_manifest.json")
GOLDEN_CASES_PATH = Path(__file__).with_name("retrieval_golden_cases.json")
TOKEN_RE = re.compile(r"[a-z0-9]+")
EVALUATION_ONLY_AUTHORITY = "evaluation_only_non_authoritative"


@dataclass(frozen=True)
class CorpusDocument:
    source_id: str
    snapshot_version: str
    source_path: str
    extraction_path: str
    text: str
    content_sha256: str
    tokens: Counter


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_source_manifest(path: Path = MANIFEST_PATH) -> dict:
    manifest = load_json(path)
    if manifest["authorityPolicy"]["mode"] != EVALUATION_ONLY_AUTHORITY:
        raise ValueError("Retrieval harness must remain evaluation-only and non-authoritative.")
    return manifest


def load_golden_cases(path: Path = GOLDEN_CASES_PATH) -> dict:
    return load_json(path)


def load_corpus(manifest: dict, root: Path = ROOT) -> list[CorpusDocument]:
    documents = []
    for source in manifest["sources"]:
        source_path = source["path"]
        absolute_path = root / source_path
        text = absolute_path.read_text(encoding="utf-8")
        documents.append(
            CorpusDocument(
                source_id=source["sourceId"],
                snapshot_version=source["snapshotVersion"],
                source_path=source_path,
                extraction_path=source["extractionPath"],
                text=text,
                content_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                tokens=Counter(_tokens(text)),
            )
        )
    return documents


def retrieve(
    query: str,
    corpus: list[CorpusDocument],
    manifest: dict,
    *,
    top_k: int,
    retrieved_at: str,
) -> list[dict]:
    query_terms = set(_tokens(query))
    idf = _inverse_document_frequency(corpus)
    scored = []
    for document in corpus:
        matched_terms = sorted(term for term in query_terms if term in document.tokens)
        score = sum(idf[term] for term in matched_terms)
        if score > 0:
            scored.append((score, document, matched_terms))

    ranked = sorted(scored, key=lambda item: (-item[0], item[1].source_id))[:top_k]
    return [
        {
            "source_id": document.source_id,
            "snapshot_version": document.snapshot_version,
            "source_path": document.source_path,
            "extraction_path": document.extraction_path,
            "content_sha256": document.content_sha256,
            "retrieved_at": retrieved_at,
            "rank": rank,
            "score": round(score, 6),
            "matched_terms": matched_terms,
            "authority": manifest["authorityPolicy"]["mode"],
        }
        for rank, (score, document, matched_terms) in enumerate(ranked, start=1)
    ]


def evaluate_retrieval_cases(manifest: dict, golden_cases: dict) -> dict:
    corpus = load_corpus(manifest)
    evaluation_date = golden_cases["evaluationDate"]
    required_fields = manifest["requiredProvenanceFields"]
    source_by_id = {source["sourceId"]: source for source in manifest["sources"]}
    precision_scores = []
    recall_scores = []
    freshness_scores = []
    provenance_scores = []
    missing_provenance = []
    stale_sources = []
    case_reports = []

    for case in golden_cases["cases"]:
        results = retrieve(
            case["query"],
            corpus,
            manifest,
            top_k=case["topK"],
            retrieved_at=evaluation_date,
        )
        expected = set(case["expectedSourceIds"])
        retrieved = {result["source_id"] for result in results}
        relevant = expected & retrieved

        precision_scores.append(len(relevant) / len(results) if results else 0.0)
        recall_scores.append(len(relevant) / len(expected) if expected else 1.0)

        fresh_count = 0
        provenance_count = 0
        for result in results:
            missing = missing_provenance_fields(result, required_fields)
            if missing:
                missing_provenance.append(
                    {
                        "caseId": case["id"],
                        "sourceId": result.get("source_id"),
                        "missingFields": missing,
                    }
                )
            else:
                provenance_count += 1

            freshness = source_freshness(
                source_by_id[result["source_id"]],
                manifest["snapshot"]["capturedAt"],
                evaluation_date,
            )
            if freshness["isFresh"]:
                fresh_count += 1
            else:
                stale_sources.append(
                    {
                        "caseId": case["id"],
                        "sourceId": result["source_id"],
                        "ageDays": freshness["ageDays"],
                        "maxSnapshotAgeDays": freshness["maxSnapshotAgeDays"],
                    }
                )

        freshness_scores.append(fresh_count / len(results) if results else 0.0)
        provenance_scores.append(provenance_count / len(results) if results else 0.0)
        case_reports.append(
            {
                "id": case["id"],
                "query": case["query"],
                "expectedSourceIds": sorted(expected),
                "retrievedSourceIds": [result["source_id"] for result in results],
                "precision": precision_scores[-1],
                "recall": recall_scores[-1],
                "freshness": freshness_scores[-1],
                "provenanceCoverage": provenance_scores[-1],
                "results": results,
            }
        )

    return {
        "harnessVersion": golden_cases["harnessVersion"],
        "authority": manifest["authorityPolicy"]["mode"],
        "authoritativeStateAllowed": False,
        "metrics": {
            "precision": _mean(precision_scores),
            "recall": _mean(recall_scores),
            "freshness": _mean(freshness_scores),
            "provenanceCoverage": _mean(provenance_scores),
        },
        "failures": {
            "missingProvenance": missing_provenance,
            "staleSources": stale_sources,
        },
        "cases": case_reports,
    }


def run_retrieval_provenance_evaluation() -> dict:
    return evaluate_retrieval_cases(load_source_manifest(), load_golden_cases())


def missing_provenance_fields(result: dict, required_fields: Iterable[str]) -> list[str]:
    missing = []
    for field in required_fields:
        if field not in result or result[field] in (None, "", []):
            missing.append(field)
    return missing


def source_freshness(source: dict, captured_at: str, evaluation_date: str) -> dict:
    max_age_days = source.get("freshnessPolicy", {}).get("maxSnapshotAgeDays")
    if max_age_days is None:
        max_age_days = 0
    age_days = (_parse_datetime(evaluation_date) - _parse_datetime(captured_at)).days
    return {
        "isFresh": age_days <= max_age_days,
        "ageDays": age_days,
        "maxSnapshotAgeDays": max_age_days,
    }


def guard_retrieval_for_authoritative_state(result: dict, required_fields: Iterable[str]) -> dict:
    reasons = []
    missing = missing_provenance_fields(result, required_fields)
    if missing:
        reasons.append({"code": "missing_provenance", "fields": missing})
    if result.get("authority") != EVALUATION_ONLY_AUTHORITY:
        reasons.append({"code": "unknown_or_live_authority_policy"})
    reasons.append({"code": "retrieval_is_evaluation_only"})
    return {
        "allowed": False,
        "allowedUses": ["offline_evaluation", "explainability_support"],
        "forbiddenUses": ["asserted_fact", "inferred_fact", "production_answer"],
        "reasons": reasons,
    }


def try_apply_retrieval_to_authoritative_state(
    store,
    fact_name: str,
    result: dict,
    required_fields: Iterable[str],
) -> dict:
    guard = guard_retrieval_for_authoritative_state(result, required_fields)
    if guard["allowed"]:
        raise AssertionError("Evaluation-only retrieval must never write authoritative facts.")
    return {
        **guard,
        "factName": fact_name,
        "stateMutated": False,
        "sourceId": result.get("source_id"),
        "existingFacts": sorted(store.get_unified_view().keys()),
    }


def _inverse_document_frequency(corpus: list[CorpusDocument]) -> dict[str, float]:
    document_count = len(corpus)
    all_terms = set().union(*(document.tokens.keys() for document in corpus))
    return {
        term: math.log((document_count + 1) / (1 + _document_frequency(term, corpus))) + 1
        for term in all_terms
    }


def _document_frequency(term: str, corpus: list[CorpusDocument]) -> int:
    return sum(1 for document in corpus if term in document.tokens)


def _tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 6) if values else 0.0


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


if __name__ == "__main__":
    print(json.dumps(run_retrieval_provenance_evaluation(), indent=2, sort_keys=True))
