package com.gaxtron.mobile.data.repository

import com.gaxtron.mobile.data.SavedApiKey
import com.gaxtron.mobile.data.SessionStore
import com.gaxtron.mobile.data.network.RetrofitProvider
import com.gaxtron.mobile.data.network.dto.ApiKeyCreateRequest
import com.gaxtron.mobile.data.network.dto.ApiKeyResponse

class ApiKeyRepository(private val session: SessionStore) {

    private val api get() = RetrofitProvider.apiFor(session.baseUrl.value)
    private fun bearer() = "Bearer ${session.token.value.orEmpty()}"

    suspend fun listApiKeys(): List<ApiKeyResponse> = api.listApiKeys(bearer())

    /** Creates the key server-side and immediately saves the one-time raw value locally. */
    suspend fun createApiKey(name: String): SavedApiKey {
        val created = api.createApiKey(bearer(), ApiKeyCreateRequest(name))
        val saved = SavedApiKey(id = created.id, name = created.name, keyPrefix = created.keyPrefix, rawKey = created.apiKey)
        session.addApiKey(saved)
        return saved
    }

    suspend fun revokeApiKey(id: Int) {
        api.revokeApiKey(bearer(), id)
        session.removeApiKey(id)
    }

    suspend fun regenerateApiKey(id: Int): SavedApiKey {
        val regenerated = api.regenerateApiKey(bearer(), id)
        session.removeApiKey(id)
        val saved = SavedApiKey(
            id = regenerated.id,
            name = regenerated.name,
            keyPrefix = regenerated.keyPrefix,
            rawKey = regenerated.apiKey,
        )
        session.addApiKey(saved)
        return saved
    }
}
