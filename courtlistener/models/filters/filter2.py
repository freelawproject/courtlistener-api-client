from pydantic import BaseModel


class Filter2(BaseModel):
    """Filter2.

    Filters for fields with types: ['str']
    and lookup types: ['gt', 'gte', 'lt', 'lte']
    """

    gt: None | str = None
    gte: None | str = None
    lt: None | str = None
    lte: None | str = None
