import { HttpClient, httpResource } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import type { AuditEntry, AuditVerify, Proof } from '../api/types';
import { AnchorsCard } from './anchors-card';
import { Icon } from '../shared/icon';

@Component({
  selector: 'ch-audit',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, Icon, AnchorsCard],
  template: `
    <div class="page">
      <header class="page-head">
        <div>
          <h1>Audit log</h1>
          <p>
            Every decision and every view of personal data. Each entry carries the hash of the one
            before it, so a changed or deleted entry breaks the chain.
          </p>
        </div>
      </header>

      <div
        class="card card-pad chain"
        [class.ok]="verify.value()?.valid"
        [class.bad]="verify.value()?.valid === false"
      >
        <ch-icon [name]="verify.value()?.valid === false ? 'x' : 'shield'" [size]="22" />
        <div class="grow">
          @if (verify.value(); as v) {
            @if (v.valid) {
              <strong>Chain intact</strong> — {{ v.entries }} entries recomputed and verified.
            } @else {
              <strong>Chain broken at entry {{ v.first_bad_id }}</strong> — that entry or one before
              it was changed.
            }
            <div class="mono muted">head {{ v.head }}</div>
          } @else {
            Verifying the chain…
          }
        </div>
        <button
          class="btn sm"
          type="button"
          (click)="verify.reload()"
          [disabled]="verify.isLoading()"
        >
          Verify again
        </button>
      </div>

      <ch-anchors-card />

      <form class="row filters" (ngSubmit)="apply()">
        <input
          class="input"
          name="action"
          placeholder="Action, e.g. application.stage_changed"
          [(ngModel)]="actionField"
        />
        <input class="input" name="entity" placeholder="Entity id" [(ngModel)]="entityField" />
        <button class="btn" type="submit">Filter</button>
      </form>

      <div class="card">
        <div class="table-wrap">
          <table class="table">
            <thead>
              <tr>
                <th class="r">#</th>
                <th>When</th>
                <th>Who</th>
                <th>Action</th>
                <th>Entity</th>
                <th>Details</th>
                <th>Hash</th>
                <th>On chain</th>
              </tr>
            </thead>
            <tbody>
              @for (e of entries.value() ?? []; track e.id) {
                <tr>
                  <td class="r num muted">{{ e.id }}</td>
                  <td class="num">{{ e.at.slice(0, 19).replace('T', ' ') }}</td>
                  <td>{{ e.actor_type }}</td>
                  <td>
                    <span class="chip">{{ e.action }}</span>
                  </td>
                  <td class="mono">{{ e.entity_type }} {{ e.entity_id.slice(0, 8) }}</td>
                  <td class="mono details">{{ json(e.data) }}</td>
                  <td class="mono muted">{{ e.hash.slice(0, 12) }}…</td>
                  <td class="proof">
                    @switch (proofState(e.id)) {
                      @case ('idle') {
                        <button class="btn ghost sm" type="button" (click)="prove(e.id)">
                          Prove
                        </button>
                      }
                      @case ('loading') {
                        <span class="muted">…</span>
                      }
                      @case ('verified') {
                        <span
                          class="chip met"
                          title="The contract's verifyEntry accepted this entry and its Merkle proof"
                        >
                          <ch-icon name="check" [size]="11" />verified
                        </span>
                      }
                      @case ('pending') {
                        <span
                          class="chip"
                          title="Logged after the last anchor; it will be in the next one"
                          >not yet</span
                        >
                      }
                      @case ('changed') {
                        <span class="chip missing" title="This entry differs from what was anchored"
                          >changed</span
                        >
                      }
                      @default {
                        <span class="chip partial" title="The chain could not be reached"
                          >unknown</span
                        >
                      }
                    }
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="8" class="empty">
                    {{ entries.isLoading() ? 'Loading…' : 'No entries.' }}
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
    .chain {
      display: flex;
      align-items: center;
      gap: 14px;
      margin-bottom: 14px;
    }
    .chain.ok {
      border-color: color-mix(in srgb, var(--met) 40%, var(--border));
      background: var(--met-soft);
      color: var(--met);
    }
    .chain.bad {
      border-color: var(--missing);
      background: var(--missing-soft);
      color: var(--missing);
    }
    .chain .mono {
      margin-top: 2px;
      word-break: break-all;
    }
    .filters {
      margin-bottom: 14px;
    }
    .filters .input {
      width: 300px;
    }
    .proof {
      white-space: nowrap;
    }
    .details {
      max-width: 380px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  `,
})
export class Audit {
  private readonly http = inject(HttpClient);
  private readonly proofs = signal<Record<number, Proof | 'loading' | 'error'>>({});
  protected readonly verify = httpResource<AuditVerify>(() => '/api/audit/verify');
  private readonly action = signal('');
  private readonly entity = signal('');
  protected readonly entries = httpResource<AuditEntry[]>(() => ({
    url: '/api/audit',
    params: {
      limit: 200,
      ...(this.action() ? { action: this.action() } : {}),
      ...(this.entity() ? { entity_id: this.entity() } : {}),
    },
  }));
  protected actionField = '';
  protected entityField = '';

  protected apply(): void {
    this.action.set(this.actionField.trim());
    this.entity.set(this.entityField.trim());
  }

  protected prove(id: number): void {
    this.proofs.update((all) => ({ ...all, [id]: 'loading' }));
    this.http.get<Proof>(`/api/audit/${id}/proof`).subscribe({
      next: (proof) => this.proofs.update((all) => ({ ...all, [id]: proof })),
      error: () => this.proofs.update((all) => ({ ...all, [id]: 'error' })),
    });
  }

  protected proofState(
    id: number,
  ): 'idle' | 'loading' | 'verified' | 'pending' | 'changed' | 'unknown' {
    const proof = this.proofs()[id];
    if (proof === undefined) return 'idle';
    if (proof === 'loading') return 'loading';
    if (proof === 'error') return 'unknown';
    if (!proof.anchored) return 'pending';
    if (proof.verified_on_chain) return 'verified';
    if (proof.root_matches_log === false || proof.verified_on_chain === false) return 'changed';
    return 'unknown';
  }

  protected json(data: unknown): string {
    return JSON.stringify(data);
  }
}
