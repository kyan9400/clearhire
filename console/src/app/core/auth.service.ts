import { HttpBackend, HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, finalize, map, shareReplay, tap } from 'rxjs';

import type { TokenOut, User } from '../api/types';

const REFRESH_KEY = 'clearhire.refresh';

/**
 * The access token lives only in memory; the refresh token in localStorage so a reload keeps the session.
 * Requests made here skip the interceptors (HttpBackend), so a failing refresh cannot loop.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = new HttpClient(inject(HttpBackend));
  private readonly router = inject(Router);
  private refreshing: Observable<string> | null = null;

  readonly user = signal<User | null>(null);
  readonly accessToken = signal<string | null>(null);
  readonly signedIn = computed(() => this.user() !== null);
  /** Hiring managers only ever see blind profiles; the API enforces it, the UI just doesn't offer more. */
  readonly canSeePersonalData = computed(() => this.user()?.role !== 'hiring_manager');
  readonly canEdit = computed(
    () => this.user()?.role === 'admin' || this.user()?.role === 'recruiter',
  );

  login(email: string, password: string): Observable<User> {
    return this.http.post<TokenOut>('/api/auth/login', { email, password }).pipe(
      tap((tokens) => this.store(tokens)),
      map((tokens) => tokens.user),
    );
  }

  /** Restore a session from the stored refresh token, if there is one. */
  restore(): Observable<string> | null {
    return readRefresh() ? this.refresh() : null;
  }

  /** One refresh at a time: concurrent 401s wait for the same request. */
  refresh(): Observable<string> {
    this.refreshing ??= this.http
      .post<TokenOut>('/api/auth/refresh', { refresh_token: readRefresh() ?? '' })
      .pipe(
        tap((tokens) => this.store(tokens)),
        map((tokens) => tokens.access_token),
        finalize(() => (this.refreshing = null)),
        shareReplay(1),
      );
    return this.refreshing;
  }

  logout(): void {
    this.user.set(null);
    this.accessToken.set(null);
    try {
      localStorage.removeItem(REFRESH_KEY);
    } catch {
      // storage can be unavailable (private mode); nothing to remove then
    }
    void this.router.navigate(['/login']);
  }

  private store(tokens: TokenOut): void {
    this.user.set(tokens.user);
    this.accessToken.set(tokens.access_token);
    try {
      localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
    } catch {
      // the session then lasts until the tab closes
    }
  }
}

function readRefresh(): string | null {
  try {
    return localStorage.getItem(REFRESH_KEY);
  } catch {
    return null;
  }
}
