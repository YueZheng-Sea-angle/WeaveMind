from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.database import get_db
from app.models.book import Book, ProcessingStatus
from app.schemas.book import BookCreate, BookRead, BookListItem

router = APIRouter()


@router.get("", response_model=list[BookListItem])
async def list_books(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Book).order_by(Book.created_at.desc()))
    return result.scalars().all()


@router.get("/{book_id}", response_model=BookRead)
async def get_book(book_id: int, db: AsyncSession = Depends(get_db)):
    book = await db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="书籍不存在")
    return book


@router.post("", response_model=BookRead, status_code=201)
async def create_book(payload: BookCreate, db: AsyncSession = Depends(get_db)):
    book = Book(**payload.model_dump())
    db.add(book)
    await db.flush()
    await db.refresh(book)
    return book


@router.post("/{book_id}/upload", response_model=BookRead)
async def upload_book_file(
    book_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    book = await db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="书籍不存在")
    if not file.filename or not file.filename.endswith((".txt", ".md")):
        raise HTTPException(status_code=400, detail="仅支持 .txt 或 .md 文件")

    content = await file.read()
    text = content.decode("utf-8", errors="replace")

    from app.services.chapter_splitter import split_chapters
    from app.models.chapter import Chapter
    from app.models.book import ProcessingStatus

    book.processing_status = ProcessingStatus.SPLITTING
    await db.flush()

    chapters = await split_chapters(text)
    for i, ch in enumerate(chapters, start=1):
        chapter = Chapter(
            book_id=book_id,
            chapter_number=i,
            title=ch["title"],
            raw_text=ch["text"],
            word_count=len(ch["text"]),
        )
        db.add(chapter)

    book.total_chapters = len(chapters)
    book.processing_status = ProcessingStatus.PENDING
    await db.flush()
    await db.refresh(book)
    return book


@router.post("/{book_id}/process", status_code=202)
async def trigger_processing(book_id: int, db: AsyncSession = Depends(get_db)):
    """触发书籍处理（实体提取 + 章节锚点构建），通过 SSE 流查看进度。"""
    book = await db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="书籍不存在")
    if book.processing_status == ProcessingStatus.PROCESSING:
        raise HTTPException(status_code=409, detail="书籍正在处理中，请勿重复触发")
    return {"message": "处理已触发，请连接 SSE 流获取进度", "book_id": book_id}


@router.get("/{book_id}/process/stream")
async def process_stream(book_id: int):
    """SSE 流：实时推送书籍处理进度（实体提取 + 章节锚点）。"""
    from app.agents.orchestrator import process_book_stream

    return StreamingResponse(
        process_book_stream(book_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/{book_id}", status_code=204)
async def delete_book(book_id: int, db: AsyncSession = Depends(get_db)):
    book = await db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="书籍不存在")
    await db.delete(book)
