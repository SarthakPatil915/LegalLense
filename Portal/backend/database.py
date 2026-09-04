"""MongoDB connection lifecycle for the LegalLense backend."""

from __future__ import annotations

import logging
import os

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError

logger = logging.getLogger("legallense.database")

DEFAULT_MONGODB_URI = "mongodb://127.0.0.1:27017/LegalLense"
DATABASE_NAME = "LegalLense"
MONGODB_CONNECT_TIMEOUT_MS = 5000

_client: MongoClient | None = None
_database: Database | None = None


def connect_to_mongodb() -> Database:
    """Connect to MongoDB, verify the server, and return the LegalLense database."""
    global _client, _database

    mongodb_uri = os.getenv("MONGODB_URI", DEFAULT_MONGODB_URI)
    client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=MONGODB_CONNECT_TIMEOUT_MS, tz_aware=True)

    try:
        client.admin.command("ping")
    except PyMongoError:
        client.close()
        logger.exception("MongoDB connection failed")
        raise RuntimeError("Could not connect to MongoDB") from None

    _client = client
    _database = client[DATABASE_NAME]
    _database.users.create_index("email", unique=True)
    _database.products.create_index([("manufacturerId", 1), ("updatedAt", -1)])
    _database.productRevisions.create_index([("productId", 1), ("version", -1)])
    _database.scans.create_index([("userId", 1), ("date", -1)])
    _database.sessions.create_index("expiresAt", expireAfterSeconds=0)
    _database.history.create_index([("userId", 1), ("createdAt", -1)])
    logger.info("Connected to MongoDB database '%s'", DATABASE_NAME)
    return _database


def close_mongodb() -> None:
    """Close the MongoDB client during backend shutdown."""
    global _client, _database

    if _client is not None:
        _client.close()
        logger.info("MongoDB connection closed")

    _client = None
    _database = None


def get_database() -> Database:
    """Return the active database connection for future repositories/routes."""
    if _database is None:
        raise RuntimeError("MongoDB is not connected")
    return _database