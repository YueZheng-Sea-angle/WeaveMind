from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.database import get_db
from app.models.entity import Entity, Relation, Event
from app.schemas.entity import EntityRead, EntityCreate, EntityUpdate, RelationRead, EventRead

router = APIRouter()


@router.get("/{book_id}/entities", response_model=list[EntityRead])
async def list_entities(
    book_id: int,
    entity_type: str | None = Query(None),
    q: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Entity).where(Entity.book_id == book_id)
    if entity_type:
        stmt = stmt.where(Entity.type == entity_type)
    if q:
        stmt = stmt.where(Entity.name.ilike(f"%{q}%"))
    result = await db.execute(stmt.order_by(Entity.name))
    return result.scalars().all()


@router.get("/{book_id}/entities/{entity_id}", response_model=EntityRead)
async def get_entity(book_id: int, entity_id: int, db: AsyncSession = Depends(get_db)):
    entity = await db.get(Entity, entity_id)
    if not entity or entity.book_id != book_id:
        raise HTTPException(status_code=404, detail="实体不存在")
    return entity


@router.post("/{book_id}/entities", response_model=EntityRead, status_code=201)
async def create_entity(
    book_id: int, payload: EntityCreate, db: AsyncSession = Depends(get_db)
):
    entity = Entity(book_id=book_id, **payload.model_dump())
    db.add(entity)
    await db.flush()
    await db.refresh(entity)
    return entity


@router.patch("/{book_id}/entities/{entity_id}", response_model=EntityRead)
async def update_entity(
    book_id: int,
    entity_id: int,
    payload: EntityUpdate,
    db: AsyncSession = Depends(get_db),
):
    entity = await db.get(Entity, entity_id)
    if not entity or entity.book_id != book_id:
        raise HTTPException(status_code=404, detail="实体不存在")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(entity, field, value)
    await db.flush()
    await db.refresh(entity)
    return entity


@router.delete("/{book_id}/entities/{entity_id}", status_code=204)
async def delete_entity(book_id: int, entity_id: int, db: AsyncSession = Depends(get_db)):
    entity = await db.get(Entity, entity_id)
    if not entity or entity.book_id != book_id:
        raise HTTPException(status_code=404, detail="实体不存在")
    await db.delete(entity)


@router.get("/{book_id}/relations", response_model=list[RelationRead])
async def list_relations(book_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Relation).where(Relation.book_id == book_id))
    return result.scalars().all()


@router.get("/{book_id}/events", response_model=list[EventRead])
async def list_events(
    book_id: int,
    chapter_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Event).where(Event.book_id == book_id)
    if chapter_id:
        stmt = stmt.where(Event.chapter_id == chapter_id)
    result = await db.execute(stmt)
    return result.scalars().all()
