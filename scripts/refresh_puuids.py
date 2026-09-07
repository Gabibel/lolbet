"""Re-résout tous les PUUID après un changement de clé API Riot.

Pourquoi ce script existe : Riot chiffre les identifiants avec une clé propre
à chaque projet. Un PUUID obtenu avec une clé ne se déchiffre pas avec une
autre. Après une rotation de clé, tous les PUUID en base deviennent donc
inutilisables et SPECTATOR-V5 répond ``400 Exception decrypting`` sur chacun.

Ce qui n'est **pas** chiffré, c'est le Riot ID (``Pseudo#TAG``). Le script
repart de là : il redemande le PUUID de chaque joueur à ACCOUNT-V1 avec la
clé actuelle, puis réécrit l'ancien PUUID partout où il apparaît, pour que
l'historique reste rattaché au bon joueur.

    python scripts/refresh_puuids.py            # diagnostic, n'écrit rien
    python scripts/refresh_puuids.py --apply    # applique la correction

À lancer bot arrêté : il écrit dans les mêmes tables que la boucle de suivi.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy import update as sql_update
from sqlalchemy.exc import OperationalError

from lolbet.config import get_settings
from lolbet.db import create_engine, create_session_factory
from lolbet.models import (
    ApiCacheEntry,
    Player,
    PlayerGameStat,
    RankSnapshot,
    SideBet,
    TrackedGame,
    TrackedParticipant,
)
from lolbet.riot.cache import TTLCache
from lolbet.riot.client import RiotAPIError, RiotClient, RiotUnauthorized
from lolbet.riot.ratelimit import build_default_limiter

# Toutes les colonnes qui portent un PUUID. En oublier une laisserait un
# historique orphelin, rattaché à un identifiant que Riot ne connaît plus.
PUUID_COLUMNS = (
    (Player, Player.puuid),
    (TrackedParticipant, TrackedParticipant.puuid),
    (PlayerGameStat, PlayerGameStat.puuid),
    (RankSnapshot, RankSnapshot.puuid),
    (TrackedGame, TrackedGame.watcher_puuid),
    # La cible d'un pari annexe : sans elle, un pari deja regle
    # pointerait vers un identifiant que Riot ne reconnait plus.
    (SideBet, SideBet.target_puuid),
)

# Entrées de cache qui contiennent ou indexent un PUUID périmé. Les résultats
# de match sont immuables et ne coûtent rien à garder.
STALE_CACHE_PREFIXES = ("account:", "league:", "summoner:", "mastery:")


@dataclass
class Outcome:
    riot_id: str
    platform: str
    old_puuid: str
    new_puuid: str | None
    error: str = ""

    @property
    def changed(self) -> bool:
        return self.new_puuid is not None and self.new_puuid != self.old_puuid

    @property
    def status(self) -> str:
        if self.error:
            return f"ECHEC   {self.error}"
        if self.new_puuid is None:
            return "INTROUVABLE  Riot ne connaît pas ce Riot ID"
        if not self.changed:
            return "inchangé"
        return f"À CORRIGER   {self.old_puuid[:12]}… -> {self.new_puuid[:12]}…"


async def resolve(client: RiotClient, player: Player) -> Outcome:
    try:
        account = await client.get_account_by_riot_id(
            player.game_name, player.tag_line, player.platform
        )
    except RiotUnauthorized as exc:
        return Outcome(
            player.riot_id, player.platform, player.puuid, None, f"clé refusée ({exc})"
        )
    except RiotAPIError as exc:
        return Outcome(player.riot_id, player.platform, player.puuid, None, str(exc))

    new_puuid = (account or {}).get("puuid")
    return Outcome(player.riot_id, player.platform, player.puuid, new_puuid)


async def rewrite(session, old: str, new: str) -> dict[str, int]:
    """Remplace un PUUID partout. Renvoie le nombre de lignes par table."""
    touched: dict[str, int] = {}
    for model, column in PUUID_COLUMNS:
        result = await session.execute(
            sql_update(model).where(column == old).values({column.key: new})
        )
        if result.rowcount:
            touched[model.__tablename__] = result.rowcount
    return touched


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="écrit les corrections. Sans ce drapeau, le script ne fait que constater.",
    )
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    # Cache désactivé : une entrée ACCOUNT-V1 de moins de sept jours
    # renverrait précisément l'ancien PUUID qu'on cherche à remplacer.
    cache = TTLCache(session_factory=None, persist=False)
    client = RiotClient(
        settings,
        cache,
        build_default_limiter(
            settings.rate_limit_per_second,
            settings.rate_limit_per_two_minutes,
            settings.max_concurrent_requests,
        ),
    )

    try:
        try:
            async with session_factory() as session:
                players = list((await session.execute(select(Player))).scalars())
        except OperationalError:
            # Presque toujours un chemin de base erroné : le script en crée
            # une vide plutôt que de trouver celle du bot.
            url = settings.database_url.split("///")[-1]
            print(f"Base introuvable ou vide : {url}", file=sys.stderr)
            print(
                "Lance le script depuis le dossier du bot, ou passe le bon "
                "LOLBET_DATABASE_URL.",
                file=sys.stderr,
            )
            return 2

        if not players:
            print("Aucun joueur inscrit : rien à faire.")
            return 0

        print(f"{len(players)} joueur(s) inscrit(s).\n")
        outcomes = [await resolve(client, player) for player in players]
        for outcome in outcomes:
            print(f"  {outcome.riot_id:<28} {outcome.status}")

        broken = [o for o in outcomes if o.error or o.new_puuid is None]
        to_fix = [o for o in outcomes if o.changed]

        print()
        if broken:
            print(f"{len(broken)} joueur(s) non résolus : voir les lignes ci-dessus.")
        if not to_fix:
            print("Aucun PUUID à corriger.")
            return 1 if broken else 0

        print(f"{len(to_fix)} PUUID à remplacer.")
        if not args.apply:
            print("\nDiagnostic seulement. Relance avec --apply pour corriger.")
            return 0

        async with session_factory() as session:
            for outcome in to_fix:
                assert outcome.new_puuid is not None
                touched = await rewrite(session, outcome.old_puuid, outcome.new_puuid)
                detail = ", ".join(f"{name}={count}" for name, count in touched.items())
                print(f"  {outcome.riot_id:<28} {detail or 'aucune ligne'}")

            # Le cache mémorise le lien Riot ID -> ancien PUUID : le garder
            # ferait réapparaître l'identifiant périmé au prochain démarrage.
            purged = 0
            for prefix in STALE_CACHE_PREFIXES:
                result = await session.execute(
                    delete(ApiCacheEntry).where(ApiCacheEntry.key.startswith(prefix))
                )
                purged += result.rowcount or 0
            await session.commit()

        print(f"\nTerminé. {len(to_fix)} joueur(s) corrigés, {purged} entrées de cache purgées.")
        print("Redémarre le bot : sudo systemctl restart lolbet")
        return 0
    finally:
        await client.aclose()
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
