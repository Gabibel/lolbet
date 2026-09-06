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
    0: "Partie personnalisée",
    400: "Normale draft",
    420: "Classé Solo/Duo",
    430: "Normale aveugle",
    440: "Classé Flexible",
    450: "ARAM",
    490: "Partie rapide",
    700: "Clash",
    720: "Clash ARAM",
    830: "Coop contre IA (intro)",
    840: "Coop contre IA (débutant)",
    850: "Coop contre IA (intermédiaire)",
    900: "URF",
    1020: "Un pour tous",
    1300: "Nexus Blitz",
    1700: "Arène",
    1900: "URF",
}

TEAM_NAMES = {BLUE_TEAM: "Équipe Bleue", RED_TEAM: "Équipe Rouge"}
TEAM_EMOJI = {BLUE_TEAM: "\N{LARGE BLUE CIRCLE}", RED_TEAM: "\N{LARGE RED CIRCLE}"}

EMOJI_LIVE = "\N{LARGE RED CIRCLE}"
EMOJI_LOCK = "\N{LOCK}"
EMOJI_TROPHY = "\N{TROPHY}"
EMOJI_DEFEAT = "\N{CROSS MARK}"

MASTERY_DISCLAIMER = (
    "Maîtrise, rang et elo moyen sont des informations brutes, à vous de juger : "
    "ce n'est pas une prédiction du résultat."
)


def _side_label(side: str | None) -> str:
    return {"WIN": "VICTOIRE", "LOSS": "DÉFAITE"}.get(side or "", str(side))


def queue_name(queue_id: int) -> str:
    return QUEUE_NAMES.get(int(queue_id), f"File {queue_id}")


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
        parts.append(f"jouée {format_ago(player.mastery_last_played)}")
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
        details.append("Non classé")
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
        verdict = "équilibré sur le papier"
    else:
        leader = "Bleue" if delta > 0 else "Rouge"
        verdict = f"Équipe **{leader}** favorite de {abs(delta):.0f} points de ladder"
    return (
        f"{TEAM_EMOJI[BLUE_TEAM]} Moyenne bleue **{blue_label}** • "
        f"{TEAM_EMOJI[RED_TEAM]} Moyenne rouge **{red_label}**\n{verdict}"
    )


def _odds_value(pool: Pool, tracked_team_name: str) -> str:
    if pool.count == 0:
        return "Aucun pari pour l'instant. Le premier fixe la cote."
    rows = []
    for side, label in ((BetSide.WIN, "VICTOIRE"), (BetSide.LOSS, "DÉFAITE")):
        amount = pool.win_amount if side == BetSide.WIN else pool.loss_amount
        count = pool.win_count if side == BetSide.WIN else pool.loss_count
        multiplier = pool.multiplier(side)
        odds = f"x{multiplier:.2f}" if multiplier else "-"
        rows.append(f"**{label}** {amount:,} pièces ({count}) → {odds}")
    implied = pool.implied_probability(BetSide.WIN)
    backing = (
        f"\nLa cagnotte donne {tracked_team_name} à {implied * 100:.0f}%"
        if implied is not None
        else ""
    )
    return (
        f"{' • '.join(rows)}\nCagnotte : **{pool.total:,}** pièces, "
        f"0% de commission{backing}"
    )


def build_game_embed(
    card: GameCard,
    pool: Pool,
    ddragon: DDragon,
    *,
    status: str = GameStatus.LIVE,
) -> discord.Embed:
    """The live-game announcement, in either its open or locked state."""
    tracked = card.tracked
    names = ", ".join(discord.utils.escape_markdown(p.riot_id) for p in tracked) or "Joueur suivi"
    locked = status != GameStatus.LIVE
    state = f"{EMOJI_LOCK} PARIS FERMÉS" if locked else f"{EMOJI_LIVE} EN PARTIE"
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
        suffix = " (suivie)" if team_id == card.tracked_team_id else ""
        embed.add_field(
            name=f"{TEAM_EMOJI[team_id]} {TEAM_NAMES[team_id]}{suffix}",
            value=_team_field_value(players, ddragon),
            inline=False,
        )

    favourite = _favourite_line(card)
    if favourite:
        embed.add_field(name="Elo moyen", value=favourite, inline=False)

    tracked_team_name = TEAM_NAMES.get(card.tracked_team_id, "l'équipe suivie")
    if locked:
        embed.add_field(
            name="\N{LOCK} Paris fermés",
            value=_odds_value(pool, tracked_team_name),
            inline=False,
        )
    else:
        lock_note = (
            f"Fermeture {discord_timestamp(card.lock_at)}"
            if card.lock_at
            else "Fermeture imminente"
        )
        embed.add_field(
            name=f"\N{MONEY BAG} Paris ouverts – {lock_note}",
            value=_odds_value(pool, tracked_team_name),
            inline=False,
        )

    footer = f"{card.riot_game_id} • {MASTERY_DISCLAIMER}"
    if not card.enriched:
        footer = f"{card.riot_game_id} • chargement des rangs et maîtrises..."
    embed.set_footer(text=footer[:2048])
    return embed


def _description(card: GameCard, ddragon: DDragon) -> str:
    lines = [f"**{queue_name(card.queue_id)}** • `{card.platform.upper()}`"]
    if card.started_at is not None:
        lines[0] += f" • début {discord_timestamp(card.started_at)}"
    for player in card.tracked:
        champion = ddragon.champion_name(player.champion_id)
        mention = f"<@{player.discord_id}>" if player.discord_id else player.riot_id
        rank = f" – {player.rank.display}" if player.rank else ""
        lines.append(f"{mention} sur **{champion}**{rank}")
    return "\n".join(lines)[:4096]


# -- results ---------------------------------------------------------------


def _stat_line(score: PlayerScore, ddragon: DDragon) -> str:
    champion = score.champion_name or ddragon.champion_name(score.champion_id)
    return (
        f"`{champion:<12}` **{score.kda_line}** "
        f"({score.kda_ratio:.1f} KDA)\n"
        f" {score.cs} CS ({score.cs_per_min:.1f}/min) • "
        f"{format_points(score.damage)} dégâts • {format_points(score.gold)} or • "
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
        f" {score.kda_line} • {reasons} • note {score.score:.0f}"
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
    headline = f"{EMOJI_TROPHY} VICTOIRE" if won else f"{EMOJI_DEFEAT} DÉFAITE"
    tracked_team_name = TEAM_NAMES.get(tracked_team_id, "Équipe suivie")
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
            name="Joueurs suivis",
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
            name="\N{DOWNWARDS BLACK ARROW} LVP - pire performance",
            value=_award_line(scores.worst, ddragon, tracked_puuids, worst=True)[:1024],
            inline=False,
        )

    if settlement is not None:
        embed.add_field(
            name="\N{MONEY BAG} Gains", value=_payout_value(settlement), inline=False
        )

    embed.set_footer(
        text=f"{riot_game_id} • notes calculées par scoring.py, pièces virtuelles"
    )
    return embed


def _payout_value(settlement: Settlement) -> str:
    if settlement.pool.count == 0:
        return "Personne n'a parié sur celle-là."
    if settlement.refunded:
        return (
            f"Aucun pari du bon côté : les {settlement.pool.total:,} pièces "
            "ont été remboursées."
        )
    lines = [
        f"Cagnotte **{settlement.pool.total:,}** pièces • côté gagnant : "
        f"**{_side_label(settlement.winning_side)}**"
    ]
    winners = sorted(settlement.paid, key=lambda row: row[2], reverse=True)[:10]
    for user_id, stake, payout in winners:
        profit = payout - stake
        sign = "+" if profit >= 0 else ""
        lines.append(f"<@{user_id}> {stake:,} → **{payout:,}** ({sign}{profit:,})")
    if len(settlement.paid) > 10:
        lines.append(f"...et {len(settlement.paid) - 10} autres gagnants")
    if settlement.lost:
        lost_total = sum(stake for _, stake in settlement.lost)
        lines.append(
            f"{len(settlement.lost)} paris perdants, {lost_total:,} pièces dans la cagnotte"
        )
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
        title=f"{EMOJI_LOCK} Paris fermés - {names}"[:256],
        colour=COLOUR_LOCKED,
        description=(
            f"La fenêtre de {window_seconds // 60} minutes est écoulée. Cagnotte finale :"
            if pool.count
            else f"La fenêtre de {window_seconds // 60} minutes est écoulée. "
            "Personne n'a parié."
        ),
    )

    for side, label, emoji in (
        (BetSide.WIN, f"{tracked_team_name} gagne", EMOJI_TROPHY),
        (BetSide.LOSS, f"{tracked_team_name} perd", EMOJI_DEFEAT),
    ):
        amount = pool.win_amount if side == BetSide.WIN else pool.loss_amount
        side_bets = [bet for bet in bets if bet.side == side]
        multiplier = pool.multiplier(side)
        odds = f" - cote x{multiplier:.2f}" if multiplier else ""
        lines = [f"<@{bet.user_id}> {bet.amount:,}" for bet in side_bets[:10]]
        if len(side_bets) > 10:
            lines.append(f"...et {len(side_bets) - 10} autres")
        embed.add_field(
            name=f"{emoji} {label} - {amount:,} pièces{odds}",
            value="\n".join(lines) if lines else "Personne",
            inline=True,
        )

    embed.set_footer(text=f"{riot_game_id} - pièces virtuelles uniquement")
    return embed


def build_void_embed(riot_game_id: str, refunded: Settlement | None) -> discord.Embed:
    embed = discord.Embed(
        title="\N{WARNING SIGN} Partie impossible à résoudre",
        colour=COLOUR_VOID,
        description=(
            "La partie n'est jamais apparue dans MATCH-V5 (remake, ou Riot ne "
            "l'a jamais publiée). Tous les paris ont été remboursés."
        ),
    )
    if refunded is not None and refunded.pool.count:
        embed.add_field(
            name="Remboursé",
            value=f"{refunded.pool.total:,} pièces sur {refunded.pool.count} paris",
        )
    embed.set_footer(text=riot_game_id)
    return embed
