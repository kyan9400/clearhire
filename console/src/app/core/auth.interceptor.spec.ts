import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { authInterceptor } from './auth.interceptor';
import { AuthService } from './auth.service';

const USER = {
  id: 'u1',
  email: 'recruiter@clearhire.demo',
  name: 'Recruiter',
  role: 'recruiter' as const,
};

describe('authInterceptor', () => {
  let http: HttpClient;
  let backend: HttpTestingController;
  let auth: AuthService;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        provideRouter([{ path: 'login', children: [] }]),
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
    auth = TestBed.inject(AuthService);
  });

  afterEach(() => backend.verify());

  function signIn(): void {
    auth.login(USER.email, 'clearhire-demo').subscribe();
    backend
      .expectOne('/api/auth/login')
      .flush({ access_token: 'old', refresh_token: 'r1', token_type: 'bearer', user: USER });
  }

  it('sends the access token to the API but not to public endpoints', () => {
    signIn();
    http.get('/api/vacancies').subscribe();
    http.get('/api/public/vacancies').subscribe();
    expect(backend.expectOne('/api/vacancies').request.headers.get('Authorization')).toBe(
      'Bearer old',
    );
    expect(backend.expectOne('/api/public/vacancies').request.headers.has('Authorization')).toBe(
      false,
    );
  });

  it('refreshes once on a 401 and retries both waiting requests with the new token', () => {
    signIn();
    const results: unknown[] = [];
    http.get('/api/vacancies').subscribe((body) => results.push(body));
    http.get('/api/candidates').subscribe((body) => results.push(body));
    backend.expectOne('/api/vacancies').flush(null, { status: 401, statusText: 'Unauthorized' });
    backend.expectOne('/api/candidates').flush(null, { status: 401, statusText: 'Unauthorized' });

    const refresh = backend.expectOne('/api/auth/refresh');
    expect(refresh.request.body).toEqual({ refresh_token: 'r1' });
    refresh.flush({ access_token: 'new', refresh_token: 'r2', token_type: 'bearer', user: USER });

    const retried = [backend.expectOne('/api/vacancies'), backend.expectOne('/api/candidates')];
    for (const request of retried) {
      expect(request.request.headers.get('Authorization')).toBe('Bearer new');
      request.flush([]);
    }
    expect(results).toEqual([[], []]);
    expect(localStorage.getItem('clearhire.refresh')).toBe('r2');
  });

  it('signs out when the refresh is refused', () => {
    signIn();
    let failed = false;
    http.get('/api/vacancies').subscribe({ error: () => (failed = true) });
    backend.expectOne('/api/vacancies').flush(null, { status: 401, statusText: 'Unauthorized' });
    backend.expectOne('/api/auth/refresh').flush(null, { status: 401, statusText: 'Unauthorized' });
    expect(failed).toBe(true);
    expect(auth.signedIn()).toBe(false);
    expect(localStorage.getItem('clearhire.refresh')).toBeNull();
  });
});
