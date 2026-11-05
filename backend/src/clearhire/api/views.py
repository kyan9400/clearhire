"""Turning matcher objects into API responses, with personal details blacked out in blind mode."""

from __future__ import annotations

from clearhire.api.schemas import EvidenceOut
from clearhire.fairness import pii_spans, redact_for_display
from clearhire.matching import Evidence, IndexedCV
from clearhire.text import quote


def evidence_view(cv: IndexedCV, evidence: Evidence, *, blind: bool) -> EvidenceOut:
    if not blind or evidence.source == "inferred":
        return EvidenceOut(quote=evidence.quote, highlight=evidence.highlight, page=evidence.page,
                           section=evidence.section, source=evidence.source)  # fmt: skip
    redacted = redact_for_display(
        cv.profile.text, pii_spans(cv.profile)
    )  # same length, so offsets still hold
    text, start, end = quote(redacted, evidence.span[0], evidence.span[1])
    return EvidenceOut(quote=text, highlight=(start, end), page=evidence.page, section=evidence.section,
                       source=evidence.source)  # fmt: skip
