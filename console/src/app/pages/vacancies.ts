import { httpResource } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import type { Vacancy, VacancyStatus } from '../api/types';
import { Api } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { Icon } from '../shared/icon';
import { relativeDate } from '../shared/format';

const STATUS_FILTERS: { value: VacancyStatus | ''; label: string }[] = [
  { value: 'open', label: 'Open' },
  { value: 'draft', label: 'Drafts' },
  { value: 'closed', label: 'Closed' },
  { value: '', label: 'All' },
];

@Component({
  selector: 'ch-vacancies',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, FormsModule, Icon],
  template: `
    <div class="page">
      <header class="page-head">
        <div>
          <h1>Vacancies</h1>
          <p>
            Requirements are read from the description; every applicant is checked against each one.
          </p>
        </div>
        <div class="row">
          <div class="segmented">
            @for (f of filters; track f.value) {
              <button
                type="button"
                [class.active]="status() === f.value"
                (click)="status.set(f.value)"
              >
                {{ f.label }}
              </button>
            }
          </div>
          @if (auth.canEdit()) {
            <button class="btn primary" type="button" (click)="creating.set(!creating())">
              <ch-icon name="plus" />New vacancy
            </button>
          }
        </div>
      </header>

      @if (creating()) {
        <form class="card card-pad create" (ngSubmit)="create()">
          <h2>New vacancy</h2>
          <div class="cols">
            <label class="field"
              ><span>Title</span
              ><input class="input" name="title" required minlength="2" [(ngModel)]="draft.title"
            /></label>
            <label class="field"
              ><span>Company</span><input class="input" name="company" [(ngModel)]="draft.company"
            /></label>
            <label class="field"
              ><span>Location</span
              ><input class="input" name="location" [(ngModel)]="draft.location"
            /></label>
            <label class="check"
              ><input type="checkbox" name="remote" [(ngModel)]="draft.remote" />Remote
              possible</label
            >
          </div>
          <label class="field">
            <span
              >Description — list requirements one per line; "nice to have" lines become
              optional</span
            >
            <textarea
              class="textarea"
              name="description"
              required
              minlength="10"
              rows="10"
              [(ngModel)]="draft.description"
              placeholder="Requirements:&#10;- Python 3+ years&#10;- FastAPI or Django&#10;- English B2&#10;Nice to have:&#10;- Kubernetes"
            ></textarea>
          </label>
          @if (createError()) {
            <div class="error-box">{{ createError() }}</div>
          }
          <div class="row">
            <button class="btn primary" type="submit" [disabled]="busy()">
              Create and read requirements
            </button>
            <button class="btn ghost" type="button" (click)="creating.set(false)">Cancel</button>
          </div>
        </form>
      }

      <div class="card">
        <div class="table-wrap">
          <table class="table">
            <thead>
              <tr>
                <th>Vacancy</th>
                <th>Status</th>
                <th class="r">Requirements</th>
                <th class="r">Applicants</th>
                <th class="r">Meet every must-have</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              @for (v of rows(); track v.id) {
                <tr class="clickable" (click)="open(v)">
                  <td>
                    <a [routerLink]="['/vacancies', v.id]" (click)="$event.stopPropagation()"
                      ><strong>{{ v.title }}</strong></a
                    >
                    <div class="muted small">
                      {{ v.company }} · {{ v.location }}{{ v.remote ? ' · remote' : '' }}
                    </div>
                  </td>
                  <td>
                    <span class="chip" [class.accent]="v.status === 'open'">{{ v.status }}</span>
                  </td>
                  <td class="r num">
                    {{ mustCount(v) }} must · {{ v.requirements.length - mustCount(v) }} nice
                  </td>
                  <td class="r num">{{ v.applicants }}</td>
                  <td class="r num">
                    {{ v.qualified }}
                    @if (v.applicants) {
                      <span class="muted"
                        >({{ ((v.qualified / v.applicants) * 100).toFixed(0) }}%)</span
                      >
                    }
                  </td>
                  <td class="muted">{{ relativeDate(v.created_at) }}</td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="6" class="empty">
                    {{ vacancies.isLoading() ? 'Loading…' : 'No vacancies here.' }}
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `,
  styles: `
    .small {
      font-size: 12px;
    }
    .create {
      display: grid;
      gap: 14px;
      margin-bottom: 16px;
    }
    .cols {
      display: grid;
      grid-template-columns: 2fr 1fr 1fr auto;
      gap: 12px;
      align-items: end;
    }
    @media (max-width: 800px) {
      .cols {
        grid-template-columns: 1fr;
      }
    }
  `,
})
export class Vacancies {
  protected readonly auth = inject(AuthService);
  private readonly api = inject(Api);
  private readonly router = inject(Router);

  protected readonly filters = STATUS_FILTERS;
  protected readonly status = signal<VacancyStatus | ''>('open');
  protected readonly vacancies = httpResource<Vacancy[]>(() => ({
    url: '/api/vacancies',
    params: this.api.params({ status: this.status() }),
  }));
  protected readonly rows = computed(() => this.vacancies.value() ?? []);
  protected readonly relativeDate = relativeDate;

  protected readonly creating = signal(false);
  protected readonly busy = signal(false);
  protected readonly createError = signal('');
  protected draft = { title: '', company: '', location: 'Moscow', remote: true, description: '' };

  protected mustCount(v: Vacancy): number {
    return v.requirements.filter((r) => r.must).length;
  }

  protected open(v: Vacancy): void {
    void this.router.navigate(['/vacancies', v.id]);
  }

  protected create(): void {
    this.busy.set(true);
    this.createError.set('');
    this.api
      .createVacancy({
        ...this.draft,
        language: /[а-яё]/i.test(this.draft.description) ? 'ru' : 'en',
        status: 'open',
      })
      .subscribe({
        next: (vacancy) =>
          void this.router.navigate(['/vacancies', vacancy.id], {
            queryParams: { tab: 'requirements' },
          }),
        error: () => {
          this.busy.set(false);
          this.createError.set('Could not create the vacancy. Check the title and description.');
        },
      });
  }
}
