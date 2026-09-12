package com.gaxtron.mobile.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider

/** Plain-Kotlin ViewModel factory — no DI framework, just a constructor call. */
class ViewModelFactory(private val creator: () -> ViewModel) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T = creator() as T
}
