import { HttpClient, httpResource } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';

import type { AnchorCheck, Anchors } from '../api/types';
import { Icon } from '../shared/icon';

/** The audit log's anchors on the chain, and a check of the whole log against them. */
@Component({
  selector: 'ch-anchors-card',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon],
  template: `
    @if (anchors.value(); as a) {
      <section class="card card-pad anchors" aria-labelledby="anchors-title">
        <div class="head">
          <ch-icon name="link" [size]="20" />
          <div class="grow">
            <h3 id="anchors-title">Anchored on chain</h3>
            @if (a.enabled) {
              <p class="muted small">
                {{ a.chain_name }}{{ a.chain_id ? ' · chain ' + a.chain_id : '' }} · contract
                <span class="mono">{{ a.contract }}</span> · every {{ period(a.period_seconds) }},
                {{ a.unanchored }} entries waiting
              </p>
            } @else {
              <p class="muted small">Anchoring is not configured on this server.</p>
            }
          </div>
          @if (a.enabled) {
            <button class="btn sm" type="button" (click)="runCheck()" [disabled]="checking()">
              {{ checking() ? 'Checking…' : 'Check the log against the chain' }}
            </button>
          }
        </div>

        @if (check(); as c) {
          <p
            class="result"
            [class.ok]="c.reachable && c.matching === c.anchors"
            [class.bad]="c.first_mismatch_period !== null"
          >
            @if (!c.reachable) {
              The chain could not be reached; {{ c.matching }} of {{ c.anchors }} anchors checked.
            } @else if (c.first_mismatch_period === null) {
              All {{ c.anchors }} anchored periods rebuilt from the log match the chain: nothing
              anchored has been changed.
            } @else {
              The log no longer matches the chain from the period starting
              {{ periodStart(c.first_mismatch_period, a.period_seconds) }}: entries anchored then
              have been changed.
            }
          </p>
        }

        @if (a.items.length) {
          <div class="table-wrap">
            <table class="table compact">
              <thead>
                <tr>
                  <th>Period (UTC)</th>
                  <th class="r">Entries</th>
                  <th>Ids</th>
                  <th>Merkle root</th>
                  <th>Transaction</th>
                </tr>
              </thead>
              <tbody>
                @for (row of a.items.slice(0, 6); track row.period) {
                  <tr>
                    <td class="num">{{ row.starts_at.slice(0, 16).replace('T', ' ') }}</td>
                    <td class="r num">{{ row.entries }}</td>
                    <td class="num muted">{{ row.first_id }}–{{ row.last_id }}</td>
                    <td class="mono" [title]="row.root">{{ row.root.slice(0, 14) }}…</td>
                    <td class="mono">
                      @if (row.tx_hash && a.explorer_tx_url) {
                        <a [href]="a.explorer_tx_url + row.tx_hash" target="_blank" rel="noopener"
                          >{{ row.tx_hash.slice(0, 12) }}…</a
                        >
                      } @else {
                        <span [title]="row.tx_hash">{{
                          row.tx_hash ? row.tx_hash.slice(0, 12) + '…' : 'recovered'
                        }}</span>
                        <span class="muted"> · block {{ row.block }}</span>
                      }
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        }
      </section>
    }
  `,
  styles: `
    .anchors {
      margin-bottom: 14px;
    }
    .head {
      display: flex;
      align-items: center;
      gap: 12px;
      color: var(--accent-text);
    }
    .head h3 {
      margin: 0;
      color: var(--text);
    }
    .head p {
      margin: 2px 0 0;
    }
    .small {
      font-size: 12px;
    }
    .mono {
      word-break: break-all;
    }
    .result {
      margin: 12px 0 0;
      padding: 8px 12px;
      border-radius: var(--radius-sm);
      background: var(--surface-2);
      font-size: 13px;
    }
    .result.ok {
      background: var(--met-soft);
      color: var(--met);
    }
    .result.bad {
      background: var(--missing-soft);
      color: var(--missing);
    }
    .table-wrap {
      margin-top: 12px;
    }
  `,
})
export class AnchorsCard {
  private readonly http = inject(HttpClient);
  protected readonly anchors = httpResource<Anchors>(() => '/api/audit/anchors');
  protected readonly check = signal<AnchorCheck | null>(null);
  protected readonly checking = signal(false);
  protected readonly hasAnchors = computed(() => (this.anchors.value()?.items.length ?? 0) > 0);

  protected runCheck(): void {
    this.checking.set(true);
    this.http.get<AnchorCheck>('/api/audit/anchors/check').subscribe({
      next: (c) => {
        this.check.set(c);
        this.checking.set(false);
      },
      error: () => {
        this.check.set({ anchors: 0, matching: 0, reachable: false, first_mismatch_period: null });
        this.checking.set(false);
      },
    });
  }

  protected period(seconds: number): string {
    return seconds % 3600 === 0
      ? seconds === 3600
        ? 'hour'
        : `${seconds / 3600} hours`
      : `${seconds / 60} minutes`;
  }

  protected periodStart(period: number, seconds: number): string {
    return new Date(period * seconds * 1000).toISOString().slice(0, 16).replace('T', ' ');
  }
}
