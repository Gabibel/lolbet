"""Les GIF du récap, et rien d'autre.

Fichier de données, à éditer librement : colle ici les GIF que votre serveur
trouve drôles. Un GIF de Tenor se récupère en ouvrant sa page, clic droit sur
l'image → « Copier l'adresse de l'image » ; l'URL ressemble à
``https://media.tenor.com/<id>AAAAM/<nom>.gif``. Giphy et les liens directs
vers un ``.gif`` fonctionnent aussi.

Règles :

* garder au moins une entrée par situation, sinon rien ne sort pour elle ;
* une situation absente de ce dictionnaire n'envoie jamais de GIF — c'est
  voulu, un GIF à chaque partie deviendrait du bruit ;
* le registre est le même que pour les phrases : on chambre le jeu, pas la
  personne.

Ces adresses de départ ont été vérifiées le jour de leur ajout. Un GIF
supprimé de Tenor donne simplement une image cassée dans Discord : rien ne
plante, mais autant le remplacer.
"""

from __future__ import annotations

# Situation -> GIF possibles. La situation est décidée dans ``gifs.py`` à
# partir de la catégorie de vanne.
GIFS: dict[str, tuple[str, ...]] = {
    # Trois défaites d'affilée, ou plus.
    "losing_streak": (
        "https://media.tenor.com/-H-VoVjmdU0AAAAM/what-a-loser.gif",
        "https://media.tenor.com/GxgspcAiWKIAAAAM/loser-looser.gif",
        "https://media.tenor.com/rLOC2GKhPzMAAAAM/loser-meme.gif",
        "https://media.tenor.com/9Agk7KZa1OgAAAAM/looser.gif",
        "https://media.tenor.com/34ikQEKc1jcAAAAM/how-to-be-a-loser-loser.gif",
    ),
    # Dix morts ou plus, record de morts.
    "fed": (
        "https://media.tenor.com/8KSSKjA9XWoAAAAM/feeding-league-of-legends.gif",
        "https://media.tenor.com/IQdjl2NXCZAAAAAM/feeding-league-of-legends.gif",
        "https://media.tenor.com/5ncdWpPaydkAAAAM/lep-league-of-legends.gif",
        "https://media.tenor.com/xX0UOUIixaoAAAAM/feeding.gif",
        "https://media.tenor.com/Ozhqeu0hJHUAAAAM/lol-feed.gif",
    ),
    # Pire joueur des dix, dans une défaite.
    "worst": (
        "https://media.tenor.com/xrtr2bheUUYAAAAM/clown.gif",
        "https://media.tenor.com/A4YdvFbCqdkAAAAM/clown.gif",
        "https://media.tenor.com/a8o3CefNj2MAAAAM/clown-clowntoclown.gif",
        "https://media.tenor.com/endS0nWvzuUAAAAM/clown.gif",
    ),
    # Division perdue, ou grosse chute de LP.
    "demoted": (
        "https://media.tenor.com/M8SzMGsNIYAAAAAM/crying-sad.gif",
        "https://media.tenor.com/V2MJz1JD36UAAAAM/sad-cry.gif",
        "https://media.tenor.com/ckyZ0OkRYOYAAAAM/cry-sad.gif",
        "https://media.tenor.com/PeMjlAFDB48AAAAM/ar-crying.gif",
    ),
    # Gagné en ayant mal joué : porté.
    "lucky_win": (
        "https://media.tenor.com/cjKN3cedV5oAAAAM/lucky.gif",
        "https://media.tenor.com/Lcn0YGlLZKIAAAAM/lucky-lucky-you.gif",
        "https://media.tenor.com/7pBi8klOe24AAAAM/lucky.gif",
        "https://media.tenor.com/tOBZiVEsUQIAAAAM/luck.gif",
    ),
    # Trois victoires d'affilée, ou plus.
    "winning_streak": (
        "https://media.tenor.com/iw0EGZ15GkoAAAAM/you-cant-stop-me-unstoppable.gif",
        "https://media.tenor.com/MoVuE3LnACcAAAAM/unstoppable.gif",
        "https://media.tenor.com/dch-Umy47mUAAAAM/unstoppable.gif",
        "https://media.tenor.com/TOsSlxilktcAAAAM/unstoppable.gif",
    ),
}

# Ce que le bot cherche sur Tenor quand une clé est configurée, pour
# varier au-delà de la liste ci-dessus.
TENOR_QUERIES: dict[str, str] = {
    "losing_streak": "loser",
    "fed": "league of legends feeding",
    "worst": "clown",
    "demoted": "crying",
    "lucky_win": "lucky",
    "winning_streak": "unstoppable",
}

# La légende au-dessus du GIF, par situation. ``{mention}`` est remplacé.
CAPTIONS: dict[str, tuple[str, ...]] = {
    "losing_streak": (
        "{mention} la série continue.",
        "{mention} on a trouvé un GIF pour toi.",
        "{mention} ça fait beaucoup, là.",
    ),
    "fed": (
        "{mention} le respawn te salue.",
        "{mention} l'équipe adverse te remercie.",
    ),
    "worst": (
        "{mention} dernier des dix.",
        "{mention} c'est toi, oui.",
    ),
    "demoted": (
        "{mention} une division en moins.",
        "{mention} le classement a tranché.",
    ),
    "lucky_win": (
        "{mention} porté jusqu'à la ligne.",
        "{mention} remercie ton équipe.",
    ),
    "winning_streak": (
        "{mention} bon, là on ne peut rien dire.",
        "{mention} la série est réelle. Pour l'instant.",
    ),
}


def total_gifs() -> int:
    return sum(len(urls) for urls in GIFS.values())
