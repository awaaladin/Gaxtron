"""Ported from GaX/app/core/exceptions.py, minus the FastAPI-specific HTTPException helper —
DRF views catch these and map to responses themselves."""

from rest_framework import status as drf_status


class AppError(Exception):
    def __init__(self, message: str, status_code: int = drf_status.HTTP_400_BAD_REQUEST):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class PaymentNotFoundError(AppError):
    def __init__(self):
        super().__init__("Payment not found", drf_status.HTTP_404_NOT_FOUND)


class DuplicatePaymentError(AppError):
    def __init__(self):
        super().__init__("Duplicate payment request", drf_status.HTTP_409_CONFLICT)
