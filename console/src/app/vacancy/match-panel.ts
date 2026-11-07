import { httpResource } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import type { Evidence, Match, Note, Requirement } from '../api/types';
import { Api } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { Icon } from '../shared/icon';
import { Score, Status } from '../shared/score';
import { relativeDate } from '../shared/format';
import { AssistantCard } from './assistant-card';

interface QuotePart {
  text: string;
  mark: boolean;
}

/** Splits an evidence quote around its highlighted span. */
export function quoteParts(evidence: Evidence): QuotePart[] {
  const [start, end] = evidence.highlight;
  if (end <= start) return [{ text: evidence.quote, mark: false }];
  return [
    { text: evidence.quote.slice(0, start), mark: false },
    { text: evidence.quote.slice(start, end), mark: true },
    { text: evidence.quote.slice(end), mark: false },
  ].filter((part) => part.text);
}

@Component({
  selector: 'ch-match-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, Icon, Score, Status, AssistantCard],
  template: `
    <aside class="panel" aria-label="Match details">
      <header>
        @if (match.value(); as m) {
          <div class="grow">
            <h2>{{ m.name }}</h2>
            <div class="row muted small">
              <span>{{ m.must_met }} of {{ m.must_total }} must-haves</span>
              <span>·</span>
              <span>similarity {{ (m.semantic * 100).toFixed(0) }}</span>
              @if (m.blind) {
                <span class="chip met"><ch-icon name="eyeOff" [size]="12" />blind</span>
              }
            </div>
          </div>
          <ch-score [value]="m.score" [qualified]="m.must_met === m.must_total" />
        } @else {
          <div class="grow"><div class="skeleton" style="width: 60%"></div></div>
        }
        <button class="btn ghost sm" type="button" (click)="closed.emit()" aria-label="Close">
          <ch-icon name="x" />
        </button>
      </header>

      <div class="body">
        @if (match.error()) {
          <div class="error-box">Could not load this match.</div>
        }
        @if (match.value(); as m) {
          <div class="actions row">
            @if (auth.canSeePersonalData() && !m.blind) {
              <a class="btn sm" [routerLink]="['/candidates', m.candidate_id]">Profile</a>
              <button class="btn sm" type="button" (click)="api.openCv(m.candidate_id)">
                <ch-icon name="file" />Original CV
              </button>
            }
          </div>

          <ch-assistant-card
            [vacancyId]="vacancyId()"
            [candidateId]="candidateId()"
            [language]="language()"
          />

          <ol class="reqs">
            @for (row of rows(); track row.requirement.id) {
              <li [class]="row.result?.status ?? ''">
                <div class="req-head">
                  @if (row.result) {
                    <ch-status [status]="row.result.status" />
                  }
                  <span class="text">{{ row.requirement.text }}</span>
                  @if (!row.requirement.must) {
                    <span class="chip">nice to have</span>
                  }
                </div>
                @if (row.result?.detail) {
                  <p class="detail">{{ row.result!.detail }}</p>
                }
                @for (ev of row.result?.evidence ?? []; track $index) {
                  <blockquote>
                    @for (part of quoteParts(ev); track $index) {
                      @if (part.mark) {
                        <mark>{{ part.text }}</mark>
                      } @else {
                        <span>{{ part.text }}</span>
                      }
                    }
                    <footer class="muted">
                      {{ ev.section }}{{ ev.page ? ' · page ' + ev.page : ''
                      }}{{ ev.source === 'semantic' ? ' · found by meaning' : '' }}
                    </footer>
                  </blockquote>
                }
              </li>
            }
          </ol>

          @if (applicationId()) {
            <section class="notes">
              <h3>Notes</h3>
              @for (note of notes.value() ?? []; track note.id) {
                <div class="note">
                  <p>{{ note.text }}</p>
                  <span class="muted small">{{ relativeDate(note.created_at) }}</span>
                </div>
              } @empty {
                <p class="muted small">No notes yet.</p>
              }
              <form class="row" (ngSubmit)="addNote()">
                <input
                  class="input grow"
                  name="note"
                  placeholder="Add a note for the team"
                  [(ngModel)]="noteText"
                  maxlength="4000"
                />
                <button class="btn sm" type="submit" [disabled]="!noteText.trim() || saving()">
                  Add
                </button>
              </form>
            </section>
          }
        }
      </div>
    </aside>
  `,
  styles: `
    .panel {
      position: fixed;
      top: 0;
      right: 0;
      bottom: 0;
      z-index: 20;
      width: min(560px, 100vw);
      display: flex;
      flex-direction: column;
      background: var(--surface);
      border-left: 1px solid var(--border);
      box-shadow: var(--shadow-lg);
    }
    header {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 16px 18px;
      border-bottom: 1px solid var(--border);
    }
    .body {
      flex: 1;
      overflow-y: auto;
      padding: 14px 18px 32px;
    }
    .small {
      font-size: 12px;
    }
    .actions {
      margin-bottom: 12px;
    }
    .reqs {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 10px;
    }
    .reqs li {
      padding: 12px;
      border: 1px solid var(--border);
      border-radius: var(--radius);
      border-left-width: 3px;
    }
    .reqs li.met {
      border-left-color: var(--met);
    }
    .reqs li.partial {
      border-left-color: var(--partial);
    }
    .reqs li.missing {
      border-left-color: var(--missing);
    }
    .req-head {
      display: flex;
      align-items: baseline;
      gap: 8px;
      flex-wrap: wrap;
    }
    .req-head .text {
      flex: 1;
      min-width: 200px;
      font-weight: 500;
    }
    .detail {
      margin: 6px 0 0;
      color: var(--text-2);
      font-size: 13px;
    }
    blockquote {
      margin: 8px 0 0;
      padding: 8px 10px;
      border-radius: var(--radius-sm);
      background: var(--surface-2);
      font-size: 13px;
      line-height: 1.55;
    }
    blockquote footer {
      margin-top: 4px;
      font-size: 11px;
    }
    .notes {
      margin-top: 22px;
      display: grid;
      gap: 8px;
    }
    .note {
      padding: 8px 10px;
      border-radius: var(--radius-sm);
      background: var(--surface-2);
    }
    .note p {
      margin: 0 0 2px;
      white-space: pre-wrap;
    }
  `,
})
export class MatchPanel {
  protected readonly api = inject(Api);
  protected readonly auth = inject(AuthService);

  readonly vacancyId = input.required<string>();
  readonly candidateId = input.required<string>();
  readonly applicationId = input<string | null>(null);
  readonly closed = output<void>();

  protected readonly match = httpResource<Match>(() => ({
    url: `/api/vacancies/${this.vacancyId()}/matches/${this.candidateId()}`,
    params: { blind: this.api.blind() },
  }));
  protected readonly notes = httpResource<Note[]>(() =>
    this.applicationId() ? `/api/applications/${this.applicationId()}/notes` : undefined,
  );

  protected readonly rows = computed(() => {
    const m = this.match.value();
    if (!m) return [];
    const results = new Map(m.results.map((r) => [r.requirement_id, r]));
    return m.requirements.map((requirement: Requirement) => ({
      requirement,
      result: results.get(requirement.id),
    }));
  });

  /** The vacancy's language, from its requirements, for the assistant's suggested questions. */
  protected readonly language = computed(() => {
    const text = (this.match.value()?.requirements ?? []).map((r) => r.text).join(' ');
    return (text.match(/[а-яё]/gi)?.length ?? 0) > (text.match(/[a-z]/gi)?.length ?? 0)
      ? 'ru'
      : 'en';
  });

  protected readonly quoteParts = quoteParts;
  protected readonly relativeDate = relativeDate;
  protected noteText = '';
  protected readonly saving = signal(false);

  protected addNote(): void {
    const id = this.applicationId();
    if (!id || !this.noteText.trim()) return;
    this.saving.set(true);
    this.api.addNote(id, this.noteText.trim()).subscribe({
      next: () => {
        this.noteText = '';
        this.saving.set(false);
        this.notes.reload();
      },
      error: () => this.saving.set(false),
    });
  }
}
