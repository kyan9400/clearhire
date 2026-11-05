"""Hiring analytics with pandas: the funnel, time to hire, sources, scores and the most common gaps."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from clearhire.db.models import Application, Match, StageEvent, Vacancy

FUNNEL = ["new", "screening", "interview", "offer", "hired"]


async def frames(session: AsyncSession) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    applications = pd.DataFrame(
        (await session.execute(select(Application.id, Application.vacancy_id, Application.candidate_id,
                                      Application.stage, Application.source, Application.created_at))).all(),
        columns=["id", "vacancy_id", "candidate_id", "stage", "source", "created_at"],
    )  # fmt: skip
    events = pd.DataFrame(
        (await session.execute(select(StageEvent.application_id, StageEvent.stage, StageEvent.at))).all(),
        columns=["application_id", "stage", "at"],
    )
    matches = pd.DataFrame(
        (await session.execute(
            select(Match.candidate_id, Match.vacancy_id, Match.score, Match.must_met, Match.must_total, Match.results)
            .join(Application, (Application.candidate_id == Match.candidate_id) & (Application.vacancy_id == Match.vacancy_id))
        )).all(),
        columns=["candidate_id", "vacancy_id", "score", "must_met", "must_total", "results"],
    )  # fmt: skip
    for frame, column in ((applications, "stage"), (applications, "source"), (events, "stage")):
        if not frame.empty:
            frame[column] = frame[column].map(lambda value: getattr(value, "value", value))
    return applications, events, matches


def funnel(applications: pd.DataFrame, events: pd.DataFrame) -> list[dict[str, Any]]:
    """How many applications ever reached each stage, and the share that moved on from the previous one."""
    if events.empty:
        return [{"stage": s, "reached": 0, "conversion": None} for s in FUNNEL]
    reached = events.groupby("stage")["application_id"].nunique().reindex(FUNNEL, fill_value=0)
    reached["new"] = max(int(reached["new"]), len(applications))
    out, previous = [], None
    for stage in FUNNEL:
        count = int(reached[stage])
        out.append({"stage": stage, "reached": count,
                    "conversion": round(count / previous, 3) if previous else None})  # fmt: skip
        previous = count or None
    return out


def time_to_hire(applications: pd.DataFrame, events: pd.DataFrame) -> dict[str, float | None]:
    """Days from application to hire: median and 90th percentile."""
    hired = (
        events[events["stage"] == "hired"].groupby("application_id")["at"].min() if not events.empty else None
    )
    if hired is None or hired.empty or applications.empty:
        return {"median_days": None, "p90_days": None, "hires": 0}
    started = applications.set_index("id")["created_at"]
    days = (hired - started.reindex(hired.index)).dropna().dt.total_seconds() / 86400
    if days.empty:
        return {"median_days": None, "p90_days": None, "hires": 0}
    return {"median_days": round(float(days.median()), 1), "p90_days": round(float(np.percentile(days, 90)), 1),
            "hires": int(days.size)}  # fmt: skip


def sources(applications: pd.DataFrame) -> list[dict[str, Any]]:
    if applications.empty:
        return []
    table = applications.assign(advanced=applications["stage"].isin(["interview", "offer", "hired"]))
    grouped = table.groupby("source").agg(applications=("id", "count"), advanced=("advanced", "sum"))
    grouped["interview_rate"] = (grouped["advanced"] / grouped["applications"]).round(3)
    return [{"source": str(source), **{str(k): (int(v) if k != "interview_rate" else float(v)) for k, v in row.items()}}
            for source, row in grouped.iterrows()]  # fmt: skip


def score_distribution(matches: pd.DataFrame, bins: int = 10) -> list[dict[str, Any]]:
    if matches.empty:
        return []
    counts, edges = np.histogram(matches["score"], bins=bins, range=(0, 1))
    return [{"from": round(float(edges[i]), 2), "to": round(float(edges[i + 1]), 2), "count": int(c)}
            for i, c in enumerate(counts)]  # fmt: skip


def common_gaps(matches: pd.DataFrame, vacancies: dict[str, Vacancy], top: int = 10) -> list[dict[str, Any]]:
    """The must-haves applicants miss most often: a sign a vacancy asks for something the market lacks."""
    rows = []
    for _, match in matches.iterrows():
        vacancy = vacancies.get(str(match["vacancy_id"]))
        if vacancy is None:
            continue
        texts = {r["id"]: r["text"] for r in vacancy.requirements if r.get("must")}
        for result in match["results"]:
            if result["status"] == "missing" and result["requirement_id"] in texts:
                rows.append({"vacancy": vacancy.title, "requirement": texts[result["requirement_id"]]})
    if not rows:
        return []
    table = pd.DataFrame(rows).value_counts().rename("applicants").reset_index().head(top)
    return [{str(k): (int(v) if isinstance(v, (int, np.integer)) else v) for k, v in r.items()}
            for r in table.to_dict(orient="records")]  # fmt: skip


async def overview(session: AsyncSession) -> dict[str, Any]:
    applications, events, matches = await frames(session)
    vacancies = {str(v.id): v for v in (await session.execute(select(Vacancy))).scalars()}
    by_stage = applications["stage"].value_counts().to_dict() if not applications.empty else {}
    qualified = int((matches["must_met"] == matches["must_total"]).sum()) if not matches.empty else 0
    return {
        "applications": len(applications),
        "open_vacancies": sum(1 for v in vacancies.values() if v.status.value == "open"),
        "qualified_applications": qualified,
        "by_stage": {stage: int(by_stage.get(stage, 0)) for stage in [*FUNNEL, "rejected"]},
        "funnel": funnel(applications, events),
        "time_to_hire": time_to_hire(applications, events),
        "sources": sources(applications),
        "score_distribution": score_distribution(matches),
        "common_gaps": common_gaps(matches, vacancies),
    }
