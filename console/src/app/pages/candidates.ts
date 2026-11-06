import { httpResource } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  input,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import type { Candidate, SearchHit } from '../api/types';
import { Api } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { Icon } from '../shared/icon';
import { SOURCE_LABEL, duration, relativeDate } from '../shared/format';

@Component({
  selector: 'ch-candidates',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, Icon],
  template: `
    <div class="page">
      <header class="page-head">
        <div>
          <h1>Candidates</h1>
          <p>Search reads keywords, meaning and skills at once, in Russian and English.</p>
        </div>
        @if (auth.canEdit()) {
          <button class="btn primary" type="button" (click)="uploading.set(!uploading())">
            <ch-icon name="upload" />Add CV
          </button>
        }
      </header>

      @if (uploading()) {
        <form class="card card-pad upload" (ngSubmit)="upload()">
          <label class="drop" [class.has]="file()">
            <input type="file" accept=".pdf,.docx,.txt,.png,.jpg,.jpeg" (change)="pick($event)" />
            <ch-icon name="file" [size]="22" />
            <span>{{
              file()?.name ?? 'Choose a PDF, DOCX or photo of a CV (scans are read with OCR)'
            }}</span>
          </label>
          <label class="check">
            <input type="checkbox" name="consent" [(ngModel)]="consent" />
            The candidate agreed to the processing of their personal data (152-FZ)
          </label>
          @if (uploadMessage()) {
            <div [class.error-box]="uploadFailed()">{{ uploadMessage() }}</div>
          }
          <div class="row">
            <button class="btn primary" type="submit" [disabled]="!file() || !consent || busy()">
              Upload and read
            </button>
            <button class="btn ghost" type="button" (click)="uploading.set(false)">Cancel</button>
          </div>
        </form>
      }

      <form class="card card-pad search" (ngSubmit)="search()">
        <ch-icon name="search" />
        <input
          class="input grow"
          name="q"
          placeholder="e.g. Kafka микросервисы, team lead with fintech experience"
          [(ngModel)]="text"
        />
        <label class="field years">
          <span>Min. years</span>
          <input
            class="input num"
            name="years"
            type="number"
            min="0"
            max="40"
            [(ngModel)]="yearsField"
          />
        </label>
        <button class="btn primary" type="submit">Search</button>
        @if (q()) {
          <button class="btn ghost" type="button" (click)="clear()">Clear</button>
        }
      </form>

      <div class="card">
        <div class="table-wrap">
          @if (q() || minYears()) {
            <table class="table">
              <thead>
                <tr>
                  <th>Candidate</th>
                  <th>Why it matched</th>
                  <th class="r">Experience</th>
                  <th>Skills</th>
                </tr>
              </thead>
              <tbody>
                @for (hit of hits.value() ?? []; track hit.candidate_id) {
                  <tr class="clickable" (click)="open(hit.candidate_id)">
                    <td>
                      <strong>{{ hit.name }}</strong>
                    </td>
                    <td class="snippet">{{ hit.snippet || '—' }}</td>
                    <td class="r num">{{ duration(hit.experience_months) }}</td>
                    <td class="skills">{{ hit.skills.slice(0, 6).join(', ') }}</td>
                  </tr>
                } @empty {
                  <tr>
                    <td colspan="4" class="empty">
                      {{ hits.isLoading() ? 'Searching…' : 'Nobody matches.' }}
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          } @else {
            <table class="table">
              <thead>
                <tr>
                  <th>Candidate</th>
                  <th>CV</th>
                  <th class="r">Experience</th>
                  <th>Skills</th>
                  <th>Source</th>
                  <th>Added</th>
                </tr>
              </thead>
              <tbody>
                @for (c of list.value() ?? []; track c.id) {
                  <tr class="clickable" (click)="open(c.id)">
                    <td>
                      <a [routerLink]="['/candidates', c.id]" (click)="$event.stopPropagation()"
                        ><strong>{{ c.name }}</strong></a
                      >
                      @if (c.city) {
                        <div class="muted small">{{ c.city }}</div>
                      }
                    </td>
                    <td>
                      <span
                        class="chip"
                        [class.met]="c.document_status === 'parsed'"
                        [class.missing]="c.document_status === 'failed'"
                        >{{ c.document_status ?? '—' }}</span
                      >
                    </td>
                    <td class="r num">{{ duration(c.experience_months) }}</td>
                    <td class="skills">{{ c.skills.slice(0, 6).join(', ') }}</td>
                    <td class="muted">{{ sourceLabel[c.source] }}</td>
                    <td class="muted">{{ relativeDate(c.created_at) }}</td>
                  </tr>
                } @empty {
                  <tr>
                    <td colspan="6" class="empty">
                      {{ list.isLoading() ? 'Loading…' : 'No candidates yet.' }}
                    </td>
                  </tr>
                }
              </tbody>
            </table>
            <div class="pager row">
              <button
                class="btn sm"
                type="button"
                [disabled]="offset() === 0"
                (click)="offset.set(offset() - pageSize)"
              >
                Previous
              </button>
              <span class="muted small"
                >{{ offset() + 1 }}–{{ offset() + (list.value()?.length ?? 0) }}</span
              >
              <button
                class="btn sm"
                type="button"
                [disabled]="(list.value()?.length ?? 0) < pageSize"
                (click)="offset.set(offset() + pageSize)"
              >
                Next
              </button>
            </div>
          }
        </div>
      </div>
    </div>
  `,
  styles: `
    .small {
      font-size: 12px;
    }
    .search {
      display: flex;
      align-items: flex-end;
      gap: 10px;
      margin-bottom: 14px;
    }
    .search > ch-icon {
      align-self: center;
      color: var(--text-3);
    }
    .years {
      width: 100px;
    }
    .snippet {
      max-width: 520px;
      color: var(--text-2);
      font-size: 13px;
    }
    .skills {
      max-width: 320px;
      color: var(--text-2);
      font-size: 13px;
    }
    .pager {
      justify-content: flex-end;
      padding: 10px 14px;
      border-top: 1px solid var(--border);
    }
    .upload {
      display: grid;
      gap: 12px;
      margin-bottom: 14px;
    }
    .drop {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 18px;
      border: 1.5px dashed var(--border-strong);
      border-radius: var(--radius);
      color: var(--text-2);
      cursor: pointer;
    }
    .drop.has {
      border-style: solid;
      border-color: var(--accent);
      color: var(--text);
    }
    .drop input {
      position: absolute;
      width: 1px;
      height: 1px;
      opacity: 0;
    }
    @media (max-width: 720px) {
      .search {
        flex-wrap: wrap;
      }
    }
  `,
})
export class Candidates implements OnInit {
  protected readonly auth = inject(AuthService);
  private readonly api = inject(Api);
  private readonly router = inject(Router);

  /** Query parameters, so a search can be linked to and survives going back. */
  readonly q = input<string>('');
  readonly years = input<string>('');

  protected readonly pageSize = 50;
  protected readonly offset = signal(0);
  protected readonly minYears = computed(() => Number(this.years()) || 0);
  protected text = '';
  protected yearsField: number | null = null;
  protected readonly sourceLabel = SOURCE_LABEL;
  protected readonly duration = duration;
  protected readonly relativeDate = relativeDate;

  protected readonly list = httpResource<Candidate[]>(() =>
    this.q() || this.minYears()
      ? undefined
      : {
          url: '/api/candidates',
          params: { blind: this.api.blind(), limit: this.pageSize, offset: this.offset() },
        },
  );
  protected readonly hits = httpResource<SearchHit[]>(() =>
    this.q() || this.minYears()
      ? {
          url: '/api/candidates/search',
          params: this.api.params({
            q: this.q(),
            min_years: this.minYears(),
            blind: this.api.blind(),
            limit: 50,
          }),
        }
      : undefined,
  );

  protected readonly uploading = signal(false);
  protected readonly file = signal<File | null>(null);
  protected consent = false;
  protected readonly busy = signal(false);
  protected readonly uploadMessage = signal('');
  protected readonly uploadFailed = signal(false);

  ngOnInit(): void {
    this.text = this.q();
    this.yearsField = this.minYears() || null;
  }

  protected search(): void {
    void this.router.navigate([], {
      queryParams: { q: this.text.trim() || null, years: this.yearsValue() },
    });
  }

  protected clear(): void {
    this.text = '';
    void this.router.navigate([], { queryParams: { q: null, years: null } });
  }

  private yearsValue(): number | null {
    return this.yearsField && this.yearsField > 0 ? this.yearsField : null;
  }

  protected open(id: string): void {
    void this.router.navigate(['/candidates', id]);
  }

  protected pick(event: Event): void {
    this.file.set((event.target as HTMLInputElement).files?.[0] ?? null);
  }

  protected upload(): void {
    const file = this.file();
    if (!file) return;
    this.busy.set(true);
    this.uploadMessage.set('');
    this.api.upload(file, this.consent, null).subscribe({
      next: (candidate) => void this.router.navigate(['/candidates', candidate.id]),
      error: (error: { status?: number }) => {
        this.busy.set(false);
        this.uploadFailed.set(true);
        this.uploadMessage.set(
          error.status === 413
            ? 'The file is too large.'
            : error.status === 415
              ? 'This file type cannot be read.'
              : 'Upload failed.',
        );
      },
    });
  }
}
