"""Vérification des droits d'annonce.

La panne réelle : le bot détectait les parties, mais Discord refusait chaque
annonce faute de permission dans le salon. Rien ne le signalait côté Discord,
il fallait lire les logs du serveur.
"""

from __future__ import annotations

from lolbet.cogs.admin import BASE_PERMISSIONS, THREAD_PERMISSIONS, missing_permissions


class FakePermissions:
    def __init__(self, **granted: bool) -> None:
        self._granted = granted

    def __getattr__(self, name: str) -> bool:
        return self._granted.get(name, False)


class FakeChannel:
    def __init__(self, **granted: bool) -> None:
        self._permissions = FakePermissions(**granted)

    def permissions_for(self, _member) -> FakePermissions:
        return self._permissions


ME = object()
ALL_BASE = dict.fromkeys(BASE_PERMISSIONS, True)
ALL_THREADS = dict.fromkeys(THREAD_PERMISSIONS, True)


def test_a_fully_allowed_channel_reports_nothing_missing():
    channel = FakeChannel(**ALL_BASE)
    assert missing_permissions(channel, ME, with_threads=False) == []


def test_a_channel_that_denies_sending_is_caught():
    """Le cas exact de la panne : Discord repondait Forbidden."""
    channel = FakeChannel(embed_links=True)
    missing = missing_permissions(channel, ME, with_threads=False)
    assert missing == ["Envoyer des messages"]


def test_missing_embed_links_is_caught():
    """Tout passe par des embeds : sans ce droit, aucune annonce ne part."""
    channel = FakeChannel(send_messages=True)
    assert missing_permissions(channel, ME, with_threads=False) == ["Intégrer des liens"]


def test_a_locked_channel_lists_everything():
    missing = missing_permissions(FakeChannel(), ME, with_threads=False)
    assert set(missing) == set(BASE_PERMISSIONS.values())


def test_thread_permissions_are_only_required_when_threads_are_on():
    channel = FakeChannel(**ALL_BASE)
    assert missing_permissions(channel, ME, with_threads=False) == []
    assert set(missing_permissions(channel, ME, with_threads=True)) == set(
        THREAD_PERMISSIONS.values()
    )


def test_thread_permissions_satisfied():
    channel = FakeChannel(**ALL_BASE, **ALL_THREADS)
    assert missing_permissions(channel, ME, with_threads=True) == []


def test_an_unknown_channel_cannot_be_judged():
    """None n'est pas « tout va bien » : c'est « je ne peux pas savoir »."""
    assert missing_permissions(None, ME, with_threads=False) is None
    assert missing_permissions(FakeChannel(**ALL_BASE), None, with_threads=False) is None
