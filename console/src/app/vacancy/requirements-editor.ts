import { httpResource } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  effect,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import type { Observable } from 'rxjs';

import type { Requirement, Skill, Vacancy } from '../api/types';
import { Api } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { Icon } from '../shared/icon';
import { LANGUAGE_NAME, LEVEL_NAME } from '../shared/format';

const KINDS: { value: string; label: string }[] = [
  { value: 'skill', label: 'Skill' },
  { value: 'experience', label: 'Total experience' },
  { value: 'language', label: 'Language' },
  { value: 'education', label: 'Degree' },
  { value: 'other', label: 'Other (checked by meaning)' },
];
const DEGREES = ['', 'Vocational', "Bachelor's", "Master's", 'PhD'];

/**
 * What the matcher checks for one vacancy. Requirements are read from the description by the API; the
 * recruiter corrects them here. Saving bumps the requirements version, which re-ranks every applicant.
 */
@Component({
  selector: 'ch-requirements-editor',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, Icon],
  template: `
    <div class="card">
      <div class="card-head">
        <div>
          <h2>Requirements</h2>
          <span class="muted small"
            >version {{ vacancy().requirements_version }} · each line is checked against every
            CV</span
          >
        </div>
        @if (auth.canEdit()) {
          <div class="row">
            <button class="btn sm" type="button" (click)="reread()" [disabled]="busy()">
              <ch-icon name="sparkle" />Re-read from description
            </button>
            <button class="btn sm" type="button" (click)="add()"><ch-icon name="plus" />Add</button>
            <button
              class="btn primary sm"
              type="button"
              (click)="save()"
              [disabled]="busy() || !dirty()"
            >
              Save and re-rank
            </button>
          </div>
        }
      </div>
      @if (message()) {
        <div class="message" [class.error-box]="failed()">{{ message() }}</div>
      }
      <ol class="list">
        @for (r of rows(); track r.id; let i = $index) {
          <li>
            <div class="line">
              <label
                class="must"
                [class.on]="r.must"
                [title]="r.must ? 'Must-have' : 'Nice to have'"
              >
                <input
                  type="checkbox"
                  [ngModel]="r.must"
                  (ngModelChange)="patch(i, { must: $event, weight: $event ? 1 : 0.5 })"
                  [disabled]="!auth.canEdit()"
                />
                {{ r.must ? 'Must' : 'Nice' }}
              </label>
              <input
                class="input text"
                [ngModel]="r.text"
                (ngModelChange)="patch(i, { text: $event })"
                [readonly]="!auth.canEdit()"
                aria-label="Requirement text"
              />
              <select
                class="select kind"
                [ngModel]="r.kind"
                (ngModelChange)="patch(i, { kind: $event })"
                [disabled]="!auth.canEdit()"
                aria-label="Kind"
              >
                @for (k of kinds; track k.value) {
                  <option [value]="k.value">{{ k.label }}</option>
                }
              </select>
              @if (auth.canEdit()) {
                <button
                  class="btn ghost sm"
                  type="button"
                  (click)="remove(i)"
                  aria-label="Remove requirement"
                >
                  <ch-icon name="trash" />
                </button>
              }
            </div>

            <div class="params">
              @switch (r.kind) {
                @case ('skill') {
                  @for (s of r.skills; track s) {
                    <span class="chip accent"
                      >{{ s }}
                      @if (auth.canEdit()) {
                        <button
                          class="x"
                          type="button"
                          (click)="removeSkill(i, s)"
                          [attr.aria-label]="'Remove ' + s"
                        >
                          ×
                        </button>
                      }
                    </span>
                    @if (!$last) {
                      <span class="muted small">{{ r.any_of ? 'or' : 'and' }}</span>
                    }
                  }
                  @if (auth.canEdit()) {
                    <span class="add-skill">
                      <input
                        class="input sm"
                        placeholder="+ skill"
                        [ngModel]="skillQuery()[r.id] ?? ''"
                        (ngModelChange)="searchSkill(r.id, $event)"
                        (keydown.enter)="$event.preventDefault()"
                      />
                      @if (activeRow() === r.id && (skills.value() ?? []).length) {
                        <span class="suggest">
                          @for (s of skills.value()!.slice(0, 8); track s.id) {
                            <button type="button" (click)="addSkill(i, s)">
                              {{ s.name }} <span class="muted">{{ s.category }}</span>
                            </button>
                          }
                        </span>
                      }
                    </span>
                    @if (r.skills.length > 1) {
                      <label class="check small"
                        ><input
                          type="checkbox"
                          [ngModel]="r.any_of"
                          (ngModelChange)="patch(i, { any_of: $event })"
                        />any one is enough</label
                      >
                    }
                  }
                  <label class="years small">
                    at least
                    <input
                      class="input sm num"
                      type="number"
                      min="0"
                      max="30"
                      step="0.5"
                      [ngModel]="r.min_years"
                      (ngModelChange)="patch(i, { min_years: $event || null })"
                      [readonly]="!auth.canEdit()"
                    />
                    years
                  </label>
                }
                @case ('experience') {
                  <label class="years small">
                    at least
                    <input
                      class="input sm num"
                      type="number"
                      min="0"
                      max="40"
                      step="0.5"
                      [ngModel]="r.min_years"
                      (ngModelChange)="patch(i, { min_years: $event || null })"
                      [readonly]="!auth.canEdit()"
                    />
                    years in total
                  </label>
                }
                @case ('language') {
                  <select
                    class="select sm"
                    [ngModel]="r.language"
                    (ngModelChange)="patch(i, { language: $event })"
                    [disabled]="!auth.canEdit()"
                    aria-label="Language"
                  >
                    @for (l of languages; track l[0]) {
                      <option [value]="l[0]">{{ l[1] }}</option>
                    }
                  </select>
                  <span class="small muted">at least</span>
                  <select
                    class="select sm"
                    [ngModel]="r.min_level"
                    (ngModelChange)="patch(i, { min_level: +$event })"
                    [disabled]="!auth.canEdit()"
                    aria-label="Minimum level"
                  >
                    @for (level of levels; track $index) {
                      @if ($index > 0) {
                        <option [value]="$index">{{ level }}</option>
                      }
                    }
                  </select>
                }
                @case ('education') {
                  <span class="small muted">at least</span>
                  <select
                    class="select sm"
                    [ngModel]="r.min_degree"
                    (ngModelChange)="patch(i, { min_degree: +$event })"
                    [disabled]="!auth.canEdit()"
                    aria-label="Minimum degree"
                  >
                    @for (d of degrees; track $index) {
                      @if ($index > 0) {
                        <option [value]="$index">{{ d }}</option>
                      }
                    }
                  </select>
                }
                @default {
                  <span class="small muted"
                    >Compared with the CV by meaning (multilingual embeddings); shows the closest
                    passages.</span
                  >
                }
              }
            </div>
          </li>
        } @empty {
          <li class="empty">
            No requirements yet. Write them in the description and re-read, or add one.
          </li>
        }
      </ol>
    </div>
  `,
  styles: `
    .small {
      font-size: 12px;
    }
    .message {
      margin: 12px 18px 0;
    }
    .list {
      list-style: none;
      margin: 0;
      padding: 6px 0;
    }
    .list > li {
      padding: 12px 18px;
      border-bottom: 1px solid var(--border);
      display: grid;
      gap: 8px;
    }
    .list > li:last-child {
      border-bottom: 0;
    }
    .line {
      display: flex;
      gap: 8px;
      align-items: center;
    }
    .text {
      flex: 1;
    }
    .kind {
      width: 210px;
    }
    .must {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      width: 68px;
      justify-content: center;
      height: 30px;
      border-radius: 999px;
      border: 1px solid var(--border);
      font-size: 12px;
      font-weight: 600;
      color: var(--text-3);
      cursor: pointer;
    }
    .must input {
      display: none;
    }
    .must.on {
      background: var(--accent-soft);
      color: var(--accent-text);
      border-color: transparent;
    }
    .params {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
      padding-left: 76px;
    }
    .x {
      border: 0;
      background: none;
      color: inherit;
      cursor: pointer;
      padding: 0 0 0 2px;
      font-size: 14px;
      line-height: 1;
    }
    .input.sm,
    .select.sm {
      min-height: 26px;
      height: 26px;
      padding: 2px 8px;
      font-size: 12px;
      width: auto;
    }
    .years .input.sm {
      width: 64px;
    }
    .years {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      color: var(--text-2);
      margin-left: 8px;
    }
    .add-skill {
      position: relative;
    }
    .add-skill .input {
      width: 120px;
    }
    .suggest {
      position: absolute;
      top: 30px;
      left: 0;
      z-index: 5;
      display: grid;
      min-width: 220px;
      padding: 4px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      box-shadow: var(--shadow-lg);
    }
    .suggest button {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      border: 0;
      background: none;
      color: var(--text);
      padding: 6px 8px;
      border-radius: 4px;
      text-align: left;
      font: inherit;
      font-size: 13px;
      cursor: pointer;
    }
    .suggest button:hover {
      background: var(--surface-2);
    }
    @media (max-width: 800px) {
      .line {
        flex-wrap: wrap;
      }
      .kind {
        width: 100%;
      }
      .params {
        padding-left: 0;
      }
    }
  `,
})
export class RequirementsEditor {
  protected readonly auth = inject(AuthService);
  private readonly api = inject(Api);

  readonly vacancy = input.required<Vacancy>();
  readonly saved = output<Vacancy>();

  protected readonly kinds = KINDS;
  protected readonly levels = LEVEL_NAME;
  protected readonly degrees = DEGREES;
  protected readonly languages = Object.entries(LANGUAGE_NAME);

  protected readonly rows = signal<Requirement[]>([]);
  protected readonly dirty = signal(false);
  protected readonly busy = signal(false);
  protected readonly message = signal('');
  protected readonly failed = signal(false);

  protected readonly skillQuery = signal<Record<string, string>>({});
  protected readonly activeRow = signal<string | null>(null);
  private readonly query = signal('');
  protected readonly skills = httpResource<Skill[]>(() =>
    this.query().trim().length >= 2
      ? { url: '/api/skills', params: { q: this.query().trim() } }
      : undefined,
  );

  constructor() {
    effect(() => {
      this.rows.set(structuredClone(this.vacancy().requirements));
      this.dirty.set(false);
    });
  }

  protected patch(index: number, change: Partial<Requirement>): void {
    this.rows.update((rows) => rows.map((r, i) => (i === index ? { ...r, ...change } : r)));
    this.dirty.set(true);
  }

  protected add(): void {
    const taken = new Set(this.rows().map((r) => r.id));
    let n = this.rows().length + 1;
    while (taken.has(`r${n}`)) n++;
    this.rows.update((rows) => [
      ...rows,
      {
        id: `r${n}`,
        text: '',
        kind: 'skill',
        must: true,
        skills: [],
        any_of: false,
        min_years: null,
        language: null,
        min_level: null,
        min_degree: null,
        weight: 1,
      },
    ]);
    this.dirty.set(true);
  }

  protected remove(index: number): void {
    this.rows.update((rows) => rows.filter((_, i) => i !== index));
    this.dirty.set(true);
  }

  protected searchSkill(rowId: string, text: string): void {
    this.skillQuery.update((q) => ({ ...q, [rowId]: text }));
    this.activeRow.set(rowId);
    this.query.set(text);
  }

  protected addSkill(index: number, skill: Skill): void {
    const row = this.rows()[index]!;
    if (!row.skills.includes(skill.id)) this.patch(index, { skills: [...row.skills, skill.id] });
    this.skillQuery.update((q) => ({ ...q, [row.id]: '' }));
    this.activeRow.set(null);
    this.query.set('');
  }

  protected removeSkill(index: number, skillId: string): void {
    this.patch(index, { skills: this.rows()[index]!.skills.filter((s) => s !== skillId) });
  }

  protected reread(): void {
    this.run(this.api.parseRequirements(this.vacancy().description), (requirements) => {
      this.rows.set(requirements);
      this.dirty.set(true);
      return `Read ${requirements.length} requirements from the description. Review them, then save.`;
    });
  }

  protected save(): void {
    this.run(this.api.saveRequirements(this.vacancy().id, this.rows()), (vacancy) => {
      this.saved.emit(vacancy);
      return `Saved as version ${vacancy.requirements_version}. Applicants are being re-ranked.`;
    });
  }

  private run<T>(request: Observable<T>, done: (value: T) => string): void {
    this.busy.set(true);
    this.message.set('');
    request.subscribe({
      next: (value) => {
        this.busy.set(false);
        this.failed.set(false);
        this.message.set(done(value));
      },
      error: () => {
        this.busy.set(false);
        this.failed.set(true);
        this.message.set('The API refused the change. Check that every requirement has text.');
      },
    });
  }
}
