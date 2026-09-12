package com.gaxtron.mobile.data.repository

import com.gaxtron.mobile.data.SessionStore
import com.gaxtron.mobile.data.SessionUser
import com.gaxtron.mobile.data.network.RetrofitProvider
import com.gaxtron.mobile.data.network.dto.RegisterRequest

class AuthRepository(private val session: SessionStore) {

    private val api get() = RetrofitProvider.apiFor(session.baseUrl.value)

    suspend fun register(email: String, username: String, password: String) {
        val tokenResponse = api.register(RegisterRequest(email, username, password))
        finishLogin(tokenResponse.accessToken)
    }

    suspend fun login(email: String, password: String) {
        val tokenResponse = api.login(email, password)
        finishLogin(tokenResponse.accessToken)
    }

    /** access_token / token_type is all the backend actually returns — fetch the profile separately. */
    private suspend fun finishLogin(accessToken: String) {
        val profile = api.me("Bearer $accessToken")
        session.signIn(
            token = accessToken,
            user = SessionUser(
                id = profile.id,
                email = profile.email,
                username = profile.username,
                walletAddress = profile.walletAddress,
            ),
        )
    }

    suspend fun refreshProfile() {
        val token = session.token.value ?: return
        val profile = api.me("Bearer $token")
        session.updateUser(
            SessionUser(
                id = profile.id,
                email = profile.email,
                username = profile.username,
                walletAddress = profile.walletAddress,
            ),
        )
    }

    fun logout() = session.signOut()
}
