import { Inject, Injectable, Logger, Module, OnApplicationBootstrap, OnApplicationShutdown } from '@nestjs/common';
import { Bot } from 'grammy';
import { Redis } from 'ioredis';

import { ClearhireApi } from './api';
import { BotConfig } from './config';
import { EventConsumer } from './events';
import { register } from './handlers';
import { RedisStore } from './store';
import { T } from './texts';

const REDIS = Symbol('redis');

@Injectable()
export class TelegramBot implements OnApplicationBootstrap, OnApplicationShutdown {
  private readonly logger = new Logger('bot');
  private readonly bot: Bot;
  private readonly events: EventConsumer;

  constructor(
    private readonly config: BotConfig,
    @Inject(REDIS) private readonly redis: Redis,
  ) {
    this.bot = new Bot(config.token);
    const store = new RedisStore(redis);
    const log = (message: string, error?: unknown) =>
      this.logger.error(message, error instanceof Error ? error.stack : error);
    register(this.bot, {
      api: new ClearhireApi(config.apiUrl, config.botSecret),
      store,
      careersUrl: config.careersUrl,
      download: (fileId) => this.download(fileId),
      log,
    });
    // a second Redis connection: XREADGROUP blocks the one it runs on
    this.events = new EventConsumer(
      redis.duplicate(),
      {
        store,
        recruiterChats: config.recruiterChats,
        consoleUrl: config.consoleUrl,
        send: (chat, text, keyboard) =>
          this.bot.api.sendMessage(chat, text, {
            parse_mode: 'HTML',
            link_preview_options: { is_disabled: true },
            reply_markup: keyboard,
          }),
      },
      // one fixed consumer name: a recreated container must re-read what the old one left unacknowledged
      'telegram-bot',
      log,
    );
  }

  async onApplicationBootstrap(): Promise<void> {
    await this.bot.init();
    for (const lang of ['en', 'ru'] as const) {
      const commands = Object.entries(T[lang].commands).map(([command, description]) => ({ command, description }));
      await this.bot.api.setMyCommands(commands, lang === 'ru' ? { language_code: 'ru' } : {});
    }
    await this.events.start();
    // long polling: no public port or webhook needed
    void this.bot.start({
      drop_pending_updates: false,
      onStart: (me) => this.logger.log(`@${me.username} is running`),
    });
  }

  async onApplicationShutdown(): Promise<void> {
    this.events.stop();
    await this.bot.stop();
    this.redis.disconnect();
  }

  private async download(fileId: string): Promise<Uint8Array> {
    const file = await this.bot.api.getFile(fileId);
    if (!file.file_path) throw new Error('Telegram gave no file path');
    const response = await fetch(`https://api.telegram.org/file/bot${this.config.token}/${file.file_path}`, {
      signal: AbortSignal.timeout(60_000),
    });
    if (!response.ok) throw new Error(`file download failed: HTTP ${response.status}`);
    return new Uint8Array(await response.arrayBuffer());
  }
}

@Module({
  providers: [
    { provide: BotConfig, useFactory: () => BotConfig.fromEnv() },
    {
      provide: REDIS,
      inject: [BotConfig],
      useFactory: (config: BotConfig) => new Redis(config.redisUrl, { maxRetriesPerRequest: null }),
    },
    TelegramBot,
  ],
})
export class AppModule {}
