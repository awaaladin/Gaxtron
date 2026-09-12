package com.gaxtron.mobile.util

import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter
import java.time.format.DateTimeParseException

private val displayFormat: DateTimeFormatter = DateTimeFormatter.ofPattern("MMM d, HH:mm")

/** Backend timestamps are ISO-8601, sometimes with an offset and sometimes naive UTC. */
fun formatTimestamp(raw: String?): String {
    if (raw.isNullOrBlank()) return "—"
    return try {
        OffsetDateTime.parse(raw).format(displayFormat)
    } catch (_: DateTimeParseException) {
        try {
            LocalDateTime.parse(raw).format(displayFormat)
        } catch (_: DateTimeParseException) {
            raw
        }
    }
}

fun formatAmount(amount: Double, currency: String): String {
    val trimmed = "%.6f".format(amount).trimEnd('0').trimEnd('.')
    return "${trimmed.ifEmpty { "0" }} $currency"
}

/** Same pending → confirming → confirmed/failed rule the web checkout page (checkout-page.js) uses. */
fun checkoutPhase(status: String, confirmations: Int): CheckoutPhase = when {
    status == "confirmed" -> CheckoutPhase.CONFIRMED
    status == "failed" || status == "expired" -> CheckoutPhase.FAILED
    confirmations > 0 -> CheckoutPhase.CONFIRMING
    else -> CheckoutPhase.PENDING
}

enum class CheckoutPhase { PENDING, CONFIRMING, CONFIRMED, FAILED }
