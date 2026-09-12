package com.gaxtron.mobile.data

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.gaxtron.mobile.BuildConfig
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.Serializable
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

@Serializable
data class SavedApiKey(
    val id: Int,
    val name: String,
    val keyPrefix: String,
    /** The raw secret — only ever known on the device that created it. */
    val rawKey: String,
)

@Serializable
data class SessionUser(
    val id: Int,
    val email: String,
    val username: String,
    val walletAddress: String? = null,
)

/**
 * Local session/credential storage, backed by EncryptedSharedPreferences.
 * Holds the JWT, the current user, the configurable backend base URL, and any
 * API keys created from this device (the server never re-sends a raw key after
 * creation, so this is the only place it's recoverable from).
 */
class SessionStore(context: Context) {

    private val json = Json { ignoreUnknownKeys = true }

    private val prefs: SharedPreferences = run {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            context,
            "gaxtron_secure_prefs",
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    private val _baseUrl = MutableStateFlow(prefs.getString(KEY_BASE_URL, null) ?: BuildConfig.DEFAULT_BASE_URL)
    val baseUrl: StateFlow<String> = _baseUrl.asStateFlow()

    private val _token = MutableStateFlow(prefs.getString(KEY_TOKEN, null))
    val token: StateFlow<String?> = _token.asStateFlow()

    private val _user = MutableStateFlow(readUser())
    val user: StateFlow<SessionUser?> = _user.asStateFlow()

    private val _apiKeys = MutableStateFlow(readApiKeys())
    val apiKeys: StateFlow<List<SavedApiKey>> = _apiKeys.asStateFlow()

    fun setBaseUrl(url: String) {
        prefs.edit().putString(KEY_BASE_URL, url).apply()
        _baseUrl.value = url
    }

    fun signIn(token: String, user: SessionUser) {
        prefs.edit()
            .putString(KEY_TOKEN, token)
            .putString(KEY_USER, json.encodeToString(SessionUser.serializer(), user))
            .apply()
        _token.value = token
        _user.value = user
    }

    fun updateUser(user: SessionUser) {
        prefs.edit().putString(KEY_USER, json.encodeToString(SessionUser.serializer(), user)).apply()
        _user.value = user
    }

    fun signOut() {
        prefs.edit().remove(KEY_TOKEN).remove(KEY_USER).remove(KEY_API_KEYS).apply()
        _token.value = null
        _user.value = null
        _apiKeys.value = emptyList()
    }

    fun addApiKey(key: SavedApiKey) {
        val updated = _apiKeys.value.filterNot { it.id == key.id } + key
        persistApiKeys(updated)
    }

    fun removeApiKey(id: Int) {
        persistApiKeys(_apiKeys.value.filterNot { it.id == id })
    }

    private fun persistApiKeys(keys: List<SavedApiKey>) {
        prefs.edit().putString(KEY_API_KEYS, json.encodeToString(keys)).apply()
        _apiKeys.value = keys
    }

    private fun readUser(): SessionUser? {
        val raw = prefs.getString(KEY_USER, null) ?: return null
        return runCatching { json.decodeFromString(SessionUser.serializer(), raw) }.getOrNull()
    }

    private fun readApiKeys(): List<SavedApiKey> {
        val raw = prefs.getString(KEY_API_KEYS, null) ?: return emptyList()
        return runCatching { json.decodeFromString<List<SavedApiKey>>(raw) }.getOrNull() ?: emptyList()
    }

    companion object {
        private const val KEY_BASE_URL = "base_url"
        private const val KEY_TOKEN = "jwt_token"
        private const val KEY_USER = "session_user"
        private const val KEY_API_KEYS = "saved_api_keys"
    }
}
