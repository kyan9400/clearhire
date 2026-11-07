"""Questions the assistant refuses before the model sees them: about traits that must not influence hiring.

Age, gender, pregnancy and family, ethnicity and nationality, religion, health and disability, sexual
orientation and political views (Labour Code of the Russian Federation, art. 3 and 64; the same list in
most other jurisdictions). The model never sees these details anyway, so it could only guess, and a guess
is exactly the bias blind screening exists to remove. Matching is on word stems, in English and Russian,
and narrow on purpose: "race conditions", "healthcare" or "client orientation" are fair questions.
"""

from __future__ import annotations

import re

_PROTECTED = re.compile(
    r"""
    \b(?:how\s+old|age[ds]?|birth\w*|born|young\w*|elderly|retire\w*
      |gender|sex|male|female|man|woman|men|women|girl|guy
      |pregnan\w*|maternity|paternity|married|marital|spouse|wife|husband|kids?|children|family\s+plans?
      |religio\w*|church|mosque|muslim|christian|jewish|orthodox\s+christian
      |ethnic\w*|racial|nationality|national\s+origin
      |health\s+(?:condition|issue|problem)s?|disab\w*|illness|chronic\w*|sick\w*
      |sexual\w*|gay|lesbian|political\s+(?:views?|party|affiliation)|politics)\b
    |(?:возраст\w*|сколько\s+(?:ему|ей)\s+лет|год\w*\s+рождения|родил\w*|пенсион\w*|пожил\w*
      |\bпол\b|мужчин\w*|женщин\w*|девушк\w*
      |беремен\w*|декрет\w*|замуж\w*|женат\w*|супруг\w*|\bдет(?:и|ей|ям|ьми)\b|ребен\w*|ребён\w*|семейн\w*
      |религи\w*|вероисповед\w*|верующ\w*|национальност\w*|этнич\w*
      |здоровь\w*|инвалид\w*|болезн\w*|болеет|сексуальн\w*|политическ\w*\s+взгляд\w*)
    """,
    re.IGNORECASE | re.VERBOSE,
)

REFUSAL = {
    "en": (
        "I can't help with that. Age, gender, family, health, religion, ethnicity and similar traits must not "
        "influence hiring, and Clearhire hides them from the model. Ask about skills, experience or the "
        "requirements instead."
    ),
    "ru": (
        "С этим я не помогу. Возраст, пол, семья, здоровье, религия, национальность и подобные признаки не "
        "должны влиять на найм, и Clearhire скрывает их от модели. Спросите о навыках, опыте или требованиях."
    ),
}


def protected_topic(question: str) -> str | None:
    """The protected trait a question is about, or None."""
    match = _PROTECTED.search(question)
    return match.group(0).lower() if match else None


def language_of(text: str) -> str:
    cyrillic = sum("а" <= ch.lower() <= "я" or ch in "ёЁ" for ch in text)
    latin = sum("a" <= ch.lower() <= "z" for ch in text)
    return "ru" if cyrillic > latin else "en"
