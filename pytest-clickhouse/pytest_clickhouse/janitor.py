from contextlib import contextmanager

from clickhouse_driver import Client as Clickhouse

class ClickhouseJanitor:
    """
    Manage clickhouse database state    
    """


    def __init__(self, dbname: str, clickhouse_url: str):
        self.dbname = dbname
        self.clickhouse_url = clickhouse_url
        self.click = None


    def init(self):
        """
        Initialize client and test database in clickhouse
        """
        self.click: Clickhouse = Clickhouse.from_url(self.clickhouse_url)
        query = f"""
        CREATE DATABASE IF NOT EXISTS {self.dbname} 
        COMMENT 'test database' 
        """
        self.click.execute(query, {})


    def drop(self):
        """
        Drop test database
        """
        query = f"""
        DROP DATABASE IF EXISTS {self.dbname} 
        """
        self.click.execute(query, {})

    
    def __enter__(self):
        self.init()


    def __exit__(self):
        self.drop()
