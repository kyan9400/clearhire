import { httpResource } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, signal } from '@angular/core';

import type { Overview as OverviewData, Source, Stage } from '../api/types';
import { BarChart, type Bar } from '../shared/bar-chart';
import { SOURCE_LABEL, STAGE_LABEL, percent } from '../shared/format';

@Component({
  selector: 'ch-overview',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [BarChart],
  template: `
    <div class="page">
      <header class="page-head">
        <div>
          <h1>Overview</h1>
          <p>Hiring across every open vacancy.</p>
        </div>
        <div class="segmented" role="tablist" aria-label="Show as">
          <button type="button" [class.active]="!asTable()" (click)="asTable.set(false)">
            Charts
          </button>
          <button type="button" [class.active]="asTable()" (click)="asTable.set(true)">
            Tables
          </button>
        </div>
      </header>

      @if (data.error()) {
        <div class="error-box">Could not load the overview.</div>
      } @else if (data.value(); as d) {
        <section class="tiles">
          <div class="card card-pad tile">
            <span class="muted">Applications</span>
            <strong class="num">{{ d.applications }}</strong>
            <span class="muted">{{ d.open_vacancies }} open vacancies</span>
          </div>
          <div class="card card-pad tile">
            <span class="muted">Meet every must-have</span>
            <strong class="num">{{ d.qualified_applications }}</strong>
            <span class="muted"
              >{{ share(d.qualified_applications, d.applications) }} of applications</span
            >
          </div>
          <div class="card card-pad tile">
            <span class="muted">Median time to hire</span>
            <strong class="num">{{ d.time_to_hire.median_days ?? '—' }}<small> days</small></strong>
            <span class="muted"
              >90th percentile {{ d.time_to_hire.p90_days ?? '—' }} days ·
              {{ d.time_to_hire.hires }} hires</span
            >
          </div>
          <div class="card card-pad tile">
            <span class="muted">In interviews now</span>
            <strong class="num">{{ d.by_stage['interview'] ?? 0 }}</strong>
            <span class="muted">{{ d.by_stage['offer'] ?? 0 }} with an offer</span>
          </div>
        </section>

        <section class="grid">
          <div class="card">
            <div class="card-head">
              <h2>Funnel</h2>
              <span class="muted">reached each stage</span>
            </div>
            <div class="card-pad">
              @if (asTable()) {
                <table class="table">
                  <thead>
                    <tr>
                      <th>Stage</th>
                      <th class="r">Applications</th>
                      <th class="r">From previous</th>
                    </tr>
                  </thead>
                  <tbody>
                    @for (step of d.funnel; track step.stage) {
                      <tr>
                        <td>{{ stageLabel(step.stage) }}</td>
                        <td class="r num">{{ step.reached }}</td>
                        <td class="r num">{{ pct(step.conversion) }}</td>
                      </tr>
                    }
                  </tbody>
                </table>
              } @else {
                <div class="funnel">
                  @for (step of d.funnel; track step.stage) {
                    <div class="step">
                      <span class="name">{{ stageLabel(step.stage) }}</span>
                      <span class="track" [title]="step.reached + ' applications'">
                        <span
                          class="fill"
                          [style.width.%]="(step.reached / funnelMax()) * 100"
                        ></span>
                      </span>
                      <span class="num value">{{ step.reached }}</span>
                      <span class="num conv muted">{{
                        step.conversion === null ? '' : pct(step.conversion)
                      }}</span>
                    </div>
                  }
                </div>
              }
            </div>
          </div>

          <div class="card">
            <div class="card-head">
              <h2>Match scores</h2>
              <span class="muted">every application, 0–100</span>
            </div>
            <div class="card-pad">
              @if (asTable()) {
                <table class="table">
                  <thead>
                    <tr>
                      <th>Score</th>
                      <th class="r">Applications</th>
                    </tr>
                  </thead>
                  <tbody>
                    @for (bar of scoreBars(); track bar.label) {
                      <tr>
                        <td>{{ bar.label }}</td>
                        <td class="r num">{{ bar.value }}</td>
                      </tr>
                    }
                  </tbody>
                </table>
              } @else {
                <ch-bar-chart
                  [bars]="scoreBars()"
                  unit="applications"
                  label="Applications by match score"
                />
              }
            </div>
          </div>

          <div class="card">
            <div class="card-head">
              <h2>Sources</h2>
              <span class="muted">share that reached an interview</span>
            </div>
            <table class="table">
              <thead>
                <tr>
                  <th>Source</th>
                  <th class="r">Applications</th>
                  <th class="r">Interviewed</th>
                  <th>Rate</th>
                </tr>
              </thead>
              <tbody>
                @for (row of d.sources; track row.source) {
                  <tr>
                    <td>{{ sourceLabel(row.source) }}</td>
                    <td class="r num">{{ row.applications }}</td>
                    <td class="r num">{{ row.advanced }}</td>
                    <td class="rate">
                      <span class="track"
                        ><span class="fill" [style.width.%]="row.interview_rate * 100"></span
                      ></span>
                      <span class="num">{{ pct(row.interview_rate) }}</span>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>

          <div class="card">
            <div class="card-head">
              <h2>Most-missed must-haves</h2>
              <span class="muted">what the market lacks</span>
            </div>
            <table class="table">
              <thead>
                <tr>
                  <th>Requirement</th>
                  <th class="r">Applicants without it</th>
                </tr>
              </thead>
              <tbody>
                @for (gap of d.common_gaps; track gap.vacancy + gap.requirement) {
                  <tr>
                    <td>
                      {{ gap.requirement }}
                      <div class="muted small">{{ gap.vacancy }}</div>
                    </td>
                    <td class="r num">{{ gap.applicants }}</td>
                  </tr>
                } @empty {
                  <tr>
                    <td colspan="2" class="empty">No gaps yet.</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        </section>
      } @else {
        <section class="tiles">
          @for (i of [1, 2, 3, 4]; track i) {
            <div class="card card-pad tile">
              <div class="skeleton"></div>
              <div class="skeleton big"></div>
            </div>
          }
        </section>
      }
    </div>
  `,
  styles: `
    .tiles {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 14px;
      margin-bottom: 14px;
    }
    .tile {
      display: grid;
      gap: 2px;
    }
    .tile strong {
      font-size: 28px;
      font-weight: 650;
      letter-spacing: -0.02em;
    }
    .tile small {
      font-size: 14px;
      font-weight: 500;
      color: var(--text-3);
    }
    .tile .skeleton.big {
      height: 28px;
      width: 60%;
      margin-top: 8px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
      gap: 14px;
    }
    .funnel {
      display: grid;
      gap: 10px;
    }
    .step {
      display: grid;
      grid-template-columns: 84px 1fr 40px 44px;
      align-items: center;
      gap: 10px;
    }
    .name {
      color: var(--text-2);
    }
    .value {
      text-align: right;
      font-weight: 600;
    }
    .conv {
      text-align: right;
      font-size: 12px;
    }
    .track {
      height: 10px;
      border-radius: 5px;
      background: var(--surface-2);
      overflow: hidden;
    }
    .fill {
      display: block;
      height: 100%;
      border-radius: 0 4px 4px 0;
      background: var(--accent);
    }
    .rate {
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 140px;
    }
    .rate .track {
      flex: 1;
      height: 6px;
    }
    .small {
      font-size: 12px;
    }
    @media (max-width: 720px) {
      .grid {
        grid-template-columns: 1fr;
      }
    }
  `,
})
export class Overview {
  protected readonly data = httpResource<OverviewData>(() => '/api/analytics/overview');
  protected readonly asTable = signal(false);

  protected readonly funnelMax = computed(() =>
    Math.max(1, ...(this.data.value()?.funnel.map((s) => s.reached) ?? [1])),
  );
  protected readonly scoreBars = computed<Bar[]>(() =>
    (this.data.value()?.score_distribution ?? []).map((b) => ({
      label: `${Math.round(b.low * 100)}–${Math.round(b.high * 100)}`,
      value: b.count,
    })),
  );

  protected stageLabel(stage: string): string {
    return STAGE_LABEL[stage as Stage] ?? stage;
  }

  protected sourceLabel(source: string): string {
    return SOURCE_LABEL[source as Source] ?? source;
  }

  protected pct(value: number | null): string {
    return percent(value);
  }

  protected share(part: number, whole: number): string {
    return whole ? percent(part / whole) : '—';
  }
}
