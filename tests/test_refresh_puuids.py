"""Rotation de clé API : re-résolution des PUUID.

Riot chiffre les identifiants avec une clé propre à chaque projet, donc un
changement de clé rend tous les PUUID stockés indéchiffrables. Le script de
correction touche cinq tables ; en oublier une laisserait un historique
orphelin, rattaché à un joueur que Riot ne reconnaît plus. C'est exactement
ce que ce fichier vérifie, parce que le script s'exécute sur la vraie base.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from sqlalchemy import select

from lolbet.models import (
    ApiCacheEntry,
    GameStatus,
    Player,
    PlayerGameStat,
    RankSnapshot,
    TrackedGame,
    TrackedParticipant,
)

OLD = "ancien-puuid-chiffre-avec-la-cle-precedente"
NEW = "nouveau-puuid-chiffre-avec-la-cle-actuelle"
AUTRE = "puuid-d-un-autre-joueur"


def load_script():
    """Le script vit dans scripts/, hors du paquet : import par chemin."""
    path = Path(__file__).resolve().parents[1] / "scripts" / "refresh_puuids.py"
    spec = importlib.util.spec_from_file_location("refresh_puuids", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # @dataclass va chercher le module dans sys.modules pendant l'exécution.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


script = load_script()


async def seed(session_factory, puuid: str = OLD, discord_id: int = 11) -> int:
    """Un joueur et toutes les lignes qui portent son PUUID."""
    async with session_factory() as session:
        game = TrackedGame(
            guild_id=1,
            riot_game_id=f"EUW1_{abs(hash(puuid)) % 10**9}",
            platform="euw1",
            status=GameStatus.RESOLVED,
            tracked_team_id=100,
            watcher_puuid=puuid,
        )
        session.add(game)
        await session.flush()
        game_id = int(game.id or 0)

        session.add(
            Player(
                guild_id=1,
                discord_id=discord_id,
                puuid=puuid,
                game_name="Joueur",
                tag_line="EUW",
                platform="euw1",
            )
        )
        session.add(
            TrackedParticipant(
                game_id=game_id,
                puuid=puuid,
                discord_id=discord_id,
                riot_id="Joueur#EUW",
                team_id=100,
            )
        )
        session.add(
            PlayerGameStat(
                game_id=game_id,
                guild_id=1,
                discord_id=discord_id,
                puuid=puuid,
                riot_game_id=game.riot_game_id,
            )
        )
        session.add(
            RankSnapshot(
                puuid=puuid,
                platform="euw1",
                tier="GOLD",
                division="IV",
                league_points=42,
                ladder_score=1242,
            )
        )
        await session.commit()
        return game_id


async def test_every_table_that_holds_a_puuid_is_rewritten(session_factory):
    await seed(session_factory)

    async with session_factory() as session:
        touched = await script.rewrite(session, OLD, NEW)
        await session.commit()

    # Les cinq tables, nommément : c'est la liste qu'on ne veut pas voir
    # rétrécir sans qu'un test le signale.
    assert set(touched) == {
        "player",
        "tracked_participant",
        "player_game_stat",
        "rank_snapshot",
        "tracked_game",
    }

    async with session_factory() as session:
        assert (await session.execute(select(Player.puuid))).scalar_one() == NEW
        assert (
            await session.execute(select(TrackedParticipant.puuid))
        ).scalar_one() == NEW
        assert (await session.execute(select(PlayerGameStat.puuid))).scalar_one() == NEW
        assert (await session.execute(select(RankSnapshot.puuid))).scalar_one() == NEW
        assert (
            await session.execute(select(TrackedGame.watcher_puuid))
        ).scalar_one() == NEW


async def test_the_history_stays_attached_to_the_player(session_factory):
    """Le vrai enjeu : après correction, l'historique doit encore se retrouver."""
    await seed(session_factory)

    async with session_factory() as session:
        await script.rewrite(session, OLD, NEW)
        await session.commit()

    async with session_factory() as session:
        player = (await session.execute(select(Player))).scalar_one()
        stats = (
            (
                await session.execute(
                    select(PlayerGameStat).where(PlayerGameStat.puuid == player.puuid)
                )
            )
            .scalars()
            .all()
        )
        snapshots = (
            (
                await session.execute(
                    select(RankSnapshot).where(RankSnapshot.puuid == player.puuid)
                )
            )
            .scalars()
            .all()
        )
    assert len(stats) == 1
    assert len(snapshots) == 1


async def test_another_player_is_left_alone(session_factory):
    await seed(session_factory)
    await seed(session_factory, puuid=AUTRE, discord_id=22)

    async with session_factory() as session:
        await script.rewrite(session, OLD, NEW)
        await session.commit()

    async with session_factory() as session:
        puuids = set((await session.execute(select(Player.puuid))).scalars())
    assert puuids == {NEW, AUTRE}


async def test_rewriting_an_absent_puuid_changes_nothing(session_factory):
    await seed(session_factory)

    async with session_factory() as session:
        touched = await script.rewrite(session, "puuid-inconnu", NEW)
        await session.commit()

    assert touched == {}
    async with session_factory() as session:
        assert (await session.execute(select(Player.puuid))).scalar_one() == OLD


async def test_the_stale_cache_entries_are_the_ones_holding_a_puuid(session_factory):
    """Purger le cache compte autant que réécrire : il mémorise Riot ID -> PUUID."""
    async with session_factory() as session:
        for key in (
            "account:riot-id:euw1:joueur:euw",
            "account:puuid:ancien",
            "league:euw1:ancien",
            "summoner:euw1:ancien",
            "mastery:euw1:ancien:64",
            "match:EUW1_123",
            "ddragon:version",
        ):
            session.add(ApiCacheEntry(key=key, payload="{}", expires_at=None))
        await session.commit()

    from sqlalchemy import delete

    async with session_factory() as session:
        for prefix in script.STALE_CACHE_PREFIXES:
            await session.execute(
                delete(ApiCacheEntry).where(ApiCacheEntry.key.startswith(prefix))
            )
        await session.commit()

    async with session_factory() as session:
        remaining = set((await session.execute(select(ApiCacheEntry.key))).scalars())

    # Les résultats de match sont immuables et ne contiennent pas d'identifiant
    # à re-chiffrer : les jeter coûterait des appels pour rien.
    assert remaining == {"match:EUW1_123", "ddragon:version"}


def test_the_column_list_covers_every_puuid_column_in_the_models():
    """Un nouveau modèle portant un PUUID doit être ajouté au script."""
    from sqlmodel import SQLModel

    declared = set()
    for mapper in SQLModel._sa_registry.mappers:
        table = mapper.local_table
        if table is None:
            continue
        for column in table.columns:
            if "puuid" in column.name:
                declared.add((table.name, column.name))

    covered = {
        (model.__tablename__, column.key) for model, column in script.PUUID_COLUMNS
    }
    assert declared == covered, (
        "colonnes PUUID non couvertes par scripts/refresh_puuids.py : "
        f"{sorted(declared - covered)}"
    )
