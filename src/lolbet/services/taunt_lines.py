"""Toutes les phrases de fin de partie, et rien d'autre.

Ce fichier ne contient aucune logique : tu peux éditer, ajouter ou supprimer
des lignes librement sans rien casser. Le choix de la catégorie est fait dans
``taunts.py``, qui tire ensuite une phrase au hasard dans la liste.

Règles à respecter en éditant :

* garder au moins une phrase par catégorie, sinon le tirage échoue ;
* les champs entre accolades sont remplacés à l'exécution. Disponibles
  partout : ``{deaths}``, ``{kills}``, ``{assists}``, ``{streak}``,
  ``{minutes}``, ``{cs}``, ``{vision}``, ``{lp}``, ``{player}``. Une accolade seule casse le
  formatage : écrire ``{{`` pour une accolade littérale ;
* le registre est celui du chat de fin de partie : ça tape fort, ça chambre
  sans retenue. Mais **uniquement sur la performance**. Rien sur la personne,
  sa famille, son origine ou son intelligence, et rien qui touche à se faire
  du mal. Un serveur entre amis, pas un signalement.
"""

from __future__ import annotations

# =========================================================================
# CE QUI S'EST PASSÉ DANS LA PARTIE
# =========================================================================

# Pire joueur des dix, et défaite. La catégorie la plus dure.
WORST_LOST = (
    "Pire joueur de la partie et défaite. Désinstalle.",
    "Tu as int, tu as perdu, et tu vas relancer dans trente secondes.",
    "Dernier des dix. Même l'équipe d'en face a eu pitié.",
    "Ton équipe a joué en 4 contre 6 et tu étais dans les six.",
    "Cette partie était perdue au champ select. La tienne.",
    "Griefing involontaire, mais griefing quand même.",
    "Dix joueurs, tu es dixième. Ce n'est pas de la malchance, c'est un niveau.",
    "Tu as coûté la partie à quatre personnes qui ne t'avaient rien demandé.",
    "Retourne en normal. Sérieusement.",
    "Le seul truc que tu as carry, c'est la défaite.",
    "Tu es la raison pour laquelle le bouton mute existe.",
    "Statistiquement, tu as joué contre ton équipe.",
    "Personne n'a « diff ». Toi, si.",
    "Ton équipe a perdu à cause de toi et ils le savent tous.",
    "Ce n'est pas une partie, c'est une pièce à conviction.",
    "Tu as offert la partie, et même pas rapidement.",
    "Il faut du talent pour être aussi mauvais avec autant d'assurance.",
    "Ils ont gagné sans jouer. Tu t'en es chargé.",
    "Le pire des dix, dans une défaite. Le combo qu'on ne raconte pas.",
    "Ta partie tient sur une ligne, et elle est toute rouge.",
    "Tu as trouvé le fond, tu as creusé, puis tu as demandé une pelle.",
    "Quatre personnes ont perdu des LP à cause d'une seule. Devine laquelle.",
)

# Pire joueur des dix, mais victoire quand même.
WORST_WON = (
    "Pire joueur des dix mais tu gagnes. Va remercier tes coéquipiers.",
    "Porté. Pas aidé, pas accompagné. Porté.",
    "Tu as gagné une partie où tu étais un handicap.",
    "Quatre personnes ont bossé, une était en visite.",
    "Victoire volée. Tout le monde a vu le tableau des scores.",
    "T'inquiète, les LP comptent pareil pour les passagers.",
    "Ils ont gagné 4 contre 5. Félicitations à eux.",
    "Le carry, ce n'était pas toi. Ce n'est même pas discutable.",
    "Tu étais l'adversaire le plus utile de l'équipe d'en face.",
    "Gagné. Maintenant efface la capture d'écran.",
    "Si tu avais joué en face, ils gagnaient quand même.",
    "Ton équipe a compensé. Beaucoup. Énormément.",
    "Tu as pris des LP que tu n'as pas mérités. Tu les reperdras seul.",
    "Le scoreboard dit défaite, le résultat dit victoire. Crois le scoreboard.",
    "Grosse performance collective. Enfin, à quatre.",
    "Tu as gagné sans participer. Certains appellent ça un talent.",
    "Victoire. Ne dis rien, prends les LP et sors.",
    "Il a fallu que quatre personnes soient excellentes pour compenser une.",
    "Bravo à ton équipe. Vraiment, à ton équipe.",
    "Passager clandestin sur un compte que tu ne mérites pas.",
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
    "MVP dans une défaite. Le titre le plus inutile du jeu.",
    "Tu as porté, ils ont lâché. Solo queue, quoi.",
    "Meilleur des dix et tu perds. Apprends à jouer les cinq rôles.",
    "Rien à te reprocher. Le reste de l'équipe, tout.",
    "Tu méritais mieux. Le classement s'en moque.",
    "Tu as fait ta part. Ils ont fait la leur, dans l'autre sens.",
    "Grosse partie, zéro LP. Bienvenue en solo queue.",
    "Quatre boulets et toi. Ça ne suffit jamais.",
    "Tu peux flamer, cette fois tu en as le droit.",
    "Le seul à avoir joué, et le seul à perdre des LP. Logique.",
    "Ta partie était excellente. Le reste était une catastrophe.",
    "Ils t'ont volé une victoire. Ça arrive une fois sur deux, apparemment.",
    "Statistiquement irréprochable, collectivement massacré.",
    "Le genre de défaite qui fait désinstaller. Ne le fais pas.",
    "Tu as tout fait. Ça n'a servi à rien. C'est le jeu.",
    "MVP, défaite, et personne pour s'excuser. Classique.",
    "Tout ça pour ça.",
    "Tu as porté quatre valises et elles t'ont lâché à l'arrivée.",
    "Aucune faute de ta part. Que des leurs.",
    "Tu vas te coucher énervé, et c'est mérité.",
)

# Dix morts ou plus, avec la défaite.
FED_LOST = (
    "{deaths} morts. Ce n'est plus feed, c'est du sponsoring.",
    "{deaths} morts et une défaite. Tu as financé leur build entier.",
    "{deaths} morts : l'équipe d'en face t'a envoyé une carte de remerciement.",
    "Tu es mort {deaths} fois. Ils n'ont pas eu besoin de farmer.",
    "{deaths} morts. À un moment, il faut arrêter de sortir de la base.",
    "{deaths} morts : tu es un objectif, pas un joueur.",
    "Le compteur affiche {deaths}. Ce n'est pas un score, c'est un aveu.",
    "{deaths} morts. Tu as passé plus de temps mort que vivant.",
    "{deaths} fois au sol. Le respawn t'appelle par ton prénom.",
    "{deaths} morts et une défaite. Les deux à la fois, bravo.",
    "Tu as int {deaths} fois. Ce n'est plus une erreur, c'est une méthode.",
    "{deaths} morts : ils ont fini par se disputer tes primes.",
    "{deaths} morts. La fontaine était ta position principale.",
    "Avec {deaths} morts, tu as joué le rôle de sbire de luxe.",
    "{deaths} morts. Ton équipe aurait dû te ban au champ select.",
    "{deaths} morts, une défaite, zéro remise en question. Le triplé.",
    "Tu as donné {deaths} kills. On appelle ça de la générosité pathologique.",
    "{deaths} morts. Le jeu propose pourtant une touche pour reculer.",
    "{deaths} morts : du griefing avec les meilleures intentions.",
    "Ils ont gagné grâce à toi. Littéralement.",
    "{deaths} morts. Ton écran de mort connaît mieux la carte que toi.",
    "{deaths} morts, et tu vas relancer. Le vrai courage.",
)

# Dix morts ou plus, mais victoire.
FED_WON = (
    "{deaths} morts et tu gagnes. Le matchmaking est cassé, c'est confirmé.",
    "{deaths} morts. Victoire. Ferme le scoreboard et ne le rouvre jamais.",
    "Tu es mort {deaths} fois et tu oses sourire.",
    "{deaths} morts pour une victoire : tes coéquipiers méritent un salaire.",
    "Gagné avec {deaths} morts. Quelqu'un a joué à ta place.",
    "{deaths} morts et le W au bout. La justice n'existe pas.",
    "Tu as tout donné à l'ennemi et ils ont perdu quand même.",
    "{deaths} morts. Quatre personnes ont réparé tes dégâts en direct.",
    "Victoire avec {deaths} morts : garde ça pour toi.",
    "{deaths} morts, point vert. Le jeu est mal codé.",
    "Tu as gagné. Avec {deaths} morts. On préfère ne pas creuser.",
    "{deaths} morts et une victoire : ça ne devrait pas exister.",
    "Ils ont gagné malgré toi. Dis-leur merci, en privé.",
    "{deaths} morts. Ton équipe a joué en handicap volontaire et a gagné.",
    "Le résultat est bon, le chemin était une catastrophe.",
    "{deaths} morts : palpitant pour tout le monde sauf pour toi.",
    "Tu as gagné en jouant contre ton camp la moitié du temps.",
    "{deaths} morts et un W. Encadre-le, ça n'arrivera plus.",
    "Tu es mort {deaths} fois et tu vas quand même parler dans le vocal.",
    "Victoire acquise malgré une générosité rare envers l'adversaire.",
)

# KDA inférieur à 1, défaite. Le mauvais jour ordinaire.
BAD_LOST = (
    "Défaite. Et cette fois tu ne peux pas accuser le jungler.",
    "Une de plus. Le classement descend tout seul, tu n'aides pas.",
    "Partie oubliable, comme les cinq précédentes.",
    "Tu as fait de la figuration dans ta propre partie.",
    "Ce n'était pas ta partie. Ni la précédente. Ni celle d'avant.",
    "Défaite méritée, et tu le sais très bien.",
    "Rien n'a marché, et ça se voit sur chaque ligne.",
    "Tu as essayé. Enfin, on veut le croire.",
    "Le genre de partie qu'on ne raconte à personne.",
    "Défaite sans relief. Même pas de quoi rager correctement.",
    "Ça n'a jamais démarré. Toi non plus.",
    "Tu as perdu, et sans style.",
    "L'équipe a coulé et tu tenais l'ancre.",
    "Il y avait mieux à faire de ta soirée.",
    "Aucun moment marquant, sauf la défaite.",
    "Une partie moyenne dans une défaite : le combo le plus fade du jeu.",
    "Tu as joué comme si tu regardais autre chose. C'était le cas ?",
    "Le scoreboard ne ment pas et ne fait pas de cadeau.",
    "Défaite banale. C'est peut-être ça, le pire.",
    "On repassera pour le highlight.",
    "Partie terminée, LP partis, leçon non retenue.",
    "Tu vas relancer direct, hein. C'est ça, le problème.",
)

# KDA inférieur à 1, mais victoire.
BAD_WON = (
    "Tu as gagné malgré toi. Ça compte quand même, malheureusement.",
    "Victoire tellement discrète qu'on a vérifié que tu étais là.",
    "Gagné. Ton équipe a compensé, comme d'habitude.",
    "Le résultat est là, ta contribution beaucoup moins.",
    "Passager confirmé. Bon voyage.",
    "Tu as gagné sans jouer. C'est un talent, dans un sens.",
    "Ils ont porté, tu as encaissé.",
    "Bonne nouvelle : les LP ne regardent pas ton KDA.",
    "Victoire propre pour l'équipe, sale pour toi.",
    "Tu as gagné. On s'arrête là, par charité.",
    "Ton score dit une chose, le résultat une autre. Garde le résultat.",
    "Une victoire reste une victoire, même subie.",
    "Tu as accompagné la victoire plus que tu ne l'as provoquée.",
    "Le W est là. Ne regarde surtout pas le reste.",
    "Discret, effacé, absent. Mais gagnant.",
    "Ton équipe a fait le boulot, tu as fait acte de présence.",
    "Victoire. La prochaine fois, viens aider.",
    "Bien joué à eux.",
    "Tu as gagné et personne ne saura expliquer comment.",
    "Prends les LP et sors sans faire de bruit.",
)

# KDA d'au moins 4, mais défaite.
GOOD_LOST = (
    "Bonne partie, équipe pourrie. Le grand classique.",
    "Tu as tenu ta ligne, le reste a fondu.",
    "Rien à te reprocher. Profite, c'est rare.",
    "Belle partie dans une défaite. La spécialité de la maison.",
    "Tu as fait le boulot, le score final ne le dira jamais.",
    "Solide, et complètement seul.",
    "Ta ligne est propre, ton équipe non.",
    "Défaite frustrante. Celles-là restent en travers.",
    "Tu as joué correctement. Eux ont joué.",
    "Une bonne partie perdue : le pire format qui existe.",
    "Tu peux dormir tranquille, ce n'était pas toi.",
    "Performance honnête, issue dégueulasse.",
    "Tu as tenu, ils ont lâché. Rien de neuf.",
    "Défaite avec les honneurs. Ça ne rend pas les LP.",
    "Bonne partie. Résultat nul. On passe.",
    "Le genre de défaite qui ne devrait pas compter.",
    "Tu as bien joué. Sincèrement. Ça n'a rien changé.",
    "Statistiquement irréprochable, collectivement perdu.",
    "La prochaine sera la bonne. Statistiquement, un jour.",
    "Rien à redire sur ta partie. Sur les leurs, tout.",
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
    "Première partie enregistrée. Tout est archivé à partir de maintenant.",
    "Te voilà fiché. Chaque mort sera comptée.",
    "Première ligne au dossier. Il va s'épaissir, on le sent.",
    "Bienvenue. Ici on ne pardonne rien et on n'oublie rien.",
    "Premier relevé. On va voir combien de temps tu tiens.",
    "Le compteur est lancé. Il ne s'arrête jamais.",
    "Première apparition. Les suivantes seront jugées, et durement.",
    "Tu es sous surveillance. Joue en conséquence.",
    "Personne ne peut encore rien te reprocher. Ça viendra.",
    "Bienvenue dans les statistiques. Elles ne mentent pas, elles.",
    "Dossier ouvert. Il ne se refermera plus.",
    "On démarre à zéro. Techniquement, tu ne peux que décevoir.",
    "Ta première trace. Espérons qu'elle ne soit pas représentative.",
    "Première partie. Le jury se met en place.",
    "C'est parti. À partir de maintenant, tout se paie.",
)

# Nouveau record personnel de morts (au moins dix).
RECORD_DEATHS = (
    "Record personnel : {deaths} morts. Il fallait le faire, tu l'as fait.",
    "{deaths} morts, ton pire total. Tu progresses, dans le mauvais sens.",
    "Jamais tu n'étais mort autant. On croyait le fond atteint, tu as innové.",
    "{deaths} morts : record battu. Certains sommets ne se cherchent pas.",
    "Nouveau record de morts. Une progression constante vers le bas.",
    "{deaths} morts. Ton ancien record te semblait trop confortable ?",
    "Record pulvérisé, catégorie distributeur automatique.",
    "{deaths} morts : personne ne t'avait demandé de te dépasser là-dessus.",
    "Nouveau sommet. Enfin, nouveau gouffre.",
    "{deaths} morts. L'ancien record paraît ridicule à côté.",
    "Tu as battu ton record. Ce n'est pas celui qu'on espérait.",
    "{deaths} morts : ton maximum historique. Bravo, j'imagine.",
    "Le livre des records vient d'être mis à jour, en rouge.",
    "{deaths} morts. Il fallait oser. Tu as osé.",
    "Record battu. Tu peux arrêter de progresser dans cette direction.",
    "{deaths} morts : ta pire partie à vie, et la nuit est jeune.",
    "Tu repousses tes limites. Vers le bas, mais tu les repousses.",
    "{deaths} morts. On archive, et on ressort ça à chaque vocal.",
    "Nouveau record. On aurait préféré un autre. Vraiment.",
    "{deaths} morts : au-dessus de tout ce que tu avais fait avant.",
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
    "{streak} défaites d'affilée. Éteins. Le. PC.",
    "{streak} de suite. Ce n'est plus une passe, c'est ton niveau.",
    "{streak}e défaite consécutive. Le classement te remet à ta place.",
    "Toujours pas de victoire depuis {streak} parties. Tu insistes pourquoi ?",
    "{streak} défaites de rang. À ce stade, c'est une méthode.",
    "{streak} d'affilée. Le tilt te contrôle et tu ne le vois même pas.",
    "Encore une. Ça fait {streak}. Personne ne compte, sauf moi.",
    "{streak} défaites consécutives. Le jeu essaie de te dire quelque chose.",
    "Série en cours : {streak}. Elle n'a rien de flatteur.",
    "{streak} de suite. Statistiquement, il faut vraiment le vouloir.",
    "Tu enchaînes : {streak} sans gagner. Bravo.",
    "{streak}e défaite d'affilée. L'option « arrêter » existe toujours.",
    "{streak} de rang. La spirale a un nom, et c'est le tien.",
    "Toujours rien après {streak} parties. On perd espoir.",
    "{streak} défaites consécutives : les LP partent par paquets.",
    "Série noire à {streak}. On note pour la postérité.",
    "{streak} de suite. Change de champion, de rôle, de jeu.",
    "{streak} défaites d'affilée : un exploit inversé.",
    "Le compteur affiche {streak}. Il ne descend pas.",
    "{streak} sans gagner. Ton compte mérite mieux que toi.",
    "{streak}e consécutive. Une pause. Sérieusement. Une pause.",
    "{streak} défaites de rang. Une seule victoire effacerait tout. Une.",
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
    "Encore LVP. Ce n'est plus un accident, c'est une carrière.",
    "Pire joueur, encore. Le titre te va trop bien.",
    "Tu collectionnes les LVP comme d'autres collectionnent les victoires.",
    "Nouveau LVP au palmarès. Il devient impressionnant.",
    "Encore dernier. On va te réserver la place définitivement.",
    "LVP récidiviste. Le dossier est épais.",
    "Ce n'est plus de la malchance, c'est un profil.",
    "Encore le pire des dix. Tu vises la constance ?",
    "Un LVP de plus. La collection est presque complète.",
    "Tu reprends ta place habituelle en bas du tableau.",
    "LVP, encore. On ne fait même plus semblant d'être surpris.",
    "Nouvelle entrée dans ta série de LVP. Elle est longue.",
    "Encore toi. Statistiquement, ce n'est plus un hasard.",
    "Le titre de pire joueur te suit partout. Il a ses raisons.",
    "Encore LVP. On va créer une catégorie à ton nom.",
)

# Division ou palier perdu. Le plus dur des résultats.
DEMOTED = (
    "Rétrogradé. {lp} LP, et une division en moins. Bien joué.",
    "Tu descends d'une division. On avait prévenu, tu as insisté.",
    "Division perdue. Tout est à refaire.",
    "{lp} LP : assez pour changer de division, dans le mauvais sens.",
    "Rétrogradation actée. Le classement ne fait pas de sentiment.",
    "Une division en moins. Le retour va être long.",
    "Tu quittes ta division par le bas. C'était mérité.",
    "{lp} LP et un palier en moins. Soirée réussie.",
    "Descente confirmée. On note la date, pour plus tard.",
    "Division perdue : le genre de partie dont on se souvient longtemps.",
    "Tu redescends. Le chemin inverse est bien plus long.",
    "Rétrogradé. Il te restait la fierté. Plus maintenant.",
    "{lp} LP en moins, et le palier avec. Complet.",
    "La division t'a lâché. Elle avait ses raisons.",
    "Descendu d'un cran. Ce n'était pas le soir pour forcer.",
    "Rétrogradation. Au moins tu vas stomp plus mauvais que toi.",
)

# Division ou palier gagné.
PROMOTED = (
    "Promu ! {lp} LP et une division en plus.",
    "Tu montes d'une division. Bien joué, sincèrement.",
    "Division gagnée. Profite, le palier suivant mord.",
    "{lp} LP : assez pour passer le palier. Excellent.",
    "Promotion actée. On t'attend au prochain cran.",
    "Une division en plus. La progression paie.",
    "Tu changes de division, par le haut cette fois.",
    "{lp} LP et un palier gagné. Grosse soirée.",
    "Montée confirmée. Reste à la garder.",
    "Promu. C'est le moment de s'arrêter, statistiquement.",
    "Division supérieure débloquée. Ne gâche pas tout ce soir.",
    "Tu montes. Rare, donc noté.",
    "{lp} LP : le palier est passé.",
    "Promotion. On applaudit, puis on attend la rechute.",
)

# Grosse perte de LP, sans rétrogradation.
LP_CRASH = (
    "{lp} LP d'un coup. Ça pique, hein.",
    "{lp} LP. À ce rythme, la division ne tiendra pas la semaine.",
    "Tu laisses {lp} LP sur la table. Aïe.",
    "{lp} LP envolés en une partie. Il en faut peu.",
    "{lp} LP : la partie coûte cher.",
    "Perte sèche de {lp} LP. Respire, puis arrête.",
    "{lp} LP. La prochaine sera meilleure. Forcément. Peut-être.",
    "{lp} LP en moins. Le compteur descend vite quand tu joues.",
    "{lp} LP. Une soirée de plus à rattraper.",
    "{lp} LP perdus. La division commence à regarder ailleurs.",
    "{lp} LP : le genre de partie qu'on aimerait ne pas avoir lancée.",
)

# Gros gain de LP, sans promotion.
LP_SURGE = (
    "{lp} LP en une partie. Continue.",
    "{lp} LP : le classement remonte enfin.",
    "{lp} LP d'un coup. Voilà à quoi ça ressemble.",
    "{lp} LP. La division suivante approche.",
    "{lp} LP gagnés. Bien joué.",
    "{lp} LP : la meilleure façon de finir une soirée.",
    "{lp} LP en une partie. Refais-en trente comme ça.",
    "{lp} LP. Le classement commence à te respecter.",
    "{lp} LP d'un coup : la division suivante n'est plus loin.",
    "{lp} LP. Arrête-toi là, ce serait sage.",
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
    "Zéro mort et une défaite. Il fallait peut-être jouer, aussi.",
    "Aucune mort, aucune influence. Tu étais où ?",
    "Tu n'es pas mort une fois et tu as quand même perdu. Fort.",
    "Zéro mort. On se demande si tu es sorti de la base.",
    "Survivre ne suffit pas. Il faut jouer.",
    "Aucune mort, défaite quand même : la prudence a ses limites.",
    "Tu as très bien survécu à une partie que ton équipe perdait sans toi.",
    "Zéro mort. Ton équipe, elle, était sur le terrain.",
    "Impeccable défensivement, absent le reste du temps.",
    "Pas une mort, pas une victoire, pas une trace.",
    "Ta ligne de score est propre. Le score final, non.",
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
    "Balayé en {minutes} minutes. Au suivant.",
    "{minutes} minutes : même pas le temps de sortir un objet.",
    "Défaite expresse. {minutes} minutes, et on n'en parle plus.",
    "{minutes} minutes. Le nexus est tombé avant ton premier objet.",
    "Écrasement en {minutes} minutes. Rien à analyser, tout à oublier.",
    "{minutes} minutes de partie. Un échauffement raté.",
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
    "Perdu après {minutes} minutes. Ce temps ne reviendra jamais.",
    "{minutes} minutes de partie et rien au bout. Cruel.",
    "Marathon de {minutes} minutes, défaite à l'arrivée. Superbe.",
    "{minutes} minutes pour ça. On compatit, un peu.",
    "Longue, disputée, perdue. {minutes} minutes de ta vie.",
    "{minutes} minutes : autant de temps pour un résultat négatif.",
    "Vous avez tenu {minutes} minutes avant de craquer.",
    "{minutes} minutes. Le nexus est tombé du mauvais côté.",
    "Défaite après {minutes} minutes. Va te coucher.",
    "{minutes} minutes et zéro LP. Soirée réussie.",
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
    "{vision} de vision. Les balises sont gratuites, au cas où.",
    "Vision à {vision} : la carte devait être une surprise permanente.",
    "{vision} en vision. On appelle ça jouer au hasard.",
    "Score de vision {vision}. Le brouillard de guerre te remercie.",
    "{vision} de vision sur toute la partie. Impressionnant, dans un sens.",
    "{vision} de vision. Mode aveugle assumé.",
)

JAB_CS = (
    "{cs_per_min} CS par minute. Les sbires se portent bien, merci.",
    "{cs_per_min} CS/min : la vague t'a survécu.",
    "Avec {cs_per_min} CS par minute, l'or devait venir d'ailleurs.",
    "{cs_per_min} CS/min. Le farm n'était pas la priorité, visiblement.",
    "{cs_per_min} CS par minute : les sbires ennemis meurent de vieillesse.",
    "{cs_per_min} CS/min. Un bot ferait mieux, littéralement.",
)

JAB_DAMAGE = (
    "{damage} de dégâts en {minutes} minutes. Tu étais spectateur ?",
    "{damage} de dégâts. Les adversaires n'ont rien senti passer.",
    "{damage} de dégâts sur {minutes} minutes : discret jusqu'au bout.",
    "Avec {damage} de dégâts, tu as surtout fait de la présence.",
    "{damage} de dégâts. Une tourelle en fait plus.",
    "{damage} de dégâts. Mode pacifiste.",
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
    "\N{POLICE CAR} {mention} est le maillon faible. Au revoir.",
    "\N{POLICE CAR} Dernier des dix : {mention}. Encore.",
)

MVP_LINES = (
    "\N{GLOWING STAR} MVP de la partie : {mention} - savoure, c'est rare.",
    "\N{GLOWING STAR} Meilleur joueur des dix : {mention}.",
    "\N{GLOWING STAR} {mention} rafle le titre de MVP. Mérité.",
    "\N{GLOWING STAR} MVP : {mention}. Rien à redire.",
    "\N{GLOWING STAR} Meilleure performance de la partie : {mention}.",
)


# Table utilisée par taunts.py. Les clés sont des identifiants de code :

# =========================================================================
# LOT IMPORTÉ
# =========================================================================
#
# Converti depuis un fichier de 20 000 lignes qui ne contenait en réalité que
# 310 phrases distinctes : la même phrase y était relancée avec des nombres
# tirés au hasard, un préfixe et un emoji différents. Les nombres inventés ont
# été remplacés par les vrais champs, et toute phrase citant une statistique
# que le bot ne mesure pas (objectifs, wards, pourcentages) a été écartée.
#
# Le lot est entièrement moqueur : il n'alimente que des situations de
# défaite. Les éloges restent les phrases écrites plus haut, sinon une bonne
# partie se verrait féliciter par une insulte.

# Moqueries qui n'affirment ni victoire ni défaite chiffrée : le tirage y
# pioche en plus des phrases spécifiques, dans toutes les situations de
# défaite. Rien ici ne cite un nombre, donc rien ne peut être faux.
GENERIC_LOSS = (
    "A TP pour arriver exactement là où personne ne voulait être.",
    "A TP. La question est : pourquoi ?",
    "A choisi de jouer avec une confiance supérieure à ses statistiques.",
    "A choisi de jouer comme si chaque ward était une option payante.",
    "A choisi de jouer comme si la défaite était une condition de victoire.",
    "A choisi de jouer comme si le cooldown du flash était une légende.",
    "A choisi de jouer comme si les LP étaient remboursables.",
    "A choisi de jouer contre la logique et la logique a gagné.",
    "A choisi de jouer le matchup comme s'il avait été choisi au hasard.",
    "A choisi de jouer le rôle principal dans « Où est passé mon avantage ? »",
    "A confondu pression et présence occasionnelle.",
    "A demandé du peel. Le Nexus a répondu.",
    "A demandé le tutoriel. Il l'a finalement trouvé.",
    "A demandé qu'on ne parle pas de cette game. Le bot a pris des notes.",
    "A demandé une analyse. Voici le scoreboard.",
    "A dive sous tour avec une confiance supérieure à sa barre de PV.",
    "A donné le shutdown avec la ponctualité d'un service de livraison.",
    "A donné un shutdown tellement gros que l'équipe adverse a appelé ça Noël.",
    "A débloqué le rôle de distributeur automatique.",
    "A décidé de battre son propre record de retour à la fontaine.",
    "A décidé de créer un nouveau type de positionnement.",
    "A décidé de devenir le fournisseur officiel de gold du lobby.",
    "A décidé de découvrir le concept de adc diff.",
    "A décidé de découvrir le concept de comeback adverse.",
    "A décidé de découvrir le concept de jungle diff.",
    "A décidé de découvrir le concept de mid diff.",
    "A décidé de découvrir le concept de support diff.",
    "A décidé de découvrir le concept de top diff.",
    "A décidé de découvrir que le drake spawn à une heure précise.",
    "A décidé de découvrir que les tours peuvent tirer.",
    "A décidé de déposer une candidature au poste de spectateur.",
    "A décidé de prouver qu'un mauvais fight peut être très mémorable.",
    "A décidé de prouver que « j'y vais quand même » est une stratégie.",
    "A décidé de recevoir une leçon gratuite. Les frais de scolarité étaient en LP.",
    "A décidé de rendre le matchup encore plus intéressant.",
    "A décidé de rendre les statistiques particulièrement bavardes.",
    "A décidé de réaliser que le bouton R avait un cooldown.",
    "A décidé de tester la distance maximale entre lui et son équipe.",
    "A décidé de transformer un stomp en suspense.",
    "A décidé de transformer une phase de lane en documentaire animalier.",
    "A découvert la puissance du farming… des écrans gris.",
    "A découvert le fast travel sans avoir besoin de TP.",
    "A découvert qu'une tour ne peut pas défendre quatre objectifs en même temps.",
    "A découvert que regarder la minimap était une compétence.",
    "A découvert une nouvelle mécanique : le retour instantané à la base.",
    "A démontré pourquoi la théorie seule ne suffit pas.",
    "A envoyé un ping « ? » comme si le scoreboard était ambigu.",
    "A eu le first blood et a ensuite organisé une collecte de kills pour l'autre équipe.",
    "A eu tout l'or du monde et a acheté du suspense.",
    "A fait connaissance avec la notion de conséquences.",
    "A fait un don sans reçu fiscal.",
    "A fait un pentakill puis a découvert que la partie continuait.",
    "A fait un pentakill. Le Nexus adverse a survécu, détail administratif.",
    "A farmé comme un roi et combattu comme un stagiaire.",
    "A flashé. La tour avait déjà calculé la trajectoire.",
    "A fourni les ressources. L'adversaire a fourni les résultats.",
    "A gagné la lane, puis a découvert que la carte était plus grande.",
    "A gagné le lane matchup et perdu le concept de map.",
    "A gagné son duel et perdu cette magnifique game : priorité claire.",
    "A gagné son duel et perdu la game : priorité claire.",
    "A gagné tellement facilement que le Nexus adverse est encore debout.",
    "A investi dans l'équipe ennemie. Placement risqué.",
    "A joué avec une confiance supérieure à ses statistiques.",
    "A joué comme si chaque ward était une option payante.",
    "A joué comme si la défaite était une condition de victoire.",
    "A joué comme si le cooldown du flash était une légende.",
    "A joué comme si les LP étaient remboursables.",
    "A joué contre la logique et la logique a gagné.",
    "A joué le matchup comme s'il avait été choisi au hasard.",
    "A joué le rôle principal dans « Où est passé mon avantage ? »",
    "A laissé les chiffres parler. Ils n'étaient pas très diplomates.",
    "A mis le « limit testing » à un niveau académique.",
    "A mis son champion dans des situations inédites.",
    "A offert du contenu premium gratuitement.",
    "A offert le Baron avec livraison incluse.",
    "A offert tellement de gold que l'équipe adverse devrait remercier le sponsor.",
    "A parfaitement exécuté quelque chose. On cherche encore quoi.",
    "A participé à la fameuse victoire adverse avec une régularité remarquable.",
    "A participé à la victoire adverse avec une régularité remarquable.",
    "A passé cette magnifique game à récolter des ressources pour personne.",
    "A passé la game à récolter des ressources pour personne.",
    "A passé plus de temps mort qu'en train de farmer.",
    "A perdu l'objectif mais gagné une histoire à raconter.",
    "A perdu son duel et gagné une histoire à raconter.",
    "A ping le danger puis est allé voir le danger de près.",
    "A pris le Baron, puis a donné cette magnifique game. Échange intéressant.",
    "A pris le Baron, puis a donné la game. Échange intéressant.",
    "A pris le concept de « back » très au sérieux.",
    "A pris le mot « split » très personnellement.",
    "A pris le shutdown et a oublié que les ennemis respawnent.",
    "A regardé la minimap juste après le gank. Synchronisation parfaite.",
    "A remporté le concours de CS. Le concours de victoire était ailleurs.",
    "A rendu le late game particulièrement confortable pour l'autre équipe.",
    "A réussi l'exploit de perdre un avantage qu'on croyait impossible à perdre.",
    "A réussi à feed sans jamais perdre son calme. Respect.",
    "A réussi à surprendre ses ennemis, ses alliés et probablement lui-même.",
    "A sauté le cours sur le reset.",
    "A tellement respecté la tour qu'il est allé lui rendre visite plusieurs fois.",
    "A tenté un steal. Le Baron a décliné.",
    "A tenu cette magnifique game comme un château de cartes dans un ventilateur.",
    "A tenu la game comme un château de cartes dans un ventilateur.",
    "A terminé le tutoriel sans trouver la fameuse victoire.",
    "A terminé le tutoriel sans trouver la victoire.",
    "A testé une nouvelle stratégie : perdre avec confiance.",
    "A transformé chaque objectif en question ouverte.",
    "A transformé un avantage en souvenir.",
    "A trouvé le seul endroit de la map où il ne fallait pas être.",
    "A trouvé une utilisation créative de son champion.",
    "A volé le Baron. La victoire, elle, est restée chez l'adversaire.",
    "A volé le dragon et s'est fait voler la partie.",
    "A vu le danger arriver et lui a ouvert la porte.",
    "A wardé la zone après y être mort. La progression est réelle.",
    "Affirme que cette magnifique game était free.",
    "Affirme que la game était free.",
    "Analyse terminée : le scoreboard avait raison.",
    "Annonce une revanche dès que le matchmaking accepte ses excuses.",
    "Archive sauvegardée sous : « pourquoi ? »",
    "Au moins les minions ont passé une bonne game.",
    "Aucune accusation, juste des statistiques.",
    "Avait l'avance. La partie avait d'autres plans.",
    "Avait le contrôle. Puis le contrôle a été rendu.",
    "Avait un plan. Le plan avait besoin d'un autre plan.",
    "Baron Nashor vient officiellement de gagner le duel mental.",
    "Beaucoup de confiance, quelques détails à corriger.",
    "Cette game a décidé de nourrir le serveur pendant une semaine.",
    "Cette game sera ressortie dans trois mois.",
    "Cette game vient de nourrir le serveur pendant une semaine.",
    "Chaque mort était différente. Certaines se ressemblaient beaucoup.",
    "Connaît maintenant parfaitement le chemin vers la fontaine.",
    "Cours accéléré : pourquoi on ne dive pas sous tour.",
    "Cours terminé : chapitre 1, regarder la minimap.",
    "En pratique, le scoreboard a choisi une autre théorie.",
    "Game terminée. Preuves sauvegardées.",
    "Garde confiance. C'est peut-être le plus impressionnant.",
    "Il a pris les cinq, la facture arrive.",
    "Innocent jusqu'à l'ouverture du scoreboard.",
    "L'intention était excellente. Le résultat demande une seconde lecture.",
    "La boutique adverse a probablement envoyé une carte de fidélité.",
    "La cohésion d'équipe était présente sur le papier.",
    "La commission d'enquête ouvre le replay.",
    "La dignité est optionnelle, le scoreboard est obligatoire.",
    "La game est terminée, mais les excuses viennent de commencer.",
    "La game était free. Le bouton de victoire devait être caché.",
    "La game était sous contrôle. Quelqu'un a appuyé sur un bouton.",
    "La lane phase a décidé de déposer une plainte.",
    "La lane phase vient de déposer une plainte.",
    "La lane était théoriquement gagnable.",
    "La leçon du jour : une ward coûte moins cher qu'un écran gris.",
    "La récolte était bonne. La moisson des LP, moins.",
    "La sentence est légère : une prochaine game.",
    "La stratégie était mystérieuse. Même le replay cherche encore.",
    "La théorie et la pratique viennent de se rencontrer.",
    "La tour a officiellement participé au duel.",
    "Le Baron était gratuit. Apparemment, il fallait quand même payer en patience.",
    "Le KDA est magnifique. Le résultat a moins de filtres.",
    "Le Nexus adverse a reçu une menace. Pas une menace crédible, mais une menace.",
    "Le Nexus adverse avait encore des PV et beaucoup de confiance.",
    "Le Nexus n'a pas été convaincu par l'argumentaire.",
    "Le Nexus était à portée. Mentalement aussi, paraît-il.",
    "Le bot est là pour rappeler ce que le joueur préférerait oublier.",
    "Le bot ne juge personne. Le sacro-saint scoreboard, par contre…",
    "Le bot ne juge personne. Le scoreboard, par contre…",
    "Le bouton « Acheter des wards » était disponible, pourtant.",
    "Le carry adverse a décidé de recevoir un financement participatif.",
    "Le carry adverse vient de recevoir un financement participatif.",
    "Le champion avait un kit complet. La stratégie était en DLC.",
    "Le champion demande probablement un changement de joueur.",
    "Le champion était prêt. Le joueur aussi. Le résultat, moins.",
    "Le chat aurait beaucoup de choses à dire. Heureusement, le bot s'en charge.",
    "Le clip est prêt. Le contexte est inutile.",
    "Le coaching post-game sera facturé en LP.",
    "Le comeback n'était pas prévu au planning.",
    "Le compteur de morts a demandé une augmentation.",
    "Le contenu était abondant.",
    "Le contexte n'améliore malheureusement pas le résultat.",
    "Le contre-pick avait besoin d'un peu plus de contre.",
    "Le danger était annoncé. La réponse aussi.",
    "Le dossier contient déjà trop de preuves.",
    "Le dragon a vu venir le play. Le bot aussi.",
    "Le dragon avait choisi son camp.",
    "Le dragon n'était pas compliqué. Il était juste ailleurs.",
    "Le flash était disponible. La décision, beaucoup moins.",
    "Le groupe a décidé de gagner un nouveau meme.",
    "Le groupe vient de gagner un nouveau meme.",
    "Le kill était gratuit. La répétition l'était aussi.",
    "Le lobby va probablement avoir besoin d'un débrief.",
    "Le matchmaking avait de l'humour aujourd'hui.",
    "Le matchup n'était peut-être pas le problème.",
    "Le matchup était difficile. La game aussi.",
    "Le mental est intact. Les statistiques, moins.",
    "Le minimap était pourtant en libre accès.",
    "Le move était audacieux. Le résultat aussi.",
    "Le passif a fait tout ce qu'il pouvait.",
    "Le ping objectif avait pourtant été envoyé.",
    "Le placement était tellement original que personne ne l'avait prévu.",
    "Le plan de jeu est officiellement classé confidentiel.",
    "Le plan secret est resté secret jusqu'à la fin.",
    "Le point d'interrogation était probablement le meilleur move de cette magnifique game.",
    "Le point d'interrogation était probablement le meilleur move de la game.",
    "Le professeur demande à revoir le chapitre sur les objectifs.",
    "Le raccourci vers la fontaine est officiellement découvert.",
    "Le replay demande une analyse image par image.",
    "Le replay mérite plus d'attention que cette magnifique game.",
    "Le replay mérite plus d'attention que la game.",
    "Le respawn adverse commence à devenir un abonnement.",
    "Le sacro-saint scoreboard a besoin d'aucune explication supplémentaire.",
    "Le sacro-saint scoreboard a demandé une minute de silence.",
    "Le sacro-saint scoreboard ne ment pas, même quand on lui demande gentiment.",
    "Le scoreboard a besoin d'aucune explication supplémentaire.",
    "Le scoreboard a demandé une minute de silence.",
    "Le scoreboard ne ment pas, même quand on lui demande gentiment.",
    "Le smite avait probablement besoin d'une pause.",
    "Le smite était en RTT.",
    "Le splitpush est efficace. Encore faut-il regarder le reste de la carte.",
    "Le suspense était excellent. La gestion d'avance, moins.",
    "Le teamfight a commencé à cinq. Il s'est terminé en réunion de crise.",
    "Le throw était si propre qu'on pourrait l'encadrer.",
    "Le timer n'était pas un conseil.",
    "Le tribunal du Nexus rend son verdict : compliqué.",
    "Le tutoriel avait pourtant des images.",
    "Les statistiques sont là. Le débat est facultatif.",
    "Même l'adversaire semblait surpris.",
    "Ne regarde pas les statistiques. Elles le regardent, elles.",
    "On apprécie l'initiative. Un peu moins son résultat.",
    "On ne dira rien sur la KDA. Elle a déjà tout dit.",
    "Pas d'insulte, juste une KDA qui demande des explications.",
    "Positionnement expérimental, résultats expérimentaux.",
    "Théoriquement, tout était possible.",
    "Un nouveau record vient d'être établi : beaucoup d'action, peu de résultat.",
    "Un objectif en moins, une excuse en plus.",
    "Un teamfight, trois décisions discutables, zéro regret.",
    "Une décision courageuse, statistiquement discutable.",
    "Vient d'inventer un nouveau chemin vers l'écran gris.",
    "Vient de battre son propre record de retour à la fontaine.",
    "Vient de créer un nouveau type de positionnement.",
    "Vient de devenir le fournisseur officiel de gold du lobby.",
    "Vient de découvrir le concept de adc diff.",
    "Vient de découvrir le concept de comeback adverse.",
    "Vient de découvrir le concept de jungle diff.",
    "Vient de découvrir le concept de mid diff.",
    "Vient de découvrir le concept de support diff.",
    "Vient de découvrir le concept de top diff.",
    "Vient de découvrir que le drake spawn à une heure précise.",
    "Vient de découvrir que les tours peuvent tirer.",
    "Vient de déposer une candidature au poste de spectateur.",
    "Vient de prouver qu'un mauvais fight peut être très mémorable.",
    "Vient de prouver que « j'y vais quand même » est une stratégie.",
    "Vient de recevoir une leçon gratuite. Les frais de scolarité étaient en LP.",
    "Vient de rendre le matchup encore plus intéressant.",
    "Vient de rendre les statistiques particulièrement bavardes.",
    "Vient de réaliser que le bouton R avait un cooldown.",
    "Vient de tester la distance maximale entre lui et son équipe.",
    "Vient de transformer un stomp en suspense.",
    "Vient de transformer une phase de lane en documentaire animalier.",
    "Était fed. Le Nexus adverse n'a pas reçu l'information.",
    "Était fed. Puis le mot « fed » a changé de propriétaire.",
)

# Mauvaise partie, défaite. La catégorie la plus large.
RAGEBAIT_BAD_LOST = (
    "A décidé de faire un magnifique {kills}/{deaths}/{assists}… avec une régularité impressionnante.",
    "A transformé {cs} CS en abonnement à l'écran gris.",
    "Avait {kills}/{deaths}. Le Nexus avait d'autres idées.",
    "L'optimisme de {player} est probablement la vraie victoire.",
    "L'économie adverse remercie chaleureusement {player}.",
    "L'équipe disait non. {player} a dit oui.",
    "La fontaine connaît maintenant {player} par son prénom.",
    "La fontaine est devenue le véritable objectif de {player}.",
    "La minimap disait non. {player} a dit oui.",
    "La route était longue. {player} l'a raccourcie.",
    "La tour disait non. {player} a dit oui.",
    "Le Baron disait non. {player} a dit oui.",
    "Le Nexus adverse a demandé si {player} avait vraiment essayé.",
    "Le carry adverse a décidé de remercier {player} sans même écrire dans le chat.",
    "Le carry adverse remercie {player} pour sa collaboration.",
    "Le carry adverse vient de remercier {player} sans même écrire dans le chat.",
    "Le champion adverse avait besoin de quelques kills. {player} avait la solution.",
    "Le cooldown disait non. {player} a dit oui.",
    "Le dossier {player} est désormais classé « intéressant ».",
    "Le dragon a survécu. La réputation de {player}, moins.",
    "Le marchand de l'équipe adverse connaît maintenant très bien {player}.",
    "Le replay sera utilisé contre {player} devant le tribunal du lobby.",
    "Le sacro-saint scoreboard recommande à {player} de ne pas regarder les statistiques.",
    "Le scaling adverse remercie {player} pour sa patience.",
    "Le scoreboard recommande à {player} de ne pas regarder les statistiques.",
    "Les minions ont probablement élu {player} MVP.",
    "Merci {player}, le bot ne manquera pas de matériel aujourd'hui.",
    "Même après {kills}/{deaths}, {player} continue de croire au comeback. Foi admirable.",
    "Un play impossible à prévoir. Même par {player}.",
    "Vient de faire un magnifique {kills}/{deaths}/{assists}… avec une régularité impressionnante.",
    "{cs} CS et toujours pas de victoire. Rendement impressionnant.",
    "{cs} CS, beaucoup de minions, une conclusion inattendue.",
    "{cs} CS, {deaths} morts. Les minions ont gagné.",
    "{deaths} morts : ce n'est plus une statistique, c'est une série.",
    "{deaths} morts, zéro regrets.",
    "{deaths} morts. Le bouton « spectateur » aurait économisé du temps.",
    "{kills} kills, mais cette magnifique game voulait quand même partir ailleurs.",
    "{kills} kills, mais la game voulait quand même partir ailleurs.",
    "{kills}/{deaths} et pourtant cette magnifique game a trouvé le moyen de devenir intéressante.",
    "{kills}/{deaths} et pourtant la game a trouvé le moyen de devenir intéressante.",
)

# Beaucoup de morts : ces phrases citent le KDA réel.
RAGEBAIT_FED_LOST = (
    "A offert {deaths} occasions à l'équipe adverse. Service client impeccable.",
    "A participé à {deaths} écrans gris. Consistance remarquable.",
    "{kills}/{deaths}/{assists} : KDA sponsorisée par le chaos.",
    "{kills}/{deaths}/{assists} : la fontaine a plus vu {player} que ses coéquipiers.",
    "{kills}/{deaths}/{assists} : le respawn adverse a demandé une pause.",
)

# Se vanter avec un mauvais score : registre du pire joueur.
RAGEBAIT_WORST_LOST = (
    "{kills}/{deaths}/{assists} — MVP selon lui.",
    "{kills}/{deaths}/{assists} — « GG EZ »",
)

# Cite la série de défaites en cours.
RAGEBAIT_STREAK_LOST = (
    "A perdu {streak} fois et trouvé {streak} excuses.",
)

# Cite la durée réelle de la partie.
RAGEBAIT_LONG_GAME_LOST = (
    "A acheté une ward après {minutes} minutes. La lumière est enfin arrivée.",
    "A réussi à rendre une game de {minutes} minutes mémorable pour de mauvaises raisons.",
    "On pourrait faire une vidéo de {minutes} minutes sur cette game.",
    "{minutes} minutes pour arriver à la même conclusion.",
)


# tu peux modifier les phrases, mais pas renommer les clés.
TAUNTS: dict[str, tuple[str, ...]] = {
    "worst_lost": WORST_LOST + RAGEBAIT_WORST_LOST,
    "worst_won": WORST_WON,
    "mvp_won": MVP_WON,
    "mvp_lost": MVP_LOST,
    "fed_lost": FED_LOST + RAGEBAIT_FED_LOST,
    "fed_won": FED_WON,
    "bad_lost": BAD_LOST + RAGEBAIT_BAD_LOST,
    "bad_won": BAD_WON,
    "good_lost": GOOD_LOST,
    "good_won": GOOD_WON,
    "first_game": FIRST_GAME,
    "record_deaths": RECORD_DEATHS,
    "record_kills": RECORD_KILLS,
    "streak_lost": STREAK_LOST + RAGEBAIT_STREAK_LOST,
    "streak_won": STREAK_WON,
    "first_mvp": FIRST_MVP,
    "repeat_lvp": REPEAT_LVP,
    "deathless_won": DEATHLESS_WON,
    "deathless_lost": DEATHLESS_LOST,
    "stomp_won": STOMP_WON,
    "stomp_lost": STOMP_LOST,
    "long_game_won": LONG_GAME_WON,
    "long_game_lost": LONG_GAME_LOST + RAGEBAIT_LONG_GAME_LOST,
    "demoted": DEMOTED,
    "promoted": PROMOTED,
    "lp_crash": LP_CRASH,
    "lp_surge": LP_SURGE,
}


def total_lines() -> int:
    """Nombre de phrases disponibles, piques et lignes spéciales comprises."""
    return (
        sum(len(lines) for lines in TAUNTS.values())
        + len(GENERIC_LOSS)
        + sum(len(lines) for lines in JABS.values())
        + len(LVP_LINES)
        + len(MVP_LINES)
    )
