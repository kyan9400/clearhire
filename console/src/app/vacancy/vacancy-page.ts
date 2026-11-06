import { httpResource } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import type { RankedCandidate, Ranking, Vacancy } from '../api/types';
import { Api } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { Icon } from '../shared/icon';
import { STAGE_LABEL, duration } from '../shared/format';
import { Score } from '../shared/score';
import { MatchPanel } from './match-panel';
import { Pipeline } from './pipeline';
import { RequirementsEditor } from './requirements-editor';

type Tab = 'ranking' | 'pipeline' | 'requirements';
type Scope = 'applicants' | 'pool';

@Component({
  selector: 'ch-vacancy-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, Icon, Score, MatchPanel, Pipeline, RequirementsEditor],
  template: `
    <div class="page">
      <a class="back" routerLink="/vacancies"><ch-icon name="arrowLeft" [size]="14" />Vacancies</a>

      @if (vacancy.value(); as v) {
        <header class="page-head">
          <div>
            <h1>{{ v.title }}</h1>
            <p>
              {{ v.company }} · {{ v.location }}{{ v.remote ? ' · remote' : '' }} ·
              {{ v.applicants }} applicants, {{ v.qualified }} meet every must-have
            </p>
          </div>
          <nav class="segmented" aria-label="Sections">
            <a
              [routerLink]="[]"
              [queryParams]="{ tab: 'ranking' }"
              [class.active]="activeTab() === 'ranking'"
              >Ranking</a
            >
            <a
              [routerLink]="[]"
              [queryParams]="{ tab: 'pipeline' }"
              [class.active]="activeTab() === 'pipeline'"
              >Pipeline</a
            >
            <a
              [routerLink]="[]"
              [queryParams]="{ tab: 'requirements' }"
              [class.active]="activeTab() === 'requirements'"
              >Requirements · {{ v.requirements.length }}</a
            >
          </nav>
        </header>

        @switch (activeTab()) {
          @case ('ranking') {
            <div class="card">
              <div class="card-head">
                <div class="segmented">
                  <a
                    [routerLink]="[]"
                    [queryParams]="{ scope: 'applicants' }"
                    queryParamsHandling="merge"
                    [class.active]="activeScope() === 'applicants'"
                    >Applicants</a
                  >
                  <a
                    [routerLink]="[]"
                    [queryParams]="{ scope: 'pool' }"
                    queryParamsHandling="merge"
                    [class.active]="activeScope() === 'pool'"
                    >Whole talent pool</a
                  >
                </div>
                <span class="muted small">
                  Ordered by unmet must-haves, then requirement score, then similarity
                  @if (ranking.value(); as r) {
                    · {{ r.total }} ranked
                  }
                </span>
              </div>
              <div class="table-wrap">
                <table class="table">
                  <thead>
                    <tr>
                      <th class="r">#</th>
                      <th>Candidate</th>
                      <th>Score</th>
                      <th>Must-haves</th>
                      <th>Strengths</th>
                      <th>Gaps</th>
                      <th class="r">Experience</th>
                      <th>Stage</th>
                    </tr>
                  </thead>
                  <tbody>
                    @for (c of ranking.value()?.items ?? []; track c.candidate_id; let i = $index) {
                      <tr
                        class="clickable"
                        [class.selected]="c.candidate_id === candidate()"
                        (click)="select(c)"
                      >
                        <td class="r muted num">{{ i + 1 }}</td>
                        <td>
                          <strong>{{ c.name }}</strong>
                        </td>
                        <td><ch-score [value]="c.score" [qualified]="c.qualified" /></td>
                        <td>
                          <span
                            class="chip"
                            [class.met]="c.qualified"
                            [class.partial]="!c.qualified && !c.must_have_gaps"
                            [class.missing]="c.must_have_gaps > 0"
                            [title]="
                              c.must_met +
                              ' met, ' +
                              partly(c) +
                              ' partly, ' +
                              c.must_have_gaps +
                              ' missing'
                            "
                          >
                            {{ c.must_met }}/{{ c.must_total
                            }}{{ partly(c) ? ' +' + partly(c) + ' partly' : '' }}
                          </span>
                        </td>
                        <td class="list-cell" [title]="names(c.strengths)">
                          {{ names(c.strengths) }}
                        </td>
                        <td class="list-cell gaps" [title]="names(c.gaps)">
                          {{ names(c.gaps) || '—' }}
                        </td>
                        <td class="r num">{{ duration(c.experience_months) }}</td>
                        <td>
                          @if (c.stage) {
                            <span class="chip">{{ stageLabel[c.stage] }}</span>
                          } @else if (auth.canEdit()) {
                            <button class="btn sm" type="button" (click)="invite(c, $event)">
                              Add to vacancy
                            </button>
                          }
                        </td>
                      </tr>
                    } @empty {
                      <tr>
                        <td colspan="8" class="empty">
                          {{ ranking.isLoading() ? 'Ranking…' : 'No candidates yet.' }}
                        </td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
            </div>
          }
          @case ('pipeline') {
            <ch-pipeline
              [applicants]="applicants.value()?.items ?? []"
              (selected)="select($event)"
            />
          }
          @case ('requirements') {
            <div class="req-layout">
              <ch-requirements-editor [vacancy]="v" (saved)="onSaved()" />
              <div class="card card-pad description">
                <h3>Description</h3>
                <pre>{{ v.description }}</pre>
              </div>
            </div>
          }
        }

        @if (candidate(); as cid) {
          <ch-match-panel
            [vacancyId]="v.id"
            [candidateId]="cid"
            [applicationId]="selectedApplication()"
            (closed)="close()"
          />
        }
      } @else if (vacancy.error()) {
        <div class="error-box">This vacancy does not exist or you cannot see it.</div>
      } @else {
        <div class="skeleton" style="width: 40%; height: 24px"></div>
      }
    </div>
  `,
  styles: `
    .back {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      margin-bottom: 10px;
      font-size: 13px;
      color: var(--text-3);
    }
    .small {
      font-size: 12px;
    }
    tr.selected td {
      background: var(--accent-soft) !important;
    }
    .list-cell {
      max-width: 220px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: var(--text-2);
      font-size: 13px;
    }
    .gaps {
      color: var(--missing);
    }
    .req-layout {
      display: grid;
      grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr);
      gap: 14px;
      align-items: start;
    }
    .description pre {
      white-space: pre-wrap;
      font: 13px/1.6 var(--font);
      color: var(--text-2);
      margin: 8px 0 0;
    }
    @media (max-width: 1100px) {
      .req-layout {
        grid-template-columns: 1fr;
      }
    }
  `,
})
export class VacancyPage {
  protected readonly api = inject(Api);
  protected readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  /** Route parameter and query parameters, bound by withComponentInputBinding(). */
  readonly id = input.required<string>();
  readonly tab = input<string>();
  readonly scope = input<string>();
  readonly candidate = input<string>();

  protected readonly activeTab = computed<Tab>(() =>
    ['pipeline', 'requirements'].includes(this.tab() ?? '') ? (this.tab() as Tab) : 'ranking',
  );
  protected readonly activeScope = computed<Scope>(() =>
    this.scope() === 'pool' ? 'pool' : 'applicants',
  );
  protected readonly stageLabel = STAGE_LABEL;
  protected readonly duration = duration;

  protected readonly vacancy = httpResource<Vacancy>(() => `/api/vacancies/${this.id()}`);
  protected readonly ranking = httpResource<Ranking>(() =>
    this.activeTab() === 'ranking'
      ? {
          url: `/api/vacancies/${this.id()}/ranking`,
          params: { scope: this.activeScope(), blind: this.api.blind(), limit: 100 },
        }
      : undefined,
  );
  /** Every applicant for the pipeline board (ranked, so cards in a column are best first). */
  protected readonly applicants = httpResource<Ranking>(() =>
    this.activeTab() === 'pipeline'
      ? {
          url: `/api/vacancies/${this.id()}/ranking`,
          params: { scope: 'applicants', blind: this.api.blind(), limit: 500 },
        }
      : undefined,
  );

  protected readonly selectedApplication = computed(() => {
    const id = this.candidate();
    const items = [
      ...(this.ranking.value()?.items ?? []),
      ...(this.applicants.value()?.items ?? []),
    ];
    return items.find((c) => c.candidate_id === id)?.application_id ?? null;
  });

  /** Requirement id -> its short name: the skills it checks, or else its text. */
  private readonly requirementNames = computed(() => {
    const out = new Map<string, string>();
    for (const r of this.vacancy.value()?.requirements ?? []) {
      out.set(r.id, r.skills.length ? r.skills.join(r.any_of ? ' / ' : ' + ') : r.text);
    }
    return out;
  });

  protected names(ids: string[]): string {
    const names = this.requirementNames();
    return ids.map((id) => names.get(id) ?? id).join(', ');
  }

  protected partly(c: RankedCandidate): number {
    return c.must_total - c.must_met - c.must_have_gaps;
  }

  protected select(c: RankedCandidate): void {
    void this.router.navigate([], {
      queryParams: { candidate: c.candidate_id },
      queryParamsHandling: 'merge',
    });
  }

  protected close(): void {
    void this.router.navigate([], {
      queryParams: { candidate: null },
      queryParamsHandling: 'merge',
    });
  }

  protected invite(c: RankedCandidate, event: Event): void {
    event.stopPropagation();
    this.api.addToVacancy(c.candidate_id, this.id()).subscribe(() => this.ranking.reload());
  }

  protected onSaved(): void {
    this.vacancy.reload();
  }
}
