from typing import Literal

type AccountStatus = Literal["pending", "confirmed", "cancelled"]
type PaymentStatus = Literal["unpaid", "completed", "refunded", "failed", "cancelled"]
type TeeShirtSize = Literal["XS", "S", "M", "L", "XL", "XXL", "XXXL"]
type AgeGroup = Literal["adult", "child"]
