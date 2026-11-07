# AI assistant evaluation

Model: `qwen3.5:9b`, local, on the server's GPU. 30 candidate-vacancy pairs sampled from the synthetic dataset (seed 11). Every request is redacted: the model never sees names, contacts, age or gender.

## Match summaries

| Written by the model | Sentences kept | Dropped (cited nothing) | Cited-sentence rate | Personal-detail leaks | p50 s | p95 s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 30/30 | 104 | 9 | 0.92 | 0 | 4.48 | 5.37 |

## Questions about skills

Yes/no questions, half about a skill the CV has and half about one it does not, graded against the generator's truth.

| Asked | Answered yes/no | Accuracy | When present | When absent | Grounded | Quotes in CV | Lookups per answer | p50 s | p95 s |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 60 | 60 | 1.0 | 1.0 | 1.0 | 0.917 | 37/38 | 1.95 | 2.89 | 4.13 |

## Fairness guard

Protected questions refused: 16/16. Fair questions wrongly refused: 0/16.

## Examples

```json
{
  "vacancy": "Mobile Developer",
  "candidate": "c0232",
  "summary": "The candidate meets the Android platform requirement and possesses C2 English proficiency, which exceeds the B1 threshold for intermediate English. Evidence of experience includes one year working with Kotlin, CI/CD, and Android on a product serving 46 thousand monthly users, alongside implementation of unit testing processes. However, the candidate lacks any demonstrated experience with Swift, failing to meet the mandatory two-year requirement for this language. Additionally, there is no mention of hands-on Jetpack Compose usage or a track record of owning features from idea to production in the provided text.",
  "refs": [
    [
      "R2",
      "E1",
      "R3",
      "E2"
    ],
    [
      "E1",
      "E3",
      "E4"
    ],
    [
      "R1"
    ],
    [
      "R4",
      "R6"
    ]
  ]
}
```

```json
{
  "question": "Есть ли в резюме опыт с REST API? Начните ответ с «да» или «нет».",
  "truth": true,
  "answer": "Да, в резюме есть опыт работы с REST API. Кандидат внедрил REST API в процессы команды в двух ролях [P1][P2] и указывает этот навык в разделе технических навыков [P3].",
  "steps": [
    "search_cv({\"query\": \"Есть ли в резюме опыт с REST API? Начните ответ с «да» или «нет».\"})",
    "skill_lookup({\"skill\": \"Есть ли в резюме опыт с REST API? Начните ответ с «да» или «нет».\"})"
  ]
}
```

```json
{
  "question": "Есть ли в резюме опыт с Jetpack Compose? Начните ответ с «да» или «нет».",
  "truth": false,
  "answer": "Нет, в резюме нет опыта с Jetpack Compose. Поиск по навыкам подтверждает, что это название не встречается ни под одним из его вариантов [K1].",
  "steps": [
    "search_cv({\"query\": \"Есть ли в резюме опыт с Jetpack Compose? Начните ответ с «да» или «нет».\"})",
    "skill_lookup({\"skill\": \"Есть ли в резюме опыт с Jetpack Compose? Начните ответ с «да» или «нет».\"})"
  ]
}
```

```json
{
  "vacancy": "Senior Python Engineer",
  "candidate": "c0287",
  "summary": "Strong evidence includes their leadership in implementing pytest and Django while optimizing system performance using PostgreSQL. They also demonstrate hands-on skills in developing REST API services and integrating systems with partners. The only gap is the absence of any mentioned experience or knowledge regarding Redis, which is listed as a nice-to-have requirement.",
  "refs": [
    [
      "E1",
      "E2",
      "E3",
      "E4",
      "E5",
      "E6"
    ],
    [
      "E7",
      "E8"
    ],
    [
      "R6"
    ]
  ]
}
```

```json
{
  "question": "Есть ли в резюме опыт с Git? Начните ответ с «да» или «нет».",
  "truth": true,
  "answer": "Да, в резюме есть опыт работы с Git. Кандидат внедрил git в процессы команды на должности Ведущего Python-разработчика [P2][K1].",
  "steps": [
    "search_cv({\"query\": \"Есть ли в резюме опыт с Git? Начните ответ с «да» или «нет».\"})",
    "skill_lookup({\"skill\": \"Есть ли в резюме опыт с Git? Начните ответ с «да» или «нет».\"})"
  ]
}
```

```json
{
  "question": "Есть ли в резюме опыт с Redis? Начните ответ с «да» или «нет».",
  "truth": false,
  "answer": "Нет, в резюме нет опыта с Redis. Поиск по навыкам подтверждает, что Redis не упоминается ни под каким из его названий [K1].",
  "steps": [
    "search_cv({\"query\": \"Есть ли в резюме опыт с Redis? Начните ответ с «да» или «нет».\"})",
    "skill_lookup({\"skill\": \"Есть ли в резюме опыт с Redis? Начните ответ с «да» или «нет».\"})"
  ]
}
```
