"""Generates a couple of random sample broker->client emails and loads them
into both the normal DB and the vector DB. Run directly to (re)seed."""
import random
import uuid
from datetime import datetime, timedelta

from database import init_db, insert_email
from vector_store import add_email

CLIENTS = [
    {"name": "Jan Peeters", "email": "jan.peeters@example.com"},
    {"name": "Sophie Dubois", "email": "sophie.dubois@example.com"},
    {"name": "Ahmed El Amrani", "email": "ahmed.elamrani@example.com"},
]

TEMPLATES = [
    {
        "subject": "Uw offerte brandverzekering",
        "body": (
            "Beste {name},\n\n"
            "In bijlage vindt u de offerte voor uw brandverzekering, referentie {ref}. "
            "De jaarlijkse premie bedraagt {premium} euro. "
            "Laat ons weten of u akkoord gaat, dan maken we de polis in orde.\n\n"
            "Met vriendelijke groeten,\nUw verzekeringsmakelaar"
        ),
    },
    {
        "subject": "Bevestiging schadedossier auto",
        "body": (
            "Beste {name},\n\n"
            "We bevestigen de opening van uw schadedossier {ref} na het ongeval van "
            "vorige week. De verzekeraar zal binnen de 10 werkdagen contact met u opnemen. "
            "Uw vrijstelling bedraagt {premium} euro.\n\n"
            "Met vriendelijke groeten,\nUw verzekeringsmakelaar"
        ),
    },
]


def generate_random_email() -> dict:
    client = random.choice(CLIENTS)
    template = random.choice(TEMPLATES)
    ref = f"REF-{random.randint(10000, 99999)}"
    premium = random.choice([120, 245, 380, 510])
    date = (datetime.now() - timedelta(days=random.randint(0, 30))).isoformat()
    return {
        "id": str(uuid.uuid4()),
        "client_name": client["name"],
        "client_email": client["email"],
        "subject": template["subject"],
        "body": template["body"].format(name=client["name"], ref=ref, premium=premium),
        "date": date,
    }


def seed(n: int = 2):
    init_db()
    for _ in range(n):
        email = generate_random_email()
        insert_email(email)
        add_email(email)
        print(f"Seeded email {email['id']} -> {email['client_name']}: {email['subject']}")


if __name__ == "__main__":
    seed()
