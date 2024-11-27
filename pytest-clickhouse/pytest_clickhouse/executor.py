from typing import Optional
import time

import docker
from docker.models.containers import Container as DockerContainer 

class ClickhouseExecutor:
    """
    Clickhouse executor running on docker
    """
    
    
    def __init__(self, image_name: str, dbname: str):
        self.image_name = image_name
        self.container = None
        self.clickhouse_url = ""
        self.dbname = dbname


    def start(self):
        client = docker.from_env()
        image_name = self.image_name
        client.images.pull(image_name)

        # run a container with a random port mapping for ClickHouse default port 9000
        container = client.containers.run(
            image_name,
            ports={
                "9000/tcp": None
            },
            detach=True,
        )
        assert isinstance(container, DockerContainer)
        self.container = container
        
        # obtain the port mapping
        container.reload()
        assert isinstance(container.attrs, dict)
        host_port = container.attrs["NetworkSettings"]["Ports"]["9000/tcp"][0]["HostPort"]

        # construct the connection string
        clickhouse_url = f"clickhouse://localhost:{host_port}"
        self.clickhouse_url = clickhouse_url


    def wait_for_clickhouse(self):
        while 1:
            if self.running():
                break
            time.sleep(1)


    def running(self) -> bool:
        if self.container and self.container.status == 'running':
            return True
        return False


    def terminate(self):
        if self.container:
            self.container.stop()
            self.container.remove()


    def __enter__(self):
        self.start()


    def __exit__(self):
        self.terminate()
