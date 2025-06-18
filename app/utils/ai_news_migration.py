from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from datetime import datetime
from typing import List, Dict
from app.models.ai_news_model import AINewsDB

async def categorize_by_tags(tags: List[str]) -> str:
    """Determina la categoria in base ai tag esistenti."""
    tags = [tag.lower() for tag in tags]
    
    # Definizione dei tag per categoria
    tech_tags = {"tech", "technical", "coding", "development", "programming", "software", "ai", "ml"}
    business_tags = {"business", "company", "enterprise", "strategy", "management", "organization"}
    other_tags = {"resource", "event", "faq", "guide", "tutorial", "announcement"}
    
    # Controlla le corrispondenze
    if any(tag in tech_tags for tag in tags):
        return "technical"
    if any(tag in business_tags for tag in tags):
        return "business"
    if any(tag in other_tags for tag in tags):
        return "other"
    return "generic"

async def migrate_news_categories(db: AsyncIOMotorClient) -> Dict[str, int]:
    """Migra le news esistenti aggiungendo categorie e statistiche aggiornate."""
    news_collection = db.get_collection("ai_news")
    stats = {"generic": 0, "technical": 0, "business": 0, "other": 0}
    
    async for news in news_collection.find({}):
        # Determina la categoria
        category = await categorize_by_tags(news.get("tags", []))
        stats[category] += 1
        
        # Calcola total_interactions
        current_stats = news.get("stats", {})
        total_interactions = sum([
            current_stats.get("views", 0),
            current_stats.get("likes", 0),
            current_stats.get("comments", 0)
        ])
        
        # Aggiorna il documento
        await news_collection.update_one(
            {"_id": news["_id"]},
            {
                "$set": {
                    "category": category,
                    "stats.replies": 0,  # Inizializza il conteggio delle risposte
                    "stats.total_interactions": total_interactions
                }
            }
        )
    
    return stats

async def migrate_comment_depths(db):
    """Aggiorna i commenti esistenti con il campo depth."""
    comments_collection = db.get_collection("comments")
    stats = {"root": 0, "replies": 0}
    # Prima passata: imposta depth=0 per i commenti root
    await comments_collection.update_many(
        {"parent_id": None},
        {"$set": {"depth": 0}}
    )
    stats["root"] = await comments_collection.count_documents({"parent_id": None})
    # Seconda passata: aggiorna depth per le risposte
    async for comment in comments_collection.find({"parent_id": {"$ne": None}}):
        parent = await comments_collection.find_one({"_id": comment["parent_id"]})
        if parent:
            depth = parent.get("depth", 0) + 1
            await comments_collection.update_one(
                {"_id": comment["_id"]},
                {"$set": {"depth": depth}}
            )
            stats["replies"] += 1
    return stats

async def run_migration(db: AsyncIOMotorClient):
    """Esegue la migrazione completa."""
    news_stats = await migrate_news_categories(db)
    comment_stats = await migrate_comment_depths(db)
    return {"news": news_stats, "comments": comment_stats}

async def migrate_existing_news(db):
    """Migra i documenti esistenti al nuovo schema."""
    cursor = db.ai_news.find({})
    async for doc in cursor:
        # Prepara il nuovo formato
        new_doc = {
            "_id": doc["_id"],
            "title": doc["title"],
            "description": doc.get("description", ""),
            "section": "generale",  # default per news esistenti
            "branch": doc["branch"],
            "employment_type": doc.get("employment_type", "*"),
            "tags": doc.get("tags", []),
            "content": {
                "type": "file" if doc.get("filename") else "url",
                "filename": doc.get("filename"),
                "external_url": doc.get("external_url"),
            },
            "content_type": doc.get("content_type"),
            "show_on_home": doc.get("show_on_home", False),
            "author_id": doc.get("author_id", ObjectId()),
            "uploaded_at": doc.get("uploaded_at", datetime.utcnow()),
            "stats": {"views": 0, "likes": 0, "comments": 0},
            "metadata": {}
        }
        # Aggiorna il documento
        await db.ai_news.replace_one({"_id": doc["_id"]}, new_doc)