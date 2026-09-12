package com.gaxtron.mobile.ui.merchant

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.gaxtron.mobile.data.SavedApiKey
import com.gaxtron.mobile.data.network.dto.ApiKeyResponse
import com.gaxtron.mobile.data.network.dto.CreatePaymentResponse
import com.gaxtron.mobile.data.network.dto.PaymentResponse
import com.gaxtron.mobile.data.network.dto.VerifyPaymentResponse
import com.gaxtron.mobile.data.repository.ApiKeyRepository
import com.gaxtron.mobile.data.repository.PaymentRepository
import com.gaxtron.mobile.util.toUserMessage
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class MerchantViewModel(
    private val paymentRepository: PaymentRepository,
    private val apiKeyRepository: ApiKeyRepository,
) : ViewModel() {

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _payments = MutableStateFlow<List<PaymentResponse>>(emptyList())
    val payments: StateFlow<List<PaymentResponse>> = _payments.asStateFlow()

    private val _serverApiKeys = MutableStateFlow<List<ApiKeyResponse>>(emptyList())
    val serverApiKeys: StateFlow<List<ApiKeyResponse>> = _serverApiKeys.asStateFlow()

    fun loadPayments(apiKey: String, onError: (String) -> Unit = {}) {
        viewModelScope.launch {
            _isLoading.value = true
            try {
                _payments.value = paymentRepository.listPayments(apiKey)
            } catch (e: Exception) {
                onError(e.toUserMessage())
            } finally {
                _isLoading.value = false
            }
        }
    }

    fun createPayment(
        apiKey: String,
        amount: String,
        callbackUrl: String,
        onResult: (Result<CreatePaymentResponse>) -> Unit,
    ) {
        viewModelScope.launch {
            _isLoading.value = true
            try {
                val payment = paymentRepository.createPayment(apiKey, amount, callbackUrl)
                onResult(Result.success(payment))
            } catch (e: Exception) {
                onResult(Result.failure(RuntimeException(e.toUserMessage(), e)))
            } finally {
                _isLoading.value = false
            }
        }
    }

    fun verifyPayment(apiKey: String, id: Int, onResult: (Result<VerifyPaymentResponse>) -> Unit) {
        viewModelScope.launch {
            try {
                onResult(Result.success(paymentRepository.verifyPayment(apiKey, id)))
            } catch (e: Exception) {
                onResult(Result.failure(RuntimeException(e.toUserMessage(), e)))
            }
        }
    }

    fun refreshServerApiKeys(onError: (String) -> Unit = {}) {
        viewModelScope.launch {
            _isLoading.value = true
            try {
                _serverApiKeys.value = apiKeyRepository.listApiKeys()
            } catch (e: Exception) {
                onError(e.toUserMessage())
            } finally {
                _isLoading.value = false
            }
        }
    }

    fun createApiKey(name: String, onResult: (Result<SavedApiKey>) -> Unit) {
        viewModelScope.launch {
            _isLoading.value = true
            try {
                val saved = apiKeyRepository.createApiKey(name)
                onResult(Result.success(saved))
                refreshServerApiKeys()
            } catch (e: Exception) {
                onResult(Result.failure(RuntimeException(e.toUserMessage(), e)))
            } finally {
                _isLoading.value = false
            }
        }
    }

    fun revokeApiKey(id: Int, onResult: (Result<Unit>) -> Unit) {
        viewModelScope.launch {
            try {
                apiKeyRepository.revokeApiKey(id)
                onResult(Result.success(Unit))
                refreshServerApiKeys()
            } catch (e: Exception) {
                onResult(Result.failure(RuntimeException(e.toUserMessage(), e)))
            }
        }
    }
}
