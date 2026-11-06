import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';

export interface Bar {
  label: string;
  value: number;
  /** Shown in the tooltip after the value. */
  detail?: string;
}

/**
 * One series of vertical bars (a histogram, a count per bucket). Bars grow from the baseline with rounded
 * data-ends, a 2px gap between them, a recessive grid, and a tooltip on hover or focus of each column.
 */
@Component({
  selector: 'ch-bar-chart',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="plot" [style.height.px]="height()" role="img" [attr.aria-label]="label()">
      @for (tick of ticks(); track tick) {
        <div class="grid" [style.bottom.%]="(tick / max()) * 100">
          <span class="num">{{ tick }}</span>
        </div>
      }
      <div class="bars">
        @for (bar of bars(); track bar.label; let i = $index) {
          <button
            type="button"
            class="col"
            (mouseenter)="active.set(i)"
            (mouseleave)="active.set(null)"
            (focus)="active.set(i)"
            (blur)="active.set(null)"
            [attr.aria-label]="bar.label + ': ' + bar.value"
          >
            <span class="fill" [style.height.%]="(bar.value / max()) * 100"></span>
            @if (active() === i) {
              <span class="tip" role="tooltip">
                <strong class="num">{{ bar.value }}</strong> {{ unit() }}
                <span>{{ bar.label }}{{ bar.detail ? ' · ' + bar.detail : '' }}</span>
              </span>
            }
          </button>
        }
      </div>
    </div>
    <div class="axis">
      @for (bar of bars(); track bar.label; let i = $index) {
        <span [class.hidden]="i % labelEvery() !== 0">{{ bar.label }}</span>
      }
    </div>
  `,
  styles: `
    :host {
      display: block;
      padding-left: 28px;
    }
    .plot {
      position: relative;
    }
    .grid {
      position: absolute;
      left: 0;
      right: 0;
      border-top: 1px solid var(--border);
    }
    .grid span {
      position: absolute;
      left: -28px;
      top: -8px;
      width: 22px;
      text-align: right;
      font-size: 11px;
      color: var(--text-3);
    }
    .bars {
      position: absolute;
      inset: 0;
      display: flex;
      align-items: flex-end;
      gap: 2px;
    }
    .col {
      position: relative;
      flex: 1;
      height: 100%;
      display: flex;
      align-items: flex-end;
      border: 0;
      padding: 0;
      background: transparent;
      cursor: default;
    }
    .col:hover .fill,
    .col:focus-visible .fill {
      filter: brightness(1.15);
    }
    .fill {
      width: 100%;
      min-height: 1px;
      border-radius: 4px 4px 0 0;
      background: var(--accent);
    }
    .tip {
      position: absolute;
      bottom: calc(100% + 6px);
      left: 50%;
      transform: translateX(-50%);
      z-index: 2;
      display: grid;
      gap: 1px;
      padding: 6px 9px;
      border-radius: 6px;
      white-space: nowrap;
      text-align: left;
      background: var(--text);
      color: var(--bg);
      font-size: 12px;
      box-shadow: var(--shadow-lg);
      pointer-events: none;
    }
    .tip span {
      opacity: 0.8;
    }
    .axis {
      display: flex;
      gap: 2px;
      margin-top: 6px;
    }
    .axis span {
      flex: 1;
      text-align: center;
      font-size: 11px;
      color: var(--text-3);
      white-space: nowrap;
    }
    .axis span.hidden {
      visibility: hidden;
    }
  `,
})
export class BarChart {
  readonly bars = input.required<Bar[]>();
  readonly label = input('');
  readonly unit = input('');
  readonly height = input(160);

  protected readonly active = signal<number | null>(null);
  protected readonly max = computed(() => niceMax(Math.max(1, ...this.bars().map((b) => b.value))));
  protected readonly ticks = computed(() => {
    const max = this.max();
    return [0, max / 2, max].map((t) => Math.round(t));
  });
  protected readonly labelEvery = computed(() => Math.max(1, Math.ceil(this.bars().length / 6)));
}

/** Rounds a maximum up to 1, 2 or 5 times a power of ten, so the grid lines land on round numbers. */
export function niceMax(value: number): number {
  const power = 10 ** Math.floor(Math.log10(value));
  for (const step of [1, 2, 5, 10]) {
    if (value <= step * power) return step * power;
  }
  return 10 * power;
}
