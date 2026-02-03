from datetime import date, datetime

from pydantic import BaseModel


class Filter8(BaseModel):
    """Filter8.

    Filters for fields with types: ['datetime']
    and lookup types: ['day', 'gt', 'gte', 'hour', 'lt', 'lte', 'minute', 'month', 'range', 'second', 'year']
    """
    day: None | int = None
    gt: None | datetime = None
    gte: None | datetime = None
    hour: None | int = None
    lt: None | datetime = None
    lte: None | datetime = None
    minute: None | int = None
    month: None | int = None
    range: None | tuple[datetime, datetime] = None
    second: None | int = None
    year: None | int = None
