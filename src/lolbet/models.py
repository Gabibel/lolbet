"""SQLModel tables. Everything lives in one local SQLite file."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Column, Index, UniqueConstraint
from sqlmodel import Field, SQLModel

from .utils import utcnow

SOLO_QUEUE_TYPE = "RANKED_SOLO_5x5"


class GameStatus(StrEnum):
    LIVE = "LIVE"  # announced, bets open
    LOCKED = "LOCKED"  # bets closed, game still running
    PENDING_RESULT = "PENDING_RESULT"  # spectator returned 404, waiting on MATCH-V5
    RESOLVED = "RESOLVED"  # recap posted, bets paid out
    VOID = "VOID"  # match never appeared, bets refunded


class BetSide(StrEnum):
    WIN = "WIN"
    LOSS = "LOSS"


class Player(SQLModel, table=True):
    """A Discord user registered in a specific guild."""

    __tablename__ = "player"
    __table_args__ = (
        UniqueConstraint("guild_id", "discord_id", name="uq_player_guild_user"),
        Index("ix_player_puuid", "puuid"),
    )

    id: int | None = Field(default=None, primary_key=True)
    # Discord snowflakes need 64 bits; SQLite INTEGER is 64-bit, BigInteger
    # just makes that explicit and keeps other backends honest.
    guild_id: int = Field(sa_column=Column(BigInteger, nullable=False, index=True))
    discord_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    puuid: str = Field(max_length=100)
    game_name: str
    tag_line: str
    platform: str = Field(max_length=8)
    registered_at: datetime = Field(default_factory=utcnow)
    riot_id_refreshed_at: datetime = Field(default_factory=utcnow)

    @property
    def riot_id(self) -> str:
        return f"{self.game_name}#{self.tag_line}"


class GuildConfig(SQLModel, table=True):
    __tablename__ = "guild_config"

    guild_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    announce_channel_id: int | None = Field(
        default=None, sa_column=Column(BigInteger, nullable=True)
    )
    updated_at: datetime = Field(default_factory=utcnow)


class Wallet(SQLModel, table=True):
    """Virtual coins. Scoped per guild so leaderboards are per community."""

    __tablename__ = "wallet"
    __table_args__ = (UniqueConstraint("guild_id", "user_id", name="uq_wallet_guild_user"),)

    id: int | None = Field(default=None, primary_key=True)
    guild_id: int = Field(sa_column=Column(BigInteger, nullable=False, index=True))
    user_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    balance: int = 0
    total_wagered: int = 0
    bets_won: int = 0
    bets_lost: int = 0
    net_profit: int = 0
    last_daily_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class TrackedGame(SQLModel, table=True):
    """One live game as announced in one guild."""

    __tablename__ = "tracked_game"
    __table_args__ = (
        UniqueConstraint("guild_id", "riot_game_id", name="uq_game_guild_riot"),
        Index("ix_tracked_game_status", "status"),
    )

    id: int | None = Field(default=None, primary_key=True)
    guild_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    # "EUW1_7123456789" - platform prefix + "_" + spectator gameId.
    riot_game_id: str = Field(index=True, max_length=32)
    platform: str = Field(max_length=8)
    queue_id: int = 0
    status: str = Field(default=GameStatus.LIVE, max_length=20)

    # The team our tracked players are on. Bets are on that team winning.
    tracked_team_id: int = 100
    winning_team_id: int | None = None

    game_start_at: datetime | None = None
    detected_at: datetime = Field(default_factory=utcnow)
    lock_at: datetime | None = None
    resolve_after: datetime | None = None
    next_result_attempt_at: datetime | None = None
    result_attempts: int = 0
    resolved_at: datetime | None = None

    channel_id: int | None = Field(default=None, sa_column=Column(BigInteger, nullable=True))
    message_id: int | None = Field(default=None, sa_column=Column(BigInteger, nullable=True))
    thread_id: int | None = Field(default=None, sa_column=Column(BigInteger, nullable=True))

    # The puuid we keep polling to notice the game ending.
    watcher_puuid: str = ""
    # Raw spectator payload, so a restart can rebuild the embed without a call.
    spectator_json: str = ""
    enriched: bool = False


class TrackedParticipant(SQLModel, table=True):
    """A registered player inside a tracked game (our own users only)."""

    __tablename__ = "tracked_participant"
    __table_args__ = (UniqueConstraint("game_id", "puuid", name="uq_participant_game_puuid"),)

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="tracked_game.id", index=True)
    puuid: str = Field(max_length=100)
    discord_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    riot_id: str = ""
    champion_id: int = 0
    team_id: int = 100


class Bet(SQLModel, table=True):
    """One position per user per game, enforced by the unique constraint."""

    __tablename__ = "bet"
    __table_args__ = (
        UniqueConstraint("user_id", "game_id", name="uq_bet_user_game"),
        Index("ix_bet_game", "game_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="tracked_game.id")
    guild_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    user_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    side: str = Field(max_length=8)
    amount: int
    # Cote figee au moment du pari : c'est elle qui sera payee, pas
    # celle affichee plus tard quand d'autres auront mise.
    odds: float = 0.0
    created_at: datetime = Field(default_factory=utcnow)
    payout: int | None = None
    settled_at: datetime | None = None


class ApiCacheEntry(SQLModel, table=True):
    """Persisted TTL cache so a restart starts warm instead of hammering Riot."""

    __tablename__ = "api_cache"

    key: str = Field(primary_key=True, max_length=255)
    payload: str
    # NULL means never expires (MATCH-V5 results are immutable).
    expires_at: float | None = Field(default=None, index=True)
    stored_at: float = 0.0


class PlayerGameStat(SQLModel, table=True):
    """Ce qu'un joueur suivi a fait dans une partie terminée.

    Écrit une fois au moment du règlement. Sans cette table, l'historique et
    les séries se reconstruiraient à chaque fois depuis MATCH-V5.
    """

    __tablename__ = "player_game_stat"
    __table_args__ = (
        UniqueConstraint("game_id", "puuid", name="uq_stat_game_puuid"),
        Index("ix_stat_guild_user", "guild_id", "discord_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="tracked_game.id", index=True)
    guild_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    discord_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    puuid: str = Field(max_length=100)

    riot_game_id: str = Field(max_length=32)
    queue_id: int = 0
    duration_seconds: int = 0
    champion_id: int = 0
    champion_name: str = ""
    position: str = Field(default="", max_length=16)

    win: bool = False
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    cs: int = 0
    cs_per_min: float = 0.0
    damage: int = 0
    gold: int = 0
    vision_score: int = 0
    score: float = 0.0
    is_mvp: bool = False
    is_lvp: bool = False

    played_at: datetime = Field(default_factory=utcnow, index=True)

    @property
    def kda_line(self) -> str:
        return f"{self.kills}/{self.deaths}/{self.assists}"

    @property
    def kda_ratio(self) -> float:
        return (self.kills + self.assists) / max(1, self.deaths)


class RankSnapshot(SQLModel, table=True):
    """Un relevé de rang, pour tracer la progression de LP."""

    __tablename__ = "rank_snapshot"
    __table_args__ = (Index("ix_rank_puuid_time", "puuid", "captured_at"),)

    id: int | None = Field(default=None, primary_key=True)
    puuid: str = Field(max_length=100)
    platform: str = Field(max_length=8)
    queue: str = Field(default=SOLO_QUEUE_TYPE, max_length=32)

    tier: str = Field(max_length=16)
    division: str = Field(default="I", max_length=4)
    league_points: int = 0
    # Position sur l'échelle continue : c'est elle qui rend les écarts
    # comparables entre paliers.
    ladder_score: int = 0
    wins: int = 0
    losses: int = 0

    # Renseigné quand le relevé suit une partie précise.
    game_id: int | None = Field(default=None, foreign_key="tracked_game.id")
    captured_at: datetime = Field(default_factory=utcnow)


class Season(SQLModel, table=True):
    """Une saison de paris. Une seule est active par serveur à la fois."""

    __tablename__ = "season"
    __table_args__ = (
        UniqueConstraint("guild_id", "number", name="uq_season_guild_number"),
        Index("ix_season_guild_open", "guild_id", "ended_at"),
    )

    id: int | None = Field(default=None, primary_key=True)
    guild_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    number: int = 1
    name: str = ""
    started_at: datetime = Field(default_factory=utcnow)
    # NULL = saison en cours.
    ended_at: datetime | None = None
    starting_balance: int = 1000


class SeasonStanding(SQLModel, table=True):
    """Le classement figé d'une saison close : le palmarès."""

    __tablename__ = "season_standing"
    __table_args__ = (
        UniqueConstraint("season_id", "user_id", name="uq_standing_season_user"),
        Index("ix_standing_season_position", "season_id", "position"),
    )

    id: int | None = Field(default=None, primary_key=True)
    season_id: int = Field(foreign_key="season.id", index=True)
    guild_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    user_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    position: int = 0
    balance: int = 0
    bets_won: int = 0
    bets_lost: int = 0
    net_profit: int = 0
    total_wagered: int = 0
    riot_id: str = ""
