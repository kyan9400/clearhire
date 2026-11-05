"""Writing synthetic CVs (PDF, Word, scanned PDF) and vacancy texts.

A CV is first laid out as blocks (title, lines, headings, bullets, a two-column sidebar), then drawn by
the PDF or Word writer. Wording is chosen from the candidate id, never from gender or name, so the
fairness evaluation can render the same CV for a man and a woman and compare like with like: only the
header and, in Russian, the past-tense verb endings differ.
"""

from __future__ import annotations

import hashlib
import io
import random
from dataclasses import dataclass, field
from pathlib import Path

from clearhire.skills import Taxonomy, load_taxonomy
from clearhire.synth.archetypes import Archetype
from clearhire.synth.bullets import BULLETS, GENERIC, fitting_order
from clearhire.synth.generate import REFERENCE_DATE, TruthCandidate, TruthVacancy, translit
from clearhire.text import fold

MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTHS_EN_LONG = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
                  "October", "November", "December"]  # fmt: skip
MONTHS_RU = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь",
             "ноябрь", "декабрь"]  # fmt: skip
MONTHS_RU_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября",
                 "октября", "ноября", "декабря"]  # fmt: skip

TEMPLATES = {"ru": ("classic", "hh", "compact"), "en": ("classic", "compact", "sidebar")}

PLAIN = [
    ("Worked closely with product managers and designers.", "Взаимодействовал{a} с менеджерами продукта и дизайнерами."),
    ("Took part in planning sessions and estimations.", "Участвовал{a} в планировании и оценке задач."),
    ("Onboarded new colleagues and wrote internal guides.", "Помогал{a} новым коллегам и писал{a} внутренние инструкции."),
]  # fmt: skip
LEAD = ("Led a team of {n} engineers.", "Руководил{a} командой из {n} разработчиков.")

LEVEL_EN = {1: "Beginner", 2: "Elementary", 3: "Intermediate", 4: "Upper-Intermediate", 5: "Advanced",
            6: "Proficient", 7: "Native"}  # fmt: skip
LEVEL_RU = {1: "Начальный", 2: "Элементарный", 3: "Средний", 4: "Средне-продвинутый", 5: "Продвинутый",
            6: "В совершенстве", 7: "Родной"}  # fmt: skip
CEFR = {1: "A1", 2: "A2", 3: "B1", 4: "B2", 5: "C1", 6: "C2"}
LANG_EN = {"en": "English", "ru": "Russian", "ar": "Arabic", "zh": "Chinese", "de": "German", "fr": "French",
           "es": "Spanish", "tr": "Turkish"}  # fmt: skip
LANG_RU = {"en": "Английский", "ru": "Русский", "ar": "Арабский", "zh": "Китайский", "de": "Немецкий",
           "fr": "Французский", "es": "Испанский", "tr": "Турецкий"}  # fmt: skip


@dataclass
class Block:
    kind: str  # title | subtitle | line | heading | bullet | gap | sidebar
    text: str = ""
    left: list[Block] = field(default_factory=list)
    right: list[Block] = field(default_factory=list)


def stable_rng(*parts: object) -> random.Random:
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "little"))


def surface(
    skill_id: str, taxonomy: Taxonomy, rng: random.Random, language: str, *, in_sentence: bool = True
) -> str:
    """How a CV writes a skill: usually its name, sometimes another common spelling."""
    skill = taxonomy.skills[skill_id]
    detectable = [a for a in skill.aliases if not a.endswith("*")]
    if fold(skill.name) in detectable and rng.random() < 0.75:
        return skill.name
    options = [
        a
        for a in detectable
        if (language == "ru" and not in_sentence) or not any("а" <= ch <= "я" for ch in a)
    ]
    # Russian aliases are nominative ("машинное обучение"); inside a sentence they would need declension
    if not options:
        return skill.name
    alias = rng.choice(options)
    if alias.isascii() and alias.islower() and alias.isalpha() and len(alias) > 3:
        return alias.capitalize()
    return alias


def _ru_years(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} год"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} года"
    return f"{n} лет"


def _ru_years_genitive(n: int) -> str:
    """After "от" and "не менее": "от 1 года", "от 3 лет", "от 21 года"."""
    return f"{n} года" if n % 10 == 1 and n % 100 != 11 else f"{n} лет"


def _ru_months(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} месяц"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} месяца"
    return f"{n} месяцев"


def ru_duration(months: int) -> str:
    years, rest = divmod(months, 12)
    parts = [_ru_years(years)] if years else []
    if rest:
        parts.append(_ru_months(rest))
    return " ".join(parts) or _ru_months(0)


def _date(ym: tuple[int, int], style: str, language: str) -> str:
    year, month = ym
    if style == "numeric":
        return f"{month:02d}.{year}" if language == "ru" else f"{month:02d}/{year}"
    if style == "year":
        return str(year)
    if language == "ru":
        name = MONTHS_RU[month - 1]
        return f"{name.capitalize() if style == 'hh' else name} {year}"
    return f"{(MONTHS_EN_LONG if style == 'long' else MONTHS_EN)[month - 1]} {year}"


def _range(position_start: tuple[int, int], position_end: tuple[int, int], current: bool, style: str,
           language: str) -> str:  # fmt: skip
    if current:
        present = {"ru": {"hh": "настоящее время", "numeric": "н.в."}.get(style, "настоящее время")}.get(
            language, "Present"
        )
        end = present
    else:
        end = _date(position_end, style, language)
    dash = " — " if style in ("hh", "long") or language == "ru" else " – "
    return f"{_date(position_start, style, language)}{dash}{end}"


def _bullets(candidate: TruthCandidate, index: int, taxonomy: Taxonomy, gender: str) -> list[str]:
    position = candidate.positions[index]
    rng = stable_rng(candidate.id, "bullets", index)
    a = "а" if gender == "f" else ""
    skills = [s for s in position.skills if s != "team_lead"]
    rng.shuffle(skills)
    out: list[str] = []
    keys = list(BULLETS)
    rng.shuffle(keys)
    while skills:
        size = min(len(skills), rng.choice([1, 2, 2, 3]))
        group, skills = skills[:size], skills[size:]
        categories = [taxonomy.skills[s].category for s in group]
        fitting = [(k, order) for k in keys if len(BULLETS[k][0]) == size
                   and (order := fitting_order(BULLETS[k][0], group, categories)) is not None]  # fmt: skip
        specific = [item for item in fitting if item[0] not in GENERIC]
        key, order = (specific or fitting)[0]
        words = {
            f"s{slot + 1}": surface(group[i], taxonomy, rng, candidate.language)
            for slot, i in enumerate(order)
        }
        _, english, russian = BULLETS[key]
        template = russian if candidate.language == "ru" else english
        out.append(template.format(a=a, n=rng.randint(15, 60), **words))
    if "team_lead" in position.skills:
        template = LEAD[1 if candidate.language == "ru" else 0]
        out.insert(0, template.format(a=a, n=candidate.lead_team or 4))
    if rng.random() < 0.5:
        plain = PLAIN[rng.randrange(len(PLAIN))][1 if candidate.language == "ru" else 0]
        out.append(plain.format(a=a))
    return out


def _languages(candidate: TruthCandidate, template: str) -> list[str]:
    rng = stable_rng(candidate.id, "languages")
    lines = []
    for code, level in candidate.languages.items():
        if candidate.language == "ru":
            name = LANG_RU[code]
            if level == 7:
                lines.append(f"{name} — Родной")
            elif template == "hh":
                lines.append(f"{name} — {CEFR[level]} — {LEVEL_RU[level]}")
            elif rng.random() < 0.5:
                lines.append(f"{name} язык: {CEFR[level]}")
            else:
                lines.append(f"{name} — {LEVEL_RU[level].lower()}")
        else:
            name = LANG_EN[code]
            if level == 7:
                lines.append(f"{name} — native")
            elif rng.random() < 0.5:
                lines.append(f"{name} — {CEFR[level]} ({LEVEL_EN[level]})")
            else:
                lines.append(f"{name}: {CEFR[level]}")
    return lines


def _education(candidate: TruthCandidate) -> str | None:
    if candidate.degree == 0:
        return None
    if candidate.language == "ru":
        if candidate.degree == 1:
            return f"Колледж информационных технологий, {candidate.study_field}, {candidate.graduation_year}"
        word = {2: stable_rng(candidate.id, "deg").choice(["бакалавр", "специалист"]), 3: "магистр",
                4: "кандидат наук"}[candidate.degree]  # fmt: skip
        return f"{candidate.university} — {word}, {candidate.study_field}, {candidate.graduation_year}"
    if candidate.degree == 1:
        return f"City College — diploma in {candidate.study_field}, {candidate.graduation_year}"
    word = {2: "BSc", 3: "MSc", 4: "PhD"}[candidate.degree]
    return f"{candidate.university} — {word} {candidate.study_field}, {candidate.graduation_year}"


def _age(candidate: TruthCandidate) -> int:
    birth = candidate.birth
    return (
        REFERENCE_DATE.year
        - birth.year
        - ((REFERENCE_DATE.month, REFERENCE_DATE.day) < (birth.month, birth.day))
    )


def contacts(candidate: TruthCandidate) -> tuple[str, str, str]:
    digits = int(hashlib.sha256(candidate.id.encode()).hexdigest()[:7], 16) % 10_000_000
    phone = f"+7 000 {digits // 10000:03d}-{digits // 100 % 100:02d}-{digits % 100:02d}"
    latin = (
        translit(candidate.first_name).lower()
        if not candidate.first_name.isascii()
        else candidate.first_name.lower()
    )
    surname = (
        translit(candidate.last_name).lower()
        if not candidate.last_name.isascii()
        else candidate.last_name.lower()
    )
    email = f"{latin}.{surname}".replace(" ", "").replace("'", "") + "@example.com"
    return phone, email, f"@cand_{candidate.id[1:]}"


def cv_blocks(candidate: TruthCandidate, template: str, taxonomy: Taxonomy | None = None, *,
              gender: str | None = None) -> list[Block]:  # fmt: skip
    taxonomy = taxonomy or load_taxonomy()
    gender = gender or candidate.gender
    ru = candidate.language == "ru"
    rng = stable_rng(candidate.id, "layout")
    phone, email, telegram = contacts(candidate)
    title = candidate.positions[0].title
    blocks: list[Block] = [Block("title", candidate.full_name)]
    if template == "hh":
        age = _age(candidate)
        born = "родилась" if gender == "f" else "родился"
        sex = "Женщина" if gender == "f" else "Мужчина"
        birth = candidate.birth
        blocks.append(
            Block(
                "line",
                f"{sex}, {_ru_years(age)}, {born} {birth.day} {MONTHS_RU_GEN[birth.month - 1]} {birth.year}",
            )
        )
        blocks += [
            Block("line", candidate.city),
            Block("line", phone),
            Block("line", email),
            Block("line", f"Telegram: {telegram}"),
        ]
    else:
        blocks.append(Block("subtitle", f"{title} · {candidate.city}"))
        blocks.append(Block("line", f"{phone} · {email} · Telegram: {telegram}"))
    total = candidate.total_months()
    years = total // 12
    summary_heading = {"classic": "О себе" if ru else "Summary", "hh": "Обо мне", "compact": "О СЕБЕ" if ru else "PROFILE",
                       "sidebar": "Profile"}[template]  # fmt: skip
    summary = (f"{title}, опыт работы {ru_duration(total)}." if ru
               else f"{title} with {years or 1}+ years of experience.")  # fmt: skip

    style = {"classic": "short", "hh": "hh", "compact": "year" if rng.random() < 0.3 else "numeric",
             "sidebar": "long"}[template]  # fmt: skip
    if ru and style == "short":
        style = "short" if rng.random() < 0.6 else "numeric"
    experience_heading = {
        "classic": "Опыт работы" if ru else "Work Experience",
        "hh": f"Опыт работы — {ru_duration(total)}",
        "compact": "ОПЫТ РАБОТЫ" if ru else "EXPERIENCE",
        "sidebar": "Experience",
    }[template]
    experience: list[Block] = [Block("heading", experience_heading)]
    for index, position in enumerate(candidate.positions):
        dates = _range(position.start, position.end, position.current, style, candidate.language)
        if template == "hh":
            experience += [Block("line", dates), Block("line", ru_duration(position.months)),
                           Block("line", position.company), Block("line", position.title)]  # fmt: skip
        elif template == "compact":
            experience.append(Block("line", f"{position.company} | {position.title} | {dates}"))
        else:
            experience += [Block("line", f"{position.title} — {position.company}"), Block("line", dates)]
        experience += [Block("bullet", text) for text in _bullets(candidate, index, taxonomy, gender)]
        experience.append(Block("gap"))

    skills_heading = {"classic": "Навыки" if ru else "Skills", "hh": "Ключевые навыки",
                      "compact": "ТЕХНИЧЕСКИЕ НАВЫКИ" if ru else "TECHNICAL SKILLS", "sidebar": "Key skills"}[template]  # fmt: skip
    names = [
        surface(s, taxonomy, stable_rng(candidate.id, "skill", s), candidate.language, in_sentence=False)
        for s in candidate.listed_skills
    ]
    names = [taxonomy.skills[s].strict[0] if taxonomy.skills[s].strict and rng.random() < 0.5 else n
             for s, n in zip(candidate.listed_skills, names, strict=True)]  # fmt: skip
    skills_blocks = [Block("heading", skills_heading), Block("line", ", ".join(names))] if names else []
    language_heading = {"classic": "Языки" if ru else "Languages", "hh": "Знание языков",
                        "compact": "ЯЗЫКИ" if ru else "LANGUAGES", "sidebar": "Languages"}[template]  # fmt: skip
    language_blocks = [Block("heading", language_heading)] + [
        Block("line", line) for line in _languages(candidate, template)
    ]
    education = _education(candidate)
    education_blocks = (
        [Block("heading", {"compact": "ОБРАЗОВАНИЕ" if ru else "EDUCATION"}.get(template, "Образование" if ru else "Education")),
         Block("line", education)] if education else []
    )  # fmt: skip
    summary_blocks = [Block("heading", summary_heading), Block("line", summary)]

    if template == "sidebar":
        left = [*skills_blocks, Block("gap"), *language_blocks, Block("gap"), *education_blocks]
        right = [*summary_blocks, Block("gap"), *experience]
        blocks.append(Block("sidebar", left=left, right=right))
    elif template == "compact":
        blocks += summary_blocks + skills_blocks + experience + language_blocks + education_blocks
    else:
        blocks += summary_blocks + experience + skills_blocks + language_blocks + education_blocks
    return blocks


def blocks_text(blocks: list[Block]) -> str:
    """The plain text of a layout, in reading order (what a perfect parser would read)."""
    lines: list[str] = []
    for block in blocks:
        if block.kind == "sidebar":
            lines.append(blocks_text(block.left))
            lines.append(blocks_text(block.right))
        elif block.kind == "gap":
            lines.append("")
        elif block.kind == "bullet":
            lines.append(f"• {block.text}")
        else:
            lines.append(block.text)
    return "\n".join(lines)


# ---- writers ----

_FONT_CANDIDATES = [
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/Library/Fonts/Arial Unicode.ttf", "/Library/Fonts/Arial Unicode.ttf"),
]
_FONTS_READY = False


def _register_fonts() -> None:
    global _FONTS_READY
    if _FONTS_READY:
        return
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for regular, bold in _FONT_CANDIDATES:
        if Path(regular).exists() and Path(bold).exists():
            pdfmetrics.registerFont(TTFont("CV", regular))
            pdfmetrics.registerFont(TTFont("CV-Bold", bold))
            _FONTS_READY = True
            return
    raise RuntimeError("no TrueType font with Cyrillic found (install fonts-dejavu-core)")


def write_pdf(blocks: list[Block], title: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    _register_fonts()
    styles = {
        "title": ParagraphStyle("title", fontName="CV-Bold", fontSize=18, leading=22, spaceAfter=2),
        "subtitle": ParagraphStyle("subtitle", fontName="CV", fontSize=11, leading=14, textColor=colors.HexColor("#444444")),
        "line": ParagraphStyle("line", fontName="CV", fontSize=9.5, leading=12.5),
        "heading": ParagraphStyle("heading", fontName="CV-Bold", fontSize=11.5, leading=15, spaceBefore=6, spaceAfter=2,
                                  textColor=colors.HexColor("#1f3a5f")),
        "bullet": ParagraphStyle("bullet", fontName="CV", fontSize=9.5, leading=12.5, leftIndent=10, bulletIndent=2),
    }  # fmt: skip

    def escape(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def flow(items: list[Block]) -> list[object]:
        out: list[object] = []
        for block in items:
            if block.kind == "gap":
                out.append(Spacer(1, 4))
            elif block.kind == "bullet":
                out.append(Paragraph(escape(block.text), styles["bullet"], bulletText="•"))
            elif block.kind == "sidebar":
                table = Table([[flow(block.left), flow(block.right)]], colWidths=[58 * mm, 116 * mm])
                table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                           ("RIGHTPADDING", (0, 0), (0, 0), 8)]))  # fmt: skip
                out.append(table)
            else:
                out.append(Paragraph(escape(block.text), styles[block.kind]))
        return out

    buffer = io.BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, title=title, author="Clearhire synthetic data",
                                 leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm)  # fmt: skip
    document.build(flow(blocks))
    return buffer.getvalue()


def write_docx(blocks: list[Block]) -> bytes:
    from docx import Document
    from docx.shared import Pt

    document = Document()
    document.styles["Normal"].font.size = Pt(10)

    def add(items: list[Block]) -> None:
        for block in items:
            if block.kind == "sidebar":
                add(block.right)
                add(block.left)
            elif block.kind == "title":
                run = document.add_paragraph().add_run(block.text)
                run.bold = True
                run.font.size = Pt(18)
            elif block.kind == "heading":
                document.add_heading(block.text, level=2)
            elif block.kind == "bullet":
                document.add_paragraph(block.text, style="List Bullet")
            elif block.kind == "gap":
                continue
            else:
                document.add_paragraph(block.text)

    add(blocks)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def write_scan(pdf: bytes, seed: str) -> bytes:
    """The PDF printed and scanned: an image-only PDF, slightly rotated and noisy, with no text layer."""
    import pypdfium2 as pdfium
    from PIL import Image, ImageFilter

    rng = stable_rng(seed, "scan")
    document = pdfium.PdfDocument(pdf)
    pages: list[Image.Image] = []
    try:
        for index in range(len(document)):
            image = document[index].render(scale=200 / 72).to_pil().convert("L")
            image = image.rotate(
                rng.uniform(-0.8, 0.8), resample=Image.Resampling.BICUBIC, expand=False, fillcolor=255
            )
            noise = Image.effect_noise(image.size, rng.uniform(10, 22)).convert("L")
            image = Image.blend(image, noise, 0.08).filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 0.6)))
            pages.append(image.point(lambda value: 255 if value > 235 else value))
    finally:
        document.close()
    buffer = io.BytesIO()
    pages[0].save(buffer, format="PDF", save_all=True, append_images=pages[1:], resolution=200)
    return buffer.getvalue()


def write_cv(
    candidate: TruthCandidate, template: str, file_format: str, *, gender: str | None = None
) -> bytes:
    blocks = cv_blocks(candidate, template, gender=gender)
    if file_format == "docx":
        return write_docx(blocks)
    pdf = write_pdf(blocks, f"CV — {candidate.full_name}")
    return write_scan(pdf, candidate.id) if file_format == "scan" else pdf


# ---- vacancies ----

_OTHER = (
    ("Ability to explain technical decisions to non-technical colleagues",
     "Умение объяснять технические решения нетехническим коллегам"),
    ("Comfortable owning a feature from idea to production",
     "Готовность вести задачу от идеи до продакшена"),
    ("Interest in improving engineering practices across teams",
     "Интерес к улучшению инженерных практик в командах"),
)  # fmt: skip


def _skill_names(skills: list[str], taxonomy: Taxonomy) -> list[str]:
    return [taxonomy.skills[s].name if fold(taxonomy.skills[s].name) in taxonomy.skills[s].aliases
            else next(a for a in taxonomy.skills[s].aliases if not a.endswith("*")) for s in skills]  # fmt: skip


def _requirement_line(
    req_kind: str, req: object, language: str, taxonomy: Taxonomy, rng: random.Random
) -> str:
    from clearhire.vacancy import Requirement

    assert isinstance(req, Requirement)
    names = _skill_names(req.skills, taxonomy)
    ru = language == "ru"
    if req_kind == "skill" and req.skills == ["team_lead"]:
        return "Опыт руководства командой" if ru else "Team lead experience"
    if req_kind == "skill" and req.any_of:
        joined = (" или " if ru else " or ").join(names)
        return f"Опыт работы с {joined}" if ru else rng.choice([f"Experience with {joined}", joined])
    if req_kind == "skill" and req.min_years:
        n = int(req.min_years)
        if ru:
            return rng.choice([f"Опыт коммерческой разработки на {names[0]} от {_ru_years_genitive(n)}",
                               f"Не менее {_ru_years_genitive(n)} опыта работы с {names[0]}"])  # fmt: skip
        return rng.choice(
            [f"{n}+ years of commercial experience with {names[0]}", f"At least {n} years of {names[0]}"]
        )
    if req_kind == "skill":
        joined = (" и " if ru else " and ").join(names)
        return (
            f"Уверенное знание {joined}"
            if ru
            else rng.choice([f"Good knowledge of {joined}", f"Hands-on {joined}"])
        )
    if req_kind == "language":
        level = CEFR.get(req.min_level or 3, "B1")
        return (
            f"Английский язык — от {level}"
            if ru
            else rng.choice(
                [f"English {level}+", f"{LEVEL_EN[req.min_level or 3]} English ({level}) or higher"]
            )
        )
    if req_kind == "experience":
        n = int(req.min_years or 1)
        return (
            f"Общий опыт работы по специальности от {_ru_years_genitive(n)}"
            if ru
            else f"{n}+ years of professional experience"
        )
    if req_kind == "education":
        return "Высшее техническое образование" if ru else "Degree in Computer Science or a related field"
    other = rng.choice(_OTHER)
    return other[1] if ru else other[0]


def render_vacancy(vacancy: TruthVacancy, archetype: Archetype, rng: random.Random) -> str:
    taxonomy = load_taxonomy()
    ru = vacancy.language == "ru"
    for requirement in vacancy.requirements:
        requirement.text = _requirement_line(requirement.kind, requirement, vacancy.language, taxonomy, rng)
    must = [r for r in vacancy.requirements if r.must]
    nice = [r for r in vacancy.requirements if not r.must]
    duties = archetype.duties_ru if ru else archetype.duties_en
    lines = [vacancy.title, vacancy.company, ""]
    lines.append("О вакансии" if ru else "About the role")
    lines.append(
        f"Ищем специалиста в команду {vacancy.company}." if ru else f"{vacancy.company} is growing its team."
    )
    lines += ["", "Обязанности:" if ru else "Responsibilities:"] + [f"- {d}" for d in duties]
    lines += ["", "Требования:" if ru else "Requirements:"] + [f"- {r.text}" for r in must]
    if nice:
        lines += ["", "Будет плюсом:" if ru else "Nice to have:"] + [f"- {r.text}" for r in nice]
    lines += ["", "Мы предлагаем:" if ru else "We offer:"]
    lines += (["- Удаленную работу или офис в Москве", "- ДМС и обучение за счет компании"] if ru
              else ["- Remote work or an office in Moscow", "- Health insurance and a learning budget"])  # fmt: skip
    return "\n".join(lines)
