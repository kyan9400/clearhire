import { HttpErrorResponse, httpResource } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  input,
  signal,
  untracked,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import type { Subscription } from 'rxjs';

import type { AiAnswer, AiSource, AiSummary, AssistantStatus } from '../api/types';
import { Api } from '../core/api.service';
import { Icon } from '../shared/icon';

export interface TextPart {
  text: string;
  ref?: string;
}

/** Splits model text around its [E1] / [P2] / [S1] / [R3] references, keeping only known ones. */
export function citedParts(text: string, known: ReadonlySet<string>): TextPart[] {
  const parts: TextPart[] = [];
  let last = 0;
  for (const match of text.matchAll(/\s?\[([EPSRK]\d{1,3})\]/g)) {
    const index = match.index ?? 0;
    if (index > last) parts.push({ text: text.slice(last, index) });
    const ref = match[1]!;
    if (known.has(ref)) parts.push({ text: ref, ref });
    last = index + match[0].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last) });
  return parts;
}

const SUGGESTIONS = {
  en: [
    'What did they build with the main stack?',
    'Have they led a team?',
    'Which must-haves are weakest, and why?',
  ],
  ru: [
    'Что кандидат делал на основном стеке?',
    'Был ли опыт руководства командой?',
    'Какие обязательные требования слабее всего и почему?',
  ],
};

interface Asked {
  question: string;
  answer?: AiAnswer;
  error?: string;
}

function message(error: unknown): string {
  if (error instanceof HttpErrorResponse) {
    const detail = (error.error as { detail?: unknown } | null)?.detail;
    if (typeof detail === 'string') return detail;
    if (error.status === 429) return 'Too many assistant requests. Try again later.';
  }
  return 'The assistant could not answer. Try again.';
}

@Component({
  selector: 'ch-assistant-card',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, Icon],
  template: `
    <section class="ai" aria-label="AI assistant">
      <div class="ai-head">
        <span class="ai-title"><ch-icon name="sparkle" [size]="14" />AI summary</span>
        <span class="muted tiny" [title]="modelNote()">{{ status.value()?.model ?? 'rules' }}</span>
        @if (summary(); as s) {
          @if (s.model !== 'rules' && !loadingSummary()) {
            <button class="btn ghost xs" type="button" (click)="load(true)" title="Write it again">
              Rewrite
            </button>
          }
        }
      </div>

      @if (loadingSummary()) {
        <div class="skeleton"></div>
        <div class="skeleton short"></div>
      } @else if (summary(); as s) {
        <p class="summary">
          @for (sentence of s.sentences; track $index) {
            <span>{{ sentence.text }}</span>
            @for (ref of sentence.refs; track ref) {
              <button
                type="button"
                class="ref"
                [class.open]="openRef() === ref"
                (click)="toggle(ref)"
                [attr.aria-expanded]="openRef() === ref"
              >
                {{ ref }}
              </button>
            }
            {{ ' ' }}
          }
        </p>
        @if (openSource(s.sources); as src) {
          <blockquote class="source">
            {{ src.text }}
            <footer class="muted">{{ describe(src) }}</footer>
          </blockquote>
        }
        @if (s.dropped) {
          <p class="muted tiny">
            {{ s.dropped }} sentence{{ s.dropped === 1 ? '' : 's' }} removed for citing nothing in
            the CV.
          </p>
        }
        @for (note of s.notes; track $index) {
          <p class="muted tiny">Written from the verdicts: {{ note }}.</p>
        }
      } @else if (summaryError()) {
        <p class="error-box">{{ summaryError() }}</p>
      }

      @if (status.value()?.enabled) {
        <div class="qa">
          @for (item of asked(); track $index; let turn = $index) {
            <div class="turn">
              <p class="q">{{ item.question }}</p>
              @if (item.answer; as a) {
                <div class="a" [class.refused]="a.refused">
                  <p>
                    @for (part of parts(a); track $index) {
                      @if (part.ref) {
                        <button
                          type="button"
                          class="ref"
                          [class.open]="openRef() === key(turn, part.ref)"
                          (click)="toggle(key(turn, part.ref))"
                        >
                          {{ part.ref }}
                        </button>
                      } @else {
                        <span>{{ part.text }}</span>
                      }
                    }
                  </p>
                  @for (src of a.sources; track src.ref) {
                    @if (openRef() === key(turn, src.ref)) {
                      <blockquote class="source">
                        {{ src.text }}
                        <footer class="muted">{{ describe(src) }}</footer>
                      </blockquote>
                    }
                  }
                  @if (!a.refused) {
                    <div class="meta tiny">
                      @if (a.grounded) {
                        <span class="chip met"
                          ><ch-icon name="check" [size]="11" />checked against the CV</span
                        >
                      } @else {
                        <span
                          class="chip partial"
                          title="A claim cites nothing, or a quote is not in the CV"
                        >
                          verify before relying on it
                        </span>
                      }
                      <span class="muted">{{ a.seconds.toFixed(1) }} s</span>
                      @if (a.steps.length) {
                        <details>
                          <summary class="muted">
                            {{ a.steps.length }} step{{ a.steps.length === 1 ? '' : 's' }}
                          </summary>
                          <ol class="steps">
                            @for (step of a.steps; track $index) {
                              <li>
                                <code>{{ step.tool }}</code>
                                {{ stepArgs(step.arguments) }}
                                <span class="muted">→ {{ step.refs.join(', ') || 'nothing' }}</span>
                              </li>
                            }
                          </ol>
                        </details>
                      }
                    </div>
                    @for (q of a.quotes; track $index) {
                      @if (!q.found) {
                        <p class="tiny warn">“{{ q.text }}” is not in the CV.</p>
                      }
                    }
                  }
                </div>
              } @else if (item.error) {
                <p class="error-box">{{ item.error }}</p>
              } @else {
                <div class="skeleton"></div>
                <p class="muted tiny">Reading the CV…</p>
              }
            </div>
          }

          @if (!asked().length) {
            <div class="suggest">
              @for (s of suggestions(); track s) {
                <button type="button" class="btn xs" (click)="ask(s)">{{ s }}</button>
              }
            </div>
          }
          <form class="row" (ngSubmit)="ask(question)">
            <input
              class="input grow"
              name="question"
              placeholder="Ask about this candidate's CV"
              [(ngModel)]="question"
              maxlength="500"
              autocomplete="off"
            />
            <button class="btn sm" type="submit" [disabled]="question.trim().length < 3 || busy()">
              Ask
            </button>
          </form>
          <p class="muted tiny">
            The model reads the CV with personal details removed and must cite it. Questions about
            age, gender, family, health or origin are refused.
          </p>
        </div>
      }
    </section>
  `,
  styles: `
    .ai {
      margin-bottom: 14px;
      padding: 12px 14px;
      border: 1px solid color-mix(in srgb, var(--accent) 30%, var(--border));
      border-radius: var(--radius);
      background: color-mix(in srgb, var(--accent-soft) 45%, var(--surface));
    }
    .ai-head {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 6px;
    }
    .ai-title {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      font-weight: 600;
      color: var(--accent-text);
      flex: 1;
    }
    .tiny {
      font-size: 11.5px;
    }
    .summary {
      margin: 0;
      line-height: 1.65;
    }
    .ref {
      display: inline-block;
      margin: 0 1px;
      padding: 0 5px;
      border: 1px solid var(--border-strong);
      border-radius: 4px;
      background: var(--surface);
      color: var(--accent-text);
      font: 600 10.5px/1.6 var(--mono);
      vertical-align: 1px;
      cursor: pointer;
    }
    .ref.open {
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
    }
    .source {
      margin: 8px 0 0;
      padding: 8px 10px;
      border-left: 3px solid var(--accent);
      border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
      background: var(--surface);
      font-size: 12.5px;
      line-height: 1.55;
      white-space: pre-wrap;
    }
    .source footer {
      margin-top: 3px;
      font-size: 11px;
      white-space: normal;
    }
    .qa {
      margin-top: 12px;
      padding-top: 10px;
      border-top: 1px solid var(--border);
      display: grid;
      gap: 10px;
    }
    .turn {
      display: grid;
      gap: 6px;
    }
    .q {
      margin: 0;
      justify-self: end;
      max-width: 90%;
      padding: 6px 10px;
      border-radius: 10px 10px 2px 10px;
      background: var(--accent);
      color: #fff;
      font-size: 13px;
    }
    .a {
      padding: 8px 10px;
      border-radius: 10px 10px 10px 2px;
      background: var(--surface);
      border: 1px solid var(--border);
      font-size: 13px;
      line-height: 1.6;
    }
    .a p {
      margin: 0;
    }
    .a.refused {
      background: var(--surface-2);
      color: var(--text-2);
    }
    .meta {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
      margin-top: 6px;
    }
    .meta details {
      width: 100%;
    }
    .meta summary {
      cursor: pointer;
    }
    .steps {
      margin: 4px 0 0;
      padding-left: 18px;
      display: grid;
      gap: 2px;
    }
    .warn {
      margin: 4px 0 0;
      color: var(--partial);
    }
    .suggest {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .btn.xs {
      padding: 2px 8px;
      font-size: 12px;
      min-height: 0;
    }
    .skeleton {
      height: 12px;
      margin: 6px 0;
    }
    .skeleton.short {
      width: 60%;
    }
  `,
})
export class AssistantCard {
  private readonly api = inject(Api);

  readonly vacancyId = input.required<string>();
  readonly candidateId = input.required<string>();
  readonly language = input<string>('en');

  protected readonly status = httpResource<AssistantStatus>(() => '/api/assistant');
  protected readonly summary = signal<AiSummary | null>(null);
  protected readonly summaryError = signal<string | null>(null);
  protected readonly loadingSummary = signal(false);
  protected readonly asked = signal<Asked[]>([]);
  protected readonly openRef = signal<string | null>(null);
  protected readonly busy = computed(() => this.asked().some((a) => !a.answer && !a.error));
  protected readonly suggestions = computed(() =>
    this.language() === 'ru' ? SUGGESTIONS.ru : SUGGESTIONS.en,
  );
  protected question = '';
  private request: Subscription | null = null;

  constructor() {
    // a new candidate: a fresh summary and an empty conversation
    effect(() => {
      const ids = [this.vacancyId(), this.candidateId()];
      untracked(() => {
        this.asked.set([]);
        this.openRef.set(null);
        if (ids.every(Boolean)) this.load(false);
      });
    });
    inject(DestroyRef).onDestroy(() => this.request?.unsubscribe());
  }

  protected load(refresh: boolean): void {
    this.request?.unsubscribe();
    this.loadingSummary.set(true);
    this.summaryError.set(null);
    this.request = this.api.aiSummary(this.vacancyId(), this.candidateId(), refresh).subscribe({
      next: (s) => {
        this.summary.set(s);
        this.loadingSummary.set(false);
      },
      error: (e: unknown) => {
        this.summary.set(null);
        this.summaryError.set(message(e));
        this.loadingSummary.set(false);
      },
    });
  }

  protected ask(text: string): void {
    const question = text.trim();
    if (question.length < 3 || this.busy()) return;
    this.question = '';
    const index = this.asked().length;
    this.asked.update((list) => [...list, { question }]);
    const candidate = this.candidateId();
    this.api.ask(this.vacancyId(), candidate, question).subscribe({
      next: (answer) => this.settle(candidate, index, { question, answer }),
      error: (e: unknown) => this.settle(candidate, index, { question, error: message(e) }),
    });
  }

  private settle(candidate: string, index: number, item: Asked): void {
    if (candidate !== this.candidateId()) return; // the panel moved on to someone else
    this.asked.update((list) => list.map((old, i) => (i === index ? item : old)));
  }

  protected toggle(ref: string): void {
    this.openRef.update((open) => (open === ref ? null : ref));
  }

  protected openSource(sources: AiSource[]): AiSource | undefined {
    return sources.find((s) => s.ref === this.openRef());
  }

  /** References in different answers can repeat (P1 in two answers), so open state is per answer. */
  protected key(turn: number, ref: string): string {
    return `${turn}:${ref}`;
  }

  protected parts(answer: AiAnswer): TextPart[] {
    return citedParts(answer.text, new Set(answer.sources.map((s) => s.ref)));
  }

  protected describe(src: AiSource): string {
    const kind = {
      evidence: 'evidence',
      passage: 'found by search',
      section: 'CV section',
      requirement: 'requirement',
      skill: 'skill matcher, exact',
    }[src.kind];
    return [src.section, src.page ? `page ${src.page}` : '', kind].filter(Boolean).join(' · ');
  }

  protected stepArgs(args: Record<string, string>): string {
    return Object.values(args)
      .map((v) => `“${v}”`)
      .join(' ');
  }

  protected modelNote(): string {
    return this.status.value()?.enabled
      ? 'A local model on Clearhire’s own server: CV text never leaves it.'
      : 'No language model configured: the summary is written from the verdicts.';
  }
}
