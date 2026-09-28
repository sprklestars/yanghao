"""情报 / 对话的 CSV / JSON / Excel 导出。"""

import csv
import io
import json

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import (
    Conversation,
    IntelligenceRecord,
    Message,
    Platform,
)

router = APIRouter()


def _file_response(data: bytes, filename: str, media_type: str) -> Response:
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _intelligence_rows(records) -> list[dict]:
    rows = []
    for r in records:
        contacts = r.extracted_contacts or {}
        business = r.business_info or {}
        rows.append(
            {
                "id": str(r.id),
                "task_id": str(r.task_id),
                "platform": r.platform.value,
                "target_user_id": r.target_user_id,
                "display_name": r.display_name,
                "category": r.category.value,
                "confidence": r.confidence,
                "signals": "、".join(r.signals or []),
                "phones": "、".join(contacts.get("phones") or []),
                "emails": "、".join(contacts.get("emails") or []),
                "zalo_ids": "、".join(contacts.get("zalo_ids") or []),
                "telegram_handles": "、".join(contacts.get("telegram_handles") or []),
                "facebook_urls": "、".join(contacts.get("facebook_urls") or []),
                "prices": "、".join(business.get("prices") or []),
                "addresses": "、".join(business.get("addresses") or []),
                "websites": "、".join(business.get("websites") or []),
                "bank_accounts": "、".join(business.get("bank_accounts") or []),
                "activity_status": r.activity_status.value,
                "review_status": r.review_status.value,
                "operator_notes": r.operator_notes or "",
                "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else "",
                "last_seen": r.last_seen.isoformat() if r.last_seen else "",
                "collected_at": r.collected_at.isoformat() if r.collected_at else "",
            }
        )
    return rows


def _conversation_rows(pairs) -> list[dict]:
    rows = []
    for conv, msg in pairs:
        rows.append(
            {
                "conversation_id": str(conv.id),
                "task_id": str(conv.task_id),
                "target_user_id": conv.target_user_id,
                "display_name": conv.target_display_name,
                "state": conv.state.value,
                "turn_count": conv.turn_count,
                "direction": msg.direction.value,
                "content": msg.content or "",
                "language": msg.language,
                "created_at": msg.created_at.isoformat() if msg.created_at else "",
            }
        )
    return rows


def _render(format_: str, rows: list[dict], filename_stem: str) -> Response:
    format_ = (format_ or "csv").lower()
    if not rows:
        rows = [{}]

    if format_ == "json":
        data = json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8")
        return _file_response(data, f"{filename_stem}.json", "application/json")

    headers = list(rows[0].keys())
    if format_ == "xlsx":
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = filename_stem
        ws.append(headers)
        for row in rows:
            ws.append([row.get(h, "") for h in headers])
        buf = io.BytesIO()
        wb.save(buf)
        return _file_response(
            buf.getvalue(),
            f"{filename_stem}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    # CSV：带 BOM，Excel 直接打开中文不乱码
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return _file_response(
        buf.getvalue().encode("utf-8-sig"), f"{filename_stem}.csv", "text/csv; charset=utf-8"
    )


@router.get("/export/intelligence")
async def export_intelligence(
    format: str = "csv",
    task_id: str | None = None,
    category: str | None = None,
    platform: str | None = None,
    review_status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(IntelligenceRecord).order_by(IntelligenceRecord.collected_at.desc())
    if task_id:
        query = query.where(IntelligenceRecord.task_id == task_id)
    if category:
        query = query.where(IntelligenceRecord.category == category)
    if platform:
        query = query.where(IntelligenceRecord.platform == Platform(platform))
    if review_status:
        query = query.where(IntelligenceRecord.review_status == review_status)

    records = (await db.execute(query)).scalars().all()
    return _render(format, _intelligence_rows(records), "intelligence")


@router.get("/export/conversations")
async def export_conversations(
    format: str = "csv",
    task_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Conversation, Message)
        .join(Message, Message.conversation_id == Conversation.id)
        .order_by(Message.created_at.asc())
    )
    if task_id:
        query = query.where(Conversation.task_id == task_id)

    pairs = (await db.execute(query)).all()
    return _render(format, _conversation_rows(pairs), "conversations")
