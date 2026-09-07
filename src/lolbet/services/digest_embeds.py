"""Rendu du bilan hebdomadaire, des trophées et du face-à-face."""

from __future__ import annotations

import discord

from ..models import PlayerGameStat
from .awards import Records, Trophy
from .digest import WeeklyDigest
from .headtohead import HeadToHead

COLOUR_DIGEST = discord.Colour(0x5865F2)
COLOUR_TROPHY = discord.Colour(0xF1C40F)
COLOUR_DUEL = discord.Colour(0x9B59B6)

MAX_ROWS = 10


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    """« 1 victoire », « 4 victoires »."""
    word = singular if abs(count) <= 1 else (plural or singular + "s")
    return f"{count} {word}"


def _signed(value: int | None) -> str:
    return f"{value:+d}" if value is not None else "—"


def _game_line(stat: PlayerGameStat | None) -> str:
    if stat is None:
        return "—"
    kda = f"{stat.kills}/{stat.deaths}/{stat.assists}"
    champion = stat.champion_name or "?"
    return f"<@{stat.discord_id}> \N{EM DASH} {champion} {kda}"


def build_digest_embed(digest: WeeklyDigest, *, days: int = 7) -> discord.Embed:
    """Le bilan de la semaine. Reste lisible même une semaine creuse."""
    embed = discord.Embed(
        title="\N{NEWSPAPER} Le bilan de la semaine",
        colour=COLOUR_DIGEST,
    )

    if not digest.has_data:
        embed.description = (
            "Personne n'a joué de partie classée suivie cette semaine. "
            "C'est un choix."
        )
        return embed

    embed.description = (
        f"{digest.games} partie{'s' if digest.games > 1 else ''} suivie"
        f"{'s' if digest.games > 1 else ''} \N{BULLET} "
        f"{digest.total_deaths} morts au total"
    )

    rows = []
    for player in digest.players[:MAX_ROWS]:
        rate = player.winrate
        rows.append(
            f"<@{player.discord_id}> \N{EM DASH} {player.wins}V/{player.losses}D"
            + (f" ({rate:.0f}%)" if rate is not None else "")
            + f" \N{BULLET} KDA {player.kda:.1f}"
            + f" \N{BULLET} {_signed(player.lp)} LP"
        )
    embed.add_field(name="Qui a joué", value="\n".join(rows), inline=False)

    highlights = []
    climber = digest.climber
    if climber is not None:
        highlights.append(f"\N{CHART WITH UPWARDS TREND} <@{climber.discord_id}> {_signed(climber.lp)} LP")
    faller = digest.faller
    if faller is not None:
        highlights.append(f"\N{CHART WITH DOWNWARDS TREND} <@{faller.discord_id}> {_signed(faller.lp)} LP")
    feeder = digest.feeder
    if feeder is not None and feeder.deaths:
        highlights.append(
            f"\N{SKULL} <@{feeder.discord_id}> {feeder.deaths} morts"
        )
    if highlights:
        embed.add_field(name="Les extrêmes", value="\n".join(highlights), inline=False)

    embed.add_field(
        name="Meilleure partie", value=_game_line(digest.best_game), inline=True
    )
    embed.add_field(name="Pire partie", value=_game_line(digest.worst_game), inline=True)

    if digest.bettors:
        lines = []
        for bettor in digest.bettors[:5]:
            lines.append(
                f"<@{bettor.user_id}> \N{EM DASH} {bettor.profit:+,} pièces "
                f"({bettor.won}/{bettor.settled} paris gagnés)".replace(",", " ")
            )
        embed.add_field(name="Les parieurs", value="\n".join(lines), inline=False)

    embed.set_footer(text=f"Sur les {days} derniers jours")
    return embed


def build_trophies_embed(
    user: discord.abc.User,
    trophies: list[Trophy],
    records: Records,
    *,
    missing: list[str] | None = None,
) -> discord.Embed:
    embed = discord.Embed(
        title=f"\N{TROPHY} Trophées de {user.display_name}",
        colour=COLOUR_TROPHY,
    )
    embed.set_thumbnail(url=user.display_avatar.url)

    if not records.games:
        embed.description = (
            "Aucune partie suivie pour l'instant. Les trophées arrivent tout seuls."
        )
        return embed

    embed.description = "\n".join(t.line for t in trophies) if trophies else (
        "Aucun trophée pour l'instant. Il en faut peu, mais il en faut."
    )

    lignes = []
    if records.most_kills is not None:
        lignes.append(f"Plus de kills \N{EM DASH} {records.most_kills.kills}")
    if records.most_deaths is not None:
        lignes.append(f"Plus de morts \N{EM DASH} {records.most_deaths.deaths}")
    if records.most_cs is not None:
        lignes.append(f"Plus de CS \N{EM DASH} {records.most_cs.cs}")
    if records.longest is not None:
        lignes.append(
            f"Plus longue partie \N{EM DASH} {records.longest.duration_seconds // 60} min"
        )
    if records.best_win_streak:
        lignes.append(f"Meilleure série \N{EM DASH} {records.best_win_streak} victoires")
    if records.worst_loss_streak:
        lignes.append(f"Pire série \N{EM DASH} {records.worst_loss_streak} défaites")
    if lignes:
        embed.add_field(name="Records", value="\n".join(lignes), inline=False)

    if missing:
        embed.add_field(
            name="Pas encore débloqués",
            value=", ".join(missing[:8]),
            inline=False,
        )
    embed.set_footer(text=_plural(records.games, "partie suivie", "parties suivies"))
    return embed


def _column(side, name: str) -> str:
    rate = side.winrate
    return (
        f"**{name}**\n"
        f"{side.games} parties"
        + (f" \N{BULLET} {rate:.0f}%" if rate is not None else "")
        + f"\nKDA {side.kda:.2f}"
        f"\n{side.avg_deaths:.1f} morts/partie"
        f"\n{side.mvp} MVP \N{BULLET} {side.lvp} LVP"
    )


def build_duel_embed(
    duel: HeadToHead,
    left: discord.abc.User,
    right: discord.abc.User,
) -> discord.Embed:
    embed = discord.Embed(
        title=f"\N{CROSSED SWORDS}\N{VARIATION SELECTOR-16} {left.display_name} contre {right.display_name}",
        colour=COLOUR_DUEL,
    )
    embed.add_field(value=_column(duel.left, left.display_name), name="​", inline=True)
    embed.add_field(value=_column(duel.right, right.display_name), name="​", inline=True)

    if not duel.has_shared_games:
        embed.add_field(
            name="Parties communes",
            value=(
                "Aucune pour l'instant. Les colonnes ci-dessus comparent deux "
                "historiques séparés, pas un affrontement."
            ),
            inline=False,
        )
        return embed

    lines = [
        f"{duel.together} parties ensemble "
        f"({duel.same_team} dans la même équipe, {duel.against} face à face)",
        f"Meilleur score : <@{duel.left.discord_id}> {duel.left_ahead} fois, "
        f"<@{duel.right.discord_id}> {duel.right_ahead} fois",
    ]
    if duel.against:
        lines.append(
            f"En adversaires : <@{duel.left.discord_id}> {duel.left_wins_against} "
            f"\N{EM DASH} {duel.right_wins_against} <@{duel.right.discord_id}>"
        )
    embed.add_field(name="Face à face", value="\n".join(lines), inline=False)

    leader = duel.leader
    if leader is not None:
        embed.set_footer(text="Le classement du scoreboard ne ment pas.")
    else:
        embed.set_footer(text="Parfaitement à égalité. Rejouez.")
    return embed
