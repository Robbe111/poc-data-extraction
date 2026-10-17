"""Load a small slice of the EDRM Enron dataset into both the normal DB and the vector DB.

Examples:
    python backend/ingest_enron.py --list                         # show custodians + sizes
    python backend/ingest_enron.py                                # use defaults from config.py / env
    python backend/ingest_enron.py -c meyers-a king-j --max-emails 200 --reset
"""
import argparse
import time

import config
import enron_dataset
import vector_store
from database import init_db, insert_email, reset_db

BATCH_SIZE = 100


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-c", "--custodians", nargs="+", default=config.ENRON_CUSTODIANS,
                        help=f"custodian mailboxes to ingest (default: {' '.join(config.ENRON_CUSTODIANS)})")
    parser.add_argument("-n", "--max-emails", type=int, default=config.ENRON_MAX_EMAILS,
                        help="max emails per custodian, 0 = all (default: %(default)s)")
    parser.add_argument("--reset", action="store_true", help="wipe both databases before ingesting")
    parser.add_argument("--list", action="store_true", help="list available custodians and exit")
    args = parser.parse_args()

    custodians = enron_dataset.list_custodians()

    if args.list:
        for name, info in sorted(custodians.items(), key=lambda kv: kv[1]["size"]):
            print(f"{name:25} {info['size'] / 1e6:9.1f} MB  ({len(info['files'])} file(s))")
        return

    unknown = [c for c in args.custodians if c not in custodians]
    if unknown:
        parser.error(f"unknown custodian(s): {', '.join(unknown)} — see --list")

    total_mb = sum(custodians[c]["size"] for c in args.custodians) / 1e6
    print(f"Custodians: {', '.join(args.custodians)} ({total_mb:.0f} MB download, cached in {config.ENRON_CACHE_DIR})")

    if args.reset:
        reset_db()
        vector_store.reset()
    else:
        init_db()

    started = time.time()
    n_emails = n_attachments = n_chunks = 0
    batch = []
    for custodian in args.custodians:
        for email in enron_dataset.iter_emails(custodian, custodians[custodian]["files"], args.max_emails):
            insert_email(email)
            batch.append(email)
            n_emails += 1
            n_attachments += len(email["attachments"])
            if len(batch) == BATCH_SIZE:
                n_chunks += vector_store.add_emails(batch)
                batch = []
                print(f"  {n_emails} emails, {n_attachments} attachments, {n_chunks} chunks")
    n_chunks += vector_store.add_emails(batch)

    print(f"Done in {time.time() - started:.0f}s: {n_emails} emails, "
          f"{n_attachments} attachments ({', '.join(sorted(config.ENRON_ATTACHMENT_EXTENSIONS))}), {n_chunks} chunks")


if __name__ == "__main__":
    main()
