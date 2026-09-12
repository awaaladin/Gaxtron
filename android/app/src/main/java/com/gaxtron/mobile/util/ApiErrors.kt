package com.gaxtron.mobile.util

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import retrofit2.HttpException
import java.io.IOException

/**
 * FastAPI error bodies look like {"detail": "message"} or, for validation errors,
 * {"detail": [{"msg": "..."}]}. Pull out something readable to show the user.
 */
fun Throwable.toUserMessage(): String {
    if (this is HttpException) {
        val body = response()?.errorBody()?.string()
        if (!body.isNullOrBlank()) {
            runCatching {
                val element = Json.parseToJsonElement(body).jsonObject["detail"]
                return when (element) {
                    is JsonArray -> element.firstOrNull()?.jsonObject?.get("msg")?.jsonPrimitive?.content
                    is JsonPrimitive -> element.content
                    else -> null
                } ?: "Request failed (HTTP ${code()})"
            }
        }
        return "Request failed (HTTP ${code()})"
    }
    if (this is IOException) return "Network error — check your connection and the base URL in Settings."
    return message ?: "Something went wrong"
}
