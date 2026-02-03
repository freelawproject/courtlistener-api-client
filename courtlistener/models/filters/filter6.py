from datetime import date, datetime

from pydantic import BaseModel


class Filter6(BaseModel):
    """Filter6.

    Filters for fields with types: ['str']
    and lookup types: ['contains', 'endswith', 'icontains', 'iendswith', 'iexact', 'istartswith', 'startswith']
    """
    contains: None | str = None
    endswith: None | str = None
    icontains: None | str = None
    iendswith: None | str = None
    iexact: None | str = None
    istartswith: None | str = None
    startswith: None | str = None
