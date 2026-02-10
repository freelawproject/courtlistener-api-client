from pydantic import BaseModel


class Filter4(BaseModel):
    """Filter4.

    Filters for fields with types: ['str']
    and lookup types: ['endswith', 'iendswith', 'iexact', 'istartswith', 'startswith']
    """

    endswith: None | str = None
    iendswith: None | str = None
    iexact: None | str = None
    istartswith: None | str = None
    startswith: None | str = None
