from typing import Literal

type AccountStatus = Literal["pending", "confirmed", "cancelled"]
type PaymentStatus = Literal["unpaid", "completed", "refunded", "failed", "cancelled"]
type TeeShirtSize = Literal["XS", "S", "M", "L", "XL", "XXL", "XXXL"]
type AcademicGroup = Literal["science", "humanities", "business_studies"]
type AgeGroup = Literal["adult", "child"]
type SubmissionStatus = Literal["submitted", "under_review", "approved", "rejected", "contacted"]
type StallApplicationStatus = Literal["applied", "approved", "rejected"]
type StallFeeStatus = Literal["not_required", "pending", "paid"]
