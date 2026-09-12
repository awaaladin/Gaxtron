package com.gaxtron.mobile.data.network.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class RegisterRequest(
    val email: String,
    val username: String,
    val password: String,
)

@Serializable
data class TokenResponse(
    @SerialName("access_token") val accessToken: String,
    @SerialName("token_type") val tokenType: String,
)

@Serializable
data class UserResponse(
    val id: Int,
    val email: String,
    val username: String,
    @SerialName("is_active") val isActive: Boolean,
    @SerialName("wallet_address") val walletAddress: String? = null,
)
