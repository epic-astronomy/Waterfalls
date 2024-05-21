
def main():
  from app.models import epic_data
  from app.models.epic_data import epic_watchdog, test
  from sqlmodel import select
  pg_url = f"postgresql+psycopg2:///epic"
  engine = epic_data.create_engine(pg_url, echo=True)
  from sqlmodel import Session
  session=Session(engine)
  stmnt=select(epic_watchdog)
  print(stmnt)
  print(session.exec(stmnt).all())
  print(session.exec(select(test)).all())

  import sqlalchemy
  print(sqlalchemy.__version__)


