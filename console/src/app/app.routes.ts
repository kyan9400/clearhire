import { Routes } from '@angular/router';

import { canEdit, signedIn } from './core/guards';
import { Shell } from './layout/shell';

export const routes: Routes = [
  {
    path: 'login',
    title: 'Sign in · Clearhire',
    loadComponent: () => import('./pages/login').then((m) => m.Login),
  },
  {
    path: '',
    component: Shell,
    canActivate: [signedIn],
    children: [
      {
        path: '',
        title: 'Overview · Clearhire',
        loadComponent: () => import('./pages/overview').then((m) => m.Overview),
      },
      {
        path: 'vacancies',
        title: 'Vacancies · Clearhire',
        loadComponent: () => import('./pages/vacancies').then((m) => m.Vacancies),
      },
      {
        path: 'vacancies/:id',
        title: 'Vacancy · Clearhire',
        loadComponent: () => import('./vacancy/vacancy-page').then((m) => m.VacancyPage),
      },
      {
        path: 'candidates',
        title: 'Candidates · Clearhire',
        loadComponent: () => import('./pages/candidates').then((m) => m.Candidates),
      },
      {
        path: 'candidates/:id',
        title: 'Candidate · Clearhire',
        loadComponent: () => import('./pages/candidate').then((m) => m.CandidatePage),
      },
      {
        path: 'audit',
        title: 'Audit log · Clearhire',
        canActivate: [canEdit],
        loadComponent: () => import('./pages/audit').then((m) => m.Audit),
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
