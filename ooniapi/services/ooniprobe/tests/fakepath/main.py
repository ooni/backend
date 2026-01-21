"""
This fast api server emulates the behaviour of the fastpath

It's used for integration tests in ooniprobe
"""

from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def health():
    return

@app.post("/{msmt_uid}")
def receive_msm():
    return {}
