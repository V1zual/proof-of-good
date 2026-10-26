"""Async client for the PayPal REST API (sandbox by default).

Money flow of Proof of Good:
  donor pays  -> Orders v2 (intent CAPTURE): the money lands on the platform account and waits there
  proof OK    -> Payouts v1: the tranche goes to the volunteer's PayPal
  campaign fails -> Refunds v2: every captured donation goes back to its donor
"""
import time
import uuid

import httpx

from . import config


class PayPalError(Exception):
    def __init__(self, status: int, body: str):
        self.status, self.body = status, body
        super().__init__(f"PayPal {status}: {body[:300]}")


class PayPal:
    def __init__(self):
        self.http = httpx.AsyncClient(base_url=config.PAYPAL_API, timeout=30)
        self._token, self._expires = "", 0.0

    async def _auth(self) -> str:
        if self._token and time.time() < self._expires - 60:
            return self._token
        r = await self.http.post(
            "/v1/oauth2/token",
            data={"grant_type": "client_credentials"},
            auth=(config.secret("PAYPAL_CLIENT_ID"), config.secret("PAYPAL_CLIENT_SECRET")),
        )
        if r.status_code >= 400:
            raise PayPalError(r.status_code, r.text)
        data = r.json()
        self._token, self._expires = data["access_token"], time.time() + data["expires_in"]
        return self._token

    async def call(self, method: str, path: str, body: dict | None = None, **headers) -> dict:
        headers = {"Authorization": f"Bearer {await self._auth()}",
                   "PayPal-Request-Id": uuid.uuid4().hex, **headers}
        r = await self.http.request(method, path, json=body, headers=headers)
        if r.status_code >= 400:
            raise PayPalError(r.status_code, r.text)
        return r.json() if r.content else {}

    # --- Orders v2: donations ---

    async def create_order(self, amount: float, currency: str, description: str, reference: str) -> dict:
        """A donation order; the PayPal button on the site opens it for the donor's approval."""
        return await self.call("POST", "/v2/checkout/orders", {
            "intent": "CAPTURE",
            "purchase_units": [{
                "reference_id": reference,
                "description": description[:127],
                "amount": {"currency_code": currency, "value": f"{amount:.2f}"},
            }],
        })

    async def capture_order(self, order_id: str) -> dict:
        """Takes the approved donation; returns the capture (id, amount, payer)."""
        r = await self.call("POST", f"/v2/checkout/orders/{order_id}/capture", {},
                            Prefer="return=representation")
        cap = r["purchase_units"][0]["payments"]["captures"][0]
        payer = r.get("payer", {})
        name = payer.get("name", {})
        return {
            "capture_id": cap["id"],
            "status": cap["status"],
            "amount": float(cap["amount"]["value"]),
            "currency": cap["amount"]["currency_code"],
            "payer_name": " ".join(x for x in (name.get("given_name"), name.get("surname")) if x),
            "payer_email": payer.get("email_address", ""),
            "payer_id": payer.get("payer_id", ""),
        }

    async def get_order(self, order_id: str) -> dict:
        return await self.call("GET", f"/v2/checkout/orders/{order_id}")

    # --- Refunds v2: campaign failed ---

    async def refund(self, capture_id: str, amount: float, currency: str, note: str) -> dict:
        return await self.call("POST", f"/v2/payments/captures/{capture_id}/refund", {
            "amount": {"value": f"{amount:.2f}", "currency_code": currency},
            "note_to_payer": note[:255],
        }, Prefer="return=representation")

    # --- Payouts v1: verified tranche -> volunteer ---

    async def payout(self, email: str, amount: float, currency: str, subject: str, note: str) -> dict:
        batch = uuid.uuid4().hex[:16]
        r = await self.call("POST", "/v1/payments/payouts", {
            "sender_batch_header": {"sender_batch_id": batch, "email_subject": subject[:255],
                                    "email_message": note[:1000]},
            "items": [{"recipient_type": "EMAIL", "receiver": email, "note": note[:4000],
                       "sender_item_id": batch, "amount": {"value": f"{amount:.2f}", "currency": currency}}],
        })
        return {"batch_id": r["batch_header"]["payout_batch_id"], "status": r["batch_header"]["batch_status"]}

    async def payout_status(self, batch_id: str) -> dict:
        r = await self.call("GET", f"/v1/payments/payouts/{batch_id}")
        item = (r.get("items") or [{}])[0]
        return {"batch": r["batch_header"]["batch_status"], "item": item.get("transaction_status", ""),
                "transaction_id": item.get("transaction_id", ""),
                "fee": (r["batch_header"].get("fees") or {}).get("value", "")}
