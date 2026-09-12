package com.gaxtron.mobile.data.network.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class CreatePaymentRequest(
    /** Sent as a JSON string (matches README curl examples) to avoid float precision loss. */
    val amount: String,
    @SerialName("callback_url") val callbackUrl: String,
    @SerialName("idempotency_key") val idempotencyKey: String? = null,
)

@Serializable
data class CreatePaymentResponse(
    @SerialName("payment_id") val paymentId: Int,
    @SerialName("payment_token") val paymentToken: String,
    @SerialName("payment_url") val paymentUrl: String,
    @SerialName("checkout_url") val checkoutUrl: String,
    @SerialName("wallet_address") val walletAddress: String,
    val amount: Double,
    val currency: String,
    val chain: String,
    val status: String,
    @SerialName("callback_url") val callbackUrl: String,
    @SerialName("tx_hash") val txHash: String? = null,
    val confirmations: Int = 0,
    @SerialName("created_at") val createdAt: String,
    @SerialName("expires_at") val expiresAt: String? = null,
)

@Serializable
data class PaymentResponse(
    val id: Int,
    val amount: Double,
    val chain: String,
    val currency: String,
    val status: String,
    @SerialName("wallet_address") val walletAddress: String,
    @SerialName("callback_url") val callbackUrl: String,
    @SerialName("tx_hash") val txHash: String? = null,
    val confirmations: Int = 0,
    @SerialName("payment_url") val paymentUrl: String? = null,
    @SerialName("created_at") val createdAt: String,
    @SerialName("confirmed_at") val confirmedAt: String? = null,
    @SerialName("expires_at") val expiresAt: String? = null,
)

@Serializable
data class VerifyPaymentResponse(
    val id: Int,
    val status: String,
    val amount: Double,
    val chain: String,
    val currency: String,
    @SerialName("wallet_address") val walletAddress: String,
    @SerialName("tx_hash") val txHash: String? = null,
    val confirmations: Int = 0,
    @SerialName("payment_url") val paymentUrl: String? = null,
    @SerialName("confirmed_at") val confirmedAt: String? = null,
    @SerialName("expires_at") val expiresAt: String? = null,
)

@Serializable
data class PublicPaymentStatus(
    val id: Int,
    @SerialName("public_token") val publicToken: String? = null,
    val amount: Double,
    val currency: String,
    val chain: String,
    val status: String,
    @SerialName("wallet_address") val walletAddress: String,
    val address: String? = null,
    @SerialName("tx_hash") val txHash: String? = null,
    val confirmations: Int = 0,
    @SerialName("required_confirmations") val requiredConfirmations: Int = 3,
    val network: String,
    @SerialName("created_at") val createdAt: String,
    @SerialName("confirmed_at") val confirmedAt: String? = null,
    @SerialName("expires_at") val expiresAt: String? = null,
)
