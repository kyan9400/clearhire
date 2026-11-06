import { httpResource } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  input,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import type { Candidate, Vacancy } from '../api/types';
import { Api } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { Icon } from '../shared/icon';
import {
  LANGUAGE_NAME,
  LEVEL_NAME,
  SOURCE_LABEL,
  STAGE_LABEL,
  duration,
  relativeDate,
} from '../shared/format';

@Component({
  selector: 'ch-candidate',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, Icon],
  template: `
    <div class="page">
      <a class="back" routerLink="/candidates"
        ><ch-icon name="arrowLeft" [size]="14" />Candidates</a
      >

      @if (candidate.value(); as c) {
        <header class="page-head">
          <div>
            <h1>{{ c.name }}</h1>
            <p>
              {{ c.city || 'City not stated' }} · {{ sourceLabel[c.source] }} · added
              {{ relativeDate(c.created_at) }}
            </p>
          </div>
          <div class="row">
            @if (!api.blind()) {
              <button class="btn" type="button" (click)="api.openCv(c.id)">
                <ch-icon name="file" />Original CV
              </button>
            }
            @if (auth.canEdit()) {
              <button class="btn danger" type="button" (click)="confirming.set(true)">
                <ch-icon name="trash" />Erase
              </button>
            }
          </div>
        </header>

        @if (confirming()) {
          <div class="card card-pad erase" role="alertdialog" aria-labelledby="erase-title">
            <h2 id="erase-title">Erase this candidate?</h2>
            <p>
              The CV, the profile, every application and note are deleted for good (152-FZ, the
              right to erasure). The audit log keeps a record that the erasure happened, without
              personal data.
            </p>
            <label class="field">
              <span>Type ERASE to confirm</span>
              <input class="input" name="confirm" [(ngModel)]="confirmText" autocomplete="off" />
            </label>
            <div class="row">
              <button
                class="btn danger"
                type="button"
                [disabled]="confirmText !== 'ERASE'"
                (click)="erase(c.id)"
              >
                Erase for good
              </button>
              <button class="btn ghost" type="button" (click)="confirming.set(false)">
                Cancel
              </button>
            </div>
          </div>
        }

        @if (c.document_status === 'pending') {
          <div class="card card-pad notice">Reading the CV… this page updates by itself.</div>
        } @else if (c.document_status === 'failed') {
          <div class="error-box notice">
            The CV could not be read. A scanned file needs OCR on the server.
          </div>
        }

        <div class="layout">
          <div class="card card-pad">
            <h2>Profile</h2>
            <dl>
              <dt>Experience</dt>
              <dd>{{ duration(c.experience_months) }}</dd>
              @if (!api.blind()) {
                <dt>Email</dt>
                <dd>{{ c.email ?? '—' }}</dd>
                <dt>Phone</dt>
                <dd>{{ c.phone ?? '—' }}</dd>
                <dt>Telegram</dt>
                <dd>{{ c.telegram ?? '—' }}</dd>
              }
              <dt>Languages</dt>
              <dd>
                @for (l of languages(); track l.code) {
                  <span class="chip">{{ l.name }} {{ l.level }}</span>
                } @empty {
                  —
                }
              </dd>
              <dt>Kept until</dt>
              <dd>{{ c.retain_until }} <span class="muted small">(consent expiry)</span></dd>
            </dl>
            <h3 class="skills-title">Skills · {{ c.skills.length }}</h3>
            <div class="row">
              @for (s of c.skills; track s) {
                <span class="chip">{{ s }}</span>
              }
            </div>
          </div>

          <div class="card">
            <div class="card-head">
              <h2>Applications</h2>
              @if (auth.canEdit()) {
                <form class="row" (ngSubmit)="addTo(c.id)">
                  <select
                    class="select"
                    name="vacancy"
                    [(ngModel)]="vacancyChoice"
                    aria-label="Vacancy"
                  >
                    <option value="">Add to a vacancy…</option>
                    @for (v of openVacancies(); track v.id) {
                      <option [value]="v.id">{{ v.title }}</option>
                    }
                  </select>
                  <button class="btn sm" type="submit" [disabled]="!vacancyChoice">Add</button>
                </form>
              }
            </div>
            <table class="table">
              <thead>
                <tr>
                  <th>Vacancy</th>
                  <th>Stage</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                @for (a of c.applications; track a.id) {
                  <tr class="clickable" (click)="openMatch(a.vacancy_id, c.id)">
                    <td>{{ vacancyTitle(a.vacancy_id) }}</td>
                    <td>
                      <span class="chip">{{ stageLabel[a.stage] }}</span>
                    </td>
                    <td class="muted">{{ relativeDate(a.updated_at) }}</td>
                  </tr>
                } @empty {
                  <tr>
                    <td colspan="3" class="empty">Not applied anywhere yet.</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        </div>
      } @else if (candidate.error()) {
        <div class="error-box">This candidate does not exist or was erased.</div>
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
    .notice {
      margin-bottom: 14px;
    }
    .erase {
      display: grid;
      gap: 10px;
      margin-bottom: 14px;
      border-color: var(--missing);
      max-width: 640px;
    }
    .erase p {
      margin: 0;
      color: var(--text-2);
    }
    .layout {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 14px;
      align-items: start;
    }
    dl {
      display: grid;
      grid-template-columns: 120px 1fr;
      gap: 8px 12px;
      margin: 14px 0 18px;
    }
    dt {
      color: var(--text-3);
    }
    dd {
      margin: 0;
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
    }
    .skills-title {
      margin-bottom: 8px;
    }
    @media (max-width: 900px) {
      .layout {
        grid-template-columns: 1fr;
      }
    }
  `,
})
export class CandidatePage {
  protected readonly api = inject(Api);
  protected readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  readonly id = input.required<string>();

  protected readonly candidate = httpResource<Candidate>(() => ({
    url: `/api/candidates/${this.id()}`,
    params: { blind: this.api.blind() },
  }));
  private readonly vacancies = httpResource<Vacancy[]>(() => '/api/vacancies');
  protected readonly openVacancies = computed(() => {
    const applied = new Set(this.candidate.value()?.applications.map((a) => a.vacancy_id));
    return (this.vacancies.value() ?? []).filter((v) => v.status === 'open' && !applied.has(v.id));
  });
  protected readonly languages = computed(() =>
    Object.entries(this.candidate.value()?.languages ?? {}).map(([code, level]) => ({
      code,
      name: LANGUAGE_NAME[code] ?? code.toUpperCase(),
      level: level ? LEVEL_NAME[level] : '',
    })),
  );

  protected readonly sourceLabel = SOURCE_LABEL;
  protected readonly stageLabel = STAGE_LABEL;
  protected readonly duration = duration;
  protected readonly relativeDate = relativeDate;
  protected readonly confirming = signal(false);
  protected confirmText = '';
  protected vacancyChoice = '';

  constructor() {
    // while the CV is being read, check again every two seconds
    let timer: ReturnType<typeof setTimeout> | undefined;
    effect(() => {
      clearTimeout(timer);
      if (this.candidate.value()?.document_status === 'pending') {
        timer = setTimeout(() => this.candidate.reload(), 2000);
      }
    });
    inject(DestroyRef).onDestroy(() => clearTimeout(timer));
  }

  protected vacancyTitle(id: string): string {
    return this.vacancies.value()?.find((v) => v.id === id)?.title ?? 'Vacancy';
  }

  protected openMatch(vacancyId: string, candidateId: string): void {
    void this.router.navigate(['/vacancies', vacancyId], {
      queryParams: { candidate: candidateId },
    });
  }

  protected addTo(candidateId: string): void {
    this.api.addToVacancy(candidateId, this.vacancyChoice).subscribe(() => {
      this.vacancyChoice = '';
      this.candidate.reload();
    });
  }

  protected erase(id: string): void {
    this.api.erase(id).subscribe(() => void this.router.navigate(['/candidates']));
  }
}
