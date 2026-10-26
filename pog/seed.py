"""Demo campaigns for judges and the video."""
from . import store

CAMPAIGNS = [
    ({
        "id": "generator", "title": "A generator for the maternity hospital",
        "story": "When the power goes out in Ivano-Frankivsk, the maternity ward switches to flashlights. "
                 "A 3 kW petrol generator keeps the incubators and the delivery room running through a blackout. "
                 "The money stays on hold until our AI auditor sees the receipt and the generator at the hospital.",
        "place": "Ivano-Frankivsk, Ukraine", "country": "UA",
        "volunteer_name": "Andriy K.", "volunteer_email": "volunteer-andriy@example.com",
        "volunteer_code": "GEN-2026",
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
        "volunteer_code": "WARM-12",
    }, [
        {"title": "3 oil heaters 2.5 kW", "amount": 240},
        {"title": "30 thermal mats", "amount": 150},
    ]),
    ({
        "id": "paws", "title": "Food for the Paws animal shelter",
        "story": "Eighty dogs and cats, one volunteer, winter ahead. A tonne of dry food lasts the shelter "
                 "about two months. Proof: the receipt and the pallet in the shelter's yard.",
        "place": "Lviv, Ukraine", "country": "UA",
        "volunteer_name": "Taras H.", "volunteer_email": "volunteer-taras@example.com",
        "volunteer_code": "PAWS-80",
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
            store.log(c["id"], "note", f"Campaign created by {c['volunteer_name']} — "
                                       f"{len(tranches)} tranches, released one by one after proof")
