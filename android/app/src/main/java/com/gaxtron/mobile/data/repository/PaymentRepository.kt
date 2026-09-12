package com.gaxtron.mobile.data.repository

import com.gaxtron.mobile.data.SessionStore
import com.gaxtron.mobile.data.network.RetrofitProvider
import com.gaxtron.mobile.data.network.dto.CreatePaymentRequest
import com.gaxtron.mobile.data.network.dto.CreatePaymentResponse
import com.gaxtron.mobile.data.network.dto.PaymentResponse
import com.gaxtron.mobile.data.network.dto.PublicPaymentStatus
import com.gaxtron.mobile.data.network.dto.VerifyPaymentResponse

class PaymentRepository(private val session: SessionStore) {

    private val api get() = RetrofitProvider.apiFor(session.baseUrl.value)

    suspend fun createPayment(apiKey: String, amount: String, callbackUrl: String): CreatePaymentResponse =
        api.createPayment(apiKey, CreatePaymentRequest(amount = amount, callbackUrl = callbackUrl))

    suspend fun listPayments(apiKey: String): List<PaymentResponse> = api.listPayments(apiKey)

    suspend fun getPaymentMerchant(apiKey: String, id: Int): PaymentResponse = api.getPaymentMerchant(apiKey, id)

    suspend fun verifyPayment(apiKey: String, id: Int): VerifyPaymentResponse = api.verifyPayment(apiKey, id)

    /** No auth — used by "pay a link" mode. Accepts either the numeric id or the public_token. */
    suspend fun getPublicStatus(ref: String): PublicPaymentStatus = api.getPublicPaymentStatus(ref)
}
