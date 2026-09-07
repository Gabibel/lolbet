"""Rangs Overwatch 2 : divisions, paliers, et l'échelle qui les compare.

Overwatch ne publie aucun point de compétence. Le profil public s'arrête à
une division (bronze → ultime) et un palier de 1 à 5, où **5 est le bas**.
Toute la progression que le bot peut suivre tient dans ces deux valeurs : il
n'y a pas de « +18 LP » à afficher ici, et en inventer un serait mentir.

Autre conséquence, qui n'est pas un bug du bot : Overwatch ne réévalue le rang
que toutes les 5 victoires ou 15 défaites. Le suivi avance donc par marches,
pas partie par partie.
"""

from __future__ import annotations

from dataclasses import dataclass

# Ordre exact de l'échelle, du bas vers le haut. Repris de l'enum
# CompetitiveDivision d'OverFast.
DIVISIONS: tuple[str, ...] = (
    "bronze",
    "silver",
    "gold",
    "platinum",
    "emerald",
    "diamond",
    "master",
    "grandmaster",
    "ultimate",
)

# Blizzard a renommé le sommet en cours de route. On accepte les deux noms
# pour qu'un vieux relevé reste comparable à un nouveau.
DIVISION_ALIASES: dict[str, str] = {"champion": "ultimate"}

# 5 paliers par division, et le palier 1 est le meilleur.
TIERS_PER_DIVISION = 5
BEST_TIER = 1
WORST_TIER = 5

ROLES: tuple[str, ...] = ("tank", "damage", "support", "open")

ROLE_LABELS_FR: dict[str, str] = {
    "tank": "Tank",
    "damage": "DPS",
    "support": "Support",
    "open": "File libre",
}

ROLE_EMOJI: dict[str, str] = {
    "tank": "\N{SHIELD}\N{VARIATION SELECTOR-16}",
    "damage": "\N{CROSSED SWORDS}\N{VARIATION SELECTOR-16}",
    "support": "\N{GREEN HEART}",
    "open": "\N{GAME DIE}",
}

DIVISION_LABELS_FR: dict[str, str] = {
    "bronze": "Bronze",
    "silver": "Argent",
    "gold": "Or",
    "platinum": "Platine",
    "emerald": "Émeraude",
    "diamond": "Diamant",
    "master": "Maître",
    "grandmaster": "Grand Maître",
    "ultimate": "Ultime",
}

DIVISION_EMOJI: dict[str, str] = {
    "bronze": "\N{LARGE BROWN CIRCLE}",
    "silver": "\N{MEDIUM WHITE CIRCLE}",
    "gold": "\N{LARGE YELLOW CIRCLE}",
    "platinum": "\N{LARGE BLUE CIRCLE}",
    "emerald": "\N{LARGE GREEN CIRCLE}",
    "diamond": "\N{LARGE PURPLE CIRCLE}",
    "master": "\N{LARGE ORANGE CIRCLE}",
    "grandmaster": "\N{LARGE RED CIRCLE}",
    "ultimate": "\N{MEDIUM BLACK CIRCLE}",
}

UNRANKED_LABEL = "Non classé"

PLATFORMS: tuple[str, ...] = ("pc", "console")


def normalise_division(value: str) -> str:
    division = (value or "").strip().lower()
    return DIVISION_ALIASES.get(division, division)


@dataclass(frozen=True, slots=True)
class OwRank:
    """Le rang d'un rôle : une division et un palier, rien de plus."""

    role: str
    division: str
    tier: int

    @property
    def known(self) -> bool:
        return self.division in DIVISIONS

    @property
    def score(self) -> int:
        """Position sur une échelle continue, pour comparer deux relevés.

        Zéro quand la division est inconnue : mieux vaut un écart nul qu'un
        écart faux si Blizzard ajoute un palier.
        """
        if not self.known:
            return 0
        return DIVISIONS.index(self.division) * TIERS_PER_DIVISION + (
            WORST_TIER - self._clamped_tier
        )

    @property
    def _clamped_tier(self) -> int:
        return max(BEST_TIER, min(WORST_TIER, self.tier))

    @property
    def role_label(self) -> str:
        return ROLE_LABELS_FR.get(self.role, self.role.title())

    @property
    def division_label(self) -> str:
        return DIVISION_LABELS_FR.get(self.division, self.division.title())

    @property
    def label(self) -> str:
        """``🟡 Or 3``. Le palier suit la division, comme en jeu."""
        emoji = DIVISION_EMOJI.get(self.division, "")
        return f"{emoji} {self.division_label} {self._clamped_tier}".strip()

    @property
    def display(self) -> str:
        """``⚔️ DPS — 🟡 Or 3``, pour une ligne de profil."""
        icon = ROLE_EMOJI.get(self.role, "")
        return f"{icon} {self.role_label} \N{EM DASH} {self.label}".strip()


def parse_rank(role: str, payload: dict | None) -> OwRank | None:
    """Un bloc de rôle du résumé OverFast → OwRank. None si non classé."""
    if not payload:
        return None
    division = normalise_division(str(payload.get("division") or ""))
    if not division:
        return None
    try:
        tier = int(payload.get("tier") or WORST_TIER)
    except (TypeError, ValueError):
        tier = WORST_TIER
    return OwRank(role=role, division=division, tier=tier)


def parse_summary(summary: dict, platform: str = "pc") -> dict[str, OwRank]:
    """Résumé OverFast → {rôle: rang} pour la plateforme demandée.

    Les rôles non joués ne sont pas dans le résultat : ils valent ``null``
    côté API, et un rôle non classé n'est pas un rang à zéro.
    """
    competitive = (summary or {}).get("competitive") or {}
    container = competitive.get(platform) or {}
    ranks: dict[str, OwRank] = {}
    for role in ROLES:
        rank = parse_rank(role, container.get(role))
        if rank is not None:
            ranks[role] = rank
    return ranks


def season_of(summary: dict, platform: str = "pc") -> int | None:
    competitive = (summary or {}).get("competitive") or {}
    container = competitive.get(platform) or {}
    season = container.get("season")
    return int(season) if isinstance(season, int) and season > 0 else None


def has_any_platform(summary: dict) -> bool:
    competitive = (summary or {}).get("competitive") or {}
    return any(competitive.get(platform) for platform in PLATFORMS)


def busiest_platform(summary: dict) -> str:
    """La plateforme où le joueur a un rang, PC en cas d'égalité."""
    for platform in PLATFORMS:
        if parse_summary(summary, platform):
            return platform
    return "pc"


def score_to_label(score: int) -> str:
    """Inverse de ``OwRank.score``, pour afficher une moyenne."""
    index = max(0, min(len(DIVISIONS) - 1, score // TIERS_PER_DIVISION))
    tier = WORST_TIER - (score % TIERS_PER_DIVISION)
    division = DIVISIONS[index]
    emoji = DIVISION_EMOJI.get(division, "")
    return f"{emoji} {DIVISION_LABELS_FR[division]} {tier}".strip()
