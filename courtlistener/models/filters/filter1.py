from pydantic import BaseModel


class Filter1(BaseModel):
    """Filter1.

    Filters for fields with types: ['str']
    and lookup types: ['startswith']
    """

    startswith: None | str = None
