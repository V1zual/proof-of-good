"""Demo campaigns for judges and the video. Every card here is the demo card (simulated bank feed)."""
from . import store

CAMPAIGNS = [
    ({
        "id": "try", "try_it": 1, "title": "Try it yourself: water for a shelter",
        "story": "A small test campaign for judges and testers. Donate $10 with the sandbox buyer and the first "
                 "tranche goes to the volunteer's demo card at once. Then open the volunteer portal (code TRY-IT): "
                 "make the card pay, take a photo of any bottle of water near you and send it. Try cheating too — "
                 "withdraw cash or send money to another card and watch the campaign freeze.",
        "place": "Ivano-Frankivsk, Ukraine", "country": "UA",
        "volunteer_name": "Test Volunteer", "volunteer_email": "volunteer-test@example.com",
        "volunteer_code": "TRY-IT", "card_label": "Demo card •• 2026",
    }, [
        {"title": "Bottled water for the shelter", "amount": 10},
        {"title": "Paper cups and napkins", "amount": 15},
        {"title": "Snacks for the kids", "amount": 25},
    ]),
    ({
        "id": "generator", "title": "A generator for the maternity hospital",
        "story": "When the power goes out in Ivano-Frankivsk, the maternity ward switches to flashlights. A 3 kW "
                 "petrol generator keeps the incubators and the delivery room running through a blackout. The money "
                 "waits on PayPal and reaches the volunteer one purchase at a time — every payment from his "
                 "campaign card is visible here, and the next part is released only after the last one is proven.",
        "place": "Ivano-Frankivsk, Ukraine", "country": "UA",
        "volunteer_name": "Andriy K.", "volunteer_email": "volunteer-andriy@example.com",
        "volunteer_code": "GEN-2026", "card_label": "Demo card •• 4821",
    }, [
        {"title": "Petrol generator Hyundai HHY 3050F", "amount": 900},
        {"title": "Fuel canisters and 40 l of petrol", "amount": 120},
        {"title": "Delivery and installation", "amount": 80},
    ]),
    ({
        "id": "shelter", "title": "Warm winter for the school shelter",
        "story": "School №12 turned its basement into a bomb shelter for 300 children. Three oil heaters and "
                 "thermal mats mean the kids can sit through an alarm without freezing.",
        "place": "Kharkiv, Ukraine", "country": "UA",
        "volunteer_name": "Olena M.", "volunteer_email": "volunteer-olena@example.com",
        "volunteer_code": "WARM-12", "card_label": "Demo card •• 1207",
    }, [
        {"title": "3 oil heaters 2.5 kW", "amount": 240},
        {"title": "30 thermal mats", "amount": 150},
    ]),
    ({
        "id": "paws", "title": "Food for the Paws animal shelter",
        "story": "Eighty dogs and cats, one volunteer, winter ahead. A tonne of dry food lasts the shelter "
                 "about two months.",
        "place": "Lviv, Ukraine", "country": "UA",
        "volunteer_name": "Taras H.", "volunteer_email": "volunteer-taras@example.com",
        "volunteer_code": "PAWS-80", "card_label": "Demo card •• 8080",
    }, [
        {"title": "1 000 kg of dry dog and cat food", "amount": 650},
        {"title": "Vet visit and vaccines", "amount": 200},
    ]),
]


def seed(wipe: bool = False) -> None:
    if wipe:
        store.reset()
    for c, tranches in CAMPAIGNS:
        if not store.campaign(c["id"]):
            store.add_campaign(c, tranches)
            store.log(c["id"], "note", f"Campaign created by {c['volunteer_name']} — {len(tranches)} tranches; "
                                       f"money goes to the transparent card one tranche at a time")
