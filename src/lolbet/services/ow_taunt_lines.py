"""Les phrases de changement de rang Overwatch, et rien d'autre.

Fichier jumeau de ``taunt_lines.py``, séparé pour une raison simple : les
vannes League parlent de LP et de KDA, Overwatch n'a ni l'un ni l'autre. Ici
on ne peut commenter qu'une chose, le rang, parce que c'est la seule chose
que le jeu publie.

Règles à respecter en éditant :

* garder au moins une phrase par catégorie, sinon le tirage échoue ;
* champs disponibles partout : ``{role}`` (Tank, DPS, Support, File libre),
  ``{rank}`` (le nouveau rang, ex. « Or 3 »), ``{previous}`` (l'ancien, vide
  sur un placement) et ``{steps}`` (déjà accordé : « 1 cran », « 3 crans »). Une
  accolade seule casse le formatage : écrire ``{{`` pour une accolade
  littérale ;
* le registre est celui du chat de fin de partie : ça tape fort, ça chambre
  sans retenue. Mais **uniquement sur le classement et le jeu**. Rien sur la
  personne, sa famille, son origine ou son intelligence, et rien qui touche à
  se faire du mal. Un serveur entre amis, pas un signalement.
"""

from __future__ import annotations

# =========================================================================
# CE QUI EST ARRIVÉ AU CLASSEMENT
# =========================================================================

# Division perdue. La catégorie la plus dure.
DEMOTED = (
    "Rétrogradé en {rank}. Une division entière, partie en fumée.",
    "{previous} c'était avant. Maintenant c'est {rank}, en {role}.",
    "Tu descends d'une division en {role}. On avait prévenu, tu as insisté.",
    "Division perdue. Tout est à refaire, et cette fois sans l'excuse du début de saison.",
    "{rank}. Tu as mis des semaines à monter et une soirée à tout rendre.",
    "Rétrogradation actée en {role}. Le classement ne fait pas de sentiment.",
    "Tu quittes {previous} par le bas. C'était mérité.",
    "{previous} vers {rank}. Le seul trajet que tu fais vite.",
    "Descente confirmée. On note la date, ça resservira.",
    "{rank} en {role} : le jeu a fini par se rendre compte de quelque chose.",
    "Une division en moins. Le chemin inverse va être long et tu le sais.",
    "Tu es retourné en {rank}. Comme si les mois d'avant n'avaient pas existé.",
    "Division perdue en {role}. Il fallait {steps}, tu les as trouvés.",
    "{rank}. À ce rythme, le bronze t'attend avec un café.",
    "Rétrogradé. Il te restait la fierté du rang. Plus maintenant.",
    "Tu as réussi à perdre une division sur le rôle que tu prétends maîtriser.",
)

# Division gagnée.
PROMOTED = (
    "Promu {rank} en {role}. Bien joué, sincèrement.",
    "{previous} vers {rank}. Ça, c'est du travail.",
    "Division gagnée. Profite, le palier suivant mord plus fort.",
    "{rank} en {role}. On note la date, c'est assez rare.",
    "Tu changes de division, par le haut cette fois.",
    "Montée confirmée en {rank}. Reste à la garder, c'est la partie difficile.",
    "Promotion actée. On t'attend au prochain cran.",
    "{steps} et une division entière. Grosse série.",
    "{rank}. C'est le moment de s'arrêter, statistiquement.",
    "Division supérieure débloquée. Ne gâche pas tout ce soir.",
    "Tu montes en {role}. Rare, donc noté.",
    "Promu. On applaudit, puis on attend la rechute.",
    "{previous} n'était pas ton niveau. {rank} non plus, mais on verra.",
    "Nouvelle division en {role}. Le lobby va être moins tendre.",
    "Tu passes {rank}. Personne n'y croyait, toi compris.",
    "Montée validée. Encadre la capture, ça ne durera pas.",
)

# Palier perdu à l'intérieur de la même division.
TIER_DOWN = (
    "{rank} en {role}. Un palier en moins, et ça ne s'arrête jamais là.",
    "Tu redescends d'un cran. Le début d'une longue soirée.",
    "{previous} vers {rank}. Doucement mais sûrement, vers le bas.",
    "Un palier perdu en {role}. Encore quelques-uns et on parlera de division.",
    "{rank}. Le classement corrige une erreur d'appréciation.",
    "Tu perds un cran. À force, ça finit par se voir.",
    "{previous} n'aura pas tenu longtemps.",
    "{steps} en moins en {role}. C'est peu, c'est régulier, c'est inquiétant.",
    "{rank} : la pente est douce, mais elle descend.",
    "Un palier en moins. Ce n'est pas la chute, c'est le glissement.",
    "Tu recules en {role}. Le rôle que tu joues « pour te détendre », sûrement.",
    "{rank}. Tu vas dire que c'était les coéquipiers.",
    "Cran perdu. La division suivante fait déjà des signes.",
    "{previous} vers {rank}. On appelle ça une tendance.",
)

# Palier gagné à l'intérieur de la même division.
TIER_UP = (
    "{rank} en {role}. Un cran de plus, on prend.",
    "{previous} vers {rank}. Ça avance.",
    "Un palier gagné en {role}. La division n'est plus si loin.",
    "{rank}. Continue comme ça et on aura une vraie annonce à faire.",
    "Tu gagnes un cran. Modeste, mais dans le bon sens.",
    "{steps} de plus. C'est déjà mieux que la semaine dernière.",
    "{rank} en {role} : la progression est lente, mais elle est réelle.",
    "Palier passé. Le suivant sera moins gentil.",
    "{previous} c'est fini, bienvenue en {rank}.",
    "Un cran. On ne va pas sortir le champagne, mais on note.",
    "{rank}. Le classement te rend enfin ce que tu lui prêtes.",
    "Tu montes d'un palier en {role}. Ne change rien.",
    "{previous} vers {rank}. Petit pas, bonne direction.",
    "Cran gagné. Reste à ne pas le rendre ce soir.",
)

# Premier rang relevé sur un rôle : placements terminés, ou nouveau rôle.
PLACED = (
    "Placements terminés en {role} : {rank}.",
    "{rank} en {role}. Voilà le point de départ, on regardera où ça va.",
    "Nouveau rôle suivi : {role}, {rank}. Le compteur est lancé.",
    "{role} en {rank}. On note, et on en reparle dans un mois.",
    "Premier relevé en {role} : {rank}. Tout le reste sera comparé à ça.",
    "{rank}. Ce n'est ni bien ni mal, c'est juste le début.",
    "{role} classé {rank}. Le suivi commence maintenant.",
    "Placé en {rank}. La suite dépend de toi, malheureusement.",
    "{role} : {rank}. Le bot a pris la photo, tu ne pourras plus dire le contraire.",
    "{rank} en {role}. C'est écrit quelque part maintenant.",
    "Nouveau rang suivi : {role}, {rank}. Bonne chance.",
    "{role} en {rank}. On verra bien dans quel sens ça bouge.",
)


# La clé est celle que renvoie ``RoleChange.category``.
OW_TAUNTS: dict[str, tuple[str, ...]] = {
    "promoted": PROMOTED,
    "demoted": DEMOTED,
    "tier_up": TIER_UP,
    "tier_down": TIER_DOWN,
    "placed": PLACED,
}


def total_ow_lines() -> int:
    return sum(len(lines) for lines in OW_TAUNTS.values())
