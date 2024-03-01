import httpx
import click
import random


def test_oonirun(client):
    r = client.get("/api/v2/oonirun/")
    r.raise_for_status()
    j = r.json()
    desc = j["descriptors"]
    assert isinstance(desc, list)
    if len(desc) > 0:
        for _ in range(5):
            d = random.choice(desc)
            client.get(f'/api/v2/oonirun/{d["oonirun_link_id"]}').raise_for_status()


@click.command()
@click.option(
    "--backend-base-url",
    default="http://localhost:8000",
    help="Base URL of the backend",
)
def smoketest(backend_base_url):
    """Run a smoke test against a running backend"""
    with httpx.Client(base_url=backend_base_url) as client:
        test_oonirun(client)


if __name__ == "__main__":
    smoketest()
