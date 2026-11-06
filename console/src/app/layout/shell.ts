import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { Api } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { Icon, type IconName } from '../shared/icon';
import { ROLE_LABEL, initials } from '../shared/format';

interface NavItem {
  path: string;
  label: string;
  icon: IconName;
  editorsOnly?: boolean;
}

const THEME_KEY = 'clearhire.theme';

@Component({
  selector: 'ch-shell',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, Icon],
  template: `
    <aside class="side">
      <a class="brand" routerLink="/">
        <span class="logo" aria-hidden="true"></span>
        Clearhire
      </a>
      <nav>
        @for (item of nav; track item.path) {
          @if (!item.editorsOnly || auth.canEdit()) {
            <a
              [routerLink]="item.path"
              routerLinkActive="active"
              [routerLinkActiveOptions]="{ exact: item.path === '/' }"
            >
              <ch-icon [name]="item.icon" />{{ item.label }}
            </a>
          }
        }
      </nav>

      <div class="blind" [class.on]="api.blind()">
        <label class="check">
          <input
            type="checkbox"
            [checked]="api.blind()"
            [disabled]="!auth.canSeePersonalData()"
            (change)="api.setBlind($any($event.target).checked)"
          />
          <ch-icon [name]="api.blind() ? 'eyeOff' : 'eye'" />
          Blind screening
        </label>
        <p>
          @if (!auth.canSeePersonalData()) {
            Hiring managers always see anonymous profiles.
          } @else if (api.blind()) {
            Names, contacts, age and gender are hidden — from you and from the model.
          } @else {
            Personal details are shown. Every view is written to the audit log.
          }
        </p>
      </div>

      @if (auth.user(); as user) {
        <div class="me">
          <span class="avatar">{{ initials(user.name) }}</span>
          <span class="who">
            <strong>{{ user.name }}</strong>
            <span class="muted">{{ roleLabel[user.role] }}</span>
          </span>
          <button
            class="btn ghost sm"
            type="button"
            (click)="toggleTheme()"
            [attr.aria-label]="'Switch to ' + (dark() ? 'light' : 'dark') + ' theme'"
          >
            <ch-icon [name]="dark() ? 'sun' : 'moon'" />
          </button>
          <button class="btn ghost sm" type="button" (click)="auth.logout()" aria-label="Sign out">
            <ch-icon name="logout" />
          </button>
        </div>
      }
    </aside>
    <main><router-outlet /></main>
  `,
  styles: `
    :host {
      display: grid;
      grid-template-columns: 240px 1fr;
      min-height: 100vh;
    }
    .side {
      position: sticky;
      top: 0;
      height: 100vh;
      display: flex;
      flex-direction: column;
      gap: 18px;
      padding: 18px 14px;
      border-right: 1px solid var(--border);
      background: var(--surface);
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 4px 8px;
      font-weight: 700;
      font-size: 16px;
      color: var(--text);
    }
    .brand:hover {
      text-decoration: none;
    }
    .logo {
      width: 22px;
      height: 22px;
      border-radius: 6px;
      background: conic-gradient(from 210deg, var(--accent), #22b8cf, var(--met), var(--accent));
    }
    nav {
      display: grid;
      gap: 2px;
    }
    nav a {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 8px 10px;
      border-radius: var(--radius-sm);
      color: var(--text-2);
      font-weight: 500;
    }
    nav a:hover {
      background: var(--surface-2);
      text-decoration: none;
      color: var(--text);
    }
    nav a.active {
      background: var(--accent-soft);
      color: var(--accent-text);
    }
    .blind {
      margin-top: auto;
      padding: 12px;
      border-radius: var(--radius);
      border: 1px solid var(--border);
      background: var(--surface-2);
    }
    .blind.on {
      border-color: color-mix(in srgb, var(--met) 35%, var(--border));
      background: var(--met-soft);
    }
    .blind label {
      font-weight: 600;
    }
    .blind p {
      margin: 6px 0 0;
      font-size: 12px;
      color: var(--text-2);
    }
    .me {
      display: flex;
      align-items: center;
      gap: 8px;
      padding-top: 12px;
      border-top: 1px solid var(--border);
    }
    .avatar {
      display: grid;
      place-items: center;
      width: 32px;
      height: 32px;
      border-radius: 50%;
      background: var(--accent-soft);
      color: var(--accent-text);
      font-weight: 700;
      font-size: 12px;
    }
    .who {
      display: grid;
      flex: 1;
      min-width: 0;
      font-size: 13px;
      line-height: 1.3;
    }
    .who strong {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    main {
      min-width: 0;
    }
    @media (max-width: 900px) {
      :host {
        grid-template-columns: 1fr;
      }
      .side {
        position: static;
        height: auto;
        flex-direction: row;
        flex-wrap: wrap;
        align-items: center;
        padding: 10px 16px;
      }
      nav {
        display: flex;
        flex-wrap: wrap;
      }
      .blind,
      .me {
        margin: 0;
        flex-basis: 100%;
      }
    }
  `,
})
export class Shell {
  protected readonly auth = inject(AuthService);
  protected readonly api = inject(Api);
  protected readonly roleLabel = ROLE_LABEL;
  protected readonly initials = initials;
  protected readonly dark = signal(
    document.documentElement.dataset['theme'] === 'dark' ||
      matchMedia('(prefers-color-scheme: dark)').matches,
  );

  protected readonly nav: NavItem[] = [
    { path: '/', label: 'Overview', icon: 'dashboard' },
    { path: '/vacancies', label: 'Vacancies', icon: 'briefcase' },
    { path: '/candidates', label: 'Candidates', icon: 'users' },
    { path: '/audit', label: 'Audit log', icon: 'shield', editorsOnly: true },
  ];

  protected toggleTheme(): void {
    const theme = this.dark() ? 'light' : 'dark';
    this.dark.set(theme === 'dark');
    document.documentElement.dataset['theme'] = theme;
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      // the choice then lasts until reload
    }
  }
}

/** Apply the stored theme before the first render, so there is no flash. */
export function applyStoredTheme(): void {
  try {
    const theme = localStorage.getItem(THEME_KEY);
    if (theme === 'light' || theme === 'dark') document.documentElement.dataset['theme'] = theme;
  } catch {
    // no stored choice: follow the system
  }
}
