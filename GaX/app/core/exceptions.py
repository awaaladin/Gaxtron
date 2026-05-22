from fastapi import HTTPException, status


class AppError(Exception):
    """Base application error."""

    def __init__(self, message: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class PaymentNotFoundError(AppError):
    def __init__(self):
        super().__init__("Payment not found", status.HTTP_404_NOT_FOUND)


class DuplicatePaymentError(AppError):
    def __init__(self):
        super().__init__("Duplicate payment request", status.HTTP_409_CONFLICT)


def to_http_exception(exc: AppError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)
