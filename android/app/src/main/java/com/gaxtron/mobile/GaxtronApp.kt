package com.gaxtron.mobile

import android.app.Application
import com.gaxtron.mobile.data.SessionStore
import com.gaxtron.mobile.data.repository.ApiKeyRepository
import com.gaxtron.mobile.data.repository.AuthRepository
import com.gaxtron.mobile.data.repository.PaymentRepository

/**
 * Small hand-rolled DI container — no Hilt/Koin, so the wiring here is
 * plain constructor calls anyone new to the project can follow top to bottom.
 */
class GaxtronApp : Application() {

    lateinit var session: SessionStore
        private set
    lateinit var authRepository: AuthRepository
        private set
    lateinit var apiKeyRepository: ApiKeyRepository
        private set
    lateinit var paymentRepository: PaymentRepository
        private set

    override fun onCreate() {
        super.onCreate()
        session = SessionStore(this)
        authRepository = AuthRepository(session)
        apiKeyRepository = ApiKeyRepository(session)
        paymentRepository = PaymentRepository(session)
    }
}
