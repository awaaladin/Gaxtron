package com.gaxtron.mobile.data.network

import com.gaxtron.mobile.data.network.dto.ApiKeyCreateRequest
import com.gaxtron.mobile.data.network.dto.ApiKeyCreatedResponse
import com.gaxtron.mobile.data.network.dto.ApiKeyResponse
import com.gaxtron.mobile.data.network.dto.CreatePaymentRequest
import com.gaxtron.mobile.data.network.dto.CreatePaymentResponse
import com.gaxtron.mobile.data.network.dto.PaymentResponse
import com.gaxtron.mobile.data.network.dto.PublicPaymentStatus
import com.gaxtron.mobile.data.network.dto.RegisterRequest
import com.gaxtron.mobile.data.network.dto.TokenResponse
import com.gaxtron.mobile.data.network.dto.UserResponse
import com.gaxtron.mobile.data.network.dto.VerifyPaymentResponse
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.Field
import retrofit2.http.FormUrlEncoded
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.Path

/**
 * Mirrors GaX/app/api/routers/{auth,api_keys,payments,checkout}.py exactly.
 *
 * Auth split matches the backend: JWT (Bearer) for the auth and api-keys routes,
 * X-API-Key for payment-mutating endpoints — see GaX/app/api/deps.py.
 */
interface ApiService {

    @POST("auth/register")
    suspend fun register(@Body body: RegisterRequest): TokenResponse

    @FormUrlEncoded
    @POST("auth/login")
    suspend fun login(
        @Field("username") email: String,
        @Field("password") password: String,
    ): TokenResponse

    @GET("auth/me")
    suspend fun me(@Header("Authorization") bearer: String): UserResponse

    @GET("api-keys")
    suspend fun listApiKeys(@Header("Authorization") bearer: String): List<ApiKeyResponse>

    @POST("api-keys")
    suspend fun createApiKey(
        @Header("Authorization") bearer: String,
        @Body body: ApiKeyCreateRequest,
    ): ApiKeyCreatedResponse

    @DELETE("api-keys/{id}")
    suspend fun revokeApiKey(@Header("Authorization") bearer: String, @Path("id") id: Int)

    @POST("api-keys/{id}/regenerate")
    suspend fun regenerateApiKey(
        @Header("Authorization") bearer: String,
        @Path("id") id: Int,
    ): ApiKeyCreatedResponse

    @POST("create-payment")
    suspend fun createPayment(
        @Header("X-API-Key") apiKey: String,
        @Body body: CreatePaymentRequest,
    ): CreatePaymentResponse

    @GET("payments")
    suspend fun listPayments(@Header("X-API-Key") apiKey: String): List<PaymentResponse>

    @GET("payment/{id}/merchant")
    suspend fun getPaymentMerchant(
        @Header("X-API-Key") apiKey: String,
        @Path("id") id: Int,
    ): PaymentResponse

    @GET("verify-payment/{id}")
    suspend fun verifyPayment(
        @Header("X-API-Key") apiKey: String,
        @Path("id") id: Int,
    ): VerifyPaymentResponse

    /** Public, unauthenticated — powers the "pay a link" checkout mode. */
    @GET("payment/{ref}")
    suspend fun getPublicPaymentStatus(@Path("ref") ref: String): PublicPaymentStatus
}
