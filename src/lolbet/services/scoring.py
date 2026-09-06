"""MVP / worst-player scoring from a MATCH-V5 payload.

The score is a role-weighted blend of a player contribution *shares* within
their own team (kill participation, damage, gold, tanking, vision, objectives)
plus two match-wide efficiency terms, minus a death penalty, plus a small bonus
for being on the winning side.

Everything is share-based, so the numbers stay comparable across a 20-minute
stomp and a 45-minute slugfest without any hand-tuned per-minute thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Role weights. Each column sums to 1.0 before the death penalty and win bonus,
# so a support who never deals damage is not punished for playing support.
ROLE_WEIGHTS: dict[str, dict[str, float]] = {
    "TOP": {
        "kill_participation": 0.26,
        "damage_share": 0.28,
        "tank_share": 0.14,
        "vision_share": 0.04,
        "objective": 0.10,
        "cs": 0.10,
        "gold_efficiency": 0.08,
    },
    "JUNGLE": {
        "kill_participation": 0.30,
        "damage_share": 0.18,
        "tank_share": 0.10,
        "vision_share": 0.10,
        "objective": 0.22,
        "cs": 0.04,
        "gold_efficiency": 0.06,
    },
    "MIDDLE": {
        "kill_participation": 0.28,
        "damage_share": 0.32,
        "tank_share": 0.06,
        "vision_share": 0.06,
        "objective": 0.08,
        "cs": 0.10,
        "gold_efficiency": 0.10,
    },
    "BOTTOM": {
        "kill_participation": 0.26,
        "damage_share": 0.34,
        "tank_share": 0.04,
        "vision_share": 0.04,
        "objective": 0.10,
        "cs": 0.12,
        "gold_efficiency": 0.10,
    },
    "UTILITY": {
        "kill_participation": 0.34,
        "damage_share": 0.10,
        "tank_share": 0.14,
        "vision_share": 0.26,
        "objective": 0.08,
        "cs": 0.00,
        "gold_efficiency": 0.08,
    },
}
# Used when teamPosition is missing (ARAM, some remakes, old matches).
DEFAULT_WEIGHTS: dict[str, float] = {
    "kill_participation": 0.30,
    "damage_share": 0.26,
    "tank_share": 0.10,
    "vision_share": 0.08,
    "objective": 0.10,
    "cs": 0.08,
    "gold_efficiency": 0.08,
}

DEATH_PENALTY = 0.28
WIN_BONUS = 6.0
SCALE = 100.0

METRIC_LABELS: dict[str, str] = {
    "kill_participation": "participation aux kills",
    "damage_share": "dégâts de l'équipe",
    "tank_share": "dégâts encaissés",
    "vision_share": "vision de l'équipe",
    "objective": "objectifs",
    "cs": "farm",
    "gold_efficiency": "dégâts par or",
}


@dataclass(slots=True)
class PlayerScore:
    puuid: str
    riot_id: str
    champion_id: int
    champion_name: str
    team_id: int
    position: str
    win: bool
    kills: int
    deaths: int
    assists: int
    cs: int
    cs_per_min: float
    damage: int
    gold: int
    vision_score: int
    score: float
    metrics: dict[str, float] = field(default_factory=dict)
    contributions: dict[str, float] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    reportable: set[str] = field(default_factory=set)

    @property
    def kda_line(self) -> str:
        return f"{self.kills}/{self.deaths}/{self.assists}"

    @property
    def kda_ratio(self) -> float:
        return (self.kills + self.assists) / max(1, self.deaths)

    def _relevant(self) -> list[tuple[str, float]]:
        """Contributions worth quoting as a reason.

        Two exclusions. A support is not scored on farm, so "farm 0%" is not a
        criticism. And a metric nobody in the match scored on - no objectives
        taken at all, say - carries no signal, so citing it would be noise.
        """
        pool = [
            (name, value)
            for name, value in self.contributions.items()
            if name in self.reportable
        ]
        if pool:
            return pool
        # Every metric was degenerate; fall back to whatever the role weighs.
        return [
            (name, value)
            for name, value in self.contributions.items()
            if self.weights.get(name, 0.0) > 0
        ]

    def top_metrics(self, count: int = 2) -> list[str]:
        """What this player did best, for the MVP line."""
        ranked = sorted(self._relevant(), key=lambda kv: kv[1], reverse=True)
        return [self._describe(name) for name, _ in ranked[:count]]

    def bottom_metrics(self, count: int = 2) -> list[str]:
        """What dragged this player down, for the worst-player line."""
        ranked = sorted(self._relevant(), key=lambda kv: kv[1])
        return [self._describe(name) for name, _ in ranked[:count]]

    def _describe(self, name: str) -> str:
        raw = self.metrics.get(name, 0.0)
        return f"{METRIC_LABELS.get(name, name)} {raw * 100:.0f}%"


@dataclass(slots=True)
class MatchScores:
    players: list[PlayerScore]
    mvp: PlayerScore | None
    worst: PlayerScore | None
    duration_seconds: int
    winning_team_id: int | None
    team_kills: dict[int, int]

    def by_puuid(self, puuid: str) -> PlayerScore | None:
        for player in self.players:
            if player.puuid == puuid:
                return player
        return None

    def team(self, team_id: int) -> list[PlayerScore]:
        return [p for p in self.players if p.team_id == team_id]


def match_duration_seconds(info: dict) -> int:
    """gameDuration is seconds when gameEndTimestamp is present, else ms.

    Riot changed this with patch 11.20 and never normalised the old rows.
    """
    duration = int(info.get("gameDuration") or 0)
    if info.get("gameEndTimestamp") is None and duration > 100_000:
        return duration // 1000
    return duration


def _riot_id(participant: dict) -> str:
    name = participant.get("riotIdGameName") or participant.get("summonerName") or "Unknown"
    tag = participant.get("riotIdTagline") or participant.get("riotIdTagLine") or ""
    return f"{name}#{tag}" if tag else str(name)


def _share(value: float, total: float) -> float:
    return value / total if total > 0 else 0.0


def _normalise(value: float, maximum: float) -> float:
    return value / maximum if maximum > 0 else 0.0


def score_match(match: dict) -> MatchScores:
    """Score every participant of a finished match."""
    info = match.get("info") or {}
    participants: list[dict] = list(info.get("participants") or [])
    duration = max(1, match_duration_seconds(info))
    minutes = duration / 60

    if not participants:
        return MatchScores([], None, None, duration, None, {})

    # Per-team totals (shares are always within a player own team).
    team_totals: dict[int, dict[str, float]] = {}
    for p in participants:
        team_id = int(p.get("teamId") or 0)
        totals = team_totals.setdefault(
            team_id, {"kills": 0.0, "damage": 0.0, "gold": 0.0, "tank": 0.0, "vision": 0.0}
        )
        totals["kills"] += float(p.get("kills") or 0)
        totals["damage"] += float(p.get("totalDamageDealtToChampions") or 0)
        totals["gold"] += float(p.get("goldEarned") or 0)
        totals["tank"] += float(p.get("totalDamageTaken") or 0) + float(
            p.get("damageSelfMitigated") or 0
        )
        totals["vision"] += float(p.get("visionScore") or 0)

    # Match-wide maxima for the two absolute metrics.
    raw_cs_per_min: list[float] = []
    raw_objectives: list[float] = []
    raw_efficiency: list[float] = []
    for p in participants:
        cs = float(p.get("totalMinionsKilled") or 0) + float(p.get("neutralMinionsKilled") or 0)
        raw_cs_per_min.append(cs / minutes)
        raw_objectives.append(
            float(p.get("turretTakedowns") or p.get("turretKills") or 0)
            + float(p.get("inhibitorTakedowns") or p.get("inhibitorKills") or 0)
            + 2 * float(p.get("dragonKills") or 0)
            + 3 * float(p.get("baronKills") or 0)
        )
        gold = float(p.get("goldEarned") or 0)
        damage = float(p.get("totalDamageDealtToChampions") or 0)
        raw_efficiency.append(damage / gold if gold > 0 else 0.0)

    max_cs = max(raw_cs_per_min) if raw_cs_per_min else 0.0
    max_obj = max(raw_objectives) if raw_objectives else 0.0
    max_eff = max(raw_efficiency) if raw_efficiency else 0.0

    scored: list[PlayerScore] = []
    for index, p in enumerate(participants):
        team_id = int(p.get("teamId") or 0)
        totals = team_totals[team_id]
        deaths = int(p.get("deaths") or 0)
        team_deaths = sum(
            int(other.get("deaths") or 0)
            for other in participants
            if int(other.get("teamId") or 0) == team_id
        )

        metrics = {
            "kill_participation": _share(
                float(p.get("kills") or 0) + float(p.get("assists") or 0), totals["kills"]
            ),
            "damage_share": _share(
                float(p.get("totalDamageDealtToChampions") or 0), totals["damage"]
            ),
            "tank_share": _share(
                float(p.get("totalDamageTaken") or 0) + float(p.get("damageSelfMitigated") or 0),
                totals["tank"],
            ),
            "vision_share": _share(float(p.get("visionScore") or 0), totals["vision"]),
            "objective": _normalise(raw_objectives[index], max_obj),
            "cs": _normalise(raw_cs_per_min[index], max_cs),
            "gold_efficiency": _normalise(raw_efficiency[index], max_eff),
        }
        # Kill participation can exceed 1.0 only through rounding; clamp anyway.
        metrics = {key: max(0.0, min(1.0, value)) for key, value in metrics.items()}

        position = (p.get("teamPosition") or p.get("individualPosition") or "").upper()
        weights = ROLE_WEIGHTS.get(position, DEFAULT_WEIGHTS)
        contributions = {key: metrics[key] * weight for key, weight in weights.items()}

        # A metric whose basis is zero for everyone (no objectives taken at
        # all, no damage recorded) says nothing about this player.
        degenerate = {
            "kill_participation": totals["kills"] <= 0,
            "damage_share": totals["damage"] <= 0,
            "tank_share": totals["tank"] <= 0,
            "vision_share": totals["vision"] <= 0,
            "objective": max_obj <= 0,
            "cs": max_cs <= 0,
            "gold_efficiency": max_eff <= 0,
        }
        reportable = {
            key
            for key, weight in weights.items()
            if weight > 0 and not degenerate.get(key, False)
        }

        death_rate = _share(float(deaths), float(max(1, team_deaths)))
        win = bool(p.get("win"))
        total = sum(contributions.values()) - DEATH_PENALTY * death_rate
        score = SCALE * total + (WIN_BONUS if win else 0.0)

        cs_total = int(
            float(p.get("totalMinionsKilled") or 0) + float(p.get("neutralMinionsKilled") or 0)
        )
        scored.append(
            PlayerScore(
                puuid=str(p.get("puuid") or ""),
                riot_id=_riot_id(p),
                champion_id=int(p.get("championId") or 0),
                champion_name=str(p.get("championName") or ""),
                team_id=team_id,
                position=position or "UNKNOWN",
                win=win,
                kills=int(p.get("kills") or 0),
                deaths=deaths,
                assists=int(p.get("assists") or 0),
                cs=cs_total,
                cs_per_min=raw_cs_per_min[index],
                damage=int(p.get("totalDamageDealtToChampions") or 0),
                gold=int(p.get("goldEarned") or 0),
                vision_score=int(p.get("visionScore") or 0),
                score=round(score, 2),
                metrics=metrics,
                contributions=contributions,
                weights=dict(weights),
                reportable=reportable,
            )
        )

    ordered = sorted(scored, key=lambda s: (s.score, s.kda_ratio), reverse=True)
    winning_team = _winning_team(info, scored)
    team_kills = {
        team_id: int(sum(p.kills for p in scored if p.team_id == team_id))
        for team_id in sorted(team_totals)
    }

    return MatchScores(
        players=scored,
        mvp=ordered[0] if ordered else None,
        worst=ordered[-1] if len(ordered) > 1 else None,
        duration_seconds=duration,
        winning_team_id=winning_team,
        team_kills=team_kills,
    )


def _winning_team(info: dict, scored: list[PlayerScore]) -> int | None:
    for team in info.get("teams") or []:
        if team.get("win"):
            return int(team.get("teamId") or 0)
    for player in scored:
        if player.win:
            return player.team_id
    return None
