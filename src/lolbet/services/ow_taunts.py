"""Choix de la phrase qui accompagne un changement de rang Overwatch.

Aucune logique de jugement ici : Overwatch ne publie ni KDA ni dégâts par
partie, donc la seule chose commentable est le mouvement du rang lui-même.
La catégorie vient de ``RoleChange.category``, ce module ne fait que tirer
une phrase et remplir les champs.
"""

from __future__ import annotations

import random

from .ow_taunt_lines import OW_TAUNTS, total_ow_lines
from .overwatch import RoleChange

__all__ = ["OW_TAUNTS", "ow_taunt_for", "total_ow_lines"]


def _steps(count: int) -> str:
    return f"{count} cran" if count <= 1 else f"{count} crans"


def _fields(change: RoleChange) -> dict[str, object]:
    """Tout ce qu'une phrase peut vouloir insérer."""
    return {
        "role": change.current.role_label,
        "rank": f"{change.current.division_label} {change.current.tier}",
        "previous": (
            f"{change.previous.division_label} {change.previous.tier}"
            if change.previous is not None
            else ""
        ),
        # Déjà accordé et toujours positif : le sens est porté par la
        # catégorie, et « -2 crans en moins » se lirait mal.
        "steps": _steps(abs(change.steps)),
    }


def ow_taunt_for(change: RoleChange, *, seed: str = "") -> str:
    """Une phrase pour ce mouvement de rang.

    ``seed`` rend le tirage reproductible : deux rendus du même changement
    donnent la même phrase, ce qui évite qu'un ré-affichage la fasse muter.
    """
    rng = random.Random(f"{seed}:{change.role}:{change.current.score}")
    lines = OW_TAUNTS.get(change.category) or OW_TAUNTS["placed"]
    return rng.choice(lines).format(**_fields(change))


def ow_taunt_content(changes: list[RoleChange], *, seed: str = "") -> str:
    """Une phrase par rôle qui a bougé, dans l'ordre reçu."""
    return "\n".join(ow_taunt_for(change, seed=seed) for change in changes)
