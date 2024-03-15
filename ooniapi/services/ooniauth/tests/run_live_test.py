import httpx


def main():
    d = dict(email_address="arturo@ooni.org", redirect_to="https://explorer.ooni.org/")
    r = httpx.post("https://api.dev.ooni.io/api/v1/user_register", json=d)
    print(r.text)
    j = r.json()
    print(j)
    assert r.status_code == 200


if __name__ == "__main__":
    main()
