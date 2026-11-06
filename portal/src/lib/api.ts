import type { components } from './schema';

type Schemas = components['schemas'];
export type Vacancy = Schemas['PublicVacancy'];
export type Requirement = Schemas['PublicRequirement'];
export type Precheck = Schemas['PrecheckOut'];
export type CheckItem = Schemas['CheckItem'];
export type Evidence = Schemas['EvidenceOut'];
export type Status = Schemas['StatusOut'];
export type PublicStage = Status['stage'];
export type Applied = Schemas['ApplyOut'];

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

/** The message FastAPI puts in `detail`: a string, or a list of validation errors. */
export function errorMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0] as { msg?: string; loc?: unknown[] };
    const field = first.loc?.at(-1);
    return [field, first.msg].filter(Boolean).join(': ');
  }
  if (status === 429) return 'Too many attempts from this address. Please try again later.';
  return `Something went wrong (${status}). Please try again.`;
}

/** Server-side reads go to the API directly (inside Docker, http://api:8000). */
function serverBase(): string {
  return process.env.CLEARHIRE_API_URL ?? 'http://127.0.0.1:8077';
}

async function get<T>(path: string): Promise<T | null> {
  const response = await fetch(`${serverBase()}${path}`, { cache: 'no-store' });
  if (response.status === 404) return null;
  if (!response.ok)
    throw new ApiError(response.status, errorMessage(await response.json().catch(() => null), response.status));
  return (await response.json()) as T;
}

export const api = {
  vacancies: () => get<Vacancy[]>('/api/public/vacancies').then((v) => v ?? []),
  vacancy: (id: string) => (isUuid(id) ? get<Vacancy>(`/api/public/vacancies/${id}`) : Promise.resolve(null)),
  status: (token: string) => get<Status>(`/api/public/status/${encodeURIComponent(token)}`),
};

/** Browser-side calls use same-origin paths (the reverse proxy, or the dev rewrite, forwards them). */
export async function send<T>(path: string, init: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  const body: unknown = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, errorMessage(body, response.status));
  return body as T;
}

export function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}
