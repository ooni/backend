"""
Utility functions and types to assist API development
"""
from typing import Annotated, Optional, Union
from fastapi import Query


ProbeCCOrNone = Annotated[Optional[str], Query(min_length=2, max_length=2)]
ProbeASNOrNone = Annotated[Union[int, str, None], Query()]
