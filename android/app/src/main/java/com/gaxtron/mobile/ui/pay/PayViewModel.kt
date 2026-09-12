package com.gaxtron.mobile.ui.pay

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.gaxtron.mobile.data.network.dto.PublicPaymentStatus
import com.gaxtron.mobile.data.repository.PaymentRepository
import com.gaxtron.mobile.util.CheckoutPhase
import com.gaxtron.mobile.util.checkoutPhase
import com.gaxtron.mobile.util.toUserMessage
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** Same 3s poll cadence as frontend/js/checkout-page.js (POLL_MS = 3000). */
private const val POLL_INTERVAL_MS = 3000L

class PayViewModel(private val repository: PaymentRepository) : ViewModel() {

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _status = MutableStateFlow<PublicPaymentStatus?>(null)
    val status: StateFlow<PublicPaymentStatus?> = _status.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private var pollJob: Job? = null

    /** Used by the entry screen to validate a reference exists before navigating to checkout. */
    fun lookup(ref: String, onResult: (Result<Unit>) -> Unit) {
        viewModelScope.launch {
            _isLoading.value = true
            try {
                _status.value = repository.getPublicStatus(ref)
                onResult(Result.success(Unit))
            } catch (e: Exception) {
                onResult(Result.failure(RuntimeException(e.toUserMessage(), e)))
            } finally {
                _isLoading.value = false
            }
        }
    }

    fun startPolling(ref: String) {
        stopPolling()
        pollJob = viewModelScope.launch {
            while (true) {
                try {
                    val result = repository.getPublicStatus(ref)
                    _status.value = result
                    _error.value = null
                    val phase = checkoutPhase(result.status, result.confirmations)
                    if (phase == CheckoutPhase.CONFIRMED || phase == CheckoutPhase.FAILED) break
                } catch (e: Exception) {
                    _error.value = e.toUserMessage()
                }
                delay(POLL_INTERVAL_MS)
            }
        }
    }

    fun stopPolling() {
        pollJob?.cancel()
        pollJob = null
    }

    override fun onCleared() {
        super.onCleared()
        stopPolling()
    }
}
