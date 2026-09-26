"""情报审核状态流转（纯逻辑，不碰数据库，方便单测）。"""

from datetime import datetime

from app.models.models import ReviewStatus

# 前端下拉用的候选值（与 DB 枚举 .value 一致）
REVIEW_STATUSES = tuple(status.value for status in ReviewStatus)


def parse_review_status(value) -> ReviewStatus:
    """把前端传来的字符串转成枚举；非法值抛 ``ValueError``。"""
    if isinstance(value, ReviewStatus):
        return value
    try:
        return ReviewStatus(str(value).strip().lower())
    except ValueError:
        raise ValueError(
            f"不支持的审核状态: {value}（可选：{', '.join(REVIEW_STATUSES)}）"
        )


def apply_review(record, status: ReviewStatus, notes: str | None, now: datetime) -> None:
    """就地更新一条情报的审核状态 / 备注 / 审核时间。

    - 状态回到 ``pending``：清空 ``reviewed_at``（视为还没审）；
    - 其它状态：只记录**首次**审核时间，之后改状态不会刷新它（保持审计含义）；
    - ``notes`` 传 ``None`` 表示不改动，传空串表示清空。
    """
    record.review_status = status
    if status == ReviewStatus.PENDING:
        record.reviewed_at = None
    else:
        record.reviewed_at = record.reviewed_at or now
    if notes is not None:
        record.operator_notes = notes.strip() or None
