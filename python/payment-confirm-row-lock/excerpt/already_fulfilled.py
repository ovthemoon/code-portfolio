"""발췌: 이미 확정된 결제를 또 적립하지 않는 판정. 식별자는 일반 이름으로 바꿨다.

SQLAlchemy 와 원본 모델이 필요해서 이 폴더에서는 실행하지 않는다.
이 함수는 웹훅 진입 직후 잡은 세션 행 잠금(lock_payment_session) 아래에서 불린다.
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from . import grants
from .models import PaymentSession

logger = logging.getLogger(__name__)


async def _already_fulfilled(session: AsyncSession, event: "NormalizedEvent") -> bool:
    """이 결제 세션이 이미 확정됐는데 또 적립하려 하면 True(건너뛴다).

    적립 중복 방지는 두 겹(웹훅 로그, 원장의 외부 참조 키)인데, 복구 작업과 웹훅, 콜백은 두 키가
    모두 다르다. 그래서 웹훅이 유실돼 복구 작업이 먼저 확정한 뒤 결제사가 웹훅을 재전송하면
    같은 결제로 두 번 적립됐다(재현됨).

    확정된 세션 자체를 세 번째 겹으로 쓴다. 갱신 청구는 적립을 동반하지 않으므로 적립량이 양수인
    이벤트만 대상이다.

    원래의 적립이 이미 있으면 ``refunded`` 도 확정이다. 복구 작업이 먼저 확정하고 환불까지
    끝난 뒤 지연된 결제 알림이 오면, 중복 방지 키가 새것이라 통과해 환불한 만큼 다시 적립됐다
    (재현됨). 반대로 환불이 결제보다 먼저 온 순서 역전(원래 적립 없음, 환불만 음수)은 늦게 온
    결제가 적립해 같은 지갑에서 상쇄돼야 하므로 막지 않는다.
    """
    if event.units <= 0 or not event.session_id:
        return False
    row = await session.get(PaymentSession, event.session_id)
    if row is None or row.status not in ("paid", "refunded"):
        return False
    if row.status == "refunded" and await grants.find_original_grant(
        session, provider=event.provider,
        refs=grants.payment_refs_for(row.id, row.external_ref, event.external_ref),
    ) is None:
        return False
    logger.warning(
        "[payments] blocked re-grant on a fulfilled session session=%s provider=%s event=%s units=%d",
        row.id, event.provider, event.event_id, event.units,
    )
    return True
