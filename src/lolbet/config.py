"""Configuration, loaded from the environment / .env via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Platform host -> regional cluster host. ACCOUNT-V1 and MATCH-V5 live on the
# regional cluster, everything else on the platform host.
PLATFORM_TO_REGION: dict[str, str] = {
    "euw1": "europe",
    "eun1": "europe",
    "tr1": "europe",
    "ru": "europe",
    "me1": "europe",
    "na1": "americas",
    "br1": "americas",
    "la1": "americas",
    "la2": "americas",
    "oc1": "sea",
    "sg2": "sea",
    "tw2": "sea",
    "vn2": "sea",
    "ph2": "sea",
    "th2": "sea",
    "jp1": "asia",
    "kr": "asia",
}

VALID_PLATFORMS = frozenset(PLATFORM_TO_REGION)


class Settings(BaseSettings):
    """Every knob the bot has. Prefix every env var with ``LOLBET_``."""

    model_config = SettingsConfigDict(
        env_prefix="LOLBET_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Secrets
    discord_token: str
    riot_api_key: str

    # Riot
    default_platform: str = "euw1"

    # Storage - SQLite on local disk, nothing else. WAL is enabled in db.py.
    database_url: str = "sqlite+aiosqlite:///./data/lolbet.db"

    # Polling
    poll_interval_seconds: int = Field(default=60, ge=10)
    enrich_delay_seconds: float = Field(default=3.0, ge=0)
    maintenance_interval_seconds: int = Field(default=10, ge=1)
    result_delay_seconds: int = Field(default=60, ge=0)
    result_max_attempts: int = Field(default=12, ge=1)

    # Rate limiting. Dev key is 20 req/s and 100 req/2min; a personal key is
    # higher. Both windows are honoured by a single shared bucket.
    rate_limit_per_second: int = Field(default=20, ge=1)
    rate_limit_per_two_minutes: int = Field(default=100, ge=1)
    max_concurrent_requests: int = Field(default=5, ge=1)
    request_timeout_seconds: float = Field(default=10.0, gt=0)
    max_retries: int = Field(default=3, ge=0)

    # Betting (virtual currency only - there is no real-money path anywhere)
    starting_balance: int = Field(default=1000, ge=0)
    daily_amount: int = Field(default=100, ge=0)
    daily_cooldown_hours: int = Field(default=24, ge=1)
    bet_lock_seconds: int = Field(default=300, ge=0)
    # Cotes a la bookmaker : la banque est la contrepartie, la cote
    # suit l'argent mise et se fige au moment du pari.
    #
    # Mise virtuelle de depart de chaque cote. Elle fixe la cote
    # d'ouverture et empeche les cotes absurdes sur un premier pari.
    odds_seed_coins: int = Field(default=100, ge=1)
    # Marge de la banque : ce qui evite que la masse de pieces enfle
    # indefiniment avec /quotidien.
    odds_margin: float = Field(default=0.05, ge=0.0, lt=0.5)
    odds_min: float = Field(default=1.05, gt=1.0)
    odds_max: float = Field(default=10.0, gt=1.0)
    min_bet: int = Field(default=1, ge=1)
    max_bet: int = Field(default=100_000, ge=1)
    embed_edit_debounce_seconds: float = Field(default=2.5, ge=0)

    # Where the lock notice and the recap go. False keeps everything in the
    # announcement channel as replies; True tucks them into a thread instead.
    use_threads: bool = False
    announce_lock: bool = True

    # Sauvegardes automatiques de la base SQLite.
    backup_enabled: bool = True
    backup_keep: int = Field(default=7, ge=1)
    backup_interval_hours: int = Field(default=24, ge=1)

    # Prevenir dans Discord quand la cle Riot est refusee, au plus
    # une fois par fenetre : sans ca, la panne est totalement muette.
    alert_bad_key: bool = True
    alert_cooldown_hours: int = Field(default=6, ge=1)

    # Logging
    log_level: str = "INFO"
    log_json: bool = False

    # Optional: instant slash-command sync while developing.
    dev_guild_id: int | None = None

    @field_validator("default_platform")
    @classmethod
    def _validate_platform(cls, value: str) -> str:
        platform = value.strip().lower()
        if platform not in VALID_PLATFORMS:
            raise ValueError(
                f"unknown platform {value!r}; expected one of {sorted(VALID_PLATFORMS)}"
            )
        return platform

    @property
    def region_for_default(self) -> str:
        return PLATFORM_TO_REGION[self.default_platform]

    def platform_host(self, platform: str) -> str:
        return f"https://{platform.lower()}.api.riotgames.com"

    def region_host(self, platform: str) -> str:
        region = PLATFORM_TO_REGION.get(platform.lower(), self.region_for_default)
        return f"https://{region}.api.riotgames.com"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
