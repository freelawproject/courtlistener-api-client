from datetime import date, datetime

from pydantic import BaseModel


class Filter7(BaseModel):
    """Filter7.

    Filters for fields with types: ['date']
    and lookup types: ['day', 'gt', 'gte', 'lt', 'lte', 'month', 'range', 'year']
    """
    day: None | int = None
    gt: None | date = None
    gte: None | date = None
    lt: None | date = None
    lte: None | date = None
    month: None | int = None
    range: None | tuple[date, date] = None
    year: None | int = None
