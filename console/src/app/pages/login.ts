import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { AuthService } from '../core/auth.service';

const DEMO = [
  {
    email: 'recruiter@clearhire.demo',
    label: 'Recruiter',
    note: 'ranks, moves candidates, sees personal data',
  },
  {
    email: 'manager@clearhire.demo',
    label: 'Hiring manager',
    note: 'reviews shortlists, always blind',
  },
  { email: 'admin@clearhire.demo', label: 'Admin', note: 'everything, including the audit log' },
];

@Component({
  selector: 'ch-login',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule],
  template: `
    <div class="wrap">
      <section class="intro">
        <span class="logo" aria-hidden="true"></span>
        <h1>Clearhire</h1>
        <p class="lead">Recruiting that shows its work.</p>
        <ul>
          <li>Every requirement checked against the CV, with the quote that proves it.</li>
          <li>Blind screening: names, age and gender never reach the model.</li>
          <li>A tamper-evident audit trail of every decision.</li>
        </ul>
      </section>

      <form class="card card-pad" (ngSubmit)="submit()">
        <h2>Sign in</h2>
        <label class="field">
          <span>Email</span>
          <input
            class="input"
            name="email"
            type="email"
            autocomplete="username"
            required
            [(ngModel)]="email"
          />
        </label>
        <label class="field">
          <span>Password</span>
          <input
            class="input"
            name="password"
            type="password"
            autocomplete="current-password"
            required
            [(ngModel)]="password"
          />
        </label>
        @if (error()) {
          <div class="error-box" role="alert">{{ error() }}</div>
        }
        <button class="btn primary" type="submit" [disabled]="busy()">
          {{ busy() ? 'Signing in…' : 'Sign in' }}
        </button>

        <div class="demo">
          <span class="muted">Demo accounts (password <code>clearhire-demo</code>)</span>
          @for (account of demo; track account.email) {
            <button type="button" class="account" (click)="useDemo(account.email)">
              <strong>{{ account.label }}</strong>
              <span class="muted">{{ account.note }}</span>
            </button>
          }
        </div>
      </form>
    </div>
  `,
  styles: `
    .wrap {
      min-height: 100vh;
      display: grid;
      grid-template-columns: minmax(0, 1fr) 380px;
      gap: 64px;
      align-items: center;
      max-width: 980px;
      margin: 0 auto;
      padding: 32px 24px;
    }
    .logo {
      display: block;
      width: 40px;
      height: 40px;
      border-radius: 10px;
      margin-bottom: 18px;
      background: conic-gradient(from 210deg, var(--accent), #22b8cf, var(--met), var(--accent));
    }
    h1 {
      font-size: 34px;
    }
    .lead {
      font-size: 18px;
      color: var(--text-2);
      margin: 6px 0 22px;
    }
    ul {
      margin: 0;
      padding-left: 18px;
      display: grid;
      gap: 8px;
      color: var(--text-2);
    }
    form {
      display: grid;
      gap: 14px;
      padding: 24px;
    }
    form .btn.primary {
      height: 38px;
      justify-content: center;
    }
    .demo {
      display: grid;
      gap: 6px;
      padding-top: 14px;
      border-top: 1px solid var(--border);
      font-size: 12px;
    }
    .account {
      display: grid;
      text-align: left;
      gap: 1px;
      padding: 8px 10px;
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      background: var(--surface);
      color: var(--text);
      font: inherit;
      cursor: pointer;
    }
    .account:hover {
      background: var(--surface-2);
    }
    code {
      font-family: var(--mono);
    }
    @media (max-width: 800px) {
      .wrap {
        grid-template-columns: 1fr;
        gap: 28px;
      }
    }
  `,
})
export class Login {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  /** Where to go after signing in (set by the guard). */
  readonly next = input<string>('/');

  protected readonly demo = DEMO;
  protected email = '';
  protected password = '';
  protected readonly busy = signal(false);
  protected readonly error = signal('');

  protected useDemo(email: string): void {
    this.email = email;
    this.password = 'clearhire-demo';
    this.submit();
  }

  protected submit(): void {
    this.busy.set(true);
    this.error.set('');
    this.auth.login(this.email, this.password).subscribe({
      next: () => void this.router.navigateByUrl(this.next() || '/'),
      error: (error: unknown) => {
        this.busy.set(false);
        this.error.set(
          error instanceof HttpErrorResponse && error.status === 401
            ? 'Wrong email or password.'
            : error instanceof HttpErrorResponse && error.status === 429
              ? 'Too many attempts. Wait a minute and try again.'
              : 'The server did not answer. Is the API running?',
        );
      },
    });
  }
}
