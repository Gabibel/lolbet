# LoLBet

A Discord bot that watches registered players' League of Legends games, opens a
virtual betting market the moment a game goes live, and posts a results recap
with MVP and worst-player awards when it ends, plus a line of banter aimed
at whoever just fed.

**The bot speaks French.** Command names, embeds and error messages are all
in French; the code, comments and this README are in English.

**Free forever, by construction.** No paid services, no expiring trials, no
managed database. SQLite on local disk, self-hosted on an
[Oracle Cloud Always Free](https://www.oracle.com/cloud/free/) ARM VM or a
Raspberry Pi you already own. See [Why this stays free](#why-this-stays-free).

**Virtual currency only.** Coins are rows in a SQLite file. There is no
real-money path anywhere in the code and nothing to add one to.

---

## What it does

1. **Register** — `/inscription Faker#KR1 kr` links a Riot ID to a Discord user.
2. **Detect** — the tracker polls SPECTATOR-V5 for every registered PUUID and
   posts one embed per game, however many registered users are in it. If they
   are on opposite teams the bet becomes a duel between them (see below).
3. **Bet** — clicking a bet button opens a private panel showing your balance,
   the live odds, the pool, one-click amounts and the commands you can use.
   Parimutuel pool, 0% rake. Bets lock 5 minutes after the game started.
4. **Lock** — when the window closes, a message recaps the final pool and who
   backed which side.
5. **Recap** — when the game ends, the match is fetched from MATCH-V5 and a
   recap is posted as a reply to the announcement: KDA, CS/min, damage, gold,
   vision, payouts, plus MVP and worst-player awards from
   [`scoring.py`](src/lolbet/services/scoring.py).
6. **Roast** — the recap is introduced by a line picked from
   [`taunts.py`](src/lolbet/services/taunts.py) based on how the tracked
   players actually did, and the game LVP gets sent to jail.

### Commands

| Command | Who | What |
| --- | --- | --- |
| `/inscription <RiotID#TAG> [region]` | anyone | Link your account |
| `/desinscription` | anyone | Stop tracking you (coins are kept) |
| `/profil [user]` | anyone | Riot ID, rank, balance, betting record |
| `/classement` | anyone | Richest bettors in this server |
| `/solde [user]` | anyone | Coin balance |
| `/quotidien` | anyone | +100 coins every 24h |
| `/paris` | anyone | Your open positions |
| `/annulerpari [game]` | anyone | Cancel a bet before the lock |
| `/salon [channel]` | Manage Server | Where games are announced |
| `/statut` | Manage Server | Rate-limit, cache and tracker diagnostics |

Betting itself happens on the buttons attached to each announcement.

---

## Quick start

```bash
git clone https://github.com/Gabibel/lolbet.git && cd lolbet
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # then fill in the two secrets
python -m lolbet
```

You need two things in `.env`:

- `LOLBET_DISCORD_TOKEN` — [Discord Developer Portal](https://discord.com/developers/applications)
  → your app → Bot → Reset Token.
- `LOLBET_RIOT_API_KEY` — [developer.riotgames.com](https://developer.riotgames.com/).

Invite the bot with the `bot` and `applications.commands` scopes and these
permissions: **Send Messages** and **Embed Links**. Add **Create Public
Threads** and **Send Messages in Threads** only if you set
`LOLBET_USE_THREADS=true`. No privileged intents are required — the bot never
reads message content.

Then, in your server: `/salon #lol-games`, and `/inscription YourName#TAG`.

Slash commands sync globally, which Discord can take up to an hour to
propagate. Set `LOLBET_DEV_GUILD_ID` to your server id for instant sync while
you are setting things up.

### Get a personal Riot key

The default **development key expires every 24 hours** — the bot will start
logging `tracker.bad_api_key` when it lapses. Apply once for a **personal key**
(free, permanent) at
[developer.riotgames.com/app-type](https://developer.riotgames.com/app-type);
approval takes a few days. Then raise `LOLBET_RATE_LIMIT_PER_SECOND` and
`LOLBET_RATE_LIMIT_PER_TWO_MINUTES` to whatever Riot granted you.

---

## Deployment

### Oracle Cloud Always Free ARM VM (recommended)

The Always Free tier includes 4 Ampere A1 cores and 24 GB of RAM, permanently,
with no card charge — far more than this bot needs. Create an
`Ubuntu 22.04 (aarch64)` VM.Ampere A1 instance, then:

```bash
sudo adduser --system --group --home /opt/lolbet lolbet
sudo -u lolbet git clone https://github.com/Gabibel/lolbet.git /opt/lolbet
cd /opt/lolbet
sudo -u lolbet python3 -m venv .venv
sudo -u lolbet .venv/bin/pip install .
sudo -u lolbet mkdir -p /opt/lolbet/data
sudo -u lolbet cp .env.example .env && sudo -u lolbet nano .env   # add secrets
sudo chmod 600 /opt/lolbet/.env

sudo cp deploy/lolbet.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lolbet
journalctl -u lolbet -f
```

No inbound ports are needed: the bot dials out to Discord over a websocket.
Leave the security list closed except for SSH.

### Raspberry Pi

Identical to the above — the systemd unit is already ARM-friendly and capped at
512 MB. A Pi Zero 2 W handles a few dozen tracked players comfortably; the
bottleneck is the Riot rate limit, not the hardware.

Put `data/` on the SD card only if you have to; an external USB SSD will
outlive it. SQLite in WAL mode writes little, but SD cards are SD cards.

### Why not Vercel, Netlify or any serverless host

They cannot run this bot, whatever the plan:

- it holds a **permanent websocket** to Discord, while serverless functions are
  killed after seconds;
- it **polls every 60 seconds**, while free serverless cron is daily at best;
- it stores everything in **SQLite on local disk**, and serverless filesystems
  are wiped between invocations.

Rewriting it as an HTTP-interactions bot would fix the first point and none of
the others, and would force a hosted database - which breaks the free-forever
constraint. Use the Oracle Always Free VM or a Pi.

### Docker (optional)

[`deploy/Dockerfile`](deploy/Dockerfile) builds a slim ARM64-capable image. It
is genuinely optional — on a Pi, systemd is less overhead.

### Backups

Everything lives in one file:

```bash
sqlite3 /opt/lolbet/data/lolbet.db ".backup '/opt/lolbet/data/backup.db'"
```

Use `.backup` rather than `cp`, so you get a consistent snapshot while the bot
is running.

---

## How it works

```
                 ┌──────────────┐
  poll loop ───► │ SPECTATOR-V5 │──► new game? ──► announce (phase 1, 0 extra calls)
  (staggered)    └──────────────┘                        │
                                                         ├─► betting opens (buttons)
                                                         │
                                    +3s ─► LEAGUE-V4 + SUMMONER-V4 + MASTERY-V4
                                                         └─► edit same message (phase 2)

  maintenance loop ─► lock at gameStart+5min ─► embed to LOCKED + pool recap
                   └─► spectator 404 ─► wait 60s ─► MATCH-V5 ─► settle + recap
```

### Rate limiting is the design constraint

A development key allows **20 requests/second and 100 requests/2 minutes**, and
both windows apply at once. [`ratelimit.py`](src/lolbet/riot/ratelimit.py)
implements one shared bucket holding a list of sliding windows; a request may
only start when *every* window has room. An `asyncio.Semaphore(5)` caps
in-flight requests on top of that, so a burst never spikes even when the
windows would allow it. On HTTP 429 the `Retry-After` header parks the entire
limiter — no busy-retrying.

Four more things keep the request count down:

- **Staggered polling.** A pass over all registered players is spread evenly
  across `POLL_INTERVAL_SECONDS` instead of firing at once.
- **Players in a tracked game are not polled.** One "watcher" PUUID per live
  game notices the game ending, so a five-stack costs one call per interval
  rather than five.
- **Per-endpoint TTL cache**, in memory and mirrored into SQLite so a restart
  starts warm:

  | Endpoint | TTL |
  | --- | --- |
  | ACCOUNT-V1 (Riot ID ↔ PUUID) | 7 days |
  | SUMMONER-V4 (level, icon) | 7 days |
  | LEAGUE-V4 (tier, rank, LP) | 6 hours |
  | CHAMPION-MASTERY-V4 | 24 hours, keyed on (puuid, championId) |
  | DDragon | 24 hours |
  | MATCH-V5 | forever (immutable) |
  | SPECTATOR-V5 | never cached |

- **Request coalescing.** Concurrent misses on the same key wait on one lookup
  instead of firing identical requests.

Data Dragon needs no key, has no rate limit and is not counted against the
quota, so those requests deliberately bypass the limiter.

### PUUID-only endpoints

Riot removed the `summonerId`-based routes on **20 June 2025**. This bot never
calls `/lol/league/v4/entries/by-summoner/` or `/lol/summoner/v4/summoners/{id}`.
Ranks come from `/lol/league/v4/entries/by-puuid/{puuid}`, and SPECTATOR-V5
takes a PUUID despite its `by-summoner` path.

`matchId` is the platform prefix plus the spectator `gameId`, e.g.
`EUW1_7123456789`.

### Two-phase embed

The announcement posts immediately using nothing but the spectator payload —
champions, Riot IDs, queue, teams. **Betting opens on that first post.** About
three seconds later the rank, mastery and level lookups resolve and the same
message is edited in place. This spreads 30 requests over a few seconds instead
of delaying the announcement behind them.

Mastery, rank and average elo are presented as raw information for bettors to
judge. The embed says so, and the code never claims they predict the outcome.

### Several registered players in one game

One announcement per game, never one per player. What changes is who the bet
is about:

- **Same team** (duo, five-stack): the bet stays *their team wins* vs *loses*.
- **Opposite teams**: betting on a "loss" would be meaningless, since one
  tracked player wins either way. The two sides are relabelled with the
  players' own names, the embed says it is a duel, and the recap is titled by
  whoever won rather than by a team.

Labels are derived from the tracked participants stored with the game, so they
survive a restart. `WIN` still means the reference team internally — only the
presentation changes, which keeps the payout maths untouched.

### Parimutuel payouts

```
payout = stake × (total_pool / winning_side_pool)      0% rake
```

Stakes leave the wallet when the bet is placed, so balances can never go
negative and the pool always matches coins actually held. Payouts are integers
and the rounding remainder is distributed largest-remainder style, so the pool
is conserved to the coin instead of quietly evaporating. If nobody backed the
winning side, everyone is refunded rather than the pool being burned.

`UNIQUE (user_id, game_id)` enforces one position per user per game — a
double-clicked button hits the constraint, not a race.

Embed edits are debounced (default 2.5s) so a flurry of bets produces one edit,
not ten, and Discord's per-channel edit limits are respected.

### Failure handling

- **Game vanishes from spectator** → wait 60s, then MATCH-V5 with exponential
  backoff (30s doubling, capped at 5 min, 12 attempts). If the match never
  appears, the game is voided and **every bet is refunded**.
- **Game never ends** (player unregistered mid-game, Riot hiccup) → after
  3 hours it is forced into resolution so bets are never stuck.
- **Restart** → tracked game IDs are persisted, so nothing is re-announced;
  live games keep being watched and pending results keep being resolved.
  Buttons keep working because the game ID lives in the component `custom_id`.

---

## Configuration

Every setting is an env var prefixed `LOLBET_`; see
[`.env.example`](.env.example) for the full list with defaults. The ones worth
knowing:

| Variable | Default | Notes |
| --- | --- | --- |
| `LOLBET_POLL_INTERVAL_SECONDS` | `60` | One full pass over all players |
| `LOLBET_RATE_LIMIT_PER_SECOND` | `20` | Dev key limit |
| `LOLBET_RATE_LIMIT_PER_TWO_MINUTES` | `100` | Dev key limit |
| `LOLBET_BET_LOCK_SECONDS` | `300` | After `gameStartTime` |
| `LOLBET_STARTING_BALANCE` | `1000` | Coins for a new wallet |
| `LOLBET_DAILY_AMOUNT` | `100` | `/daily` grant |
| `LOLBET_USE_THREADS` | `false` | `true` puts the lock notice and recap in a thread instead of the channel |
| `LOLBET_ANNOUNCE_LOCK` | `true` | Post a message when the betting window closes |
| `LOLBET_DEV_GUILD_ID` | unset | Set it for instant slash-command sync while developing |

---

## Development

```bash
pip install -e ".[dev]"
pytest
```

The suite covers the parts where being wrong is expensive: the dual-window rate
limiter, the TTL cache and its persistence, Riot client routing and 404/429
handling (via `respx`, no network), the payout maths, the wallet lifecycle, the
MVP/worst scoring, and the taunt selection. None of it needs a Discord token or
a Riot key.

On the banter: only players who opted in with `/inscription` are ever targeted,
and only on their stats from that game. A support is never mocked for farming,
an MVP is never piled on, and short games get no statistical jab. Keep it that
way if you add lines.

Layout:

```
src/lolbet/
  config.py            settings + platform→region routing
  db.py                async engine, WAL pragmas
  models.py            SQLModel tables
  views.py             buttons, modal, amount parsing
  riot/
    ratelimit.py       dual-window token bucket + semaphore
    cache.py           TTL cache, SQLite-mirrored
    client.py          PUUID-only endpoints
    ddragon.py         static data (no key, no limit)
    rank.py            tier/LP ladder maths
  services/
    tracker.py         poll + maintenance loops
    betting.py         parimutuel pool + wallets
    scoring.py         MVP / worst player
    taunts.py          fin-de-partie banter
    embeds.py          all Discord rendering
    enrichment.py      spectator payload → embed model
    messages.py        debounced message edits
  cogs/                slash commands
```

---

## Why this stays free

| Piece | Choice | Cost |
| --- | --- | --- |
| Hosting | Oracle Cloud Always Free ARM VM, or a Pi you own | $0, no expiry |
| Database | SQLite on local disk, WAL mode | $0, no server |
| Riot API | Personal key | $0, permanent |
| Static assets | Data Dragon CDN | $0, no key, no quota |
| Discord | Bot API | $0 |
| Scheduling | Plain asyncio loops in-process | $0, no worker service |
| Logs | journald | $0 |

Deliberately avoided: managed Postgres/Redis (all have paid tiers or expiring
credits), hosted schedulers, APM SaaS, and container registries with pull
limits. There is no hosted-cache dependency either — the TTL cache mirrors into
the same SQLite file.

If you extend this bot, keep that property: prefer a local file over a service,
and in-process loops over a worker you have to pay for.

---

## Licence

MIT. Not endorsed by Riot Games. League of Legends is a trademark of Riot
Games, Inc.
