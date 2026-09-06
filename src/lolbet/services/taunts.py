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
from .scoring import PlayerScore
from .taunt_lines import JABS, LVP_LINES, MVP_LINES, TAUNTS, total_lines

__all__ = [
    "JABS",
    "LVP_LINES",
    "MVP_LINES",
    "TAUNTS",
    "build_taunt_content",
    "taunt_for",
    "total_lines",
]

# Seuils qui décident de la catégorie.
DEATHS_FED = 10
KILLS_RECORD = 15
KDA_BAD = 1.0
KDA_GREAT = 4.0
STREAK_THRESHOLD = 3
REPEAT_LVP_THRESHOLD = 2

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
) -> str:
    """La situation la plus spécifique qui décrit cette partie."""
    won = score.win
    minutes = duration_seconds / 60

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
    score: PlayerScore, duration_seconds: int, form: PlayerForm | None
) -> dict[str, object]:
    """Tout ce qu'une phrase peut vouloir insérer."""
    streak = 0
    if form is not None:
        streak = (form.winning_streak if score.win else form.losing_streak) + 1
    return {
        "deaths": score.deaths,
        "kills": score.kills,
        "assists": score.assists,
        "streak": streak,
        "minutes": int(duration_seconds / 60),
        "cs": score.cs,
        "cs_per_min": f"{score.cs_per_min:.1f}",
        "vision": score.vision_score,
        "damage": f"{score.damage:,}".replace(",", " "),
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
    )
    fields = _fields(score, duration_seconds, form)
    line = rng.choice(TAUNTS[category]).format(**fields)

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
        )
        lines.append(f"<@{discord_id}> {phrase}")

    if worst_puuid in tracked:
        lines.append(rng.choice(LVP_LINES).format(mention=f"<@{tracked[worst_puuid]}>"))
    if mvp_puuid in tracked:
        lines.append(rng.choice(MVP_LINES).format(mention=f"<@{tracked[mvp_puuid]}>"))

    return "\n".join(lines)[:2000]
