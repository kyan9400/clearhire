import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';

import { AuthService } from './auth.service';

/** Lets signed-in staff through; after a reload it first tries the stored refresh token. */
export const signedIn: CanActivateFn = (_route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  const toLogin = router.createUrlTree(['/login'], { queryParams: { next: state.url } });
  if (auth.signedIn()) {
    return true;
  }
  const restoring = auth.restore();
  if (!restoring) {
    return toLogin;
  }
  return restoring.pipe(
    map(() => true),
    catchError(() => of(toLogin)),
  );
};

/** Pages that change data or show the audit log: admins and recruiters. */
export const canEdit: CanActivateFn = () =>
  inject(AuthService).canEdit() || inject(Router).createUrlTree(['/']);
