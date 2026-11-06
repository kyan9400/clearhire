import { bootstrapApplication } from '@angular/platform-browser';

import { App } from './app/app';
import { appConfig } from './app/app.config';
import { applyStoredTheme } from './app/layout/shell';

applyStoredTheme();
bootstrapApplication(App, appConfig).catch((err: unknown) => console.error(err));
