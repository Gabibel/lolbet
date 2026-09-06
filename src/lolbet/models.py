"""SQLModel tables. Everything lives in one local SQLite file."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Column, Index, UniqueConstraint
from sqlmodel import Field, SQLModel

from .utils import utcnow


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
