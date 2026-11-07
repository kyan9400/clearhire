import { APP_ID, SECRET, VACANCY_ID, buttons, harness, precheck, vacancy } from './harness';

const routes = {
  'GET /api/public/vacancies': () => [vacancy()],
  [`GET /api/public/vacancies/${VACANCY_ID}`]: () => vacancy(),
  [`POST /api/public/vacancies/${VACANCY_ID}/precheck`]: () => precheck,
  [`POST /api/public/vacancies/${VACANCY_ID}/apply`]: () => ({ application_id: APP_ID, status_token: 'secret-token' }),
};

describe('conversations', () => {
  it('greets in the user’s language', async () => {
    const h = harness(routes);
    await h.text('/start');
    expect(h.last().text).toContain('Clearhire careers bot');
    const ru = harness(routes);
    await ru.text('/start', 'ru');
    expect(ru.last().text).toContain('бот вакансий');
  });

  it('opens a role from a deep link on the careers site', async () => {
    const h = harness(routes);
    await h.text(`/start job_${VACANCY_ID}`);
    const card = h.last();
    expect(card.text).toContain('<b>Data Analyst</b>');
    expect(card.text).toContain('• 3+ years of SQL');
    expect(buttons(card).map((b) => b.callback_data ?? b.url)).toEqual([
      `check:${VACANCY_ID}`, `apply:${VACANCY_ID}`, `https://careers.test/jobs/${VACANCY_ID}`, 'jobs:0',
    ]); // prettier-ignore
  });

  it('pages through many roles', async () => {
    const many = Array.from({ length: 11 }, (_, i) =>
      vacancy(`3f1e0c55-8a3b-4f7e-9a7b-0f6c2d9e1a${String(i).padStart(2, '0')}`, `Role ${i}`),
    );
    const h = harness({ ...routes, 'GET /api/public/vacancies': () => many });
    await h.text('/jobs');
    expect(
      buttons(h.last())
        .map((b) => b.callback_data)
        .slice(-1),
    ).toEqual(['jobs:1']);
    await h.tap('jobs:1');
    expect(buttons(h.last()).map((b) => b.text)).toEqual([
      'Role 8 · Quartz Media',
      'Role 9 · Quartz Media',
      'Role 10 · Quartz Media',
      '‹ Back',
    ]);
  });

  it('checks a CV against a role without applying', async () => {
    const h = harness(routes);
    await h.tap(`check:${VACANCY_ID}`);
    expect(h.last().text).toContain('not stored');
    await h.document('maria.pdf');
    const report = h.last().text;
    expect(report).toContain('every must-have (1/1)');
    expect(report).toContain('✅ 3+ years of SQL');
    expect(report).toContain('«wrote <b>SQL</b> in ClickHouse»');
    expect(report).toContain('❌ Hands-on Tableau');
    expect(report).toContain('7 years 6 months');
    const call = h.requests.find((r) => r.path.endsWith('/precheck'))!;
    expect(call.headers).toEqual({ 'X-Clearhire-Bot': SECRET, 'X-Telegram-User': '42' });
    expect(h.requests.some((r) => r.path.endsWith('/apply'))).toBe(false);
  });

  it('applies through a short conversation with explicit consent', async () => {
    const h = harness(routes);
    await h.tap(`apply:${VACANCY_ID}`);
    expect(buttons(h.last())[0]!.text).toBe('Use “Maria Petrova”');
    await h.tap('name:use');
    expect(h.last().text).toBe('Your e-mail address?');
    await h.text('not an email');
    expect(h.last().text).toContain('does not look like');
    await h.text('maria@example.com');
    expect(h.last().text).toContain('152-FZ');
    expect(h.requests.some((r) => r.path.endsWith('/apply'))).toBe(false); // nothing sent before consent
    await h.tap('consent:yes');
    await h.document('maria.pdf');
    expect(h.last().text).toContain('Applied for Data Analyst');
    const apply = h.requests.find((r) => r.path.endsWith('/apply'))!;
    expect(apply.form).toEqual({
      file: '<file maria.pdf>', full_name: 'Maria Petrova', email: 'maria@example.com', consent: 'true', telegram: 'maria_p',
    }); // prettier-ignore
    expect(await h.store.applications(42)).toEqual([
      expect.objectContaining({ applicationId: APP_ID, token: 'secret-token' }),
    ]);
    expect((await h.store.session(42))?.mode).toBeUndefined();
  });

  it('offers the CV it just checked when applying', async () => {
    const h = harness(routes);
    await h.tap(`check:${VACANCY_ID}`);
    await h.document('checked.pdf');
    await h.tap(`apply:${VACANCY_ID}`);
    await h.text('Maria Petrova');
    await h.text('maria@example.com');
    await h.tap('consent:yes');
    expect(buttons(h.last()).map((b) => b.callback_data)).toEqual(['cv:use', 'cancel']);
    await h.tap('cv:use');
    expect(h.requests.find((r) => r.path.endsWith('/apply'))!.form!.file).toBe('<file checked.pdf>');
  });

  it('refuses oversized files and files sent out of context', async () => {
    const h = harness(routes);
    await h.document('cv.pdf');
    expect(h.last().text).toContain('Pick a role');
    await h.tap(`check:${VACANCY_ID}`);
    await h.document('huge.pdf', 11 * 1024 * 1024);
    expect(h.last().text).toContain('larger than 10 MB');
  });

  it('can be cancelled at any step', async () => {
    const h = harness(routes);
    await h.tap(`apply:${VACANCY_ID}`);
    await h.text('/cancel');
    expect(h.last().text).toContain('Cancelled');
    await h.text('maria@example.com');
    expect(h.last().text).toContain('did not get that');
  });

  it('shows applications and erases one on request', async () => {
    let erased = false;
    const h = harness({
      ...routes,
      'GET /api/public/status/secret-token': () =>
        erased ? new Response('{}', { status: 404 }) : { vacancy: 'Data Analyst', company: 'Quartz', stage: 'in review', updated_at: '', cv_read: true, timeline: [], items: precheck.items },
      'DELETE /api/public/status/secret-token': () => { erased = true; return undefined; },
    }); // prettier-ignore
    await h.store.track(42, 'en', {
      applicationId: APP_ID,
      token: 'secret-token',
      title: 'Data Analyst',
      appliedAt: '2026-11-01',
    });
    await h.text('/status');
    expect(h.last().text).toContain('<b>Data Analyst</b>: in review');
    expect(h.last().text).toContain('1/1 must-haves found');
    await h.tap(`erase:${APP_ID}`);
    expect(h.last().text).toContain('cannot be undone');
    await h.tap(`erase!:${APP_ID}`);
    expect(h.last().text).toContain('has been erased');
    expect(erased).toBe(true);
    expect(await h.store.applications(42)).toEqual([]);
  });

  it('turns API refusals into readable messages', async () => {
    const h = harness({
      ...routes,
      [`POST /api/public/vacancies/${VACANCY_ID}/precheck`]: () =>
        new Response(JSON.stringify({ detail: 'no text found in the document' }), { status: 422 }),
    });
    await h.tap(`check:${VACANCY_ID}`);
    await h.document();
    expect(h.last().text).toBe('no text found in the document');
  });

  it('ignores group chats, except to tell recruiters the chat id', async () => {
    const h = harness(routes);
    await h.bot.handleUpdate({
      update_id: 900,
      message: { message_id: 1, date: 0, chat: { id: -100, type: 'group', title: 'HR' }, from: { id: 7, is_bot: false, first_name: 'R' }, text: '/jobs',
        entities: [{ type: 'bot_command', offset: 0, length: 5 }] },
    } as never); // prettier-ignore
    expect(h.sent()).toEqual([]);
    await h.bot.handleUpdate({
      update_id: 901,
      message: { message_id: 2, date: 0, chat: { id: -100, type: 'group', title: 'HR' }, from: { id: 7, is_bot: false, first_name: 'R' }, text: '/whoami',
        entities: [{ type: 'bot_command', offset: 0, length: 7 }] },
    } as never); // prettier-ignore
    expect(h.last().text).toContain('<code>-100</code>');
  });
});
