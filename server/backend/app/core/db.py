from sqlmodel import Session, create_engine, select
from app.core.config import settings

engine_args=dict()
if settings.ENVIRONMENT == "local":
  engine_args = dict(echo=True)
engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI),**engine_args)
