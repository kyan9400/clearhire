import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Observable } from 'rxjs';

import type {
  Application,
  Candidate,
  Note,
  Requirement,
  Stage,
  Vacancy,
  VacancyIn,
  VacancyPatch,
} from '../api/types';
import { AuthService } from './auth.service';

/** Reads are httpResource()s in the pages; this holds the URLs they share and every write. */
@Injectable({ providedIn: 'root' })
export class Api {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);

  /** Blind screening hides names, contacts, age and photo everywhere. On by default. */
  private readonly blindChoice = signal(true);
  readonly blind = computed(() => this.blindChoice() || !this.auth.canSeePersonalData());

  setBlind(value: boolean): void {
    this.blindChoice.set(value);
  }

  params(
    values: Record<string, string | number | boolean | readonly string[] | null | undefined>,
  ): HttpParams {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(values)) {
      if (value === null || value === undefined || value === '') continue;
      if (Array.isArray(value)) {
        for (const item of value) params = params.append(key, item);
      } else {
        params = params.set(key, String(value));
      }
    }
    return params;
  }

  createVacancy(body: VacancyIn): Observable<Vacancy> {
    return this.http.post<Vacancy>('/api/vacancies', body);
  }

  updateVacancy(id: string, body: VacancyPatch): Observable<Vacancy> {
    return this.http.patch<Vacancy>(`/api/vacancies/${id}`, body);
  }

  parseRequirements(text: string): Observable<Requirement[]> {
    return this.http.post<Requirement[]>('/api/vacancies/parse-requirements', { text });
  }

  saveRequirements(id: string, requirements: Requirement[]): Observable<Vacancy> {
    return this.http.put<Vacancy>(`/api/vacancies/${id}/requirements`, { requirements });
  }

  moveApplication(id: string, stage: Stage): Observable<Application> {
    return this.http.patch<Application>(`/api/applications/${id}`, { stage });
  }

  addToVacancy(candidateId: string, vacancyId: string): Observable<Application> {
    return this.http.post<Application>('/api/applications', {
      candidate_id: candidateId,
      vacancy_id: vacancyId,
    });
  }

  addNote(applicationId: string, text: string): Observable<Note> {
    return this.http.post<Note>(`/api/applications/${applicationId}/notes`, { text });
  }

  upload(file: File, consent: boolean, vacancyId: string | null): Observable<Candidate> {
    const form = new FormData();
    form.append('file', file);
    form.append('consent', String(consent));
    if (vacancyId) form.append('vacancy_id', vacancyId);
    return this.http.post<Candidate>('/api/candidates', form);
  }

  erase(candidateId: string): Observable<void> {
    return this.http.delete<void>(`/api/candidates/${candidateId}`);
  }

  /** The original file needs the bearer token, so it is fetched and opened as a blob URL. */
  openCv(candidateId: string): void {
    const tab = window.open('', '_blank');
    this.http.get(`/api/candidates/${candidateId}/cv`, { responseType: 'blob' }).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        if (tab) tab.location.href = url;
        setTimeout(() => URL.revokeObjectURL(url), 60_000);
      },
      error: () => tab?.close(),
    });
  }
}
