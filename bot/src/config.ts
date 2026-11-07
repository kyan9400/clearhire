/** Settings from the environment, checked once at startup. */
export class BotConfig {
  constructor(
    readonly token: string,
    readonly apiUrl: string,
    readonly botSecret: string,
    readonly redisUrl: string,
    readonly careersUrl: string,
    readonly consoleUrl: string,
    /** Chats (recruiters, or a team group) told about every new application. */
    readonly recruiterChats: number[],
  ) {}

  static fromEnv(env: NodeJS.ProcessEnv = process.env): BotConfig {
    const need = (name: string): string => {
      const value = env[name]?.trim();
      if (!value) throw new Error(`${name} is not set`);
      return value;
    };
    const secret = need('CLEARHIRE_BOT_SECRET');
    if (secret.length < 32) throw new Error('CLEARHIRE_BOT_SECRET must be at least 32 characters');
    const chats = (env.RECRUITER_CHAT_IDS ?? '')
      .split(',')
      .map((id) => id.trim())
      .filter(Boolean)
      .map((id) => {
        const chat = Number(id);
        if (!Number.isSafeInteger(chat)) throw new Error(`RECRUITER_CHAT_IDS: ${id} is not a chat id`);
        return chat;
      });
    return new BotConfig(
      need('TELEGRAM_BOT_TOKEN'),
      need('CLEARHIRE_API_URL').replace(/\/$/, ''),
      secret,
      need('REDIS_URL'),
      need('CAREERS_URL').replace(/\/$/, ''),
      need('CONSOLE_URL').replace(/\/$/, ''),
      chats,
    );
  }
}
