"""Toutes les phrases de fin de partie, et rien d'autre.

Ce fichier ne contient aucune logique : tu peux éditer, ajouter ou supprimer
des lignes librement sans rien casser. Le choix de la catégorie est fait dans
``taunts.py``, qui tire ensuite une phrase au hasard dans la liste.

Règles à respecter en éditant :

* garder au moins une phrase par catégorie, sinon le tirage échoue ;
* les champs entre accolades sont remplacés à l'exécution. Disponibles
  partout : ``{deaths}``, ``{kills}``, ``{assists}``, ``{streak}``,
  ``{minutes}``, ``{cs}``, ``{vision}``. Une accolade seule casse le
  formatage : écrire ``{{`` pour une accolade littérale ;
* on chambre la performance, jamais la personne. Seuls des joueurs inscrits
  volontairement sont visés.
"""

from __future__ import annotations

# =========================================================================
# CE QUI S'EST PASSÉ DANS LA PARTIE
# =========================================================================

# Pire joueur des dix, et défaite. La catégorie la plus dure.
WORST_LOST = (
    "Tu as feed et en plus tu as perdu, belle performance.",
    "Dernier des dix joueurs et défaite : le combo complet.",
    "Statistiquement, ton équipe aurait mieux fait en 4 contre 5.",
    "Pire joueur de la partie. De la partie entière. Bravo.",
    "À ce niveau ce n'est plus une défaite, c'est une contribution à l'ennemi.",
    "Il y avait dix joueurs sur cette carte et tu as trouvé le moyen d'être dixième.",
    "Tu as perdu, et tu étais le principal argument.",
    "L'équipe adverse te remercie pour ta collaboration.",
    "On cherche encore ce que tu as apporté.",
    "Défaite collective, responsabilité très individuelle.",
    "Il y a des parties qu'on oublie. Celle-là, on va te la rappeler.",
    "Tu étais présent. C'est le point le plus positif.",
    "Le tableau des scores est un document public, malheureusement pour toi.",
    "Même en cherchant bien, aucune circonstance atténuante.",
    "Tu as tenu le rôle du figurant, avec conviction.",
    "Ton équipe a joué à quatre, en réalité.",
    "Dernier, et pas de peu.",
    "Tu as trouvé le fond, puis tu as continué à creuser.",
    "Cette partie restera dans les archives, pour de mauvaises raisons.",
    "Il faudra mieux que « c'était le jungler » pour celle-là.",
    "Le classement va te présenter la facture.",
    "Personne ne t'en veut. Tout le monde a vu, c'est différent.",
)

# Pire joueur des dix, mais victoire quand même.
WORST_WON = (
    "Pire joueur de la partie mais tu gagnes quand même. Remercie tes coéquipiers.",
    "Porté. Littéralement porté du début à la fin.",
    "Victoire volée, et tout le monde a vu le tableau des scores.",
    "Tu as gagné. Le rapport de police dit autre chose.",
    "Quatre personnes ont travaillé pour toi ce soir.",
    "La victoire compte, ta performance moins.",
    "Tu es monté dans le train en marche et tu as réclamé le mérite.",
    "Dernier des dix, et pourtant du bon côté. La vie est injuste.",
    "Tes coéquipiers méritent une médaille, pas toi.",
    "Gagné malgré toi, et de très loin.",
    "Si tu avais joué en face, on aurait eu le même résultat.",
    "Passager. Confortablement installé, mais passager.",
    "Le LP est le même pour tout le monde, heureusement pour toi.",
    "On va appeler ça un travail d'équipe. Enfin, de quatre.",
    "Tu as été porté avec une telle constance que ça force le respect.",
    "Victoire acquise. Réputation, moins.",
    "Profite : la prochaine fois ils te laisseront peut-être marcher.",
    "Statistiquement, ta présence était neutre. Au mieux.",
    "Tu as gagné une partie que tu n'as pas jouée.",
    "L'histoire retiendra la victoire. Nous, on retiendra ton score.",
)

# Meilleur joueur des dix, avec la victoire.
MVP_WON = (
    "MVP et victoire. Rien à redire, pour une fois.",
    "Là tu as joué comme si le classement comptait. Continue.",
    "Carry assumé. Profite, ça ne durera pas.",
    "Grosse partie. On note la date.",
    "Meilleur des dix. On te laisse savourer, tu l'as mérité.",
    "Parfois tu joues vraiment bien, et c'est déstabilisant.",
    "Aucune vanne disponible. Reviens jouer mal.",
    "Tu as porté l'équipe et le résultat suit. C'est rare, c'est noté.",
    "Performance propre du début à la fin.",
    "Pour une fois, le scoreboard te fait de la publicité.",
    "MVP. Le mot est lâché, ne le prends pas trop à cœur.",
    "Tu as fait le travail, et bien mieux que d'habitude.",
    "Une partie comme celle-là et on oublierait presque les autres.",
    "Impeccable. C'est agaçant.",
    "Le genre de partie qu'on ressort en argument pendant six mois.",
    "Tu as tenu la baraque. Chapeau, sincèrement.",
    "Meilleur joueur, victoire, rien à ajouter.",
    "Il fallait bien que ça arrive un jour.",
    "Tu peux te taire pendant trois parties, tu as du crédit.",
    "Là, oui. Exactement ça.",
)

# Meilleur joueur des dix, mais défaite.
MVP_LOST = (
    "Meilleur joueur de la partie et tu perds quand même. Mes condoléances.",
    "Tu as fait ton travail, tes coéquipiers ont fait le reste.",
    "La solo queue résumée en une partie.",
    "Tu as porté, ils ont lâché. Classique.",
    "Meilleur des dix, du mauvais côté du score. Ça arrive trop souvent.",
    "Rien à te reprocher. Le reste de l'équipe, en revanche.",
    "Tu méritais mieux. Tu n'as pas eu mieux.",
    "Performance solide, résultat cruel.",
    "Le genre de défaite qui use plus qu'une autre.",
    "Tu as tout fait correctement et ça n'a servi à rien.",
    "Ce n'est pas ta faute. Pour une fois, vraiment pas.",
    "Meilleur joueur sur le terrain, et pourtant une défaite de plus.",
    "Il aurait fallu jouer les cinq rôles. Tu n'en as tenu qu'un.",
    "Ta partie était bonne. Le résultat, non.",
    "Les statistiques sont de ton côté, pas le score final.",
    "Tu peux te plaindre, cette fois tu en as le droit.",
    "MVP dans une défaite : le titre le plus amer du jeu.",
    "Tout ça pour ça.",
    "Tu as fait ta part, largement. Ça n'a pas suffi.",
    "Défaite injuste. Ça compte quand même dans le classement.",
)

# Dix morts ou plus, avec la défaite.
FED_LOST = (
    "{deaths} morts. On appelle ça un service public pour l'équipe adverse.",
    "{deaths} morts et une défaite. Tu as distribué plus d'or que la banque.",
    "{deaths} fois au sol. Le respawn te connaît par ton prénom.",
    "Avec {deaths} morts, tu as surtout joué le rôle de sbire.",
    "{deaths} morts : à ce stade c'est du bénévolat.",
    "Tu es mort {deaths} fois. L'équipe d'en face a fait ses courses.",
    "{deaths} morts, et l'écran de mort commençait à durer longtemps.",
    "{deaths} morts. Ils ont fini par ne plus te remercier.",
    "Le compteur affiche {deaths}. Ce n'est pas un score, c'est un aveu.",
    "{deaths} morts en une partie. Il y a des records dont on se passe.",
    "Tu as nourri tout le monde et tu es reparti les mains vides.",
    "{deaths} morts : tu as passé plus de temps mort que vivant.",
    "L'équipe adverse a bâti sa victoire sur tes {deaths} morts.",
    "{deaths} morts. La fontaine était ta position préférée.",
    "Tu as offert {deaths} primes. Personne ne t'a rien demandé.",
    "{deaths} morts, et la défaite en prime. Le pack complet.",
    "Ils n'ont pas eu besoin de farmer, tu étais là.",
    "{deaths} morts : le jeu propose pourtant de reculer.",
    "Avec {deaths} morts, la carte devait te sembler hostile.",
    "{deaths} morts. On va dire que tu testais quelque chose.",
    "Tu es mort {deaths} fois et tu as quand même trouvé le temps de perdre.",
    "{deaths} morts, c'est presque une performance artistique.",
)

# Dix morts ou plus, mais victoire.
FED_WON = (
    "{deaths} morts et tu gagnes quand même. L'univers est mal réglé.",
    "{deaths} morts. Victoire. Ne pose pas de questions, prends les LP.",
    "Tu es mort {deaths} fois et tu souris quand même. Admirable.",
    "{deaths} morts pour une victoire : tes coéquipiers sont des héros.",
    "Gagné avec {deaths} morts au compteur. Le jeu est cassé.",
    "{deaths} morts et le W au bout. La justice n'existe pas.",
    "Tu as tout donné à l'ennemi et ils ont perdu quand même.",
    "{deaths} morts. Quelqu'un a compensé, très fort.",
    "Victoire avec {deaths} morts : garde ce scoreboard pour toi.",
    "{deaths} morts, et pourtant le point vert. Étrange soirée.",
    "Tu as gagné. Avec {deaths} morts. On préfère ne pas creuser.",
    "{deaths} morts et une victoire : statistiquement, ça ne devrait pas exister.",
    "Ils ont gagné malgré tes {deaths} morts. Dis-leur merci.",
    "{deaths} morts, victoire quand même. Le hasard fait bien les choses.",
    "Le résultat est bon, le chemin beaucoup moins.",
    "{deaths} morts : tu as rendu la partie intéressante pour tout le monde.",
    "Victoire acquise malgré une générosité rare.",
    "{deaths} morts. Ton équipe a joué en handicap volontaire.",
    "Tu as gagné en jouant contre ton propre camp une partie du temps.",
    "{deaths} morts et un W. Encadre-le, ça n'arrivera pas deux fois.",
)

# KDA inférieur à 1, défaite. Le mauvais jour ordinaire.
BAD_LOST = (
    "Défaite. On va dire que c'était le jungler.",
    "Une de plus. Le classement ne se répare pas tout seul.",
    "Partie oubliable. Comme les trois précédentes.",
    "Ce n'était pas ta partie. Ni la précédente, d'ailleurs.",
    "Défaite méritée, et tu le sais.",
    "Rien n'a marché, et ça se voit sur la ligne de score.",
    "Une partie à ranger dans la catégorie « on n'en parle plus ».",
    "Tu as essayé. Enfin, on veut le croire.",
    "Le genre de partie qui ne mérite pas de commentaire. En voici un quand même.",
    "Défaite sans relief. Presque reposant.",
    "Ça n'a jamais vraiment démarré.",
    "Tu as fait de la figuration dans ta propre partie.",
    "Défaite. Le scoreboard n'aide pas ta défense.",
    "Il y avait mieux à faire de cette demi-heure.",
    "Rien de dramatique, rien de bon non plus.",
    "Une partie moyenne dans une défaite : le duo classique.",
    "Tu as perdu, et sans panache.",
    "L'équipe a coulé, tu as suivi le mouvement.",
    "Défaite banale. C'est peut-être le pire.",
    "Aucun moment marquant, sauf la défaite.",
    "On repassera pour le highlight.",
    "Partie terminée. On efface et on recommence.",
)

# KDA inférieur à 1, mais victoire.
BAD_WON = (
    "Tu as gagné malgré toi. Ça compte quand même.",
    "Victoire discrète. Très discrète. On t'a à peine vu.",
    "Gagné. Ton équipe a compensé, mais gagné.",
    "Le résultat est là, ta contribution beaucoup moins.",
    "Victoire en mode passager. C'est un mode valide.",
    "Tu as gagné sans vraiment participer. Le rêve.",
    "Ils ont porté, tu as encaissé les LP.",
    "Bonne nouvelle : ça compte pareil au classement.",
    "Victoire propre pour l'équipe, moins pour toi.",
    "Tu as gagné. On va s'arrêter là.",
    "Ton score dit une chose, le résultat en dit une autre. Garde le résultat.",
    "Une victoire est une victoire, même invisible.",
    "Tu as accompagné la victoire plus que tu ne l'as provoquée.",
    "Le W est là. Ne regarde pas le reste.",
    "Discret, efficace : enfin, surtout discret.",
    "Ton équipe a fait le travail, tu as fait acte de présence.",
    "Victoire. La prochaine fois, viens aider.",
    "Bien joué à eux.",
    "Tu as gagné et personne ne saura comment.",
    "Prends les LP et sors sans faire de bruit.",
)

# KDA d'au moins 4, mais défaite.
GOOD_LOST = (
    "Bonne partie, mauvais résultat. Ça arrive.",
    "Tu as tenu ta ligne, le reste a coulé.",
    "Rien à te reprocher cette fois. Profites-en, c'est rare.",
    "Belle partie dans une défaite. La spécialité de la maison.",
    "Tu as fait le job. Le score final ne le dit pas.",
    "Solide, mais seul.",
    "Ta ligne de score est bonne, ton équipe non.",
    "Défaite frustrante : celles-là marquent plus que les autres.",
    "Tu as joué correctement. Le résultat est ailleurs.",
    "Une bonne partie perdue, c'est le pire format.",
    "Tu peux dormir tranquille, ce n'était pas toi.",
    "Performance honnête, issue cruelle.",
    "Tu as tenu, ils ont lâché. Rien de neuf.",
    "Défaite, mais avec les honneurs.",
    "Bonne partie. Résultat pourri. On passe.",
    "Le genre de défaite qui ne devrait pas compter.",
    "Tu as bien joué, sincèrement. Ça n'a rien changé.",
    "Statistiquement irréprochable, collectivement perdu.",
    "La prochaine sera la bonne, avec un peu de chance.",
    "Rien à redire sur ta partie. Sur les autres, si.",
)

# KDA d'au moins 4, avec la victoire.
GOOD_WON = (
    "Victoire propre. Sobre, efficace, presque suspect.",
    "Gagné sans forcer. Encore trois cents comme ça et tu es Maître.",
    "Solide. On te laisse tranquille pour cette fois.",
    "Bien joué. Voilà, c'est dit, n'en parlons plus.",
    "Partie maîtrisée. Ça change.",
    "Tu as bien joué et tu as gagné. Le système fonctionne.",
    "Rien à signaler, et c'est un compliment.",
    "Efficace du début à la fin.",
    "Victoire sans bavure. Continue comme ça.",
    "Belle partie. On ne va pas se forcer à trouver une pique.",
    "Le genre de partie qu'on aimerait voir plus souvent.",
    "Propre. Rangé. Gagné.",
    "Tu as joué sérieusement, ça se voit.",
    "Bonne partie, bon résultat, bonne soirée.",
    "Tu as mérité celle-là.",
    "Aucun reproche. Savoure, la moyenne revient toujours.",
    "Performance sérieuse dans une victoire méritée.",
    "Voilà à quoi ça ressemble quand tu appliques.",
    "Tu as gagné en jouant bien. Radical, comme méthode.",
    "Excellent. Reviens jouer mal, on manque de matière.",
)

# =========================================================================
# CE QUE L'HISTORIQUE RACONTE
# =========================================================================

# Première partie enregistrée pour ce joueur.
FIRST_GAME = (
    "Première partie enregistrée. Le compteur démarre maintenant.",
    "Bienvenue. À partir de maintenant, tout est archivé.",
    "Première ligne à ton dossier. Il va falloir vivre avec.",
    "Baptême du feu. Tout ce qui suivra sera comparé à ça.",
    "Première partie suivie : la surveillance commence.",
    "Le dossier est ouvert. Il ne se refermera plus.",
    "Bienvenue dans les statistiques. Bon courage.",
    "Première apparition. Les suivantes seront jugées.",
    "On part de zéro. Techniquement, on ne peut que monter.",
    "Premier relevé. On verra dans cent parties ce que ça donne.",
    "Te voilà fiché. Amuse-toi bien.",
    "Première partie : personne ne peut encore rien te reprocher.",
    "Le compteur est lancé. Il ne s'arrête jamais.",
    "Bienvenue. Ici, tout finit dans un tableau.",
    "Première ligne. Espérons qu'elle ne soit pas représentative.",
)

# Nouveau record personnel de morts (au moins dix).
RECORD_DEATHS = (
    "Nouveau record personnel : {deaths} morts. On grave ça quelque part.",
    "{deaths} morts, ton pire total à ce jour. Félicitations, j'imagine.",
    "Jamais tu n'étais mort autant. Le plafond était plus haut que prévu.",
    "{deaths} morts : record battu. Certains sommets ne se cherchent pas.",
    "Tu viens d'établir ton record de morts. Il tiendra peut-être une semaine.",
    "{deaths} morts. Ton ancien record te semblait sans doute trop confortable.",
    "Record personnel pulvérisé, dans le mauvais sens.",
    "{deaths} morts : personne ne t'avait demandé de te dépasser là-dessus.",
    "Nouveau sommet. Enfin, nouveau gouffre.",
    "{deaths} morts. L'ancien record est officiellement obsolète.",
    "Tu as battu ton record. Ce n'est pas celui qu'on espérait.",
    "{deaths} morts en une partie : c'est ton maximum historique.",
    "Le livre des records vient d'être mis à jour. En rouge.",
    "{deaths} morts. Il fallait oser, tu as osé.",
    "Record battu. Tu peux arrêter de progresser dans cette direction.",
    "{deaths} morts : ta pire partie à ce jour, statistiquement parlant.",
    "Tu t'améliores. Dans une catégorie discutable.",
    "{deaths} morts. On archive, on encadre, on ressort ça régulièrement.",
    "Nouveau record. On aurait préféré un autre.",
    "{deaths} morts : plus haut que tout ce que tu avais fait avant.",
)

# Nouveau record personnel de kills (au moins quinze).
RECORD_KILLS = (
    "{kills} kills : nouveau record personnel. Note la date.",
    "Record battu avec {kills} éliminations. Ça arrive.",
    "{kills} kills, ton meilleur total. On ne te reconnaît plus.",
    "Nouveau record : {kills} kills. Quelqu'un a pris le contrôle du compte ?",
    "{kills} kills. Ton ancien record vient de prendre un coup de vieux.",
    "Record personnel explosé, et pour une bonne raison cette fois.",
    "{kills} éliminations : ton sommet à ce jour.",
    "Tu n'avais jamais fait autant. C'est noté, et c'est mérité.",
    "{kills} kills. Le genre de partie qu'on ressort en soirée.",
    "Record de kills battu. Profite, la moyenne t'attend au tournant.",
    "{kills} kills : personne ne t'arrêtait ce soir.",
    "Nouveau maximum. Pour une fois du bon côté du tableau.",
    "{kills} kills. Là, on applaudit.",
    "Ton meilleur total historique. Encadre le scoreboard.",
    "{kills} kills : record personnel, et pas qu'un peu.",
)

# Au moins trois défaites consécutives, celle-ci comprise.
STREAK_LOST = (
    "{streak} défaites d'affilée. Ce n'est plus une passe, c'est une trajectoire.",
    "{streak} de suite. Une pause, peut-être ?",
    "{streak}e défaite consécutive. Le classement, lui, s'en souvient.",
    "Toujours pas de victoire depuis {streak} parties. Courage.",
    "{streak} défaites de rang. À ce stade c'est une méthode.",
    "{streak} d'affilée : la série commence à être documentée.",
    "Encore une. Ça fait {streak}. Personne ne compte, sauf moi.",
    "{streak} défaites consécutives. Le jeu essaie de te dire quelque chose.",
    "Série en cours : {streak}. Elle n'a rien de flatteur.",
    "{streak} défaites de suite. Statistiquement, ça devient improbable.",
    "Tu enchaînes : {streak} sans victoire.",
    "{streak}e défaite d'affilée. Il reste toujours l'option de s'arrêter.",
    "{streak} de rang. La spirale a un nom, et c'est celui-là.",
    "Toujours rien après {streak} parties. On garde espoir.",
    "{streak} défaites consécutives : le LP part par paquets.",
    "Série noire à {streak}. On note pour la postérité.",
    "{streak} de suite. Change de champion, de rôle, de jour.",
    "{streak} défaites d'affilée : c'est presque un exploit inversé.",
    "Le compteur de la série affiche {streak}. Il ne descend pas.",
    "{streak} sans gagner. On commence à s'inquiéter pour toi.",
    "{streak}e consécutive. Le classement fait la moue.",
    "{streak} défaites de rang. Une victoire suffirait à tout effacer. Une.",
)

# Au moins trois victoires consécutives, celle-ci comprise.
STREAK_WON = (
    "{streak} victoires d'affilée. Profite, la moyenne finit toujours par revenir.",
    "{streak} de suite. Quelqu'un a changé de compte ?",
    "{streak}e victoire consécutive. On commence à te croire.",
    "{streak} d'affilée. Personne ne t'arrête, pour l'instant.",
    "Série en cours : {streak} victoires. Ne change rien.",
    "{streak} de suite : le classement remonte enfin.",
    "{streak} victoires consécutives. C'est presque suspect.",
    "Encore une. Ça fait {streak}. Impressionnant.",
    "{streak} d'affilée : tu tiens quelque chose.",
    "{streak}e victoire de rang. On attend la chute avec impatience.",
    "Série à {streak}. Continue tant que ça marche.",
    "{streak} victoires consécutives. Quelqu'un a lu un guide ?",
    "{streak} de suite : ce n'est plus de la chance.",
    "Belle série, {streak} d'affilée. Savoure.",
    "{streak} victoires enchaînées. Le LP adore.",
    "{streak}e de rang. Tu peux te permettre une mauvaise partie. Une.",
    "{streak} d'affilée : le genre de série qu'on raconte.",
    "Série de {streak}. Ne regarde pas en arrière.",
    "{streak} victoires consécutives. On te surveille, positivement.",
    "{streak} de suite. Le jeu te doit encore quelques défaites.",
)

# Premier titre de MVP pour ce joueur.
FIRST_MVP = (
    "Premier MVP de ta carrière suivie. Il fallait bien commencer.",
    "Premier titre de meilleur joueur. On avait fini par douter.",
    "Ton tout premier MVP. La date est archivée.",
    "Premier MVP enregistré. Le début d'une longue série, peut-être.",
    "Meilleur joueur pour la première fois. Savoure, c'est inédit.",
    "Premier MVP. Personne ne l'avait vu venir, toi non plus.",
    "Ton premier titre. On encadre le scoreboard.",
    "MVP pour la première fois : il y a un début à tout.",
    "Premier MVP au compteur. On note, on félicite, on passe.",
    "Jamais MVP jusqu'ici. C'est réglé.",
    "Ton premier. Il y en aura peut-être d'autres.",
    "Premier titre de meilleur joueur : bien joué, sincèrement.",
)

# Au moins deux LVP déjà au compteur, et encore un aujourd'hui.
REPEAT_LVP = (
    "Encore LVP. Ça commence à faire une habitude documentée.",
    "Pire joueur, encore. Le titre te va bien.",
    "Tu collectionnes les LVP comme d'autres les victoires.",
    "Nouveau LVP à ton palmarès. Il s'étoffe.",
    "Encore dernier. On finit par te réserver la place.",
    "LVP récidiviste. Le dossier s'épaissit.",
    "Ce n'est plus un accident, c'est une régularité.",
    "Encore le pire des dix. Tu vises la constance ?",
    "Un LVP de plus. La collection est presque complète.",
    "Tu reprends ta place habituelle en bas du tableau.",
    "LVP, encore. On ne va plus faire semblant d'être surpris.",
    "Nouvelle entrée dans ta série de LVP. Elle est longue.",
    "Encore toi. Statistiquement, ce n'est plus de la malchance.",
    "Le titre de pire joueur commence à te suivre partout.",
    "Encore LVP. Un jour on en fera une catégorie à ton nom.",
)

# =========================================================================
# LE CONTEXTE DE LA PARTIE
# =========================================================================

# Aucune mort, avec la victoire.
DEATHLESS_WON = (
    "Zéro mort et la victoire. Rien à dire, c'est parfait.",
    "Pas une seule mort. Tu as joué en spectateur invincible.",
    "Aucune mort : partie irréprochable.",
    "Zéro mort, victoire. On cherche la vanne, on ne trouve pas.",
    "Immaculé. Zéro mort, c'est rare.",
    "Tu n'es pas mort une seule fois. Impressionnant.",
    "Zéro dans la colonne des morts. On encadre.",
    "Partie parfaite. Aucune mort, aucun reproche.",
    "Tu as survécu à tout. Et tu as gagné.",
    "Zéro mort : tu as joué en mode prudence absolue, et ça a payé.",
    "Aucune mort de la partie. Le genre de ligne qu'on montre.",
    "Sans faute. Littéralement.",
    "Zéro mort. La fontaine ne t'a pas vu de la partie.",
    "Aucune mort, victoire au bout. Journée parfaite.",
    "Tu es resté debout tout du long. Respect.",
)

# Aucune mort, mais défaite.
DEATHLESS_LOST = (
    "Zéro mort et pourtant une défaite. Il fallait peut-être prendre des risques.",
    "Aucune mort, aucune influence non plus ?",
    "Tu n'es pas mort une fois, et tu as quand même perdu.",
    "Zéro mort. On se demande où tu étais.",
    "Survivre ne suffit pas toujours.",
    "Aucune mort, défaite quand même : la prudence a ses limites.",
    "Tu as très bien survécu à une partie que ton équipe perdait.",
    "Zéro mort. Ton équipe, elle, était sur le terrain.",
    "Impeccable défensivement, absent le reste du temps.",
    "Pas une mort, pas une victoire non plus.",
    "Tu as gardé ta ligne de score propre. Le score final, moins.",
    "Zéro mort dans une défaite : le paradoxe du jour.",
)

# Partie de moins de vingt minutes.
STOMP_WON = (
    "Fini en {minutes} minutes. Ça n'a pas traîné.",
    "{minutes} minutes. Ils ont rendu les armes vite.",
    "Victoire expresse en {minutes} minutes. Efficace.",
    "{minutes} minutes de partie : à peine le temps de s'installer.",
    "Écrasé en {minutes} minutes. On aime ce rythme.",
    "{minutes} minutes. Le nexus n'a pas tenu longtemps.",
    "Partie pliée en {minutes} minutes. Rentable.",
    "{minutes} minutes pour des LP : le meilleur ratio de la soirée.",
    "Victoire en {minutes} minutes. Même pas eu le temps de feed.",
    "{minutes} minutes chrono. Bien joué.",
    "Rapide et net. {minutes} minutes.",
    "{minutes} minutes : ils ont abandonné avant toi.",
)

STOMP_LOST = (
    "Écrasé en {minutes} minutes. Ça n'a jamais commencé.",
    "{minutes} minutes. Le temps de comprendre, c'était fini.",
    "Défaite en {minutes} minutes : au moins ça a été rapide.",
    "{minutes} minutes de souffrance. Le bon côté, c'est la brièveté.",
    "Balayé en {minutes} minutes. On passe à la suivante.",
    "{minutes} minutes : même pas le temps de sortir un objet.",
    "Défaite expresse. {minutes} minutes, et au suivant.",
    "{minutes} minutes. Le nexus est tombé avant ton premier objet.",
    "Écrasement en {minutes} minutes. Rien à analyser.",
    "{minutes} minutes de partie. On va appeler ça un échauffement.",
    "Rapide, indolore, humiliant. {minutes} minutes.",
    "{minutes} minutes : la défaite la plus efficace de ta soirée.",
    "Fini en {minutes} minutes. Au moins tu récupères ton temps.",
    "{minutes} minutes. Il n'y a même pas de leçon à en tirer.",
)

# Partie de plus de quarante minutes.
LONG_GAME_WON = (
    "{minutes} minutes de partie, et la victoire au bout. Mérité.",
    "Marathon de {minutes} minutes remporté. Solide.",
    "{minutes} minutes : vous ne lâchez rien, c'est bien.",
    "Victoire après {minutes} minutes. Va dormir.",
    "{minutes} minutes. Le genre de partie qui se gagne à l'usure.",
    "Interminable, mais gagnée. {minutes} minutes.",
    "{minutes} minutes de tension pour un W. Ça valait le coup.",
    "Vous avez fini par les avoir. {minutes} minutes.",
    "{minutes} minutes : la patience a payé.",
    "Longue partie, bonne fin. {minutes} minutes.",
    "{minutes} minutes debout. Le mental était là.",
    "Victoire au bout de {minutes} minutes. Personne n'a lâché.",
)

LONG_GAME_LOST = (
    "{minutes} minutes pour perdre. Le pire format qui existe.",
    "Perdu après {minutes} minutes. Ce temps ne reviendra pas.",
    "{minutes} minutes de partie et rien au bout. Cruel.",
    "Marathon de {minutes} minutes, défaite à l'arrivée.",
    "{minutes} minutes pour ça. On compatit, un peu.",
    "Longue, disputée, perdue. {minutes} minutes.",
    "{minutes} minutes : autant de temps pour un résultat négatif.",
    "Vous avez tenu {minutes} minutes avant de craquer.",
    "{minutes} minutes de partie. Le nexus a fini par tomber du mauvais côté.",
    "Défaite après {minutes} minutes. Va te coucher.",
    "{minutes} minutes et zéro LP. La soirée est réussie.",
    "Perdu au bout de {minutes} minutes : les pires défaites sont les plus longues.",
    "{minutes} minutes. Il aurait mieux valu abandonner à la dixième.",
    "Un match interminable pour une défaite. {minutes} minutes de moins à vivre.",
)


# =========================================================================
# PIQUES OPTIONNELLES
# Ajoutées après la phrase principale quand une statistique est mauvaise.
# Ne visent jamais un MVP.
# =========================================================================

JAB_VISION = (
    "Score de vision : {vision}. Tu joues les yeux fermés ?",
    "{vision} de vision. Les balises existent, elles sont même gratuites.",
    "Vision à {vision} : la carte devait être une surprise permanente.",
    "{vision} en vision. On appelle ça jouer au hasard.",
    "Score de vision {vision}. Le brouillard de guerre te remercie.",
    "{vision} de vision sur toute la partie. Impressionnant, dans un sens.",
)

JAB_CS = (
    "{cs_per_min} CS par minute. Les sbires se portent bien, merci.",
    "{cs_per_min} CS/min : la vague de sbires t'a survécu.",
    "Avec {cs_per_min} CS par minute, l'or devait venir d'ailleurs.",
    "{cs_per_min} CS/min. Le farm n'était pas ta priorité, visiblement.",
    "{cs_per_min} CS par minute : les sbires ennemis meurent de vieillesse.",
)

JAB_DAMAGE = (
    "{damage} de dégâts en {minutes} minutes. Tu étais là en spectateur ?",
    "{damage} de dégâts. Les adversaires n'ont rien senti.",
    "{damage} de dégâts sur {minutes} minutes : discret jusqu'au bout.",
    "Avec {damage} de dégâts, tu as surtout fait de la présence.",
    "{damage} de dégâts. Une tourelle en fait plus.",
)

# Regroupe les piques par nom de statistique, utilisé par taunts.py.
JABS: dict[str, tuple[str, ...]] = {
    "vision": JAB_VISION,
    "cs": JAB_CS,
    "damage": JAB_DAMAGE,
}


# =========================================================================
# LIGNES SPÉCIALES
# Postées en plus, sous les phrases individuelles.
# =========================================================================

LVP_LINES = (
    "\N{POLICE CAR} LVP de la partie : {mention} - direction la prison !",
    "\N{POLICE CAR} Pire joueur des dix : {mention}. Le titre est officiel.",
    "\N{POLICE CAR} {mention} remporte le trophée du pire joueur. Toutes nos félicitations.",
    "\N{POLICE CAR} LVP incontesté : {mention}.",
    "\N{POLICE CAR} La palme revient à {mention}, sans discussion possible.",
)

MVP_LINES = (
    "\N{GLOWING STAR} MVP de la partie : {mention} - savoure, c'est rare.",
    "\N{GLOWING STAR} Meilleur joueur des dix : {mention}.",
    "\N{GLOWING STAR} {mention} rafle le titre de MVP. Mérité.",
    "\N{GLOWING STAR} MVP : {mention}. Rien à redire.",
    "\N{GLOWING STAR} Meilleure performance de la partie : {mention}.",
)


# Table utilisée par taunts.py. Les clés sont des identifiants de code :
# tu peux modifier les phrases, mais pas renommer les clés.
TAUNTS: dict[str, tuple[str, ...]] = {
    "worst_lost": WORST_LOST,
    "worst_won": WORST_WON,
    "mvp_won": MVP_WON,
    "mvp_lost": MVP_LOST,
    "fed_lost": FED_LOST,
    "fed_won": FED_WON,
    "bad_lost": BAD_LOST,
    "bad_won": BAD_WON,
    "good_lost": GOOD_LOST,
    "good_won": GOOD_WON,
    "first_game": FIRST_GAME,
    "record_deaths": RECORD_DEATHS,
    "record_kills": RECORD_KILLS,
    "streak_lost": STREAK_LOST,
    "streak_won": STREAK_WON,
    "first_mvp": FIRST_MVP,
    "repeat_lvp": REPEAT_LVP,
    "deathless_won": DEATHLESS_WON,
    "deathless_lost": DEATHLESS_LOST,
    "stomp_won": STOMP_WON,
    "stomp_lost": STOMP_LOST,
    "long_game_won": LONG_GAME_WON,
    "long_game_lost": LONG_GAME_LOST,
}


def total_lines() -> int:
    """Nombre de phrases disponibles, piques et lignes spéciales comprises."""
    return (
        sum(len(lines) for lines in TAUNTS.values())
        + sum(len(lines) for lines in JABS.values())
        + len(LVP_LINES)
        + len(MVP_LINES)
    )
