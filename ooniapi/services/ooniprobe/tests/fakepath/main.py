"""
This fast api server emulates the behaviour of the fastpath

It's used for integration tests in ooniprobe
"""

from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def health():
    return
