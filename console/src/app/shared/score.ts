import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import type { RequirementResult } from '../api/types';
import { Icon, type IconName } from './icon';

/** A score from 0 to 1 as a number and a bar; colour follows how many must-haves are met. */
@Component({
  selector: 'ch-score',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span class="value num">{{ (value() * 100).toFixed(0) }}</span>
    <span class="bar" [class]="tone()"><span [style.width.%]="value() * 100"></span></span>
  `,
  styles: `
    :host {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-width: 96px;
    }
    .value {
      width: 26px;
      text-align: right;
      font-weight: 600;
    }
    .bar {
      flex: 1;
      height: 6px;
      border-radius: 3px;
      background: var(--surface-2);
      overflow: hidden;
    }
    .bar span {
      display: block;
      height: 100%;
      border-radius: 3px;
      background: var(--accent);
    }
    .bar.met span {
      background: var(--met);
    }
    .bar.partial span {
      background: var(--partial);
    }
  `,
})
export class Score {
  readonly value = input.required<number>();
  readonly qualified = input<boolean | null>(null);
  protected readonly tone = computed(() => {
    const q = this.qualified();
    return q === null ? '' : q ? 'met' : 'partial';
  });
}

const STATUS_ICON: Record<RequirementResult['status'], IconName> = {
  met: 'check',
  partial: 'minus',
  missing: 'x',
};
const STATUS_LABEL: Record<RequirementResult['status'], string> = {
  met: 'Met',
  partial: 'Partly',
  missing: 'Missing',
};

@Component({
  selector: 'ch-status',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon],
  template: `<span class="chip" [class]="status()"
    ><ch-icon [name]="icon()" [size]="12" />{{ label() }}</span
  >`,
})
export class Status {
  readonly status = input.required<RequirementResult['status']>();
  protected readonly icon = computed(() => STATUS_ICON[this.status()]);
  protected readonly label = computed(() => STATUS_LABEL[this.status()]);
}
