import type { components } from './api/schema';

type Schemas = components['schemas'];
export type Vacancy = Schemas['PublicVacancy'];
export type Precheck = Schemas['PrecheckOut'];
export type CheckItem = Schemas['CheckItem'];
export type Status = Schemas['StatusOut'];
export type Applied = Schemas['ApplyOut'];

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export interface CvFile {
  name: string;
  data: Uint8Array;
}

export interface Application {
  fullName: string;
  email: string;
  telegram?: string;
}

/**
 * The careers API, called as the bot: every request carries the shared secret and the Telegram user it
 * acts for, so the API rate-limits per person and records the application's source as Telegram.
 */
export class ClearhireApi {
  constructor(
    private readonly base: string,
    private readonly secret: string,
    private readonly fetchImpl: typeof fetch = fetch,
  ) {}

  vacancies(): Promise<Vacancy[]> {
    return this.call('GET', '/api/public/vacancies');
  }

  async vacancy(id: string): Promise<Vacancy | null> {
    if (!/^[0-9a-f-]{36}$/i.test(id)) return null;
    return this.call<Vacancy>('GET', `/api/public/vacancies/${id}`).catch((e: unknown) => {
      if (e instanceof ApiError && e.status === 404) return null;
      throw e;
    });
  }

  precheck(vacancyId: string, file: CvFile, user: number): Promise<Precheck> {
    const form = new FormData();
    form.append('file', new Blob([file.data]), file.name);
    return this.call('POST', `/api/public/vacancies/${vacancyId}/precheck`, form, user);
  }

  apply(vacancyId: string, file: CvFile, who: Application, user: number): Promise<Applied> {
    const form = new FormData();
    form.append('file', new Blob([file.data]), file.name);
    form.append('full_name', who.fullName);
    form.append('email', who.email);
    form.append('consent', 'true'); // asked for explicitly in the conversation before this call
    if (who.telegram) form.append('telegram', who.telegram);
    return this.call('POST', `/api/public/vacancies/${vacancyId}/apply`, form, user);
  }

  async status(token: string): Promise<Status | null> {
    return this.call<Status>('GET', `/api/public/status/${encodeURIComponent(token)}`).catch((e: unknown) => {
      if (e instanceof ApiError && e.status === 404) return null;
      throw e;
    });
  }

  async withdraw(token: string, user: number): Promise<void> {
    await this.call('DELETE', `/api/public/status/${encodeURIComponent(token)}`, undefined, user).catch(
      (e: unknown) => {
        if (!(e instanceof ApiError && e.status === 404)) throw e; // already gone is fine
      },
    );
  }

  private async call<T>(method: string, path: string, body?: FormData, user?: number): Promise<T> {
    const headers: Record<string, string> = { 'X-Clearhire-Bot': this.secret };
    if (user !== undefined) headers['X-Telegram-User'] = String(user);
    const response = await this.fetchImpl(`${this.base}${path}`, {
      method,
      body,
      headers,
      signal: AbortSignal.timeout(60_000),
    });
    if (response.status === 204) return undefined as T;
    const data: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = (data as { detail?: unknown } | null)?.detail;
      throw new ApiError(response.status, typeof detail === 'string' ? detail : `HTTP ${response.status}`);
    }
    return data as T;
  }
}
