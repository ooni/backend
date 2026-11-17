# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "psycopg[binary]",
# ]
# ///
# Use uv to run this script without dependencies
"""
Manage API tokens.

The database is taken from the OONI_PG_URL environment variable.

    uv run apitoken.py create <user_id> [--expires-at 2027-01-01T00:00:00Z]
    uv run apitoken.py list [--user-id <user_id>]
    uv run apitoken.py revoke <token_hash_prefix>
"""
import argparse
import hashlib
import os
import secrets
import sys
from datetime import datetime

import psycopg

TOKEN_PREFIX = "ooni_"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create(cur, args):
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    cur.execute(
        "INSERT INTO apitoken (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
        (hash_token(token), args.user_id, args.expires_at),
    )
    print(f"user_id: {args.user_id}", file=sys.stderr)
    print(f"hash:    {hash_token(token)[:8]}", file=sys.stderr)
    print("Store the token now, it can't be retrieved later:", file=sys.stderr)
    print(token)


def list_(cur, args):
    q = """SELECT token_hash, user_id, date_created, expires_at,
        (expires_at IS NULL OR expires_at > now()) AS valid FROM apitoken"""
    params = ()
    if args.user_id:
        q += " WHERE user_id = %s"
        params = (args.user_id,)
    cur.execute(q + " ORDER BY date_created", params)
    for h, user_id, created, expires, valid in cur.fetchall():
        print(f"{h[:8]}  {user_id}  created={created:%Y-%m-%d}  "
              f"expires={expires or 'never'}  valid={valid}")


def revoke(cur, args):
    cur.execute(
        """UPDATE apitoken SET expires_at = now()
        WHERE token_hash LIKE %s AND (expires_at IS NULL OR expires_at > now())
        RETURNING token_hash""",
        (args.hash_prefix + "%",),
    )
    rows = cur.fetchall()
    if len(rows) != 1:
        cur.connection.rollback()
        sys.exit(f"Expected 1 matching valid token, found {len(rows)}. Nothing revoked.")
    print(f"Revoked {rows[0][0][:8]}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(required=True)

    c = sub.add_parser("create")
    c.add_argument("user_id")
    c.add_argument("--expires-at", type=datetime.fromisoformat, default=None,
                   help="ISO 8601 datetime with timezone. Default: never expires")
    c.set_defaults(func=create)

    l = sub.add_parser("list")
    l.add_argument("--user-id")
    l.set_defaults(func=list_)

    r = sub.add_parser("revoke")
    r.add_argument("hash_prefix")
    r.set_defaults(func=revoke)

    args = p.parse_args()
    if getattr(args, "expires_at", None) and args.expires_at.tzinfo is None:
        p.error("--expires-at must include a timezone")

    conn = psycopg.connect(os.environ["OONI_PG_URL"])
    with conn, conn.cursor() as cur:
        args.func(cur, args)


if __name__ == "__main__":
    main()
