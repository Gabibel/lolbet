"""Discord embed construction.

Two-phase announcement: :func:`build_game_embed` works with nothing but the
spectator payload, so the first post goes out immediately and betting opens
there. The same function is called again ~3s later once the rank / mastery /
level lookups have resolved, and the message is edited in place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import discord

from ..models import BetSide, GameStatus
from ..riot.ddragon import DDragon
from ..riot.rank import RankInfo, average_score, score_to_label
from ..utils import discord_timestamp, format_ago, format_duration, format_points
from .betting import Pool, Settlement
from .scoring import MatchScores, PlayerScore

BLUE_TEAM = 100
RED_TEAM = 200

COLOUR_LIVE = discord.Colour(0x5865F2)
COLOUR_LOCKED = discord.Colour(0xE67E22)
COLOUR_WIN = discord.Colour(0x2ECC71)
COLOUR_LOSS = discord.Colour(0xE74C3C)
COLOUR_VOID = discord.Colour(0x95A5A6)

QUEUE_NAMES: dict[int, str] = {
    0: "Custom",
    400: "Normal Draft",
    420: "Ranked Solo/Duo",
    430: "Normal Blind",
    440: "Ranked Flex",
    450: "ARAM",
    490: "Quickplay",
    700: "Clash",
    720: "ARAM Clash",
    830: "Co-op vs AI (Intro)",
    840: "Co-op vs AI (Beginner)",
    850: "Co-op vs AI (Intermediate)",
    900: "URF",
    1020: "One for All",
    1300: "Nexus Blitz",
    1700: "Arena",
    1900: "URF",
}

TEAM_NAMES = {BLUE_TEAM: "Blue Team", RED_TEAM: "Red Team"}
TEAM_EMOJI = {BLUE_TEAM: "\N{LARGE BLUE CIRCLE}", RED_TEAM: "\N{LARGE RED CIRCLE}"}

EMOJI_LIVE = "\N{LARGE RED CIRCLE}"
EMOJI_LOCK = "\N{LOCK}"
EMOJI_TROPHY = "\N{TROPHY}"
EMOJI_DEFEAT = "\N{CROSS MARK}"

MASTERY_DISCLAIMER = (
    "Mastery, rank and average elo are raw information for you to judge - "
    "they are not a prediction of the result."
)


def queue_name(queue_id: int) -> str:
    return QUEUE_NAMES.get(int(queue_id), f"Queue {queue_id}")


@dataclass(slots=True)
class PlayerCard:
    """One of the ten players in a live game."""

    puuid: str
    riot_id: str
    champion_id: int
    team_id: int
    spell1_id: int = 0
    spell2_id: int = 0
    rank: RankInfo | None = None
    summoner_level: int | None = None
    mastery_level: int | None = None
    mastery_points: int | None = None
    mastery_last_played: datetime | None = None
    is_tracked: bool = False
    discord_id: int | None = None


@dataclass(slots=True)
class GameCard:
    """Everything the embed needs, independent of Discord and of the DB."""

    riot_game_id: str
    platform: str
    queue_id: int
    tracked_team_id: int
    players: list[PlayerCard] = field(default_factory=list)
    started_at: datetime | None = None
    lock_at: datetime | None = None
    enriched: bool = False

    def team(self, team_id: int) -> list[PlayerCard]:
        return [p for p in self.players if p.team_id == team_id]

    @property
    def tracked(self) -> list[PlayerCard]:
        return [p for p in self.players if p.is_tracked]

    def average_elo(self, team_id: int) -> float | None:
        return average_score([p.rank for p in self.team(team_id)])


def _mastery_text(player: PlayerCard) -> str:
    if player.mastery_points is None:
        return ""
    level = f"M{player.mastery_level}" if player.mastery_level else "M-"
    parts = [f"{level} {format_points(player.mastery_points)} pts"]
    if player.mastery_last_played is not None:
        parts.append(f"last played {format_ago(player.mastery_last_played)}")
    return " - ".join(parts)


def _player_line(player: PlayerCard, ddragon: DDragon) -> str:
    champion = ddragon.champion_name(player.champion_id)
    name = discord.utils.escape_markdown(player.riot_id)
    marker = "**>**" if player.is_tracked else "\N{BULLET}"
    head = f"{marker} `{champion:<12}` {name}"
    if player.is_tracked and player.discord_id:
        head += f" (<@{player.discord_id}>)"

    details: list[str] = []
    if player.rank is not None:
        details.append(player.rank.short)
    elif player.summoner_level is not None:
        details.append("Unranked")
    mastery = _mastery_text(player)
    if mastery:
        details.append(mastery)
    if player.summoner_level:
        details.append(f"Lv{player.summoner_level}")

    if not details:
        return head
    return f"{head}\n {' • '.join(details)}"


def _team_field_value(players: list[PlayerCard], ddragon: DDragon) -> str:
    lines = [_player_line(p, ddragon) for p in players]
    value = "\n".join(lines) or "-"
    return value[:1024]


def _favourite_line(card: GameCard) -> str | None:
    blue = card.average_elo(BLUE_TEAM)
    red = card.average_elo(RED_TEAM)
    if blue is None or red is None:
        return None
    blue_label = score_to_label(blue)
    red_label = score_to_label(red)
    delta = blue - red
    if abs(delta) < 40:
        verdict = "even on paper"
    else:
        leader = "Blue" if delta > 0 else "Red"
        verdict = f"**{leader}** favoured by {abs(delta):.0f} ladder points"
    return (
        f"{TEAM_EMOJI[BLUE_TEAM]} Blue avg **{blue_label}** • "
        f"{TEAM_EMOJI[RED_TEAM]} Red avg **{red_label}**\n{verdict}"
    )


def _odds_value(pool: Pool, tracked_team_name: str) -> str:
    if pool.count == 0:
        return "No bets yet. First one in sets the odds."
    rows = []
    for side, label in ((BetSide.WIN, "WIN"), (BetSide.LOSS, "LOSS")):
        amount = pool.win_amount if side == BetSide.WIN else pool.loss_amount
        count = pool.win_count if side == BetSide.WIN else pool.loss_count
        multiplier = pool.multiplier(side)
        odds = f"x{multiplier:.2f}" if multiplier else "-"
        rows.append(f"**{label}** {amount:,} coins ({count}) → {odds}")
    implied = pool.implied_probability(BetSide.WIN)
    backing = (
        f"\nPool backs {tracked_team_name} at {implied * 100:.0f}%"
        if implied is not None
        else ""
    )
    return f"{' • '.join(rows)}\nPool: **{pool.total:,}** coins, 0% rake{backing}"


def build_game_embed(
    card: GameCard,
    pool: Pool,
    ddragon: DDragon,
    *,
    status: str = GameStatus.LIVE,
) -> discord.Embed:
    """The live-game announcement, in either its open or locked state."""
    tracked = card.tracked
    names = ", ".join(discord.utils.escape_markdown(p.riot_id) for p in tracked) or "Tracked player"
    locked = status != GameStatus.LIVE
    state = f"{EMOJI_LOCK} LOCKED" if locked else f"{EMOJI_LIVE} LIVE"
    title = f"{state} - {names}"

    embed = discord.Embed(
        title=title[:256],
        colour=COLOUR_LOCKED if locked else COLOUR_LIVE,
        description=_description(card, ddragon),
    )

    icon = ddragon.champion_icon_url(tracked[0].champion_id) if tracked else None
    if icon:
        embed.set_thumbnail(url=icon)

    for team_id in (BLUE_TEAM, RED_TEAM):
        players = card.team(team_id)
        if not players:
            continue
        suffix = " (tracked)" if team_id == card.tracked_team_id else ""
        embed.add_field(
            name=f"{TEAM_EMOJI[team_id]} {TEAM_NAMES[team_id]}{suffix}",
            value=_team_field_value(players, ddragon),
            inline=False,
        )

    favourite = _favourite_line(card)
    if favourite:
        embed.add_field(name="Average elo", value=favourite, inline=False)

    tracked_team_name = TEAM_NAMES.get(card.tracked_team_id, "the tracked team")
    if locked:
        embed.add_field(
            name="\N{LOCK} Betting closed",
            value=_odds_value(pool, tracked_team_name),
            inline=False,
        )
    else:
        lock_note = (
            f"Locks {discord_timestamp(card.lock_at)}" if card.lock_at else "Locks shortly"
        )
        embed.add_field(
            name=f"\N{MONEY BAG} Betting open – {lock_note}",
            value=_odds_value(pool, tracked_team_name),
            inline=False,
        )

    footer = f"{card.riot_game_id} • {MASTERY_DISCLAIMER}"
    if not card.enriched:
        footer = f"{card.riot_game_id} • loading ranks and mastery..."
    embed.set_footer(text=footer[:2048])
    return embed


def _description(card: GameCard, ddragon: DDragon) -> str:
    lines = [f"**{queue_name(card.queue_id)}** • `{card.platform.upper()}`"]
    if card.started_at is not None:
        lines[0] += f" • started {discord_timestamp(card.started_at)}"
    for player in card.tracked:
        champion = ddragon.champion_name(player.champion_id)
        mention = f"<@{player.discord_id}>" if player.discord_id else player.riot_id
        rank = f" – {player.rank.display}" if player.rank else ""
        lines.append(f"{mention} on **{champion}**{rank}")
    return "\n".join(lines)[:4096]


# -- results ---------------------------------------------------------------


def _stat_line(score: PlayerScore, ddragon: DDragon) -> str:
    champion = score.champion_name or ddragon.champion_name(score.champion_id)
    return (
        f"`{champion:<12}` **{score.kda_line}** "
        f"({score.kda_ratio:.1f} KDA)\n"
        f" {score.cs} CS ({score.cs_per_min:.1f}/min) • "
        f"{format_points(score.damage)} dmg • {format_points(score.gold)} gold • "
        f"{score.vision_score} vision"
    )


def _award_line(
    score: PlayerScore,
    ddragon: DDragon,
    tracked_puuids: set[str],
    *,
    worst: bool = False,
) -> str:
    champion = score.champion_name or ddragon.champion_name(score.champion_id)
    side = TEAM_NAMES.get(score.team_id, "?")
    mark = " \N{BUSTS IN SILHOUETTE}" if score.puuid in tracked_puuids else ""
    # The MVP line says what they did best; the worst line says what sank them.
    reasons = ", ".join(score.bottom_metrics() if worst else score.top_metrics())
    name = discord.utils.escape_markdown(score.riot_id)
    return (
        f"**{name}**{mark} – {champion} ({side})\n"
        f" {score.kda_line} • {reasons} • score {score.score:.0f}"
    )


def build_result_embed(
    *,
    riot_game_id: str,
    queue_id: int,
    scores: MatchScores,
    tracked_puuids: set[str],
    tracked_team_id: int,
    settlement: Settlement | None,
    ddragon: DDragon,
) -> discord.Embed:
    won = scores.winning_team_id == tracked_team_id
    headline = f"{EMOJI_TROPHY} VICTORY" if won else f"{EMOJI_DEFEAT} DEFEAT"
    tracked_team_name = TEAM_NAMES.get(tracked_team_id, "Tracked team")
    blue_kills = scores.team_kills.get(BLUE_TEAM, 0)
    red_kills = scores.team_kills.get(RED_TEAM, 0)

    embed = discord.Embed(
        title=f"{headline} - {tracked_team_name}",
        colour=COLOUR_WIN if won else COLOUR_LOSS,
        description=(
            f"**{queue_name(queue_id)}** • {format_duration(scores.duration_seconds)} • "
            f"{TEAM_EMOJI[BLUE_TEAM]} **{blue_kills}** – **{red_kills}** {TEAM_EMOJI[RED_TEAM]}"
        ),
    )

    tracked_scores = [s for s in scores.players if s.puuid in tracked_puuids]
    if tracked_scores:
        embed.add_field(
            name="Tracked players",
            value="\n".join(_stat_line(s, ddragon) for s in tracked_scores)[:1024],
            inline=False,
        )

    if scores.mvp is not None:
        embed.add_field(
            name="\N{GLOWING STAR} MVP",
            value=_award_line(scores.mvp, ddragon, tracked_puuids)[:1024],
            inline=False,
        )
    if scores.worst is not None:
        embed.add_field(
            name="\N{DOWNWARDS BLACK ARROW} Worst performance",
            value=_award_line(scores.worst, ddragon, tracked_puuids, worst=True)[:1024],
            inline=False,
        )

    if settlement is not None:
        embed.add_field(name="\N{MONEY BAG} Payouts", value=_payout_value(settlement), inline=False)

    embed.set_footer(text=f"{riot_game_id} • scores from scoring.py, virtual coins only")
    return embed


def _payout_value(settlement: Settlement) -> str:
    if settlement.pool.count == 0:
        return "Nobody bet on this one."
    if settlement.refunded:
        return (
            f"No bets on the winning side, so all {settlement.pool.total:,} coins "
            "were refunded."
        )
    lines = [
        f"Pool **{settlement.pool.total:,}** coins • winning side: "
        f"**{settlement.winning_side}**"
    ]
    winners = sorted(settlement.paid, key=lambda row: row[2], reverse=True)[:10]
    for user_id, stake, payout in winners:
        profit = payout - stake
        sign = "+" if profit >= 0 else ""
        lines.append(f"<@{user_id}> {stake:,} → **{payout:,}** ({sign}{profit:,})")
    if len(settlement.paid) > 10:
        lines.append(f"...and {len(settlement.paid) - 10} more winners")
    if settlement.lost:
        lost_total = sum(stake for _, stake in settlement.lost)
        lines.append(f"{len(settlement.lost)} losing bets, {lost_total:,} coins into the pool")
    return "\n".join(lines)[:1024]


def build_lock_embed(
    *,
    riot_game_id: str,
    tracked_names: list[str],
    pool: Pool,
    bets: list,
    tracked_team_name: str,
    window_seconds: int,
) -> discord.Embed:
    """Posted in the channel when the betting window closes.

    The announcement embed already flips to LOCKED, but that is an edit far up
    the channel; this is the message people actually notice.
    """
    names = ", ".join(discord.utils.escape_markdown(name) for name in tracked_names)
    embed = discord.Embed(
        title=f"{EMOJI_LOCK} Betting closed - {names}"[:256],
        colour=COLOUR_LOCKED,
        description=(
            f"The {window_seconds // 60}-minute window is over. Final pool:"
            if pool.count
            else f"The {window_seconds // 60}-minute window is over. Nobody bet on this one."
        ),
    )

    for side, label, emoji in (
        (BetSide.WIN, f"{tracked_team_name} wins", EMOJI_TROPHY),
        (BetSide.LOSS, f"{tracked_team_name} loses", EMOJI_DEFEAT),
    ):
        amount = pool.win_amount if side == BetSide.WIN else pool.loss_amount
        side_bets = [bet for bet in bets if bet.side == side]
        multiplier = pool.multiplier(side)
        odds = f" - pays x{multiplier:.2f}" if multiplier else ""
        lines = [f"<@{bet.user_id}> {bet.amount:,}" for bet in side_bets[:10]]
        if len(side_bets) > 10:
            lines.append(f"...and {len(side_bets) - 10} more")
        embed.add_field(
            name=f"{emoji} {label} - {amount:,} coins{odds}",
            value="\n".join(lines) if lines else "Nobody",
            inline=True,
        )

    embed.set_footer(text=f"{riot_game_id} - virtual coins only")
    return embed


def build_void_embed(riot_game_id: str, refunded: Settlement | None) -> discord.Embed:
    embed = discord.Embed(
        title="\N{WARNING SIGN} Game could not be resolved",
        colour=COLOUR_VOID,
        description=(
            "The match never showed up in MATCH-V5 (remake, or Riot never "
            "published it). Every bet has been refunded."
        ),
    )
    if refunded is not None and refunded.pool.count:
        embed.add_field(
            name="Refunded",
            value=f"{refunded.pool.total:,} coins across {refunded.pool.count} bets",
        )
    embed.set_footer(text=riot_game_id)
    return embed
