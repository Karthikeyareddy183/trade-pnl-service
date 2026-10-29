from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.portfolio import PortfolioService
from app.services.reconciliation import ReconciliationService
from app.services.trades import TradeService


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_trade_service(session: SessionDep) -> TradeService:
    return TradeService(session)


def get_portfolio_service(session: SessionDep) -> PortfolioService:
    return PortfolioService(session)


def get_reconciliation_service(session: SessionDep) -> ReconciliationService:
    return ReconciliationService(session)


TradeServiceDep = Annotated[TradeService, Depends(get_trade_service)]
PortfolioServiceDep = Annotated[PortfolioService, Depends(get_portfolio_service)]
ReconciliationServiceDep = Annotated[ReconciliationService, Depends(get_reconciliation_service)]
