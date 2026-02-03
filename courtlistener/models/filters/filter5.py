from pydantic import BaseModel


class Filter5(BaseModel):
    """Filter5.

    Filters for fields with types: ['bool']
    and lookup types: ['gt', 'gte', 'isnull', 'lt', 'lte', 'range']
    """

    gt: None | bool = None
    gte: None | bool = None
    isnull: None | bool = None
    lt: None | bool = None
    lte: None | bool = None
    range: None | tuple[bool, bool] = None
