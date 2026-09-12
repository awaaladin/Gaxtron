package com.gaxtron.mobile.ui.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.gaxtron.mobile.data.repository.AuthRepository
import com.gaxtron.mobile.util.toUserMessage
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class AuthViewModel(private val repository: AuthRepository) : ViewModel() {

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    fun login(email: String, password: String, onResult: (Result<Unit>) -> Unit) {
        runAuthCall(onResult) { repository.login(email, password) }
    }

    fun register(email: String, username: String, password: String, onResult: (Result<Unit>) -> Unit) {
        runAuthCall(onResult) { repository.register(email, username, password) }
    }

    private fun runAuthCall(onResult: (Result<Unit>) -> Unit, block: suspend () -> Unit) {
        viewModelScope.launch {
            _isLoading.value = true
            try {
                block()
                onResult(Result.success(Unit))
            } catch (e: Exception) {
                onResult(Result.failure(RuntimeException(e.toUserMessage(), e)))
            } finally {
                _isLoading.value = false
            }
        }
    }
}
