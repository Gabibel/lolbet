"""Le lot de phrases importé, et les garde-fous qui le rendent utilisable.

Le fichier source contenait 20 000 lignes, mais seulement 310 phrases : la
même phrase y revenait avec des nombres tirés au hasard. Ces nombres sont le
danger — « 241 CS » affiché à quelqu'un qui en a fait 48 est un mensonge que
personne ne remarquerait tout de suite. D'où les règles vérifiées ici :

* aucune phrase du lot commun ne cite un chiffre, donc aucune ne peut mentir ;
* le lot commun ne sort que sur des défaites, jamais pour féliciter ;
* il reste minoritaire, sinon les phrases qui citent la vraie statistique ne
  sortiraient plus jamais.
"""

from __future__ import annotations

import re

from lolbet.services.history import PlayerForm
from lolbet.services.taunt_lines import GENERIC_LOSS, TAUNTS
from lolbet.services.taunts import (
    GENERIC_SHARE,
    LOSS_POOL_CATEGORIES,
    _draw,
    taunt_for,
)

from test_taunt_situations import VETERAN, score

import random


# -- le lot commun ---------------------------------------------------------


def test_the_shared_pool_is_substantial():
    assert len(GENERIC_LOSS) >= 250


def test_no_shared_line_claims_a_number():
    """Une phrase sans chiffre ne peut pas se tromper de chiffre."""
    for line in GENERIC_LOSS:
        assert not re.search(r"\{", line), f"champ inattendu : {line!r}"
        assert not re.search(r"\d", line.replace("chapitre 1", "")), f"chiffre nu : {line!r}"


def test_no_shared_line_announces_a_victory():
    """Le lot ne sort que sur des défaites : il ne doit rien affirmer d'autre."""
    forbidden = re.compile(
        r"a envoyé le nexus adverse dans le monde des souvenirs"
        r"|\bbien joué\b|\bfélicitations\b|\bchapeau\b",
        re.I,
    )
    offenders = [line for line in GENERIC_LOSS if forbidden.search(line)]
    assert offenders == []


def test_no_template_residue_survived():
    """Les préfixes et suffixes du générateur ne portaient aucun sens."""
    residue = re.compile(
        r"^(Verdict|Breaking News|Après analyse|Annonce du Nexus|Rapport du bot"
        r"|Dernière minute|Communiqué officiel|La commission constate"
        r"|Le sacro-saint scoreboard confirme|Le scoreboard confirme)\s*:",
        re.I,
    )
    # Le remplissage se retrouve aussi bien en tête qu'en fin de phrase.
    filler = re.compile(r"Fin d[eu] rapport\.|Sans rancune\.|On note\.|GG\.")
    for line in GENERIC_LOSS:
        assert not residue.match(line), f"préfixe résiduel : {line!r}"
        assert not filler.search(line), f"remplissage résiduel : {line!r}"


def test_the_pool_has_no_duplicates():
    assert len(set(GENERIC_LOSS)) == len(GENERIC_LOSS)


# -- où il a le droit de sortir --------------------------------------------


def test_the_pool_never_reaches_a_category_that_praises():
    """Féliciter quelqu'un avec une insulte serait la pire des sorties."""
    praise = {
        "mvp_won",
        "mvp_lost",
        "good_won",
        "good_lost",
        "first_mvp",
        "record_kills",
        "streak_won",
        "stomp_won",
        "long_game_won",
        "deathless_won",
        "deathless_lost",
        "promoted",
        "lp_surge",
        "first_game",
    }
    assert praise & LOSS_POOL_CATEGORIES == set()


def test_every_pooled_category_exists():
    assert LOSS_POOL_CATEGORIES <= set(TAUNTS)


def test_a_praise_category_only_ever_draws_its_own_lines():
    rng = random.Random(0)
    own = set(TAUNTS["mvp_won"])
    for _ in range(200):
        assert _draw("mvp_won", rng) in own


def test_a_loss_category_draws_from_both_sources():
    rng = random.Random(0)
    drawn = {_draw("bad_lost", rng) for _ in range(400)}
    assert drawn & set(GENERIC_LOSS), "le lot commun ne sort jamais"
    assert drawn & set(TAUNTS["bad_lost"]), "les phrases spécifiques ne sortent plus"


def test_the_specific_lines_stay_the_majority():
    """C'est tout l'enjeu : la phrase qui cite la vraie statistique doit primer."""
    rng = random.Random(1)
    shared = set(GENERIC_LOSS)
    draws = [_draw("long_game_lost", rng) for _ in range(2000)]
    from_pool = sum(line in shared for line in draws)
    assert from_pool / len(draws) < 0.5
    assert abs(from_pool / len(draws) - GENERIC_SHARE) < 0.06


# -- rendu de bout en bout -------------------------------------------------


def test_imported_lines_render_with_real_numbers():
    """Les nombres inventés ont été remplacés par les champs réels."""
    line = taunt_for(
        score(win=False, kills=2, deaths=11, assists=3),
        is_mvp=False,
        is_worst=False,
        duration_seconds=1800,
        form=PlayerForm(games=20, wins=5, losses=15, worst_deaths=20),
        seed="rendu",
    )
    assert "{" not in line and "}" not in line


def test_no_line_anywhere_keeps_a_placeholder_unfilled():
    veteran = VETERAN
    for seed in range(120):
        for deaths, win, minutes in ((12, False, 30), (0, True, 25), (4, False, 50)):
            line = taunt_for(
                score(win=win, deaths=deaths),
                is_mvp=False,
                is_worst=False,
                duration_seconds=minutes * 60,
                form=veteran,
                seed=str(seed),
            )
            assert "{" not in line and "}" not in line
