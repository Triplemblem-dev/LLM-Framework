from sqlalchemy.orm import Session

from app.models import ModelProfile, User
from app.seed import DEFAULT_USER_EMAIL


def get_current_user(db: Session) -> User:
    """v1 has exactly one user; the token gate is the real access control."""
    user = db.query(User).filter_by(email=DEFAULT_USER_EMAIL).one()
    return user


def get_active_model_profile(db: Session) -> ModelProfile | None:
    return db.query(ModelProfile).filter_by(is_active=True).one_or_none()
