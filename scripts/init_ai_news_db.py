from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
from datetime import datetime, timedelta
from app.utils.ai_news_migration import run_migrations

async def init_ai_news_collections(db):
    # Creazione indici per ai_news
    await db.ai_news.create_index("section")
    await db.ai_news.create_index("tags")
    await db.ai_news.create_index("branch")
    await db.ai_news.create_index("employment_type")
    await db.ai_news.create_index("uploaded_at")
    await db.ai_news.create_index("author_id")
    await db.ai_news.create_index([("title", "text"), ("description", "text")])
    await db.ai_news.create_index("stats.views")
    await db.ai_news.create_index("stats.likes")
    await db.ai_news.create_index("stats.comments")
    print("✅ Indici ai_news creati")

    # Creazione indici per tracking visite
    await db.ai_news_views.create_index([("news_id", 1), ("user_id", 1)], unique=True)
    await db.ai_news_views.create_index("viewed_at")
    # TTL index per pulizia automatica dopo 30 giorni
    await db.ai_news_views.create_index(
        "viewed_at", 
        expireAfterSeconds=30 * 24 * 60 * 60
    )
    print("✅ Indici ai_news_views creati")

    # Creazione indici per commenti
    await db.ai_news_comments.create_index("news_id")
    await db.ai_news_comments.create_index("author_id")
    await db.ai_news_comments.create_index("parent_id")
    await db.ai_news_comments.create_index("created_at")
    print("✅ Indici ai_news_comments creati")

async def main():
    # Connessione al database
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.intranet

    # Esegui le migrazioni
    await run_migrations(db)

if __name__ == "__main__":
    asyncio.run(main()) 