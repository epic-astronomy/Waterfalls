from typing import Annotated, Any, Literal, List
import json
import secrets
import warnings

from pydantic import Field


from pydantic import (
    AnyUrl,
    BeforeValidator,
    HttpUrl,
    PostgresDsn,
    computed_field,
    model_validator,
)
from pydantic_core import MultiHostUrl
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Self


def parse_cors(v: Any) -> list[str] | str:
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",")]
    elif isinstance(v, list | str):
        return v
    raise ValueError(v)


def parse_list(v: Any) -> list[str]:
    """A list from a JSON list or a comma-separated string"""
    if isinstance(v, str):
        v = json.loads(v) if v.strip().startswith("[") else [i for i in v.split(",")]
    if isinstance(v, list):
        return [str(i).strip() for i in v if str(i).strip()]
    raise ValueError(v)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_ignore_empty=True, extra="ignore"
    )
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = secrets.token_urlsafe(32)
    # 60 minutes * 24 hours * 8 days = 8 days
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    DOMAIN: str = "localhost"
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"
    WATCHLIST_MAX_ROWS_PER_PAGE: int = 25
    # NDP F-engine channel width (FS / 8192) and the first channel of each
    # imager band (epic4, epic1, epic5, epic2, epic6, epic3)
    CHAN_BW_HZ: float = 196e6 / 8192
    OBS_CHANS: List[int] = [672, 864, 1440, 2400, 2976, 3168]
    # daily digest cfreq = (chan0 + DIGEST_CHAN_OFFSET) * CHAN_BW_HZ
    DIGEST_CHAN_OFFSET: int = 31

    @computed_field  # type: ignore[misc]
    @property
    def LOWEST_FREQ_MHZ(self) -> float:
        return min(self.OBS_CHANS) * self.CHAN_BW_HZ / 1e6

    @computed_field  # type: ignore[misc]
    @property
    def server_host(self) -> str:
        # Use HTTPS for anything other than local development
        if self.ENVIRONMENT == "local":
            return f"http://{self.DOMAIN}"
        return f"https://{self.DOMAIN}"

    BACKEND_CORS_ORIGINS: Annotated[
        list[AnyUrl] | str, BeforeValidator(parse_cors)
    ] = []

    PROJECT_NAME: str = Field('',validate_default=False)
    SENTRY_DSN: HttpUrl | None = None
    POSTGRES_HOST: str = Field('', validate_default=False)
    POSTGRES_PORT: int = Field(5432, validate_default=False)
    POSTGRES_USER: str = Field('', validate_default=False)
    POSTGRES_PASSWORD: str = Field('', validate_default=False)
    POSTGRES_DB: str = Field('',validate_default=False)
    EPIC_DATA_SCHEMA: str = Field('epic',validate_default=False)
    # Per-node imaging databases. Each worker's imager writes the pixels,
    # sessions and digest of its band to a PostgreSQL on its own disk, in
    # tables of EPIC_DATA_SCHEMA; the database above keeps the global tables
    # (watch list, FRB analysis). Entries are name=host or name=host:port, as
    # a JSON list or comma separated. The default is the 40 Gb data network;
    # the 1 Gb internal network (169.254.128.11-16) also reaches the workers.
    EPIC_NODES: Annotated[list[str] | str, BeforeValidator(parse_list)] = [
        f"epic{i}=192.168.40.{20 + i}" for i in range(1, 7)
    ]
    # the per-node imager databases (cluster 16/epic, playbook 26); 5432 is the
    # old Citus worker and 5433 the all-sky monitor's database
    EPIC_NODE_PORT: int = 5434
    EPIC_NODE_DB: str = "epic"
    # read-only role on the node databases; blank falls back to POSTGRES_USER
    EPIC_NODE_USER: str = "epic_reader"
    EPIC_NODE_PASSWORD: str = ""
    EPIC_NODE_CONNECT_TIMEOUT_S: int = 3
    EPIC_NODE_STATEMENT_TIMEOUT_MS: int = 20000
    # a node that has not answered in this time drops out of the response
    EPIC_NODE_QUERY_TIMEOUT_S: float = 25.0
    # a node that refused a connection is skipped for this long
    EPIC_NODE_RETRY_S: float = 30.0
    # which nodes hold which band (chan0) is read from the session tables and
    # kept this long; "chan0=node" entries fix it instead
    EPIC_NODE_BANDS: Annotated[list[str] | str, BeforeValidator(parse_list)] = []
    EPIC_NODE_BANDS_CACHE_S: float = 300.0
    # the FRB analysis reads long windows of pixels from the nodes
    FRB_NODE_STATEMENT_TIMEOUT_MS: int = 600000

    # ---- Archive tier: older per-node data on the head node ----
    # A curator moves older partitions of the per-node tables into a
    # PostgreSQL on the head node. Every name the back end assumes about it is
    # here, to be aligned with the curator's final design. The connection
    # fields left blank (or 0) take the global database's (POSTGRES_*).
    EPIC_ARCHIVE_ENABLED: bool = True
    EPIC_ARCHIVE_HOST: str = ""
    EPIC_ARCHIVE_PORT: int = 0
    EPIC_ARCHIVE_DB: str = ""
    EPIC_ARCHIVE_USER: str = ""
    EPIC_ARCHIVE_PASSWORD: str = ""
    EPIC_ARCHIVE_SCHEMA: str = "sevilleta"
    # node table = archive table, with the same columns (the band column,
    # chan0 or cfreq, included); a node table not listed is not archived
    EPIC_ARCHIVE_TABLES: Annotated[list[str] | str, BeforeValidator(parse_list)] = [
        "epic_pixels=epic_pixels_archive",
        "epic_img_metadata2=epic_img_metadata2_archive",
        "epic_files_metadata2=epic_files_metadata2_archive",
        "epic_daily_digest=epic_daily_digest_archive",
    ]
    # Where the node's data begin, below which the archive must be read:
    #   node_oldest  the oldest row of EPIC_ARCHIVE_BOUNDARY_TABLE.column on
    #                each node (min of an indexed time column)
    #   catalogue    EPIC_ARCHIVE_CATALOGUE_SQL on the head, returning rows of
    #                (node name or chan0, archived up to)
    #   none         read the archive for every request
    EPIC_ARCHIVE_BOUNDARY: Literal["node_oldest", "catalogue", "none"] = "node_oldest"
    EPIC_ARCHIVE_BOUNDARY_TABLE: str = "epic_pixels.img_time"
    EPIC_ARCHIVE_CATALOGUE_SQL: str = (
        "select node, max(t_end) from {schema}.epic_archive_catalogue group by node"
    )
    EPIC_ARCHIVE_BOUNDARY_CACHE_S: float = 120.0
    # the archive is also read this far above the boundary, so a partition
    # moved after the boundary was cached is still found (rows in both tiers
    # are returned once)
    EPIC_ARCHIVE_OVERLAP_S: float = 86400.0
    # the archive's name in the logs and in the response flags
    EPIC_ARCHIVE_NAME: str = "archive"
    # matches the cadence of the long integrations behind the daily digest
    MAX_SPECTROGRAM_PERIOD_S: int = 180
    # CHIME/FRB watches last until the burst has crossed the lowest imaged
    # frequency, times this margin
    CHIME_WATCH_MARGIN: float = 1.2
    # dedispersed FRB products: rescan interval and how far back to look
    FRB_PRODUCTS_SCAN_S: int = 600
    FRB_PRODUCTS_MAX_AGE_DAYS: int = 30
    # the analysis runs as the frb-analysis Nomad job; True runs it in the API process instead
    FRB_PRODUCTS_ENABLED: bool = False
    # post each finished FRB analysis to the CHIME Slack channel, linking here
    FRB_SLACK_NOTIFY: bool = False
    WATERFALLS_PUBLIC_URL: str = "https://epic-astronomy.org"
    # trial DMs span the CHIME DM +- FACTOR x its quoted error, within [MIN, MAX]
    FRB_DM_HALF_FACTOR: float = 10.0
    # +-50 pc cm^-3 for every event, far beyond where the CHIME DM could lie,
    # to show how high noise peaks get elsewhere in DM. The lowest band's
    # transform then needs about 2 GB of memory per pixel (workers have 251 GB)
    FRB_DM_HALF_MIN: float = 50.0
    FRB_DM_HALF_MAX: float = 50.0
    # combine the bands of an event this many hours after its watch ends, even if some are missing
    FRB_COMBINE_AFTER_H: float = 6.0
    # the imager's geometry code and Python environment, for source positions
    # on the image, and its image grid
    FRB_GEOMETRY_PYTHON: str = "/home/epic/anaconda/envs/epic310/bin/python"
    FRB_GEOMETRY_DIR: str = "/FileStore/epicT/epic/LWA_EPIC/src/python"
    FRB_GRID_SIZE: int = 128
    FRB_GRID_RES: float = 1.056
    WATCHDOG_CHIME_SECRET: str = Field('',validate_default=False)
    SLACK_CHIME_NOTIFIER_TOKEN: str = Field('',validate_default=False)
    SLACK_CHIME_NOTIFIER_CHANNEL: str = Field('',validate_default=False)
    SLACK_CHIME_NOTIFIER_UNAME: str = Field('',validate_default=False)

    @computed_field  # type: ignore[misc]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> PostgresDsn:
        return MultiHostUrl.build(
            scheme="postgresql+psycopg2",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )

    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    SMTP_PORT: int = 587
    SMTP_HOST: str | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    # TODO: update type to EmailStr when sqlmodel supports it
    EMAILS_FROM_EMAIL: str | None = None
    EMAILS_FROM_NAME: str | None = None

    @model_validator(mode="after")
    def _set_default_emails_from(self) -> Self:
        if not self.EMAILS_FROM_NAME:
            self.EMAILS_FROM_NAME = self.PROJECT_NAME
        return self

    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int = 48

    @computed_field  # type: ignore[misc]
    @property
    def emails_enabled(self) -> bool:
        return bool(self.SMTP_HOST and self.EMAILS_FROM_EMAIL)

    # TODO: update type to EmailStr when sqlmodel supports it
    EMAIL_TEST_USER: str = "test@example.com"
    # TODO: update type to EmailStr when sqlmodel supports it
    FIRST_SUPERUSER: str = Field('', validate_default=False)
    FIRST_SUPERUSER_PASSWORD: str = Field('', validate_default=False)
    USERS_OPEN_REGISTRATION: bool = False

    def _check_default_secret(self, var_name: str, value: str | None) -> None:
        if value == "changethis":
            message = (
                f'The value of {var_name} is "changethis", '
                "for security, please change it, at least for deployments."
            )
            if self.ENVIRONMENT == "local":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)

    @model_validator(mode="after")
    def _enforce_non_default_secrets(self) -> Self:
        self._check_default_secret("SECRET_KEY", self.SECRET_KEY)
        self._check_default_secret("POSTGRES_PASSWORD", self.POSTGRES_PASSWORD)
        self._check_default_secret(
            "FIRST_SUPERUSER_PASSWORD", self.FIRST_SUPERUSER_PASSWORD
        )

        return self


settings = Settings()  # type: ignore
