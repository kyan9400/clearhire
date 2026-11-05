"""The evaluation: reads the synthetic dataset's files and scores Clearhire against their ground truth.

    clearhire eval --dataset ../datasets/synthetic --out ../eval

Nothing here sees the truth until scoring: CVs are read from their files (OCR for scans, when Tesseract
is available), vacancies from their text.
"""

from __future__ import annotations

import json
import statistics
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from clearhire.cv.profile import CandidateProfile, extract_profile
from clearhire.embeddings import Embedder
from clearhire.eval.metrics import BM25, ndcg_at, precision_at, recall_at
from clearhire.ingest import TesseractOcr, UnreadableDocument, read_document
from clearhire.matching import (
    IndexedCV,
    PreparedVacancy,
    index_cv,
    match,
    prepare_vacancy,
    semantic_similarity,
)
from clearhire.skills import Taxonomy
from clearhire.synth.dataset import load_dataset
from clearhire.synth.generate import REFERENCE_DATE, TruthCandidate, TruthVacancy, relevance
from clearhire.vacancy import Requirement, parse_requirements, vacancy_query_text


@dataclass
class Parsed:
    truth: TruthCandidate
    profile: CandidateProfile
    blind: IndexedCV
    open: IndexedCV  # the same CV embedded without blind mode, for the fairness comparison
    seconds: float


@dataclass
class Report:
    meta: dict[str, Any] = field(default_factory=dict)
    extraction: dict[str, Any] = field(default_factory=dict)
    parsing: dict[str, Any] = field(default_factory=dict)
    ranking: dict[str, Any] = field(default_factory=dict)
    fairness: dict[str, Any] = field(default_factory=dict)
    speed: dict[str, Any] = field(default_factory=dict)


def _parse(path: Path, taxonomy: Taxonomy, embedder: Embedder, ocr: TesseractOcr | None) -> tuple[CandidateProfile, IndexedCV, IndexedCV, float]:  # fmt: skip
    started = time.perf_counter()
    document = read_document(path.read_bytes(), ocr=ocr)
    profile = extract_profile(document.text, taxonomy, today=REFERENCE_DATE)
    blind = index_cv(profile, embedder, document.page_of, blind=True)
    seconds = time.perf_counter() - started
    open_ = index_cv(profile, embedder, document.page_of, blind=False)
    return profile, blind, open_, seconds


def _f1(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}


def _extraction(parsed: list[Parsed], taxonomy: Taxonomy) -> dict[str, Any]:
    groups: dict[str, list[Parsed]] = defaultdict(list)
    for item in parsed:
        groups["all"].append(item)
        groups[f"format:{item.truth.file_format}"].append(item)
        groups[f"language:{item.truth.language}"].append(item)
    out: dict[str, Any] = {}
    for name, items in sorted(groups.items()):
        tp = fp = fn = 0
        month_errors: list[int] = []
        skill_month_errors: list[int] = []
        language_hits = language_total = 0
        degree_hits = 0
        for item in items:
            truth_skills = taxonomy.closure(item.truth.explicit_skills())
            found = set(item.profile.skills)
            tp += len(truth_skills & found)
            fp += len(found - truth_skills)
            fn += len(truth_skills - found)
            month_errors.append(abs(item.profile.total_months - item.truth.total_months()))
            truth_months = item.truth.skill_months(taxonomy)
            for skill, months in truth_months.items():
                parsed_months = item.profile.skills[skill].months if skill in item.profile.skills else 0
                skill_month_errors.append(abs(parsed_months - months))
            for code, level in item.truth.languages.items():
                language_total += 1
                found_language = item.profile.languages.get(code)
                language_hits += int(found_language is not None and found_language.level == level)
            parsed_degree = item.profile.education.degree if item.profile.education else 0
            degree_hits += int(parsed_degree == item.truth.degree)
        out[name] = {
            "cvs": len(items),
            "skills": _f1(tp, fp, fn),
            "experience_months_mae": round(statistics.mean(month_errors), 2),
            "experience_exact": round(sum(1 for e in month_errors if e == 0) / len(month_errors), 4),
            "skill_months_mae": round(statistics.mean(skill_month_errors), 2) if skill_month_errors else 0.0,
            "language_level_accuracy": round(language_hits / language_total, 4) if language_total else 0.0,
            "degree_accuracy": round(degree_hits / len(items), 4),
        }
    return out


def _same_requirement(parsed: Requirement, truth: Requirement) -> dict[str, bool]:
    return {
        "kind": parsed.kind == truth.kind,
        "must": parsed.must == truth.must,
        "skills": sorted(parsed.skills) == sorted(truth.skills),
        "any_of": parsed.any_of == truth.any_of or len(truth.skills) < 2,
        "years": (parsed.min_years or 0) == (truth.min_years or 0),
        "language": (parsed.language, parsed.min_level) == (truth.language, truth.min_level),
        "degree": (parsed.min_degree or 0) == (truth.min_degree or 0),
    }


def written_order(requirements: list[Requirement]) -> list[Requirement]:
    """The order a vacancy text lists requirements in: must-haves, then nice-to-haves."""
    return [r for r in requirements if r.must] + [r for r in requirements if not r.must]


def _parsing(vacancies: list[TruthVacancy], parsed: dict[str, list[Requirement]]) -> dict[str, Any]:
    fields: dict[str, list[bool]] = defaultdict(list)
    exact: list[bool] = []
    count_ok: list[bool] = []
    for vacancy in vacancies:
        found = parsed[vacancy.id]
        written = written_order(vacancy.requirements)
        count_ok.append(len(found) == len(written))
        for truth, mine in zip(written, found, strict=False):
            checks = _same_requirement(mine, truth)
            for key, value in checks.items():
                fields[key].append(value)
            exact.append(all(checks.values()))
        exact.extend([False] * max(0, len(vacancy.requirements) - len(found)))
    return {
        "vacancies": len(vacancies),
        "requirements": sum(len(v.requirements) for v in vacancies),
        "exact": round(sum(exact) / len(exact), 4),
        "count_matches": round(sum(count_ok) / len(count_ok), 4),
        "fields": {key: round(sum(v) / len(v), 4) for key, v in fields.items()},
    }


def _ranking(vacancies: list[TruthVacancy], prepared: dict[str, PreparedVacancy],
             prepared_truth: dict[str, PreparedVacancy], parsed: list[Parsed],
             taxonomy: Taxonomy) -> dict[str, Any]:  # fmt: skip
    bm25 = BM25([item.profile.text for item in parsed])
    methods: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    qualified = {"tp": 0, "fp": 0, "fn": 0}
    seconds: list[float] = []
    for vacancy in vacancies:
        grades = [relevance(vacancy, item.truth, taxonomy) for item in parsed]
        rankings: dict[str, list[int]] = {}
        started = time.perf_counter()
        results = [match(item.blind, prepared[vacancy.id], taxonomy) for item in parsed]
        rankings["clearhire"] = sorted(range(len(parsed)), key=lambda i: (results[i].rank_key(), i))
        seconds.append(time.perf_counter() - started)
        exact = [match(item.blind, prepared_truth[vacancy.id], taxonomy) for item in parsed]
        rankings["clearhire, true requirements"] = sorted(
            range(len(parsed)), key=lambda i: (exact[i].rank_key(), i)
        )
        semantic = [semantic_similarity(item.blind, prepared[vacancy.id].vacancy_vector) for item in parsed]
        rankings["embeddings only"] = sorted(range(len(parsed)), key=lambda i: (-semantic[i], i))
        keyword = bm25.scores(vacancy_query_text(vacancy.title, vacancy.text))
        rankings["keyword (BM25)"] = sorted(range(len(parsed)), key=lambda i: (-keyword[i], i))
        rankings["perfect ranking (upper bound)"] = sorted(range(len(parsed)), key=lambda i: (-grades[i], i))
        for method, order in rankings.items():
            ranked = [grades[i] for i in order]
            methods[method]["ndcg@10"].append(ndcg_at(ranked, grades, 10))
            methods[method]["p@5"].append(precision_at(ranked, 5))
            methods[method]["recall@20"].append(recall_at(ranked, grades, 20))
        for result, grade in zip(results, grades, strict=True):
            predicted = result.qualified
            actual = grade >= 2
            qualified["tp"] += int(predicted and actual)
            qualified["fp"] += int(predicted and not actual)
            qualified["fn"] += int(actual and not predicted)
    table = {method: {metric: round(statistics.mean(values), 4) for metric, values in scores.items()}
             for method, scores in methods.items()}  # fmt: skip
    return {"methods": table, "qualified": _f1(qualified["tp"], qualified["fp"], qualified["fn"]),
            "pairs": len(vacancies) * len(parsed), "rank_pool_ms": round(1000 * statistics.mean(seconds), 1)}  # fmt: skip


def _fairness(root: Path, taxonomy: Taxonomy, embedder: Embedder, ocr: TesseractOcr | None,
              vacancies: list[TruthVacancy], prepared: dict[str, PreparedVacancy],
              by_id: dict[str, TruthCandidate]) -> dict[str, Any]:  # fmt: skip
    rows = [
        json.loads(line)
        for line in (root / "fairness.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    variants: dict[str, dict[str, tuple[IndexedCV, IndexedCV]]] = defaultdict(dict)
    for row in rows:
        _, blind, open_, _ = _parse(root / row["file"], taxonomy, embedder, ocr)
        variants[row["id"]][row["variant"]] = (blind, open_)
    out: dict[str, Any] = {}
    for mode, slot in (("blind", 0), ("open", 1)):
        per_variant: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for candidate_id, versions in variants.items():
            archetype = by_id[candidate_id].archetype
            for vacancy in [v for v in vacancies if v.archetype == archetype]:
                base = match(versions["original"][slot], prepared[vacancy.id], taxonomy)
                for variant in ("gender", "origin", "age"):
                    other = match(versions[variant][slot], prepared[vacancy.id], taxonomy)
                    stats = per_variant[variant]
                    stats["score_delta"].append(abs(other.score - base.score))
                    stats["semantic_delta"].append(abs(other.semantic - base.semantic))
                    stats["gaps_changed"].append(float(other.must_have_gaps != base.must_have_gaps))
                    stats["identical"].append(float(other.rank_key() == base.rank_key()))
        out[mode] = {
            variant: {
                "comparisons": len(stats["identical"]),
                "identical": round(statistics.mean(stats["identical"]), 4),
                "max_score_delta": round(max(stats["score_delta"]), 4),
                "max_semantic_delta": round(max(stats["semantic_delta"]), 5),
                "gaps_changed": round(statistics.mean(stats["gaps_changed"]), 4),
            }
            for variant, stats in per_variant.items()
        }
    out["candidates"] = len(variants)
    return out


def run(root: Path, taxonomy: Taxonomy, embedder: Embedder, ocr: TesseractOcr | None,
        progress: Callable[[str], None] = lambda _m: None) -> Report:  # fmt: skip
    candidates, vacancies = load_dataset(root)
    report = Report(meta={"dataset": root.name, "candidates": len(candidates), "vacancies": len(vacancies),
                          "embedding_model": embedder.name, "ocr": bool(ocr and ocr.available),
                          "reference_date": REFERENCE_DATE.isoformat()})  # fmt: skip
    parsed: list[Parsed] = []
    skipped: dict[str, str] = {}
    for index, truth in enumerate(candidates):
        if index % 50 == 0:
            progress(f"reading CVs {index}/{len(candidates)}")
        try:
            profile, blind, open_, seconds = _parse(root / truth.file, taxonomy, embedder, ocr)
        except UnreadableDocument as exc:
            skipped[truth.id] = str(exc)
            continue
        parsed.append(Parsed(truth, profile, blind, open_, seconds))
    report.meta["read"] = len(parsed)
    report.meta["skipped"] = len(skipped)
    report.meta["skipped_reasons"] = sorted(set(skipped.values()))

    progress("extraction")
    report.extraction = _extraction(parsed, taxonomy)
    parsed_requirements = {v.id: parse_requirements(v.text, taxonomy) for v in vacancies}
    report.parsing = _parsing(vacancies, parsed_requirements)
    prepared = {v.id: prepare_vacancy(parsed_requirements[v.id], vacancy_query_text(v.title, v.text), embedder)
                for v in vacancies}  # fmt: skip
    prepared_truth = {v.id: prepare_vacancy(written_order(v.requirements), vacancy_query_text(v.title, v.text), embedder)
                      for v in vacancies}  # fmt: skip

    progress("ranking")
    report.ranking = _ranking(vacancies, prepared, prepared_truth, parsed, taxonomy)
    progress("fairness")
    report.fairness = _fairness(
        root, taxonomy, embedder, ocr, vacancies, prepared, {c.id: c for c in candidates}
    )

    digital = [p.seconds for p in parsed if p.truth.file_format != "scan"]
    scans = [p.seconds for p in parsed if p.truth.file_format == "scan"]
    report.speed = {
        "read_and_index_cv_ms_p50": round(1000 * float(np.median(digital)), 1) if digital else None,
        "read_and_index_scan_ms_p50": round(1000 * float(np.median(scans)), 1) if scans else None,
        "rank_pool_ms": report.ranking["rank_pool_ms"],
        "pool_size": len(parsed),
    }
    return report


def to_markdown(report: Report) -> str:
    meta = report.meta
    lines = [
        "# Clearhire evaluation",
        "",
        f"Synthetic dataset: {meta['candidates']} CVs ({meta['read']} read"
        + (f", {meta['skipped']} skipped: {'; '.join(meta['skipped_reasons'])}" if meta["skipped"] else "")
        + f"), {meta['vacancies']} vacancies. Embeddings: `{meta['embedding_model']}`. "
        f"OCR: {'Tesseract' if meta['ocr'] else 'not available, scans skipped'}. Reference date {meta['reference_date']}.",
        "",
        "## Ranking candidates for a vacancy",
        "",
        "Every vacancy ranks the whole pool. Relevance comes from the generator's truth: 3 = all must-haves and",
        "at least half the nice-to-haves, 2 = all must-haves, 1 = at least 60% of must-haves, 0 = less.",
        "",
        "| Method | nDCG@10 | Precision@5 | Recall@20 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for method, scores in report.ranking["methods"].items():
        lines.append(
            f"| {method} | {scores['ndcg@10']:.3f} | {scores['p@5']:.3f} | {scores['recall@20']:.3f} |"
        )
    q = report.ranking["qualified"]
    lines += [
        "",
        f'"Meets every must-have" (each one fully met) against the truth, over {report.ranking["pairs"]:,} vacancy-candidate '
        f"pairs: precision {q['precision']:.3f}, recall {q['recall']:.3f}, F1 {q['f1']:.3f}.",
        "",
        "## Reading CVs",
        "",
        "| CVs | Count | Skills F1 | Precision | Recall | Experience exact | Experience MAE (months) | Skill months MAE | Language level | Degree |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for group, row in report.extraction.items():
        s = row["skills"]
        lines.append(
            f"| {group} | {row['cvs']} | {s['f1']:.3f} | {s['precision']:.3f} | {s['recall']:.3f} | "
            f"{row['experience_exact']:.1%} | {row['experience_months_mae']:.2f} | {row['skill_months_mae']:.2f} | "
            f"{row['language_level_accuracy']:.1%} | {row['degree_accuracy']:.1%} |"
        )
    p = report.parsing
    lines += [
        "",
        "## Reading vacancy requirements",
        "",
        f"{p['requirements']} requirement lines in {p['vacancies']} vacancies: {p['exact']:.1%} parsed exactly "
        f"(kind, must-have, skills, any-of, years, language level, degree); the requirement count is right for "
        f"{p['count_matches']:.1%} of vacancies.",
        "",
        "| Field | Accuracy |",
        "| --- | ---: |",
        *[f"| {key} | {value:.1%} |" for key, value in p["fields"].items()],
        "",
        "## Fairness: the same CV with only personal details changed",
        "",
        f"{report.fairness['candidates']} CVs, each re-rendered as the other gender (in Russian also the verb endings), "
        "with a name of another origin, and 15 years older; each version is matched against its role's vacancies.",
        "",
        "| Mode | Change | Comparisons | Identical result | Max score change | Max semantic change | Must-have gaps changed |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for mode in ("blind", "open"):
        for variant, row in report.fairness[mode].items():
            lines.append(
                f"| {mode} | {variant} | {row['comparisons']} | {row['identical']:.1%} | {row['max_score_delta']:.4f} | "
                f"{row['max_semantic_delta']:.5f} | {row['gaps_changed']:.1%} |"
            )
    speed = report.speed
    lines += [
        "",
        "## Speed",
        "",
        f"Reading and indexing a CV (median): {speed['read_and_index_cv_ms_p50']} ms"
        + (
            f"; a scanned CV with OCR: {speed['read_and_index_scan_ms_p50']} ms"
            if speed["read_and_index_scan_ms_p50"]
            else ""
        )
        + f". Ranking a pool of {speed['pool_size']} CVs for one vacancy: {speed['rank_pool_ms']} ms.",
        "",
    ]
    return "\n".join(lines)


def save(report: Report, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    data = {"meta": report.meta, "extraction": report.extraction, "parsing": report.parsing,
            "ranking": report.ranking, "fairness": report.fairness, "speed": report.speed}  # fmt: skip
    (out / "results.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "results.md").write_text(to_markdown(report), encoding="utf-8", newline="\n")
