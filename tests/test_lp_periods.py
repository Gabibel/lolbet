"""LP gagnés ou perdus sur la journée, la semaine, le mois et depuis le début.

La règle qui structure tout : un écart n'est affiché que s'il a vraiment été
mesuré. Sans relevé antérieur à la fenêtre, on ne comble pas le trou avec un
zéro, on affiche un tiret.
"""

from __future__ import annotations

from datetime import timedelta

from lolbet.models import RankSnapshot
from lolbet.riot.rank import FLEX_QUEUE, SOLO_QUEUE, RankInfo
from lolbet.services.progression import (
    LpSummary,
    lp_delta,
    lp_summary,
    summary_line,
)
from lolbet.utils import utcnow

PUUID = "p1"


async def store(session_factory, *, lp: int, ago_days: float, queue: str = SOLO_QUEUE):
    """Écrit un relevé daté, sans passer par le garde-fou de record_snapshot."""
    info = RankInfo(queue, "GOLD", "IV", lp)
    async with session_factory() as session:
        snapshot = RankSnapshot(
            puuid=PUUID,
            platform="euw1",
            queue=queue,
            tier="GOLD",
            division="IV",
            league_points=lp,
            ladder_score=info.score,
            captured_at=utcnow() - timedelta(days=ago_days),
        )
        session.add(snapshot)
        await session.commit()


# -- lp_delta --------------------------------------------------------------


async def test_the_delta_starts_from_the_snapshot_before_the_window(session_factory):
    """La référence est le rang qu'avait le joueur au début de la période."""
    await store(session_factory, lp=20, ago_days=3)  # avant la fenêtre
    await store(session_factory, lp=45, ago_days=0.5)
    await store(session_factory, lp=70, ago_days=0.1)

    async with session_factory() as session:
        delta = await lp_delta(session, PUUID, since=utcnow() - timedelta(days=1))
    assert delta == 50


async def test_without_an_earlier_snapshot_the_window_is_used(session_factory):
    """Faute de mieux : ça sous-estime l'écart, mais ça ne l'invente pas."""
    await store(session_factory, lp=45, ago_days=0.5)
    await store(session_factory, lp=70, ago_days=0.1)

    async with session_factory() as session:
        delta = await lp_delta(session, PUUID, since=utcnow() - timedelta(days=1))
    assert delta == 25


async def test_a_single_snapshot_measures_nothing(session_factory):
    await store(session_factory, lp=45, ago_days=0.5)
    async with session_factory() as session:
        assert await lp_delta(session, PUUID, since=utcnow() - timedelta(days=1)) is None


async def test_an_unknown_player_measures_nothing(session_factory):
    async with session_factory() as session:
        assert await lp_delta(session, "inconnu", since=utcnow()) is None


async def test_a_loss_is_negative(session_factory):
    await store(session_factory, lp=80, ago_days=2)
    await store(session_factory, lp=25, ago_days=0.2)

    async with session_factory() as session:
        delta = await lp_delta(session, PUUID, since=utcnow() - timedelta(days=1))
    assert delta == -55


async def test_two_queues_are_never_mixed(session_factory):
    """Un rang flex et un rang solo ne se soustraient pas."""
    await store(session_factory, lp=10, ago_days=2, queue=FLEX_QUEUE)
    await store(session_factory, lp=40, ago_days=2, queue=SOLO_QUEUE)
    await store(session_factory, lp=90, ago_days=0.2, queue=SOLO_QUEUE)

    async with session_factory() as session:
        delta = await lp_delta(
            session, PUUID, since=utcnow() - timedelta(days=1), queue=SOLO_QUEUE
        )
    assert delta == 50


# -- lp_summary ------------------------------------------------------------


async def test_every_window_is_measured_from_its_own_baseline(session_factory):
    """Chaque fenêtre repart du dernier relevé qui la précède."""
    await store(session_factory, lp=0, ago_days=60)
    await store(session_factory, lp=10, ago_days=40)
    await store(session_factory, lp=20, ago_days=20)
    await store(session_factory, lp=50, ago_days=4)
    await store(session_factory, lp=75, ago_days=0.2)

    async with session_factory() as session:
        summary = await lp_summary(session, PUUID)

    assert summary.day == 25  # référence : le relevé à 4 jours
    assert summary.week == 55  # référence : le relevé à 20 jours
    assert summary.month == 65  # référence : le relevé à 40 jours
    assert summary.total == 75  # depuis le tout premier
    assert summary.has_data


async def test_a_window_without_movement_reads_zero_not_nothing(session_factory):
    """Zéro LP sur la journée est une information, pas une absence de mesure."""
    await store(session_factory, lp=50, ago_days=5)
    await store(session_factory, lp=50, ago_days=0.1)

    async with session_factory() as session:
        summary = await lp_summary(session, PUUID)
    assert summary.day == 0
    assert summary.total == 0


async def test_a_brand_new_player_has_nothing_to_show(session_factory):
    async with session_factory() as session:
        summary = await lp_summary(session, "inconnu")
    assert summary == LpSummary()
    assert summary.has_data is False


async def test_one_snapshot_is_not_enough(session_factory):
    """Il faut deux relevés : c'est exactement ce que le profil annonce."""
    await store(session_factory, lp=50, ago_days=0.1)
    async with session_factory() as session:
        summary = await lp_summary(session, PUUID)
    assert summary.has_data is False
    assert summary.day is None


async def test_the_summary_follows_the_queue_of_the_latest_snapshot(session_factory):
    await store(session_factory, lp=90, ago_days=3, queue=FLEX_QUEUE)
    await store(session_factory, lp=10, ago_days=2, queue=SOLO_QUEUE)
    await store(session_factory, lp=60, ago_days=0.1, queue=SOLO_QUEUE)

    async with session_factory() as session:
        summary = await lp_summary(session, PUUID)
    assert summary.total == 50  # le rang flex n'entre jamais dans le calcul


# -- rendu -----------------------------------------------------------------


def test_the_line_signs_every_number():
    line = summary_line(LpSummary(day=18, week=-42, month=115, total=230))
    assert "Jour +18" in line
    assert "Semaine -42" in line
    assert "Mois +115" in line
    assert "Total +230" in line


def test_an_unmeasured_window_shows_a_dash_not_a_zero():
    line = summary_line(LpSummary(day=None, week=12, month=None, total=12))
    assert "Jour —" in line
    assert "Mois —" in line
    assert "Semaine +12" in line
