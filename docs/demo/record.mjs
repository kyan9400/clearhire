// Records the demo walkthrough (docs/demo) and the README screenshots (docs/screenshots) with Playwright.
//   CAREERS=https://careers.example CONSOLE=https://console.example CV=path/to/cv.pdf OUT=dir node record.mjs
// Signs in through the console's demo-account button, so no password is typed. Nothing is changed:
// the CV check runs in memory, and the demo's staff accounts are read-only.
import { chromium } from 'playwright';

const { CAREERS, CONSOLE, CV, OUT = 'out', RESOLVE } = process.env;
const size = { width: 1440, height: 900 };
const pause = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await chromium.launch({
  args: RESOLVE ? [`--host-resolver-rules=${RESOLVE}`] : [],
});
const context = await browser.newContext({
  viewport: size,
  deviceScaleFactor: 1,
  colorScheme: 'light',
  recordVideo: { dir: `${OUT}/video`, size },
});
const page = await context.newPage();

// A caption bar at the bottom of the video. Set through the DOM (not markup), so the pages' CSP allows it.
async function caption(text, ms = 0) {
  await page.evaluate((t) => {
    let bar = document.getElementById('demo-caption');
    if (!bar) {
      bar = document.createElement('div');
      bar.id = 'demo-caption';
      Object.assign(bar.style, {
        position: 'fixed', left: '50%', bottom: '28px', transform: 'translateX(-50%)', zIndex: '2147483647',
        maxWidth: '1100px', padding: '14px 26px', borderRadius: '12px', background: 'rgba(17, 24, 39, 0.92)',
        color: '#fff', font: '500 21px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif',
        textAlign: 'center', boxShadow: '0 10px 30px rgba(0,0,0,.25)', pointerEvents: 'none',
      });
      document.body.appendChild(bar);
    }
    bar.textContent = t;
    bar.style.display = t ? 'block' : 'none';
  }, text);
  if (ms) await pause(ms);
}

// Screenshots leave the caption out.
async function shot(name) {
  await page.evaluate(() => {
    const bar = document.getElementById('demo-caption');
    if (bar) bar.style.visibility = 'hidden';
  });
  await page.screenshot({ path: `${OUT}/${name}.png` });
  await page.evaluate(() => {
    const bar = document.getElementById('demo-caption');
    if (bar) bar.style.visibility = 'visible';
  });
}

// Moves the mouse in visible steps so the viewer can follow it, then clicks.
async function click(locator) {
  await locator.scrollIntoViewIfNeeded();
  const box = await locator.boundingBox();
  if (box) await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 25 });
  await pause(350);
  await locator.click();
}

async function scroll(by, steps = 12) {
  for (let i = 0; i < steps; i++) {
    await page.mouse.wheel(0, by / steps);
    await pause(60);
  }
}

// --- Careers site: a candidate checks a CV against a role before applying ---
await page.goto(CAREERS, { waitUntil: 'networkidle' });
await shot('careers-home');
await caption('Clearhire: an AI recruiting platform that shows its work. First, the candidate side.', 3500);
await scroll(500);
await pause(500);
await click(page.getByRole('heading', { name: 'Senior Python Engineer', exact: true }).first());
await page.waitForLoadState('networkidle');
await caption('Before applying, a candidate checks their CV against the role (PDF, Word, scan or photo).', 2500);
await page.locator('input[type=file]').setInputFiles(CV);
await pause(800);
await click(page.getByRole('button', { name: 'Check it against this role' }));
await page.getByRole('button', { name: 'Check again' }).waitFor({ timeout: 120_000 });
await pause(800);
await shot('careers-check');
await caption('Every requirement: found or not, with the line of the CV that proves it. The file is not stored.', 1500);
await scroll(600, 20);
await pause(3000);

// --- Console: the recruiter's side of the same role ---
await page.goto(`${CONSOLE}/login`, { waitUntil: 'networkidle' });
await caption('The recruiter console (Angular). The demo accounts are read-only.', 2500);
await click(page.getByRole('button', { name: /Recruiter/ }));
await page.waitForURL((u) => !u.pathname.startsWith('/login'));
await page.waitForLoadState('networkidle');
await pause(800);
await shot('console-overview');
await caption('Funnel, match scores, sources, and the must-haves applicants miss most.', 3000);
await scroll(700, 20);
await pause(1500);

await click(page.getByRole('link', { name: 'Vacancies' }).first());
await page.waitForLoadState('networkidle');
await pause(800);
await click(page.getByText('Senior Python Engineer', { exact: true }).first());
await page.waitForLoadState('networkidle');
await page.locator('tbody tr.clickable').first().waitFor();
await pause(800);
await shot('console-ranking');
await caption('Ranked by unmet must-haves first, then requirement score, then similarity. Blind: no names.', 4000);
await click(page.locator('tbody tr.clickable').first());
const panel = page.getByRole('complementary', { name: 'Match details' });
await panel.waitFor();

// The AI assistant: a summary that cites its evidence, then a question answered from the CV
const ai = page.getByRole('region', { name: 'AI assistant' });
await ai.locator('p.summary').waitFor({ timeout: 120_000 });
await pause(800);
await shot('console-match');
await caption('A local LLM (Qwen 3.5 9B) summarises the match. Each sentence cites evidence, or is dropped.', 4500);
const ask = ai.locator('input[name=question]');
await caption('Questions are answered from the CV, with the passages cited.');
await click(ask);
await ask.pressSequentially('Has this candidate worked with Kubernetes?', { delay: 45 });
await pause(400);
await click(ai.getByRole('button', { name: 'Ask', exact: true }));
await ai.locator('.turn .a').first().waitFor({ timeout: 120_000 });
await pause(800);
await shot('console-assistant');
await caption('The answer is checked against the CV, and lists the lookups the assistant made.', 4500);

// The audit log, anchored on a chain
await click(page.getByRole('link', { name: 'Audit log' }).first());
await page.waitForLoadState('networkidle');
await pause(1500);
await shot('console-audit');
await caption('Every decision and model call is hash-chained, and the log is anchored hourly in a smart contract.', 4500);
await scroll(600, 20);
await caption('Code, evaluation and Kubernetes deployment: github.com/kyan9400/clearhire', 4000);

await context.close();
await browser.close();
