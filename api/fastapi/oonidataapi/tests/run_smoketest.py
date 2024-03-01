import httpx
import time
import click
import random


def test_oonirun(client):
    r = client.get("/api/v2/oonirun_links")
    r.raise_for_status()
    j = r.json()
    desc = j["links"]
    assert isinstance(desc, list)
    if len(desc) > 0:
        for _ in range(5):
            d = random.choice(desc)
            client.get(f'/api/v2/oonirun/{d["oonirun_link_id"]}').raise_for_status()


def wait_for_backend(backend_base_url, timeout=10):
    start_time = time.time()

    while True:
        try:
            with httpx.Client(base_url=backend_base_url) as client:
                r = client.get("/version")
                if r.status_code == 200:
                    print("Service ready")
                    break
        except Exception as e:
            print(f"Connection failed: {e}")

        if time.time() - start_time > timeout:
            raise TimeoutError("Service did not become available in time")

        time.sleep(1)

@click.command()
@click.option(
    "--backend-base-url",
    default="http://localhost:8000",
    help="Base URL of the backend",
)
def smoketest(backend_base_url):
    """Run a smoke test against a running backend"""
    wait_for_backend(backend_base_url)

    with httpx.Client(base_url=backend_base_url) as client:
        test_oonirun(client)

if __name__ == "__main__":
    smoketest()
