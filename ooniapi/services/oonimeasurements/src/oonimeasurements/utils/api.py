"""
Utility functions and types to assist API development
"""
from typing import Annotated, Optional, Union
from fastapi import Query


ProbeCCOrNone = Annotated[Optional[str], Query(min_length=2, max_length=2)]
ProbeASNOrNone = Annotated[Union[int, str, None], Query()]

Limit = Annotated[
        int,
        Query(
            description="Number of records to return (default: 100)",
            ge=0, le=1_000_000, default=100
        ),
    ]

Offset = Annotated[
    int,
    Query(
        description="Offset from the start of the query, should be greater or equal to 0",
        ge=0, default=0
    )
]
