"""Matching inside the service: parsed CVs and prepared vacancies cached by version, results stored."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from clearhire.cv.profile import CandidateProfile
from clearhire.db.models import Chunk as ChunkRow
from clearhire.db.models import Document, Match, Profile, Vacancy
from clearhire.embeddings import Embedder
from clearhire.matching import Chunk, IndexedCV, MatchResult, PreparedVacancy, match, prepare_vacancy
from clearhire.skills import Taxonomy
from clearhire.vacancy import Requirement, vacancy_query_text


def page_lookup(pages: Sequence[Sequence[int]]) -> object:
    spans = [(int(start), int(end)) for start, end in pages]

    def page_of(offset: int) -> int | None:
        for number, (start, end) in enumerate(spans, start=1):
            if start <= offset <= end:
                return number
        return None

    return page_of


@dataclass
class CachedCV:
    version: int
    cv: IndexedCV


class Matcher:
    def __init__(self, embedder: Embedder, taxonomy: Taxonomy) -> None:
        self.embedder = embedder
        self.taxonomy = taxonomy
        self._cvs: dict[uuid.UUID, CachedCV] = {}
        self._vacancies: dict[uuid.UUID, tuple[int, PreparedVacancy]] = {}

    def forget(self, candidate_id: uuid.UUID) -> None:
        self._cvs.pop(candidate_id, None)

    def prepared(self, vacancy: Vacancy) -> PreparedVacancy:
        cached = self._vacancies.get(vacancy.id)
        if cached and cached[0] == vacancy.requirements_version:
            return cached[1]
        requirements = [Requirement.from_dict(r) for r in vacancy.requirements]
        prepared = prepare_vacancy(
            requirements, vacancy_query_text(vacancy.title, vacancy.description), self.embedder
        )
        self._vacancies[vacancy.id] = (vacancy.requirements_version, prepared)
        return prepared

    async def load(
        self, session: AsyncSession, candidate_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, IndexedCV]:
        """Parsed CVs for the candidates (those with a profile), from the cache or in three queries."""
        out: dict[uuid.UUID, IndexedCV] = {}
        versions = dict((await session.execute(
            select(Profile.candidate_id, Profile.version).where(Profile.candidate_id.in_(candidate_ids))
        )).all())  # fmt: skip
        missing = []
        for candidate_id, version in versions.items():
            cached = self._cvs.get(candidate_id)
            if cached and cached.version == version:
                out[candidate_id] = cached.cv
            else:
                missing.append(candidate_id)
        if not missing:
            return out
        rows = (await session.execute(
            select(Profile, Document.text, Document.pages).join(Document, Document.id == Profile.document_id)
            .where(Profile.candidate_id.in_(missing))
        )).all()  # fmt: skip
        chunk_rows = (await session.execute(
            select(ChunkRow).where(ChunkRow.candidate_id.in_(missing)).order_by(ChunkRow.candidate_id, ChunkRow.ordinal)
        )).scalars().all()  # fmt: skip
        chunks: dict[uuid.UUID, list[ChunkRow]] = {}
        for chunk in chunk_rows:
            chunks.setdefault(chunk.candidate_id, []).append(chunk)
        for profile_row, text, pages in rows:
            profile = CandidateProfile.from_dict(text, profile_row.data)
            own = chunks.get(profile_row.candidate_id, [])
            vectors = (np.asarray([np.asarray(c.embedding, dtype=np.float32) for c in own], dtype=np.float32)
                       if own else np.zeros((0, self.embedder.dim), dtype=np.float32))  # fmt: skip
            cv = IndexedCV(profile, [Chunk(c.text, (c.start, c.end), c.section) for c in own], vectors,
                           page_lookup(pages))  # type: ignore[arg-type]  # fmt: skip
            self._cvs[profile_row.candidate_id] = CachedCV(profile_row.version, cv)
            out[profile_row.candidate_id] = cv
        return out

    async def compute(self, session: AsyncSession, vacancy: Vacancy, candidate_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, MatchResult]:  # fmt: skip
        """Match the candidates against the vacancy and store the results (replacing older ones)."""
        cvs = await self.load(session, candidate_ids)
        prepared = self.prepared(vacancy)
        versions = dict((await session.execute(
            select(Profile.candidate_id, Profile.version).where(Profile.candidate_id.in_(list(cvs)))
        )).all())  # fmt: skip
        results: dict[uuid.UUID, MatchResult] = {}
        rows = []
        for candidate_id, cv in cvs.items():
            result = match(cv, prepared, self.taxonomy)
            results[candidate_id] = result
            rows.append({
                "candidate_id": candidate_id, "vacancy_id": vacancy.id,
                "requirements_version": vacancy.requirements_version, "profile_version": versions[candidate_id],
                "score": result.score, "must_have_gaps": result.must_have_gaps, "must_met": result.must_met,
                "must_total": result.must_total, "semantic": result.semantic,
                "results": [r for r in result.to_dict()["results"]],
            })  # fmt: skip
        for start in range(0, len(rows), 500):
            batch = rows[start : start + 500]
            statement = insert(Match).values(batch)
            await session.execute(statement.on_conflict_do_update(
                index_elements=[Match.candidate_id, Match.vacancy_id],
                set_={column: statement.excluded[column] for column in batch[0] if column not in ("candidate_id", "vacancy_id")},
            ))  # fmt: skip
        return results

    async def drop_stale(self, session: AsyncSession, vacancy: Vacancy) -> None:
        await session.execute(delete(Match).where(
            Match.vacancy_id == vacancy.id, Match.requirements_version != vacancy.requirements_version
        ))  # fmt: skip
