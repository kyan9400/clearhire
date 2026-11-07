# Clearhire Telegram bot

NestJS and [grammY](https://grammy.dev). Russian or English, following the user's Telegram language.

**Candidates**
- `/jobs`: open roles, with the requirements of each.
- **Check my CV**: send a file or a photo and see each requirement found or not, with the line of the CV
  that shows it. The file is read in memory by the API and not stored.
- **Apply**: name, e-mail, explicit 152-FZ consent, CV. The CV just checked can be reused.
- `/status`: where each application is; erasing one withdraws consent and deletes the data.
- Messages when a CV has been read, when an application moves on, or when a file could not be read.
- Deep links from the careers site: `t.me/<bot>?start=job_<vacancy id>`.

**Recruiters**: the chats in `RECRUITER_CHAT_IDS` (a person or a team group; `/whoami` tells a chat its
id) get every new application once its CV has been read, with how many must-haves it meets and a link
to the console. No names: the event carries ids and counts.

**How it fits**
- Long polling: no public port or webhook.
- It calls the careers API with a shared secret (`X-Clearhire-Bot`) and the Telegram user it acts for, so
  the API rate-limits per person instead of per bot, and records the application's source as Telegram.
- Notifications come from the API's Redis stream (`clearhire:events`) through a consumer group: each event
  is handled once, and events left unacknowledged by a crash are read again at start.
- Redis keeps the conversation state (an hour) and which chat owns which application. The status token
  never leaves Redis and that chat.

```bash
npm ci
npm test                                   # conversations, notifications, formatting, config
REDIS_TEST_URL=redis://localhost:6379/15 npm test   # plus the Redis store and the event stream
cp .env.example .env && npm run dev        # needs the API, Redis and a token from @BotFather
```
