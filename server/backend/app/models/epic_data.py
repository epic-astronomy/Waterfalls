from sqlmodel import Field, SQLModel, create_engine, MetaData
# from sqlmodel import LargeBinary, Text, select
from sqlalchemy.dialects.postgresql import  BYTEA, FLOAT, ARRAY
from sqlalchemy.types import  Float
from datetime import datetime
from pydantic import BaseModel
from uuid import UUID

# from app.core.config import settings
from typing import List, Callable, Union, Optional, Tuple, Literal
import xml.etree.ElementTree as etree
import sqlalchemy
from sqlalchemy import Column
from sqlalchemy.schema import CreateSchema
import re
from sqlalchemy.types import TypeDecorator,DateTime
from sqlalchemy import types, create_engine, Column, Integer
from app.core.config import settings

UUID_PATTERN = re.compile(
    r"^[\da-f]{8}-([\da-f]{4}-){3}[\da-f]{12}$", re.IGNORECASE
)


_metadata = MetaData(schema=settings.EPIC_DATA_SCHEMA)


class PointType(sqlalchemy.types.UserDefinedType):  # type: ignore [type-arg]
    def get_col_spec(self) -> str:
        return "POINT"

    def bind_processor(self, dialect):  # type: ignore [no-untyped-def]
        def process(value):  # type: ignore [no-untyped-def]
            return f"({value[0]},{value[1]})"

        return process

    def result_processor(self, dialect, coltype):  # type: ignore [no-untyped-def]
        def process(value):  # type: ignore [no-untyped-def]
            if value is not None:
                return tuple(map(int, value.strip("()").split(",")))
            return None

        return process

    def process_bind_param(self, value, dialect):
        return f"({value[0]},{value[1]})"

    def process_result_value(self, value, dialect):
        if value is not None:
            return tuple(map(float, value.strip("()").split(",")))
        return None


# class PointType(TypeDecorator):
#     impl = "POINT"

#     def process_bind_param(self, value, dialect):
#         return f"({value[0]},{value[1]})"

#     def process_result_value(self, value, dialect):
#         if value is not None:
#             return tuple(map(float, value.strip('()').split(',')))
#         return None


class XMLType(sqlalchemy.types.UserDefinedType):  # type: ignore [type-arg]
    def get_col_spec(self) -> str:
        return "XML"

    def bind_processor(  # type: ignore [no-untyped-def]
        self, dialect
    ) -> Callable[..., Optional[Union[str, bytes]]]:
        def process(value: Optional[str]) -> Optional[Union[str, bytes]]:
            if value is not None:
                if isinstance(value, str):
                    return value
                else:
                    return etree.tostring(value)
            else:
                return None

        return process


class epic_img_metadata_base(SQLModel):
    metadata = _metadata
    __tablename__ = "epic_img_metadata2"
    session_id: UUID | None = Field(primary_key=True)
    chan0: int | None
    n_chan: int | None
    n_pol: int | None
    chan_bw_hz: int | None
    int_time: float | None


class epic_img_metadata(epic_img_metadata_base, table=True):
    session_id: UUID = Field(primary_key=True)
    session_start: datetime = Field(sa_column=Column(DateTime(timezone=False), nullable=False))
    session_end: datetime = Field(sa_column=Column(DateTime(timezone=False), nullable=False))
    epic_version: str
    img_size: tuple[int, int] = Field(sa_column=Column(PointType))
    npix_kernel: int
    source_name: str | None #= Field(sa_column=Column(ARRAY(Text)))


class obs_period(SQLModel):
    start_time: datetime = Field(sa_column=Column(DateTime(timezone=False), nullable=False))
    end_time: datetime = Field(sa_column=Column(DateTime(timezone=False), nullable=False))


class epic_obs_period(obs_period):
    source_name: str


class epic_img_session(epic_img_metadata_base, obs_period):
    pass


class epic_img_session_public(SQLModel):
    data: list[epic_img_session]
    count: int

class epic_pixels_base(SQLModel):
    metadata = _metadata

    img_time: datetime
    pixel_values: bytes = Field(sa_column=Column(BYTEA))

class epic_pixels(epic_pixels_base, table=True):
    __tablename__ = "epic_pixels2"
    metadata = _metadata

    # img_time: datetime
    session_id: UUID = Field(primary_key=True)
    pixel_coord: tuple[int, int] = Field(
        sa_column=Column(PointType, primary_key=True)
    )
    pix_offset: tuple[int, int] = Field(
        sa_column=Column(PointType, primary_key=True)
    )
    pixel_coord: str
    pixel_lm: tuple[int, int] = Field(sa_column=Column(PointType))
    # pixel_values: bytes
    source_name: str = Field(primary_key=True)

class test_epic_pixels(SQLModel):
    pixel_values: str
    img_time: datetime

class epic_pixels_public(epic_pixels_base):
    __tablename__ = "epic_pixels"
    pass


class epic_files_metadata(SQLModel, table=True):
    metadata = _metadata

    id: int | None = Field(default=None, primary_key=True)
    file_name: str
    chan_width: float
    nchan: int
    support_size: int
    gulp_len_ms: float
    image_len_ms: float
    epoch_time_s: int
    grid_size: int
    grid_res: float
    cfreq_mhz: float
    epic_version: str
    epoch_time: datetime

class epic_daily_digest_base(SQLModel):
    img_time: datetime = Field(default=None, primary_key=True)
    stokes_i: List[float]  = Field(sa_column=Column(ARRAY(FLOAT)),default_factory=list)
    stokes_v: List[float]  = Field(sa_column=Column(ARRAY(FLOAT)),default_factory=list)
    cfreq: float

class epic_daily_digest_stats(SQLModel):
    cfreq: float
    count: int

class epic_daily_digest_public(SQLModel):
    stats: List[epic_daily_digest_stats]
    data: List[epic_daily_digest_base]

class epic_daily_digest_table(epic_daily_digest_base, table=True):
    __tablename__ = "epic_daily_digest"
    metadata = _metadata
    source_name: str= Field(default=None, primary_key=True)
    cfreq :float = Field(default=None, primary_key=True)
    
    class Config:
        arbitrary_types_allowed = True        

class daily_obs(SQLModel):
    source_name: str
    chan0: int
    chan_bw_hz: int

class epic_watchdog(SQLModel, table=True):
    # metadata = _metadata
    id: int = Field(default=None, primary_key=True)
    source: str = Field(default=None, primary_key=True)
    event_time: datetime
    ra_deg: float
    dec_deg: float
    event_type: str
    t_start: datetime
    t_end: datetime
    watch_mode: str
    patch_type: int | None = Field(default=None)
    reason: str
    author: str
    watch_status: str
    voevent: str = Field(sa_column=Column(XMLType))



class epic_watchdog_public(SQLModel):
    data: list[epic_watchdog]
    count: int | None = Field(default=None)

class chime_frb_trigger(BaseModel):
    ra: float
    dec: float
    known_source_name: str
    timestamp_utc_inf_freq: datetime
    voevent: str
    dm: float
    secret: str
    importance: float
    snr: float

if __name__ == "__main__":
    # use in-memory
    pg_url = f"postgresql+psycopg2:///epic"
    engine = create_engine(pg_url, echo=True)
    with engine.connect() as connection:
        connection.execute(
            CreateSchema(settings.EPIC_DATA_SCHEMA, if_not_exists=True)
        )
        connection.commit()

    # _metadata.create_all(engine)
    # MetaData(schema=settings.EPIC_DATA_SCHEMA).create_all(engine)
    # print(select(epic_watchdog).all())
