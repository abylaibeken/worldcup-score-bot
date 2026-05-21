from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from sqlalchemy import String
from sqlalchemy import Integer
from sqlalchemy import BigInteger

from datetime import datetime
from sqlalchemy import DateTime

from sqlalchemy import ForeignKey
from sqlalchemy import UniqueConstraint


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
    )

    username: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    full_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    points: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    
class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    home_team: Mapped[str] = mapped_column(String(100))
    away_team: Mapped[str] = mapped_column(String(100))
    kickoff_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(30), default="scheduled")
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)



class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))

    pred_home: Mapped[int] = mapped_column(Integer)
    pred_away: Mapped[int] = mapped_column(Integer)

    points: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("user_id", "match_id", name="unique_user_match_prediction"),
    )