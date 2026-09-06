"""Liaison d'un compte Riot à un compte Discord."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from lolbet.models import Player
from lolbet.services.registration import (
    AccountNotFound,
    AlreadyLinked,
    InvalidRiotId,
    link_account,
    linked_players,
    split_riot_id,
    unlink_account,
)

GUILD = 4242
ALICE, BOB = 11, 22


class FakeRiot:
    """Client Riot minimal : renvoie un puuid derive du Riot ID demande."""

    def __init__(self, known: dict[str, str] | None = None) -> None:
        # None = compte inexistant. Par defaut, tout compte existe.
        self.known = known
        self.calls: list[tuple[str, str, str]] = []

    async def get_account_by_riot_id(self, game_name, tag_line, platform):
        self.calls.append((game_name, tag_line, platform))
        key = f"{game_name}#{tag_line}"
        if self.known is not None and key not in self.known:
            return None
        puuid = (self.known or {}).get(key, f"puuid-{key.lower()}")
        return {"puuid": puuid, "gameName": game_name, "tagLine": tag_line}


async def link(session, betting, *, discord_id, riot_id, region=None, riot=None):
    return await link_account(
        session,
        riot or FakeRiot(),
        betting,
        guild_id=GUILD,
        discord_id=discord_id,
        riot_id=riot_id,
        region=region,
        default_platform="euw1",
    )


# -- lecture du Riot ID ----------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Faker#KR1", ("Faker", "KR1")),
        ("  Gabite#EUW  ", ("Gabite", "EUW")),
        ("hide on bush#KR1", ("hide on bush", "KR1")),
        ("a#b#c", ("a#b", "c")),  # le tag est ce qui suit le dernier #
    ],
)
def test_split_riot_id_accepts_valid_forms(raw, expected):
    assert split_riot_id(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "SansTag", "#EUW", "Nom#", "N" * 17 + "#EUW"])
def test_split_riot_id_rejects_the_rest(raw):
    assert split_riot_id(raw) is None


# -- liaison ---------------------------------------------------------------


async def test_linking_creates_the_player_and_the_wallet(session_factory, betting):
    async with session_factory() as session:
        result = await link(session, betting, discord_id=ALICE, riot_id="Gabite#EUW")
        await session.commit()

    assert result.created is True
    assert result.riot_id == "Gabite#EUW"
    assert result.platform == "euw1"
    assert result.balance == 1000

    async with session_factory() as session:
        players = await linked_players(session, GUILD)
    assert len(players) == 1
    assert players[0].discord_id == ALICE


async def test_relinking_replaces_the_previous_account(session_factory, betting):
    """Un compte Discord ne suit qu'un compte LoL a la fois."""
    async with session_factory() as session:
        await link(session, betting, discord_id=ALICE, riot_id="Premier#EUW")
        await session.commit()

    async with session_factory() as session:
        result = await link(session, betting, discord_id=ALICE, riot_id="Second#EUW")
        await session.commit()

    assert result.created is False  # mis a jour, pas cree
    async with session_factory() as session:
        players = await linked_players(session, GUILD)
    assert len(players) == 1
    assert players[0].riot_id == "Second#EUW"


async def test_two_members_keep_two_separate_rows(session_factory, betting):
    """Le cas qui compte : inscrire ses amis un par un."""
    async with session_factory() as session:
        await link(session, betting, discord_id=ALICE, riot_id="Alice#EUW")
        await link(session, betting, discord_id=BOB, riot_id="Bob#EUW")
        await session.commit()

    async with session_factory() as session:
        players = await linked_players(session, GUILD)
    assert {p.discord_id for p in players} == {ALICE, BOB}
    assert {p.riot_id for p in players} == {"Alice#EUW", "Bob#EUW"}


async def test_the_same_lol_account_cannot_be_claimed_twice(session_factory, betting):
    async with session_factory() as session:
        await link(session, betting, discord_id=ALICE, riot_id="Partage#EUW")
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(AlreadyLinked) as excinfo:
            await link(session, betting, discord_id=BOB, riot_id="Partage#EUW")
    assert excinfo.value.other_discord_id == ALICE
    assert "déjà lié" in str(excinfo.value)


async def test_relinking_your_own_account_is_allowed(session_factory, betting):
    """Se reinscrire sur le meme compte ne doit pas declencher le conflit."""
    async with session_factory() as session:
        await link(session, betting, discord_id=ALICE, riot_id="Gabite#EUW")
        await session.commit()

    async with session_factory() as session:
        result = await link(session, betting, discord_id=ALICE, riot_id="Gabite#EUW")
        await session.commit()
    assert result.created is False


async def test_unknown_account_is_reported(session_factory, betting):
    riot = FakeRiot(known={"Existe#EUW": "puuid-1"})
    async with session_factory() as session:
        with pytest.raises(AccountNotFound):
            await link(
                session, betting, discord_id=ALICE, riot_id="Inconnu#EUW", riot=riot
            )


async def test_malformed_riot_id_never_reaches_the_api(session_factory, betting):
    riot = FakeRiot()
    async with session_factory() as session:
        with pytest.raises(InvalidRiotId):
            await link(session, betting, discord_id=ALICE, riot_id="SansTag", riot=riot)
    assert riot.calls == []  # aucun appel gaspille


async def test_region_is_normalised(session_factory, betting):
    riot = FakeRiot()
    async with session_factory() as session:
        result = await link(
            session, betting, discord_id=ALICE, riot_id="Faker#KR1", region="kr", riot=riot
        )
        await session.commit()
    assert result.platform == "kr"
    assert riot.calls[0][2] == "kr"


async def test_unknown_region_falls_back_to_the_default(session_factory, betting):
    async with session_factory() as session:
        result = await link(
            session, betting, discord_id=ALICE, riot_id="Faker#KR1", region="pluton"
        )
        await session.commit()
    assert result.platform == "euw1"


async def test_riot_casing_wins_over_what_was_typed(session_factory, betting):
    class CasedRiot(FakeRiot):
        async def get_account_by_riot_id(self, game_name, tag_line, platform):
            return {"puuid": "p1", "gameName": "Gabite", "tagLine": "EUW"}

    async with session_factory() as session:
        result = await link(
            session, betting, discord_id=ALICE, riot_id="gabite#euw", riot=CasedRiot()
        )
        await session.commit()
    assert result.riot_id == "Gabite#EUW"


# -- retrait ---------------------------------------------------------------


async def test_unlink_removes_the_player(session_factory, betting):
    async with session_factory() as session:
        await link(session, betting, discord_id=ALICE, riot_id="Gabite#EUW")
        await session.commit()

    async with session_factory() as session:
        riot_id = await unlink_account(session, GUILD, ALICE)
        await session.commit()

    assert riot_id == "Gabite#EUW"
    async with session_factory() as session:
        assert await linked_players(session, GUILD) == []


async def test_unlink_of_an_unknown_member_is_harmless(session_factory, betting):
    async with session_factory() as session:
        assert await unlink_account(session, GUILD, 999) is None


async def test_unlink_keeps_the_wallet(session_factory, betting):
    """Les pieces survivent a une desinscription."""
    async with session_factory() as session:
        await link(session, betting, discord_id=ALICE, riot_id="Gabite#EUW")
        wallet = await betting.get_wallet(session, GUILD, ALICE)
        wallet.balance = 4321
        session.add(wallet)
        await session.commit()

    async with session_factory() as session:
        await unlink_account(session, GUILD, ALICE)
        await session.commit()

    async with session_factory() as session:
        wallet = await betting.get_wallet(session, GUILD, ALICE, create=False)
    assert wallet.balance == 4321


async def test_players_are_scoped_to_their_guild(session_factory, betting):
    async with session_factory() as session:
        await link(session, betting, discord_id=ALICE, riot_id="Gabite#EUW")
        await link_account(
            session,
            FakeRiot(),
            betting,
            guild_id=9999,
            discord_id=ALICE,
            riot_id="Autre#EUW",
            region=None,
            default_platform="euw1",
        )
        await session.commit()

    async with session_factory() as session:
        assert len(await linked_players(session, GUILD)) == 1
        assert len(await linked_players(session, 9999)) == 1
        rows = (await session.execute(select(Player))).scalars().all()
    assert len(rows) == 2
