from typing import Optional, Union

class ClickhouseNoopExecutor:
    """
    Clickhouse nooperator executor
    """
    
    
    def __init__(
        self, 
        host: str, 
        port: Union[str, int],
        dbname: str 
    ):
        self.host = host
        self.port = int(port)
        self.clickhouse_url = f"clickhouse://{self.host}:{self.port}"
        self.dbname = dbname


