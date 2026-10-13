from app.models import Alum


def counts_as_referral(referred_alum: Alum) -> bool:
    """Whether a referred account qualifies; default is confirmed status.

    Alternative policy: require a completed payment instead of confirmation.
    """
    return referred_alum.status == "confirmed"
