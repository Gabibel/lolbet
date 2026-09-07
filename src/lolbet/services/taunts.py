"""Choix de la vanne de fin de partie.

Ce fichier ne contient que la logique : les phrases sont dans
``taunt_lines.py``, qui est fait pour être édité librement.

Le principe est de toujours retenir la situation **la plus spécifique** qui
s'applique. Un joueur qui bat son record de morts pendant sa cinquième défaite
d'affilée mérite qu'on parle du record : c'est plus rare, donc plus drôle. Les
catégories génériques ne servent que quand rien de remarquable ne s'est passé.

Le tirage est déterministe (graine = identifiant de match + puuid) : un même
récapitulatif réaffiché donne toujours la même phrase.
"""

from __future__ import annotations

import random

from .history import PlayerForm
from .progression import RankChange
from .scoring import PlayerScore
from .taunt_lines import (
    GENERIC_LOSS,
    JABS,
    LVP_LINES,
    MVP_LINES,
    TAUNTS,
    total_lines,
)

__all__ = [
    "GENERIC_LOSS",
    "JABS",
    "LVP_LINES",
    "MVP_LINES",
    "TAUNTS",
    "build_taunt_content",
    "taunt_for",
    "total_lines",
]

# Situations de défaite où une moquerie générique est toujours vraie : le
# tirage y ajoute GENERIC_LOSS aux phrases spécifiques. Les catégories
# élogieuses en sont exclues, sinon une bonne partie serait félicitée par
# une insulte.
LOSS_POOL_CATEGORIES = frozenset(
    {
        "worst_lost",
        "fed_lost",
        "bad_lost",
        "streak_lost",
        "stomp_lost",
        "long_game_lost",
        "record_deaths",
        "repeat_lvp",
        "lp_crash",
        "demoted",
    }
)


# Part du tirage laissée au lot commun. Volontairement minoritaire : le lot
# compte 257 phrases contre une vingtaine par catégorie, donc un simple
# tirage uniforme le ferait sortir neuf fois sur dix et une partie de 52
# minutes ne parlerait presque jamais de sa durée. La phrase spécifique
# reste la règle, le lot commun apporte la variété.
GENERIC_SHARE = 0.35


def _draw(category: str, rng: random.Random) -> str:
    """Une phrase de la catégorie, ou du lot commun quand il est éligible."""
    if category in LOSS_POOL_CATEGORIES and rng.random() < GENERIC_SHARE:
        return rng.choice(GENERIC_LOSS)
    return rng.choice(TAUNTS[category])


# Seuils qui décident de la catégorie.
DEATHS_FED = 10
KILLS_RECORD = 15
KDA_BAD = 1.0
KDA_GREAT = 4.0
STREAK_THRESHOLD = 3
REPEAT_LVP_THRESHOLD = 2
# Un ecart de LP au-dela duquel la partie merite d'etre commentee.
LP_BIG_SWING = 25

# Une partie courte est écrasée, une longue est un marathon.
STOMP_MAX_MINUTES = 20
LONG_GAME_MIN_MINUTES = 40
# En dessous, un zéro mort ne veut rien dire (remake, partie avortée).
DEATHLESS_MIN_MINUTES = 15

# Seuils des piques statistiques.
LOW_VISION = 10
LOW_CS_PER_MIN = 3.0
LOW_DAMAGE_SHARE = 0.10
MIN_MINUTES_FOR_DETAIL = 20


def _category(
    score: PlayerScore,
    *,
    is_mvp: bool,
    is_worst: bool,
    form: PlayerForm | None = None,
    duration_seconds: int = 0,
    rank_change: RankChange | None = None,
) -> str:
    """La situation la plus spécifique qui décrit cette partie."""
    won = score.win
    minutes = duration_seconds / 60

    # Changer de division est plus rare que tout le reste : c'est ce
    # dont on parle, meme si le joueur a aussi battu un record.
    if rank_change is not None and rank_change.known:
        if rank_change.direction < 0:
            return "demoted"
        if rank_change.direction > 0:
            return "promoted"

    # -- ce que seul l'historique peut dire -------------------------------
    if form is not None:
        if form.is_new:
            return "first_game"
        # Un record ne vaut d'être cité que s'il est marquant dans l'absolu :
        # battre son record avec 3 morts n'intéresse personne.
        if score.deaths >= DEATHS_FED and score.deaths > form.worst_deaths:
            return "record_deaths"
        if score.kills >= KILLS_RECORD and score.kills > form.best_kills:
            return "record_kills"
        if is_worst and form.lvp_count >= REPEAT_LVP_THRESHOLD:
            return "repeat_lvp"
        if is_mvp and form.mvp_count == 0:
            return "first_mvp"

    # -- les titres de la partie ------------------------------------------
    if is_worst:
        return "worst_won" if won else "worst_lost"
    if is_mvp:
        return "mvp_won" if won else "mvp_lost"

    # -- les faits rares ---------------------------------------------------
    if score.deaths == 0 and minutes >= DEATHLESS_MIN_MINUTES:
        return "deathless_won" if won else "deathless_lost"

    # Une grosse variation de LP, sans changement de division.
    if rank_change is not None and rank_change.known:
        if abs(rank_change.delta) >= LP_BIG_SWING:
            return "lp_surge" if rank_change.delta > 0 else "lp_crash"

    if form is not None:
        streak = (form.winning_streak if won else form.losing_streak) + 1
        # Une série qui vient de se briser n'en est plus une.
        broke = (won and form.streak < 0) or (not won and form.streak > 0)
        if not broke and streak >= STREAK_THRESHOLD:
            return "streak_won" if won else "streak_lost"

    # -- le rythme de la partie -------------------------------------------
    if minutes and minutes < STOMP_MAX_MINUTES:
        return "stomp_won" if won else "stomp_lost"
    if minutes > LONG_GAME_MIN_MINUTES:
        return "long_game_won" if won else "long_game_lost"

    # -- rien de remarquable : on juge la performance ----------------------
    if score.deaths >= DEATHS_FED:
        return "fed_won" if won else "fed_lost"
    if score.kda_ratio < KDA_BAD:
        return "bad_won" if won else "bad_lost"
    if score.kda_ratio >= KDA_GREAT:
        return "good_won" if won else "good_lost"
    return "good_won" if won else "bad_lost"


def _fields(
    score: PlayerScore,
    duration_seconds: int,
    form: PlayerForm | None,
    rank_change: RankChange | None = None,
) -> dict[str, object]:
    """Tout ce qu'une phrase peut vouloir insérer."""
    streak = 0
    if form is not None:
        streak = (form.winning_streak if score.win else form.losing_streak) + 1
    return {
        # Le pseudo sans le tag : la mention Discord ouvre déjà la ligne,
        # ce champ ne sert qu'aux phrases qui citent le joueur au milieu.
        "player": score.riot_id.split("#")[0],
        "deaths": score.deaths,
        "kills": score.kills,
        "assists": score.assists,
        "streak": streak,
        "minutes": int(duration_seconds / 60),
        "cs": score.cs,
        "cs_per_min": f"{score.cs_per_min:.1f}",
        "vision": score.vision_score,
        "damage": f"{score.damage:,}".replace(",", " "),
        # Valeur absolue : la phrase porte deja le sens du gain ou
        # de la perte, un signe en plus donnerait « -19 LP perdus ».
        "lp": abs(rank_change.delta) if rank_change else 0,
    }


def _jab(
    score: PlayerScore,
    duration_seconds: int,
    rng: random.Random,
    fields: dict[str, object],
) -> str | None:
    """Pique optionnelle sur une statistique vraiment mauvaise."""
    if duration_seconds / 60 < MIN_MINUTES_FOR_DETAIL:
        return None

    candidates: list[str] = []
    if score.vision_score < LOW_VISION:
        candidates.extend(JABS["vision"])
    # Un support ne farme pas : lui reprocher ses CS n'a aucun sens.
    if score.position != "UTILITY" and score.cs_per_min < LOW_CS_PER_MIN:
        candidates.extend(JABS["cs"])
    if score.metrics.get("damage_share", 1.0) < LOW_DAMAGE_SHARE:
        candidates.extend(JABS["damage"])

    if not candidates:
        return None
    return rng.choice(candidates).format(**fields)


def taunt_for(
    score: PlayerScore,
    *,
    is_mvp: bool,
    is_worst: bool,
    duration_seconds: int,
    seed: str = "",
    form: PlayerForm | None = None,
    rank_change: RankChange | None = None,
) -> str:
    """Une phrase pour ce joueur, plus éventuellement une pique statistique.

    ``form`` est l'historique *avant* cette partie : il permet de parler de
    séries et de records, ce qu'une partie isolée ne dit pas.
    """
    rng = random.Random(f"{seed}:{score.puuid}")
    category = _category(
        score,
        is_mvp=is_mvp,
        is_worst=is_worst,
        form=form,
        duration_seconds=duration_seconds,
        rank_change=rank_change,
    )
    fields = _fields(score, duration_seconds, form, rank_change)
    line = _draw(category, rng).format(**fields)

    # On n'enfonce que ceux qui le méritent : jamais un MVP, jamais une
    # bonne partie.
    deserves_jab = is_worst or score.deaths >= DEATHS_FED or score.kda_ratio < KDA_BAD
    if not is_mvp and deserves_jab:
        extra = _jab(score, duration_seconds, rng, fields)
        if extra:
            line = f"{line} {extra}"
    return line


def build_taunt_content(
    scores,
    tracked: dict[str, int],
    *,
    seed: str = "",
    max_lines: int = 5,
    forms: dict[str, PlayerForm] | None = None,
    rank_changes: dict[str, RankChange] | None = None,
) -> str:
    """Le texte posté au-dessus du récapitulatif.

    ``tracked`` associe un puuid à un identifiant Discord. Une ligne par joueur
    suivi, puis la mise au pilori du LVP et l'éloge du MVP quand ce sont des
    joueurs suivis.
    """
    mvp_puuid = scores.mvp.puuid if scores.mvp else None
    worst_puuid = scores.worst.puuid if scores.worst else None
    rng = random.Random(seed)

    lines: list[str] = []
    for puuid, discord_id in list(tracked.items())[:max_lines]:
        score = scores.by_puuid(puuid)
        if score is None:
            continue
        phrase = taunt_for(
            score,
            is_mvp=puuid == mvp_puuid,
            is_worst=puuid == worst_puuid,
            duration_seconds=scores.duration_seconds,
            seed=seed,
            form=(forms or {}).get(puuid),
            rank_change=(rank_changes or {}).get(puuid),
        )
        lines.append(f"<@{discord_id}> {phrase}")

    if worst_puuid in tracked:
        lines.append(rng.choice(LVP_LINES).format(mention=f"<@{tracked[worst_puuid]}>"))
    if mvp_puuid in tracked:
        lines.append(rng.choice(MVP_LINES).format(mention=f"<@{tracked[mvp_puuid]}>"))

    return "\n".join(lines)[:2000]
