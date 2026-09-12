package com.gaxtron.mobile.data.network.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class ApiKeyCreateRequest(
    val name: String,
)

@Serializable
data class ApiKeyResponse(
    val id: Int,
    @SerialName("key_prefix") val keyPrefix: String,
    val name: String,
    @SerialName("is_active") val isActive: Boolean,
    @SerialName("created_at") val createdAt: String,
    @SerialName("last_used_at") val lastUsedAt: String? = null,
)

@Serializable
data class ApiKeyCreatedResponse(
    val id: Int,
    @SerialName("key_prefix") val keyPrefix: String,
    val name: String,
    @SerialName("is_active") val isActive: Boolean,
    @SerialName("created_at") val createdAt: String,
    @SerialName("last_used_at") val lastUsedAt: String? = null,
    /** Only ever sent once, at creation. Must be persisted client-side immediately. */
    @SerialName("api_key") val apiKey: String,
)
