"""Tier/division/LP parsing and the ladder score used for team averages."""

from __future__ import annotations

from dataclasses import dataclass

TIERS: tuple[str, ...] = (
    "IRON",
    "BRONZE",
    "SILVER",
    "GOLD",
    "PLATINUM",
    "EMERALD",
    "DIAMOND",
)
APEX_TIERS: tuple[str, ...] = ("MASTER", "GRANDMASTER", "CHALLENGER")

DIVISIONS: dict[str, int] = {"IV": 0, "III": 1, "II": 2, "I": 3}
DIVISION_ORDER: tuple[str, ...] = ("IV", "III", "II", "I")

TIER_SHORT: dict[str, str] = {
    "IRON": "I",
    "BRONZE": "B",
    "SILVER": "S",
    "GOLD": "G",
    "PLATINUM": "P",
    "EMERALD": "E",
    "DIAMOND": "D",
    "MASTER": "M",
    "GRANDMASTER": "GM",
    "CHALLENGER": "CH",
}

TIER_EMOJI: dict[str, str] = {
    "IRON": "\N{MEDIUM BLACK CIRCLE}",
    "BRONZE": "\N{LARGE BROWN CIRCLE}",
    "SILVER": "\N{MEDIUM WHITE CIRCLE}",
    "GOLD": "\N{LARGE YELLOW CIRCLE}",
    "PLATINUM": "\N{LARGE BLUE CIRCLE}",
    "EMERALD": "\N{LARGE GREEN CIRCLE}",
    "DIAMOND": "\N{LARGE PURPLE CIRCLE}",
    "MASTER": "\N{LARGE PURPLE CIRCLE}",
    "GRANDMASTER": "\N{LARGE RED CIRCLE}",
    "CHALLENGER": "\N{LARGE ORANGE CIRCLE}",
}

# Each tier is 400 points wide (4 divisions x 100 LP). Master and above share
# one continuous LP pool, so they all start at the top of Diamond and simply
# keep counting LP.
TIER_WIDTH = 400
APEX_BASE = len(TIERS) * TIER_WIDTH

SOLO_QUEUE = "RANKED_SOLO_5x5"
FLEX_QUEUE = "RANKED_FLEX_SR"


@dataclass(frozen=True, slots=True)
class RankInfo:
    queue: str
    tier: str
    division: str
    league_points: int
    wins: int = 0
    losses: int = 0

    @property
    def is_apex(self) -> bool:
        return self.tier in APEX_TIERS

    @property
    def games(self) -> int:
        return self.wins + self.losses

    @property
    def winrate(self) -> float | None:
        return (self.wins / self.games * 100) if self.games else None

    @property
    def score(self) -> int:
        """Position on a single continuous ladder, for team averages."""
        tier = self.tier.upper()
        if tier in APEX_TIERS:
            return APEX_BASE + self.league_points
        if tier not in TIERS:
            return 0
        return (
            TIERS.index(tier) * TIER_WIDTH
            + DIVISIONS.get(self.division.upper(), 0) * 100
            + self.league_points
        )

    @property
    def short(self) -> str:
        """Compact form for the ten-player team listings, e.g. ``D4 32LP``."""
        tier = self.tier.upper()
        prefix = TIER_SHORT.get(tier, tier[:2].title())
        if tier in APEX_TIERS:
            return f"{prefix} {self.league_points}LP"
        # Roman numerals read badly next to a tier letter (DIV vs D4).
        division = DIVISIONS.get(self.division.upper(), 0)
        return f"{prefix}{4 - division} {self.league_points}LP"

    @property
    def display(self) -> str:
        tier = self.tier.upper()
        emoji = TIER_EMOJI.get(tier, "")
        name = tier.title()
        core = name if tier in APEX_TIERS else f"{name} {self.division.upper()}"
        text = f"{emoji} {core} - {self.league_points} LP".strip()
        rate = self.winrate
        if rate is not None:
            text += f" ({self.wins}W {self.losses}L, {rate:.0f}%)"
        return text


UNRANKED_LABEL = "Unranked"


def parse_entries(entries: list[dict] | None) -> dict[str, RankInfo]:
    """LEAGUE-V4 payload -> {queueType: RankInfo}."""
    parsed: dict[str, RankInfo] = {}
    for entry in entries or []:
        queue = entry.get("queueType") or ""
        tier = (entry.get("tier") or "").upper()
        if not tier:
            continue
        parsed[queue] = RankInfo(
            queue=queue,
            tier=tier,
            division=(entry.get("rank") or "I").upper(),
            league_points=int(entry.get("leaguePoints") or 0),
            wins=int(entry.get("wins") or 0),
            losses=int(entry.get("losses") or 0),
        )
    return parsed


def solo_queue_rank(entries: list[dict] | None) -> RankInfo | None:
    """Solo/duo if present, otherwise flex, otherwise nothing."""
    parsed = parse_entries(entries)
    return parsed.get(SOLO_QUEUE) or parsed.get(FLEX_QUEUE)


def score_to_label(score: float) -> str:
    """Inverse of RankInfo.score, for showing an average team elo."""
    if score >= APEX_BASE:
        return f"Master+ ({int(score - APEX_BASE)} LP)"
    index = max(0, min(len(TIERS) - 1, int(score // TIER_WIDTH)))
    within = score - index * TIER_WIDTH
    division = DIVISION_ORDER[max(0, min(3, int(within // 100)))]
    return f"{TIERS[index].title()} {division}"


def average_score(ranks: list[RankInfo | None]) -> float | None:
    """Average ladder score over the ranked players only."""
    scores = [rank.score for rank in ranks if rank is not None]
    if not scores:
        return None
    return sum(scores) / len(scores)
