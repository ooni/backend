from .postgresql import SessionLocal


def get_postgresql_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
