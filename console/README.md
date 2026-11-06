# Clearhire console

The recruiter and hiring-manager app: Angular 22 (standalone components, signals, zoneless,
`httpResource`), Angular CDK drag and drop, no UI kit.

- **Overview** — funnel, match-score distribution, sources, the must-haves applicants miss most.
- **Vacancies** — requirements read from the description and edited as structured checks; candidates
  ranked by unmet must-haves, then score; a match panel with the CV quote behind every verdict;
  a pipeline board.
- **Candidates** — hybrid search (keywords + meaning + skills, Russian and English), CV upload with
  consent, profile, 152-FZ erasure.
- **Audit log** — the hash chain, verified on demand.

Blind screening is on by default, and hiring managers cannot turn it off (the API enforces it).

```bash
npm ci
npm start          # http://localhost:4200, proxies /api to the API on 127.0.0.1:8077
npm test           # Vitest
npm run api:types  # regenerate src/app/api/schema.d.ts from ../api/openapi.json
```
