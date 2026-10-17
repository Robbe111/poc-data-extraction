"""Load the synthetic broker mailbox (demo_dataset/) into both the normal DB and the vector DB.

Examples:
    python backend/ingest_demo.py            # add the demo mailbox to what's already loaded
    python backend/ingest_demo.py --reset    # wipe both databases first: demo mailbox only
"""
import argparse
import time

import demo_dataset
import vector_store
from database import init_db, insert_email, reset_db


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="wipe both databases before ingesting")
    args = parser.parse_args()

    if args.reset:
        reset_db()
        vector_store.reset()
    else:
        init_db()

    started = time.time()
    emails = list(demo_dataset.iter_emails())
    for email in emails:
        insert_email(email)
    n_chunks = vector_store.add_emails(emails)
    n_attachments = sum(len(e["attachments"]) for e in emails)
    print(f"Done in {time.time() - started:.0f}s: {len(emails)} emails, "
          f"{n_attachments} PDF attachments, {n_chunks} chunks")


if __name__ == "__main__":
    main()
