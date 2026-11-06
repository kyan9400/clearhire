import { CdkDrag, CdkDragDrop, CdkDropList, CdkDropListGroup } from '@angular/cdk/drag-drop';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';

import { STAGES, type RankedCandidate, type Stage } from '../api/types';
import { Api } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { STAGE_LABEL, duration } from '../shared/format';
import { Score } from '../shared/score';

/**
 * Applicants by stage. Dragging a card moves the application: the card moves at once and goes back if the
 * API refuses. Within a stage, cards stay in ranking order.
 */
@Component({
  selector: 'ch-pipeline',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CdkDropListGroup, CdkDropList, CdkDrag, Score],
  template: `
    @if (error()) {
      <div class="error-box" role="alert">{{ error() }}</div>
    }
    <div class="board" cdkDropListGroup>
      @for (stage of stages; track stage) {
        <section class="column" [class.rejected]="stage === 'rejected'">
          <header>
            <h3>{{ label[stage] }}</h3>
            <span class="count num">{{ columns()[stage].length }}</span>
          </header>
          <div
            class="list"
            cdkDropList
            [cdkDropListData]="stage"
            [cdkDropListDisabled]="!auth.canEdit()"
            (cdkDropListDropped)="drop($event)"
            [attr.aria-label]="label[stage]"
          >
            @for (c of columns()[stage]; track c.application_id) {
              <button
                type="button"
                class="card-item"
                cdkDrag
                [cdkDragData]="c"
                (click)="selected.emit(c)"
              >
                <span class="top">
                  <strong>{{ c.name }}</strong>
                  @if (c.qualified) {
                    <span class="chip met">all must-haves</span>
                  }
                </span>
                <ch-score [value]="c.score" [qualified]="c.qualified" />
                <span class="muted small"
                  >{{ c.must_met }}/{{ c.must_total }} must ·
                  {{ duration(c.experience_months) }}</span
                >
              </button>
            } @empty {
              <p class="empty-col muted">Drop here</p>
            }
          </div>
        </section>
      }
    </div>
  `,
  styles: `
    .board {
      display: grid;
      grid-template-columns: repeat(6, minmax(190px, 1fr));
      gap: 10px;
      overflow-x: auto;
      padding-bottom: 8px;
    }
    .column {
      display: flex;
      flex-direction: column;
      min-height: 320px;
      border-radius: var(--radius);
      background: var(--surface-2);
      border: 1px solid var(--border);
    }
    .column.rejected {
      opacity: 0.85;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 12px 6px;
    }
    .count {
      font-size: 12px;
      color: var(--text-3);
    }
    .list {
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 6px;
      padding: 6px 8px 10px;
    }
    .card-item {
      display: grid;
      gap: 6px;
      text-align: left;
      padding: 10px;
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      background: var(--surface);
      color: var(--text);
      font: inherit;
      cursor: grab;
      box-shadow: var(--shadow);
    }
    .card-item:active {
      cursor: grabbing;
    }
    .top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 6px;
    }
    .top strong {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .small {
      font-size: 12px;
    }
    .empty-col {
      margin: auto;
      font-size: 12px;
    }
  `,
})
export class Pipeline {
  protected readonly auth = inject(AuthService);
  private readonly api = inject(Api);

  readonly applicants = input.required<RankedCandidate[]>();
  readonly selected = output<RankedCandidate>();

  protected readonly stages = STAGES;
  protected readonly label = STAGE_LABEL;
  protected readonly duration = duration;
  protected readonly error = signal('');
  /** Stages changed here and not yet reflected in `applicants`. */
  private readonly moved = signal<Record<string, Stage>>({});

  protected readonly columns = computed(() => {
    const moved = this.moved();
    const out = Object.fromEntries(STAGES.map((s) => [s, [] as RankedCandidate[]])) as Record<
      Stage,
      RankedCandidate[]
    >;
    for (const c of this.applicants()) {
      if (!c.application_id) continue;
      const stage = moved[c.application_id] ?? c.stage ?? 'new';
      out[stage].push({ ...c, stage });
    }
    return out;
  });

  protected drop(event: CdkDragDrop<Stage, Stage, RankedCandidate>): void {
    const from = event.previousContainer.data;
    const to = event.container.data;
    const id = event.item.data.application_id;
    if (from === to || !id) return;
    this.error.set('');
    this.moved.update((m) => ({ ...m, [id]: to }));
    this.api.moveApplication(id, to).subscribe({
      error: () => {
        this.moved.update((m) => ({ ...m, [id]: from }));
        this.error.set(`Could not move ${event.item.data.name} to ${STAGE_LABEL[to]}.`);
      },
    });
  }
}
