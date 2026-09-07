"""Paris annexes : plus ou moins de N morts pour un joueur donné.

Pourquoi ce marché existe : quand une partie est déséquilibrée, parier sur
l'issue n'a plus d'intérêt — tout le monde voit qui va gagner. Un pari sur la
performance d'un joueur reste ouvert quel que soit le pronostic.

La ligne est proposée par le bot à partir des morts moyennes du joueur sur ses
dernières parties, et toujours en demi-point : sur une ligne entière, faire
exactement le nombre annoncé créerait une égalité, et il faudrait inventer une
règle de remboursement que personne n'aurait envie de lire.

Les cotes suivent le même modèle que le marché principal — mise virtuelle
d'amorce, cote qui bouge avec l'argent, cote figée au moment du pari.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..models import (
    GameStatus,
    PlayerGameStat,
    PropPick,
    SideBet,
    TrackedGame,
    TrackedParticipant,
    Wallet,
)
from ..utils import as_utc, utcnow
from .betting import (
    BetsClosed,
    BettingService,
    DuplicateBet,
    InsufficientFunds,
    InvalidAmount,
    compute_odds,
)

MARKET_DEATHS = "DEATHS"

# Ligne par défaut quand le joueur n'a pas encore d'historique suivi.
DEFAULT_LINE = 6.5
# Nombre de parties regardées pour proposer la ligne.
LINE_WINDOW = 10
LINE_MIN = 2.5
LINE_MAX = 14.5


class PropError(Exception):
    """Erreur métier propre aux paris annexes."""


class UnknownTarget(PropError):
    pass


@dataclass(frozen=True, slots=True)
class PropPool:
    over_amount: int = 0
    under_amount: int = 0
    over_count: int = 0
    under_count: int = 0
    over_odds: float = 0.0
    under_odds: float = 0.0

    @property
    def total(self) -> int:
        return self.over_amount + self.under_amount

    @property
    def count(self) -> int:
        return self.over_count + self.under_count

    def odds_for(self, pick: str) -> float:
        return self.over_odds if pick == PropPick.OVER else self.under_odds


@dataclass(frozen=True, slots=True)
class PropLine:
    """Un marché ouvert sur un joueur d'une partie."""

    target_puuid: str
    target_name: str
    line: float
    pool: PropPool


@dataclass(frozen=True, slots=True)
class PropSettlement:
    market: str
    paid: list[tuple[int, int, int]]
    lost: list[tuple[int, int]]
    refunded: bool = False

    @property
    def total_paid(self) -> int:
        return sum(payout for _, _, payout in self.paid)

    @property
    def count(self) -> int:
        return len(self.paid) + len(self.lost)


def round_to_half(value: float) -> float:
    """Arrondit au demi-point supérieur le plus proche, jamais un entier."""
    return float(int(value)) + 0.5


async def suggest_line(
    session: AsyncSession, guild_id: int, puuid: str, *, window: int = LINE_WINDOW
) -> float:
    """La ligne proposée : la moyenne de morts récente, en demi-point."""
    rows = (
        (
            await session.execute(
                select(PlayerGameStat.deaths)
                .where(
                    PlayerGameStat.guild_id == guild_id,
                    PlayerGameStat.puuid == puuid,
                )
                .order_by(PlayerGameStat.played_at.desc(), PlayerGameStat.id.desc())
                .limit(window)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return DEFAULT_LINE
    average = sum(rows) / len(rows)
    return max(LINE_MIN, min(LINE_MAX, round_to_half(average)))


class PropService:
    """Le pendant de ``BettingService`` pour les marchés annexes."""

    def __init__(self, settings: Settings, betting: BettingService) -> None:
        self._settings = settings
        self._betting = betting

    # -- lecture ----------------------------------------------------------

    async def bets_on(
        self, session: AsyncSession, game_id: int, target_puuid: str | None = None
    ) -> list[SideBet]:
        statement = select(SideBet).where(SideBet.game_id == game_id)
        if target_puuid is not None:
            statement = statement.where(SideBet.target_puuid == target_puuid)
        return list((await session.execute(statement)).scalars().all())

    async def pool(
        self, session: AsyncSession, game_id: int, target_puuid: str
    ) -> PropPool:
        bets = await self.bets_on(session, game_id, target_puuid)
        over = sum(b.amount for b in bets if b.pick == PropPick.OVER)
        under = sum(b.amount for b in bets if b.pick == PropPick.UNDER)
        total = over + under
        seed = self._settings.odds_seed_coins
        return PropPool(
            over_amount=over,
            under_amount=under,
            over_count=sum(1 for b in bets if b.pick == PropPick.OVER),
            under_count=sum(1 for b in bets if b.pick == PropPick.UNDER),
            over_odds=compute_odds(
                over,
                total,
                seed=seed,
                margin=self._settings.odds_margin,
                minimum=self._settings.odds_min,
                maximum=self._settings.odds_max,
            ),
            under_odds=compute_odds(
                under,
                total,
                seed=seed,
                margin=self._settings.odds_margin,
                minimum=self._settings.odds_min,
                maximum=self._settings.odds_max,
            ),
        )

    async def lines_for(
        self, session: AsyncSession, game: TrackedGame
    ) -> list[PropLine]:
        """Un marché par joueur suivi dans la partie."""
        participants = list(
            (
                await session.execute(
                    select(TrackedParticipant).where(
                        TrackedParticipant.game_id == game.id
                    )
                )
            )
            .scalars()
            .all()
        )
        lines: list[PropLine] = []
        for participant in participants:
            lines.append(
                PropLine(
                    target_puuid=participant.puuid,
                    target_name=participant.riot_id,
                    line=await self.line_for(session, game, participant.puuid),
                    pool=await self.pool(session, int(game.id or 0), participant.puuid),
                )
            )
        return lines

    async def line_for(
        self, session: AsyncSession, game: TrackedGame, target_puuid: str
    ) -> float:
        """La ligne du marché, figée dès qu'un premier pari existe.

        Sinon un deuxième parieur jouerait contre une ligne différente du
        premier, et le marché ne voudrait plus rien dire.
        """
        existing = await self.bets_on(session, int(game.id or 0), target_puuid)
        if existing:
            return existing[0].line
        return await suggest_line(session, game.guild_id, target_puuid)

    async def get_bet(
        self, session: AsyncSession, game_id: int, user_id: int, target_puuid: str
    ) -> SideBet | None:
        return (
            await session.execute(
                select(SideBet).where(
                    SideBet.game_id == game_id,
                    SideBet.user_id == user_id,
                    SideBet.market == MARKET_DEATHS,
                    SideBet.target_puuid == target_puuid,
                )
            )
        ).scalar_one_or_none()

    # -- écriture ---------------------------------------------------------

    async def place(
        self,
        session: AsyncSession,
        game: TrackedGame,
        user_id: int,
        target_puuid: str,
        pick: str,
        amount: int,
    ) -> tuple[SideBet, Wallet]:
        if not BettingService.is_open(game):
            raise BetsClosed("Les paris sont fermés pour cette partie.")
        if pick not in (PropPick.OVER, PropPick.UNDER):
            raise InvalidAmount("Choisis PLUS ou MOINS.")
        if amount < self._settings.min_bet:
            raise InvalidAmount(f"Le pari minimum est de {self._settings.min_bet} pièces.")
        if amount > self._settings.max_bet:
            raise InvalidAmount(f"Le pari maximum est de {self._settings.max_bet:,} pièces.")

        participant = (
            await session.execute(
                select(TrackedParticipant).where(
                    TrackedParticipant.game_id == game.id,
                    TrackedParticipant.puuid == target_puuid,
                )
            )
        ).scalar_one_or_none()
        if participant is None:
            raise UnknownTarget("Ce joueur n'est pas suivi dans cette partie.")

        existing = await self.get_bet(
            session, int(game.id or 0), user_id, target_puuid
        )
        if existing is not None:
            raise DuplicateBet(
                f"Tu as déjà {existing.amount:,} pièces sur "
                f"**{_pick_label(existing.pick)} {existing.line}** pour "
                f"{existing.target_name}."
            )

        line = await self.line_for(session, game, target_puuid)
        # La cote est lue avant d'ajouter la mise : parier ne doit pas
        # deplacer sa propre cote.
        pool = await self.pool(session, int(game.id or 0), target_puuid)
        odds = pool.odds_for(pick)

        wallet = await self._betting.get_wallet(session, game.guild_id, user_id)
        if wallet.balance < amount:
            raise InsufficientFunds(
                f"Tu n'as que {wallet.balance:,} pièces. "
                "Essaie `/quotidien` pour te renflouer."
            )

        wallet.balance -= amount
        wallet.total_wagered += amount
        bet = SideBet(
            game_id=int(game.id or 0),
            guild_id=game.guild_id,
            user_id=user_id,
            market=MARKET_DEATHS,
            target_puuid=target_puuid,
            target_name=participant.riot_id,
            line=line,
            pick=pick,
            amount=amount,
            odds=odds,
        )
        session.add(wallet)
        session.add(bet)
        await session.flush()
        return bet, wallet

    async def cancel(
        self, session: AsyncSession, game: TrackedGame, user_id: int, target_puuid: str
    ) -> SideBet:
        if not BettingService.is_open(game):
            raise BetsClosed("Les paris sont verrouillés, celui-là part avec toi.")
        bet = await self.get_bet(session, int(game.id or 0), user_id, target_puuid)
        if bet is None:
            raise PropError("Tu n'as aucun pari annexe sur ce joueur.")
        wallet = await self._betting.get_wallet(session, game.guild_id, user_id)
        wallet.balance += bet.amount
        wallet.total_wagered = max(0, wallet.total_wagered - bet.amount)
        session.add(wallet)
        await session.delete(bet)
        await session.flush()
        return bet

    # -- règlement --------------------------------------------------------

    async def settle(
        self, session: AsyncSession, game: TrackedGame, deaths_by_puuid: dict[str, int]
    ) -> PropSettlement:
        """Règle les paris annexes. Idempotent grâce à ``settled_at``."""
        bets = await self.bets_on(session, int(game.id or 0))
        now = utcnow()
        paid: list[tuple[int, int, int]] = []
        lost: list[tuple[int, int]] = []

        for bet in bets:
            if bet.settled_at is not None:
                continue
            actual = deaths_by_puuid.get(bet.target_puuid)
            if actual is None:
                # Le joueur n'apparaît pas dans le match : on rembourse
                # plutôt que de trancher sur une donnée absente.
                await self._give_back(session, bet, now)
                paid.append((bet.user_id, bet.amount, bet.amount))
                continue

            over = actual > bet.line
            won = (bet.pick == PropPick.OVER) == over
            wallet = await self._betting.get_wallet(session, bet.guild_id, bet.user_id)
            bet.actual = actual
            bet.settled_at = now
            if won:
                odds = bet.odds if bet.odds > 1 else self._settings.odds_min
                payout = int(bet.amount * odds)
                wallet.balance += payout
                wallet.bets_won += 1
                wallet.net_profit += payout - bet.amount
                bet.payout = payout
                paid.append((bet.user_id, bet.amount, payout))
            else:
                wallet.bets_lost += 1
                wallet.net_profit -= bet.amount
                bet.payout = 0
                lost.append((bet.user_id, bet.amount))
            session.add(wallet)
            session.add(bet)

        await session.flush()
        return PropSettlement(market=MARKET_DEATHS, paid=paid, lost=lost)

    async def refund_all(
        self, session: AsyncSession, game: TrackedGame
    ) -> PropSettlement:
        """Remake ou partie introuvable : tout le monde récupère sa mise."""
        bets = await self.bets_on(session, int(game.id or 0))
        now = utcnow()
        refunded: list[tuple[int, int, int]] = []
        for bet in bets:
            if bet.settled_at is not None:
                continue
            await self._give_back(session, bet, now)
            refunded.append((bet.user_id, bet.amount, bet.amount))
        await session.flush()
        return PropSettlement(
            market=MARKET_DEATHS, paid=refunded, lost=[], refunded=True
        )

    async def _give_back(self, session: AsyncSession, bet: SideBet, now) -> None:  # noqa: ANN001
        wallet = await self._betting.get_wallet(session, bet.guild_id, bet.user_id)
        wallet.balance += bet.amount
        wallet.total_wagered = max(0, wallet.total_wagered - bet.amount)
        bet.payout = bet.amount
        bet.settled_at = now
        session.add(wallet)
        session.add(bet)

    async def open_bets_for(
        self, session: AsyncSession, guild_id: int, user_id: int
    ) -> list[SideBet]:
        """Les paris annexes encore en cours, pour ``/paris``."""
        rows = (
            (
                await session.execute(
                    select(SideBet)
                    .join(TrackedGame, TrackedGame.id == SideBet.game_id)
                    .where(
                        SideBet.guild_id == guild_id,
                        SideBet.user_id == user_id,
                        SideBet.settled_at.is_(None),
                        TrackedGame.status.in_(
                            [GameStatus.LIVE, GameStatus.LOCKED, GameStatus.PENDING_RESULT]
                        ),
                    )
                    .order_by(SideBet.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        return list(rows)


def _pick_label(pick: str) -> str:
    return "PLUS de" if pick == PropPick.OVER else "MOINS de"


def pick_label(pick: str) -> str:
    return _pick_label(pick)


def describe(bet: SideBet) -> str:
    """``PLUS de 6.5 morts pour Faker#EUW``."""
    return f"{_pick_label(bet.pick)} {bet.line:g} morts pour {bet.target_name}"


def is_open(game: TrackedGame, *, now=None) -> bool:
    """Même fenêtre que le marché principal."""
    if game.status != GameStatus.LIVE:
        return False
    lock_at = as_utc(game.lock_at)
    return lock_at is None or (now or utcnow()) < lock_at
