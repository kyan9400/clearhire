# Clearhire evaluation

Synthetic dataset: 312 CVs (279 read, 33 skipped: the PDF is a scan and OCR is not available), 39 vacancies. Embeddings: `intfloat/multilingual-e5-small`. OCR: not available, scans skipped. Reference date 2026-10-01.

## Ranking candidates for a vacancy

Every vacancy ranks the whole pool. Relevance comes from the generator's truth: 3 = all must-haves and
at least half the nice-to-haves, 2 = all must-haves, 1 = at least 60% of must-haves, 0 = less.

| Method | nDCG@10 | Precision@5 | Recall@20 |
| --- | ---: | ---: | ---: |
| clearhire | 0.968 | 0.897 | 0.890 |
| clearhire, true requirements | 0.968 | 0.897 | 0.890 |
| embeddings only | 0.600 | 0.626 | 0.423 |
| keyword (BM25) | 0.657 | 0.646 | 0.556 |
| perfect ranking (upper bound) | 1.000 | 0.918 | 0.906 |

"Meets every must-have" (each one fully met) against the truth, over 10,881 vacancy-candidate pairs: precision 0.997, recall 0.998, F1 0.997.

## Reading CVs

| CVs | Count | Skills F1 | Precision | Recall | Experience exact | Experience MAE (months) | Skill months MAE | Language level | Degree |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 279 | 0.998 | 0.998 | 0.999 | 88.5% | 0.40 | 0.70 | 100.0% | 100.0% |
| format:docx | 73 | 0.998 | 0.996 | 1.000 | 90.4% | 0.42 | 1.20 | 100.0% | 100.0% |
| format:pdf | 206 | 0.999 | 0.998 | 0.999 | 87.9% | 0.39 | 0.52 | 100.0% | 100.0% |
| language:en | 113 | 0.998 | 0.997 | 0.998 | 92.0% | 0.35 | 0.50 | 100.0% | 100.0% |
| language:ru | 166 | 0.999 | 0.998 | 1.000 | 86.1% | 0.44 | 0.83 | 100.0% | 100.0% |

## Reading vacancy requirements

262 requirement lines in 39 vacancies: 100.0% parsed exactly (kind, must-have, skills, any-of, years, language level, degree); the requirement count is right for 100.0% of vacancies.

| Field | Accuracy |
| --- | ---: |
| kind | 100.0% |
| must | 100.0% |
| skills | 100.0% |
| any_of | 100.0% |
| years | 100.0% |
| language | 100.0% |
| degree | 100.0% |

## Fairness: the same CV with only personal details changed

54 CVs, each re-rendered as the other gender (in Russian also the verb endings), with a name of another origin, and 15 years older; each version is matched against its role's vacancies.

| Mode | Change | Comparisons | Identical result | Max score change | Max semantic change | Must-have gaps changed |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| blind | gender | 162 | 100.0% | 0.0000 | 0.00000 | 0.0% |
| blind | origin | 162 | 100.0% | 0.0000 | 0.00000 | 0.0% |
| blind | age | 162 | 100.0% | 0.0000 | 0.00000 | 0.0% |
| open | gender | 162 | 34.0% | 0.0000 | 0.00470 | 0.0% |
| open | origin | 162 | 100.0% | 0.0000 | 0.00000 | 0.0% |
| open | age | 162 | 100.0% | 0.0000 | 0.00000 | 0.0% |

## Speed

Reading and indexing a CV (median): 188.0 ms. Ranking a pool of 279 CVs for one vacancy: 27.7 ms.
