"""Petites vannes postées avec le récapitulatif de fin de partie.

Le ton est celui d'un serveur entre amis : on chambre, on n'insulte pas. Seuls
les joueurs qui se sont inscrits volontairement avec /inscription sont visés,
et uniquement sur leurs statistiques de la partie.

Le tirage est déterministe (graine = identifiant de match + puuid) : un même
récapitulatif réaffiché donne toujours la même phrase.
"""

from __future__ import annotations

import random

from .scoring import PlayerScore

# Seuils qui décident de la catégorie de vanne.
DEATHS_FED = 10
KDA_BAD = 1.0
KDA_GREAT = 4.0
LOW_VISION = 10
LOW_CS_PER_MIN = 3.0
MIN_MINUTES_FOR_DETAIL = 20

LVP_LINE = "\N{POLICE CAR} LVP de la partie : {mention} - direction la prison !"
MVP_LINE = "\N{GLOWING STAR} MVP de la partie : {mention} - savoure, c'est rare."

TAUNTS: dict[str, tuple[str, ...]] = {
    "worst_lost": (
        "Tu as feed et en plus tu as perdu, belle performance.",
        "Dernier des dix joueurs et défaite : le combo complet.",
        "Statistiquement, ton équipe aurait mieux fait en 4 contre 5.",
        "Pire joueur de la partie. De la partie entière. Bravo.",
        "À ce niveau ce n'est plus une défaite, c'est une contribution à l'ennemi.",
        "Il y avait dix joueurs sur cette carte et tu as trouvé le moyen d'être dixième.",
    ),
    "worst_won": (
        "Pire joueur de la partie mais tu gagnes quand même. Remercie tes coéquipiers.",
        "Porté. Littéralement porté du début à la fin.",
        "Victoire volée, et tout le monde a vu le tableau des scores.",
        "Tu as gagné. Le rapport de police dit autre chose.",
        "Quatre personnes ont travaillé pour toi ce soir.",
    ),
    "mvp_won": (
        "MVP et victoire. Rien à redire, pour une fois.",
        "Là tu as joué comme si le classement comptait. Continue.",
        "Carry assumé. Profite, ça ne durera pas.",
        "Grosse partie. On note la date.",
    ),
    "mvp_lost": (
        "Meilleur joueur de la partie et tu perds quand même. Mes condoléances.",
        "Tu as fait ton travail, tes coéquipiers ont fait le reste.",
        "La solo queue résumée en une partie.",
        "Tu as porté, ils ont lâché. Classique.",
    ),
    "fed_lost": (
        "{deaths} morts. On appelle ça un service public pour l'équipe adverse.",
        "{deaths} morts et une défaite. Tu as distribué plus d'or que la banque.",
        "{deaths} fois au sol. Le respawn te connaît par ton prénom.",
        "Avec {deaths} morts, tu as surtout joué le rôle de sbire.",
    ),
    "fed_won": (
        "{deaths} morts et tu gagnes quand même. L'univers est mal réglé.",
        "{deaths} morts. Victoire. Ne pose pas de questions, prends les LP.",
        "Tu es mort {deaths} fois et tu souris quand même. Admirable.",
    ),
    "bad_lost": (
        "Défaite. On va dire que c'était le jungler.",
        "Une de plus. Le classement ne se répare pas tout seul.",
        "Partie oubliable. Comme les trois précédentes.",
        "Ce n'était pas ta partie. Ni la précédente, d'ailleurs.",
        "Défaite méritée, et tu le sais.",
    ),
    "bad_won": (
        "Tu as gagné malgré toi. Ça compte quand même.",
        "Victoire discrète. Très discrète. On t'a à peine vu.",
        "Gagné. Ton équipe a compensé, mais gagné.",
    ),
    "good_lost": (
        "Bonne partie, mauvais résultat. Ça arrive.",
        "Tu as tenu ta ligne, le reste a coulé.",
        "Rien à te reprocher cette fois. Profites-en, c'est rare.",
    ),
    "good_won": (
        "Victoire propre. Sobre, efficace, presque suspect.",
        "Gagné sans forcer. Encore trois cents comme ça et tu es Maître.",
        "Solide. On te laisse tranquille pour cette fois.",
        "Bien joué. Voilà, c'est dit, n'en parlons plus.",
    ),
}

DETAIL_JABS: tuple[tuple[str, str], ...] = (
    ("vision", "Score de vision : {vision}. Tu joues les yeux fermés ?"),
    ("cs", "{cs_per_min} CS par minute. Les sbires se portent bien, merci."),
    ("damage", "{damage} de dégâts en {minutes} minutes. Tu étais là en spectateur ?"),
)


def _category(score: PlayerScore, *, is_mvp: bool, is_worst: bool) -> str:
    won = score.win
    if is_worst:
        return "worst_won" if won else "worst_lost"
    if is_mvp:
        return "mvp_won" if won else "mvp_lost"
    if score.deaths >= DEATHS_FED:
        return "fed_won" if won else "fed_lost"
    if score.kda_ratio < KDA_BAD:
        return "bad_won" if won else "bad_lost"
    if score.kda_ratio >= KDA_GREAT:
        return "good_won" if won else "good_lost"
    return "good_won" if won else "bad_lost"


def _detail_jab(score: PlayerScore, duration_seconds: int, rng: random.Random) -> str | None:
    """Pique optionnelle sur une statistique vraiment mauvaise."""
    minutes = duration_seconds / 60
    if minutes < MIN_MINUTES_FOR_DETAIL:
        return None

    candidates: list[str] = []
    if score.vision_score < LOW_VISION:
        candidates.append(DETAIL_JABS[0][1].format(vision=score.vision_score))
    # Un support ne farme pas : lui reprocher ses CS n'a aucun sens.
    if score.position != "UTILITY" and score.cs_per_min < LOW_CS_PER_MIN:
        candidates.append(DETAIL_JABS[1][1].format(cs_per_min=f"{score.cs_per_min:.1f}"))
    if score.metrics.get("damage_share", 1.0) < 0.10:
        candidates.append(
            DETAIL_JABS[2][1].format(damage=f"{score.damage:,}".replace(",", " "),
                                     minutes=int(minutes))
        )
    return rng.choice(candidates) if candidates else None


def taunt_for(
    score: PlayerScore,
    *,
    is_mvp: bool,
    is_worst: bool,
    duration_seconds: int,
    seed: str = "",
) -> str:
    """Une phrase pour ce joueur, plus éventuellement une pique statistique."""
    rng = random.Random(f"{seed}:{score.puuid}")
    line = rng.choice(TAUNTS[_category(score, is_mvp=is_mvp, is_worst=is_worst)])
    line = line.format(deaths=score.deaths)

    # On n'enfonce que ceux qui le méritent : jamais un MVP.
    if not is_mvp and (score.deaths >= DEATHS_FED or score.kda_ratio < KDA_BAD or is_worst):
        extra = _detail_jab(score, duration_seconds, rng)
        if extra:
            line = f"{line} {extra}"
    return line


def build_taunt_content(
    scores,
    tracked: dict[str, int],
    *,
    seed: str = "",
    max_lines: int = 5,
) -> str:
    """Le texte posté au-dessus du récapitulatif.

    ``tracked`` associe un puuid à un identifiant Discord. Une ligne par joueur
    suivi, puis la mise au pilori du LVP et l'éloge du MVP quand ce sont des
    joueurs suivis.
    """
    mvp_puuid = scores.mvp.puuid if scores.mvp else None
    worst_puuid = scores.worst.puuid if scores.worst else None

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
        )
        lines.append(f"<@{discord_id}> {phrase}")

    if worst_puuid in tracked:
        lines.append(LVP_LINE.format(mention=f"<@{tracked[worst_puuid]}>"))
    if mvp_puuid in tracked:
        lines.append(MVP_LINE.format(mention=f"<@{tracked[mvp_puuid]}>"))

    return "\n".join(lines)[:2000]
