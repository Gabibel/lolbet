"""Records et trophées : ce qu'on ressort à quelqu'un six mois plus tard.

Tout se calcule depuis ``player_game_stat``, qui est figé au règlement. Un
trophée obtenu ne peut donc pas disparaître parce qu'une API a changé d'avis.

Rien n'est stocké : les trophées sont dérivés à la demande. C'est un peu plus
de calcul à l'affichage, mais aucune table à maintenir cohérente, et un
trophée retiré du code disparaît proprement au lieu de traîner en base.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import PlayerGameStat


@dataclass(frozen=True, slots=True)
class Trophy:
    key: str
    label: str
    detail: str
    emoji: str = "\N{SPORTS MEDAL}"

    @property
    def line(self) -> str:
        return f"{self.emoji} **{self.label}** \N{EM DASH} {self.detail}"


@dataclass(frozen=True, slots=True)
class Rule:
    """Un trophée et la condition qui l'accorde."""

    key: str
    label: str
    emoji: str
    # Renvoie le détail à afficher, ou None si le trophée n'est pas gagné.
    check: Callable[[list[PlayerGameStat]], str | None]


def _longest_streak(games: list[PlayerGameStat], *, wins: bool) -> int:
    """Plus longue série, sur l'historique trié du plus ancien au plus récent."""
    best = current = 0
    for game in games:
        if game.win is wins:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def _peak(games: list[PlayerGameStat], key: Callable[[PlayerGameStat], float]):
    return max(games, key=key) if games else None


RULES: tuple[Rule, ...] = (
    Rule(
        "first_blood",
        "Baptême",
        "\N{BABY}",
        lambda g: f"{len(g)} parties suivies" if g else None,
    ),
    Rule(
        "veteran",
        "Vétéran",
        "\N{MILITARY MEDAL}",
        lambda g: f"{len(g)} parties suivies" if len(g) >= 50 else None,
    ),
    Rule(
        "mvp",
        "Homme du match",
        "\N{TROPHY}",
        lambda g: (
            f"{sum(1 for x in g if x.is_mvp)} fois meilleur joueur"
            if sum(1 for x in g if x.is_mvp) >= 1
            else None
        ),
    ),
    Rule(
        "mvp_serial",
        "Carry en série",
        "\N{FIRE}",
        lambda g: (
            f"{sum(1 for x in g if x.is_mvp)} fois meilleur joueur"
            if sum(1 for x in g if x.is_mvp) >= 5
            else None
        ),
    ),
    Rule(
        "lvp",
        "Boulet officiel",
        "\N{COLLISION SYMBOL}",
        lambda g: (
            f"{sum(1 for x in g if x.is_lvp)} fois pire joueur"
            if sum(1 for x in g if x.is_lvp) >= 3
            else None
        ),
    ),
    Rule(
        "feeder",
        "Distributeur automatique",
        "\N{MONEY BAG}",
        lambda g: (
            f"{max((x.deaths for x in g), default=0)} morts dans une seule partie"
            if max((x.deaths for x in g), default=0) >= 12
            else None
        ),
    ),
    Rule(
        "deathless",
        "Intouchable",
        "\N{SHIELD}\N{VARIATION SELECTOR-16}",
        lambda g: (
            f"{sum(1 for x in g if x.deaths == 0 and x.duration_seconds >= 900)} "
            "parties sans mourir"
            if sum(1 for x in g if x.deaths == 0 and x.duration_seconds >= 900) >= 1
            else None
        ),
    ),
    Rule(
        "slayer",
        "Bourreau",
        "\N{CROSSED SWORDS}\N{VARIATION SELECTOR-16}",
        lambda g: (
            f"{max((x.kills for x in g), default=0)} kills dans une partie"
            if max((x.kills for x in g), default=0) >= 15
            else None
        ),
    ),
    Rule(
        "farmer",
        "Agriculteur",
        "\N{EAR OF MAIZE}",
        lambda g: (
            f"{max((x.cs for x in g), default=0)} CS dans une partie"
            if max((x.cs for x in g), default=0) >= 300
            else None
        ),
    ),
    Rule(
        "marathon",
        "Marathonien",
        "\N{HOURGLASS}",
        lambda g: (
            f"une partie de {max((x.duration_seconds for x in g), default=0) // 60} minutes"
            if max((x.duration_seconds for x in g), default=0) >= 45 * 60
            else None
        ),
    ),
    Rule(
        "hot_streak",
        "Sur une lancée",
        "\N{HIGH VOLTAGE SIGN}",
        lambda g: (
            f"{_longest_streak(g, wins=True)} victoires d'affilée"
            if _longest_streak(g, wins=True) >= 4
            else None
        ),
    ),
    Rule(
        "cold_streak",
        "Traversée du désert",
        "\N{SNOWFLAKE}",
        lambda g: (
            f"{_longest_streak(g, wins=False)} défaites d'affilée"
            if _longest_streak(g, wins=False) >= 4
            else None
        ),
    ),
    Rule(
        "vision",
        "Y voit clair",
        "\N{EYE}\N{VARIATION SELECTOR-16}",
        lambda g: (
            f"{max((x.vision_score for x in g), default=0)} de score de vision"
            if max((x.vision_score for x in g), default=0) >= 60
            else None
        ),
    ),
)


async def player_games(
    session: AsyncSession, guild_id: int, discord_id: int
) -> list[PlayerGameStat]:
    """Tout l'historique d'un joueur, du plus ancien au plus récent."""
    rows = (
        (
            await session.execute(
                select(PlayerGameStat)
                .where(
                    PlayerGameStat.guild_id == guild_id,
                    PlayerGameStat.discord_id == discord_id,
                )
                .order_by(PlayerGameStat.played_at.asc(), PlayerGameStat.id.asc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


def trophies_for(games: list[PlayerGameStat]) -> list[Trophy]:
    """Les trophées gagnés, dans l'ordre de déclaration."""
    earned: list[Trophy] = []
    for rule in RULES:
        detail = rule.check(games)
        if detail:
            earned.append(
                Trophy(key=rule.key, label=rule.label, detail=detail, emoji=rule.emoji)
            )
    return earned


def missing_for(games: list[PlayerGameStat]) -> list[str]:
    """Les trophées pas encore gagnés, pour donner un objectif."""
    earned = {trophy.key for trophy in trophies_for(games)}
    return [rule.label for rule in RULES if rule.key not in earned]


@dataclass(frozen=True, slots=True)
class Records:
    """Les extrêmes d'un joueur, pour le profil."""

    games: int = 0
    most_kills: PlayerGameStat | None = None
    most_deaths: PlayerGameStat | None = None
    most_cs: PlayerGameStat | None = None
    best_score: PlayerGameStat | None = None
    longest: PlayerGameStat | None = None
    best_win_streak: int = 0
    worst_loss_streak: int = 0


def records_for(games: list[PlayerGameStat]) -> Records:
    if not games:
        return Records()
    return Records(
        games=len(games),
        most_kills=_peak(games, lambda g: g.kills),
        most_deaths=_peak(games, lambda g: g.deaths),
        most_cs=_peak(games, lambda g: g.cs),
        best_score=_peak(games, lambda g: g.score),
        longest=_peak(games, lambda g: g.duration_seconds),
        best_win_streak=_longest_streak(games, wins=True),
        worst_loss_streak=_longest_streak(games, wins=False),
    )
