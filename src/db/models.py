from datetime import datetime
from typing import List, Optional
from sqlalchemy import (
    JSON, ForeignKey, String, Text, DateTime, func, BigInteger, Float,
    UniqueConstraint, Integer, Table, Column
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


user_sources = Table(
    "user_sources",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("source_id", Integer, ForeignKey("sources.id"), primary_key=True),
)


class User(Base):
    """User model for storing user information and preferences"""
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, unique=True, nullable=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    language: Mapped[str] = mapped_column(String(2), default="en", nullable=False)  # User's preferred language
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    sources: Mapped[List["Source"]] = relationship("Source", secondary=user_sources, back_populates="users")
    summaries: Mapped[List["Summary"]] = relationship("Summary", back_populates="user")
    filtered_messages: Mapped[List["FilteredMessage"]] = relationship("FilteredMessage", back_populates="user")
    processing_stats: Mapped[List["ProcessingStats"]] = relationship("ProcessingStats", back_populates="user")
    user_topics: Mapped[List["UserTopic"]] = relationship(
        "UserTopic",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Source(Base):
    """Model for storing unique Telegram sources/channels"""
    __tablename__ = "sources"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    users: Mapped[List["User"]] = relationship("User", secondary=user_sources, back_populates="sources")
    messages: Mapped[List["Message"]] = relationship("Message", back_populates="source")
    filtered_messages: Mapped[List["FilteredMessage"]] = relationship("FilteredMessage", back_populates="source")


class UserTopic(Base):
    """Model for storing user's topics and cached embeddings"""
    __tablename__ = "user_topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    embedding: Mapped[Optional[List[float]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship("User", back_populates="user_topics")

    __table_args__ = (
        UniqueConstraint("user_id", "topic", name="_user_topic_uc"),
    )


class Message(Base):
    """Model for storing raw collected messages before filtering"""
    __tablename__ = "messages"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    
    # Relationships
    source: Mapped["Source"] = relationship("Source", back_populates="messages")
    filtered_versions: Mapped[List["FilteredMessage"]] = relationship("FilteredMessage", back_populates="original_message")
    
    __table_args__ = (
        UniqueConstraint('source_id', 'telegram_id', name='_source_message_uc'),
    )


class FilteredMessage(Base):
    """Model for storing filtered messages that match user topics"""
    __tablename__ = "filtered_messages"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="filtered_messages")
    original_message: Mapped["Message"] = relationship("Message", back_populates="filtered_versions")
    source: Mapped["Source"] = relationship("Source", back_populates="filtered_messages")

    __table_args__ = (
        UniqueConstraint("user_id", "message_id", "topic", name="_user_message_topic_uc"),
    )


class ProcessingStats(Base):
    """Model for storing daily processing statistics"""
    __tablename__ = "processing_stats"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    
    # Collection stats
    messages_collected: Mapped[int] = mapped_column(Integer, default=0)
    messages_processed: Mapped[int] = mapped_column(Integer, default=0)
    sources_processed: Mapped[int] = mapped_column(Integer, default=0)
    
    # Filtering stats
    messages_filtered: Mapped[int] = mapped_column(Integer, default=0)
    topics_matched: Mapped[int] = mapped_column(Integer, default=0)
    
    # Processing time (in seconds)
    collection_time: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    filtering_time: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="processing_stats")

    __table_args__ = (
        UniqueConstraint('user_id', 'date', name='_user_date_stats_uc'),
    )


class Summary(Base):
    """Model for storing generated summaries for users"""
    __tablename__ = "summaries"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="summaries")
