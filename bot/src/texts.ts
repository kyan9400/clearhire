/** Everything the bot says, in English and Russian. Messages are Telegram HTML; values are escaped by callers. */

export type Lang = 'en' | 'ru';

export function langOf(code: string | undefined): Lang {
  return code?.toLowerCase().startsWith('ru') ? 'ru' : 'en';
}

export const T = {
  en: {
    welcome:
      'Hi! I am the Clearhire careers bot.\n\n' +
      '• /jobs: open roles\n• /status: your applications\n• /help: how it works\n\n' +
      'Before you apply, I can check your CV against a role and show what was found in it, requirement by requirement.',
    help:
      '<b>How it works</b>\n' +
      '1. Pick a role in /jobs.\n' +
      '2. <b>Check my CV</b>: send the file and see which requirements are found. Nothing is stored.\n' +
      '3. <b>Apply</b>: name, e-mail, consent, CV. You get updates here.\n' +
      '4. /status shows where your applications are; you can erase your data there at any time.\n\n' +
      'People make every decision. Your name, age, gender and contacts are hidden from the model.',
    jobsTitle: (n: number) => `<b>${n} open roles.</b> Pick one:`,
    noJobs: 'There are no open roles right now. Please come back soon.',
    more: 'More ›',
    back: '‹ Back',
    jobNotFound: 'This role is closed or does not exist.',
    mustHave: 'Must have',
    niceToHave: 'Nice to have',
    remote: 'remote',
    checkCv: '📄 Check my CV',
    apply: '✉️ Apply',
    openSite: '🌐 Open on the site',
    sendCv: (title: string) =>
      `Send your CV as a file (PDF, Word or text) or a photo, and I will check it against <b>${title}</b>. ` +
      'The file is read in memory and not stored.',
    reading: 'Reading your CV…',
    checkResult: (met: number, total: number) =>
      met === total
        ? `<b>Your CV shows every must-have (${met}/${total}).</b>`
        : `<b>Found ${met} of ${total} must-haves.</b> If you have the missing ones, say so in your CV: only what is written there counts.`,
    status: { met: '✅', partial: '🟡', missing: '❌' },
    experience: (text: string) => `Experience read: ${text}.`,
    applyWithThis: '✉️ Apply with this CV',
    askName: (title: string) => `Applying for <b>${title}</b>.\n\nYour full name?`,
    useName: (name: string) => `Use “${name}”`,
    badName: 'Please send your full name (2 to 200 characters).',
    askEmail: 'Your e-mail address?',
    badEmail: 'That does not look like an e-mail address. Try again?',
    askConsent: (privacyUrl: string) =>
      'To apply, I need your consent to the processing of your personal data for this and similar roles ' +
      `(Federal Law 152-FZ). You can withdraw it and erase your data at any time with /status. <a href="${privacyUrl}">What is kept and for how long</a>`,
    agree: '✅ I agree',
    cancel: 'Cancel',
    askCv: 'Now send your CV as a file or a photo.',
    useChecked: (name: string) => `Use ${name}`,
    sending: 'Sending your application…',
    applied: (title: string) =>
      `✅ <b>Applied for ${title}.</b>\n\nI will write here when it moves on. /status shows it any time.`,
    cancelled: 'Cancelled. /jobs to start again.',
    nothingToCancel: 'Nothing to cancel.',
    unexpectedFile: 'Pick a role in /jobs first, then choose <b>Check my CV</b> or <b>Apply</b>.',
    unexpectedText: 'I did not get that. /jobs for open roles, /status for your applications.',
    tooBig: 'The file is larger than 10 MB. Please send a smaller one.',
    noApplications: 'You have no applications yet. /jobs to see open roles.',
    applicationsTitle: '<b>Your applications</b>',
    stage: {
      received: 'received',
      'in review': 'in review',
      interview: 'interview',
      offer: 'offer',
      hired: 'hired 🎉',
      closed: 'closed',
    } as Record<string, string>,
    cvRead: (met: number, total: number) => `CV read: ${met}/${total} must-haves found`,
    cvPending: 'CV being read',
    erase: (title: string) => `🗑 Erase: ${title}`,
    eraseConfirm:
      'This withdraws your consent and deletes your applications, your CV and everything read from it. It cannot be undone.',
    eraseYes: 'Yes, erase everything',
    erased: 'Your data has been erased. Thank you for your interest.',
    gone: 'This application no longer exists.',
    moved: (title: string, stage: string) => `Your application for <b>${title}</b> is now: <b>${stage}</b>.`,
    closed: (title: string) =>
      `The team has decided not to continue with your application for <b>${title}</b>. Thank you for applying. ` +
      'Your data is kept only for the period you agreed to; /status lets you erase it now.',
    scored: (title: string, met: number, total: number) =>
      `We have read your CV for <b>${title}</b>: ${met} of ${total} must-haves found. /status for details.`,
    cvFailed: (title: string) =>
      `We could not read the CV you sent for <b>${title}</b>. Please apply again with a PDF or Word file that has selectable text.`,
    whoami: (id: number) =>
      `This chat's id is <code>${id}</code>. Recruiters: add it to RECRUITER_CHAT_IDS to get new applications here.`,
    error: 'Something went wrong. Please try again in a moment.',
    commands: {
      jobs: 'Open roles',
      status: 'My applications',
      help: 'How it works',
      cancel: 'Cancel the current step',
    },
  },
  ru: {
    welcome:
      'Здравствуйте! Я бот вакансий Clearhire.\n\n' +
      '• /jobs: открытые вакансии\n• /status: ваши отклики\n• /help: как это работает\n\n' +
      'Перед откликом я могу проверить ваше резюме по вакансии и показать, что в нём найдено по каждому требованию.',
    help:
      '<b>Как это работает</b>\n' +
      '1. Выберите вакансию в /jobs.\n' +
      '2. <b>Проверить резюме</b>: пришлите файл и посмотрите, какие требования в нём найдены. Ничего не сохраняется.\n' +
      '3. <b>Откликнуться</b>: имя, e-mail, согласие, резюме. Новости придут сюда.\n' +
      '4. /status покажет ваши отклики; там же можно в любой момент удалить свои данные.\n\n' +
      'Решения принимают люди. Имя, возраст, пол и контакты скрыты от модели.',
    jobsTitle: (n: number) => `<b>Открытых вакансий: ${n}.</b> Выберите:`,
    noJobs: 'Сейчас открытых вакансий нет. Загляните позже.',
    more: 'Ещё ›',
    back: '‹ Назад',
    jobNotFound: 'Эта вакансия закрыта или не существует.',
    mustHave: 'Обязательно',
    niceToHave: 'Будет плюсом',
    remote: 'удалённо',
    checkCv: '📄 Проверить резюме',
    apply: '✉️ Откликнуться',
    openSite: '🌐 Открыть на сайте',
    sendCv: (title: string) =>
      `Пришлите резюме файлом (PDF, Word или текст) или фото, и я проверю его по вакансии <b>${title}</b>. ` +
      'Файл читается в памяти и не сохраняется.',
    reading: 'Читаю резюме…',
    checkResult: (met: number, total: number) =>
      met === total
        ? `<b>В резюме есть все обязательные требования (${met}/${total}).</b>`
        : `<b>Найдено ${met} из ${total} обязательных требований.</b> Если недостающее у вас есть, напишите об этом в резюме: учитывается только то, что там написано.`,
    status: { met: '✅', partial: '🟡', missing: '❌' },
    experience: (text: string) => `Опыт по резюме: ${text}.`,
    applyWithThis: '✉️ Откликнуться с этим резюме',
    askName: (title: string) => `Отклик на вакансию <b>${title}</b>.\n\nВаши имя и фамилия?`,
    useName: (name: string) => `Указать «${name}»`,
    badName: 'Пришлите, пожалуйста, имя и фамилию (от 2 до 200 символов).',
    askEmail: 'Ваш e-mail?',
    badEmail: 'Похоже, это не e-mail. Попробуете ещё раз?',
    askConsent: (privacyUrl: string) =>
      'Для отклика нужно ваше согласие на обработку персональных данных для этой и похожих вакансий ' +
      `(152-ФЗ). Его можно отозвать и удалить данные в любой момент через /status. <a href="${privacyUrl}">Что хранится и сколько</a>`,
    agree: '✅ Согласен(на)',
    cancel: 'Отмена',
    askCv: 'Теперь пришлите резюме файлом или фото.',
    useChecked: (name: string) => `Использовать ${name}`,
    sending: 'Отправляю отклик…',
    applied: (title: string) =>
      `✅ <b>Отклик на «${title}» отправлен.</b>\n\nЯ напишу, когда что-то изменится. /status покажет его в любой момент.`,
    cancelled: 'Отменено. /jobs, чтобы начать заново.',
    nothingToCancel: 'Отменять нечего.',
    unexpectedFile: 'Сначала выберите вакансию в /jobs, затем <b>Проверить резюме</b> или <b>Откликнуться</b>.',
    unexpectedText: 'Не понял. /jobs: вакансии, /status: ваши отклики.',
    tooBig: 'Файл больше 10 МБ. Пришлите, пожалуйста, файл поменьше.',
    noApplications: 'Откликов пока нет. /jobs, чтобы посмотреть вакансии.',
    applicationsTitle: '<b>Ваши отклики</b>',
    stage: {
      received: 'получен',
      'in review': 'на рассмотрении',
      interview: 'собеседование',
      offer: 'оффер',
      hired: 'вы приняты 🎉',
      closed: 'закрыт',
    } as Record<string, string>,
    cvRead: (met: number, total: number) => `Резюме прочитано: найдено ${met}/${total} обязательных`,
    cvPending: 'резюме читается',
    erase: (title: string) => `🗑 Удалить: ${title}`,
    eraseConfirm:
      'Это отзовёт согласие и удалит ваши отклики, резюме и всё, что из него прочитано. Отменить будет нельзя.',
    eraseYes: 'Да, удалить всё',
    erased: 'Ваши данные удалены. Спасибо за интерес.',
    gone: 'Этого отклика больше нет.',
    moved: (title: string, stage: string) => `Ваш отклик на <b>${title}</b>: <b>${stage}</b>.`,
    closed: (title: string) =>
      `Команда решила не продолжать по вашему отклику на <b>${title}</b>. Спасибо, что откликнулись. ` +
      'Данные хранятся только оговорённый срок; через /status их можно удалить сейчас.',
    scored: (title: string, met: number, total: number) =>
      `Ваше резюме на <b>${title}</b> прочитано: найдено ${met} из ${total} обязательных требований. Подробнее: /status.`,
    cvFailed: (title: string) =>
      `Не удалось прочитать резюме, отправленное на <b>${title}</b>. Откликнитесь, пожалуйста, ещё раз с PDF или Word, где текст можно выделить.`,
    whoami: (id: number) =>
      `Id этого чата: <code>${id}</code>. Рекрутерам: добавьте его в RECRUITER_CHAT_IDS, чтобы получать сюда новые отклики.`,
    error: 'Что-то пошло не так. Попробуйте, пожалуйста, чуть позже.',
    commands: {
      jobs: 'Открытые вакансии',
      status: 'Мои отклики',
      help: 'Как это работает',
      cancel: 'Отменить текущий шаг',
    },
  },
} satisfies Record<Lang, unknown>;

export type Texts = (typeof T)['en'];

/** Recruiter notifications go to a team chat; English and Russian together. */
export function recruiterAlert(title: string, source: string, met: number | null, total: number | null): string {
  const fit = met === null || total === null ? '' : ` · ${met}/${total} must-haves / обязательных`;
  return `🆕 <b>${title}</b>\nNew application · новый отклик (${source})${fit}`;
}
