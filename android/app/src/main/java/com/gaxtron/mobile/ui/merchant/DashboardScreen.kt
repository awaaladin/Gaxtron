package com.gaxtron.mobile.ui.merchant

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.VpnKey
import androidx.compose.material3.OutlinedCard
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.gaxtron.mobile.data.SavedApiKey
import com.gaxtron.mobile.data.SessionStore
import com.gaxtron.mobile.data.network.dto.PaymentResponse
import com.gaxtron.mobile.ui.ViewModelFactory
import com.gaxtron.mobile.util.checkoutPhase
import com.gaxtron.mobile.util.CheckoutPhase
import com.gaxtron.mobile.util.formatAmount
import com.gaxtron.mobile.util.formatTimestamp

@Composable
fun DashboardScreen(
    session: SessionStore,
    viewModelFactory: ViewModelFactory,
    onCreatePayment: () -> Unit,
    onOpenPayment: (Int) -> Unit,
    onOpenApiKeys: () -> Unit,
) {
    val viewModel: MerchantViewModel = viewModel(factory = viewModelFactory)
    val payments by viewModel.payments.collectAsState()
    val isLoading by viewModel.isLoading.collectAsState()
    val apiKeys by session.apiKeys.collectAsState()
    val activeKey: SavedApiKey? = apiKeys.lastOrNull()
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(activeKey?.rawKey) {
        activeKey?.let { viewModel.loadPayments(it.rawKey) { message -> error = message } }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Payments") },
                actions = {
                    IconButton(onClick = onOpenApiKeys) {
                        Icon(Icons.Filled.VpnKey, contentDescription = "API keys")
                    }
                },
            )
        },
        floatingActionButton = {
            if (activeKey != null) {
                FloatingActionButton(onClick = onCreatePayment) {
                    Icon(Icons.Filled.Add, contentDescription = "Create payment")
                }
            }
        },
    ) { padding ->
        Column(modifier = Modifier.padding(padding)) {
            if (activeKey == null) {
                NoApiKeyNotice(onOpenApiKeys)
            } else if (isLoading && payments.isEmpty()) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
            } else if (error != null && payments.isEmpty()) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text(error ?: "", color = MaterialTheme.colorScheme.error)
                }
            } else if (payments.isEmpty()) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text("No payments yet — tap + to create one.")
                }
            } else {
                LazyColumn(contentPadding = PaddingValues(16.dp)) {
                    items(payments, key = { it.id }) { payment ->
                        PaymentRow(payment, onClick = { onOpenPayment(payment.id) })
                    }
                }
            }
        }
    }
}

@Composable
private fun NoApiKeyNotice(onOpenApiKeys: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Text("You need an API key before you can create or view payments.", style = MaterialTheme.typography.titleMedium)
        Text(
            "Payment endpoints authenticate with an API key, not your login — create one in API Keys.",
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.padding(top = 8.dp),
        )
        androidx.compose.material3.Button(onClick = onOpenApiKeys, modifier = Modifier.padding(top = 16.dp)) {
            Text("Go to API Keys")
        }
    }
}

@Composable
private fun PaymentRow(payment: PaymentResponse, onClick: () -> Unit) {
    OutlinedCard(
        onClick = onClick,
        modifier = Modifier
            .fillMaxWidth()
            .padding(bottom = 8.dp),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(formatAmount(payment.amount, payment.currency), style = MaterialTheme.typography.titleMedium)
            Text("#${payment.id} · ${formatTimestamp(payment.createdAt)}", style = MaterialTheme.typography.bodyMedium)
            Text(
                statusLabel(checkoutPhase(payment.status, payment.confirmations)),
                style = MaterialTheme.typography.labelLarge,
                color = statusColor(checkoutPhase(payment.status, payment.confirmations)),
            )
        }
    }
}

@Composable
fun statusColor(phase: CheckoutPhase) = when (phase) {
    CheckoutPhase.PENDING -> com.gaxtron.mobile.ui.theme.StatusPending
    CheckoutPhase.CONFIRMING -> com.gaxtron.mobile.ui.theme.StatusConfirming
    CheckoutPhase.CONFIRMED -> com.gaxtron.mobile.ui.theme.StatusConfirmed
    CheckoutPhase.FAILED -> com.gaxtron.mobile.ui.theme.StatusFailed
}

fun statusLabel(phase: CheckoutPhase) = when (phase) {
    CheckoutPhase.PENDING -> "Awaiting payment"
    CheckoutPhase.CONFIRMING -> "Confirming on-chain"
    CheckoutPhase.CONFIRMED -> "Confirmed"
    CheckoutPhase.FAILED -> "Failed / expired"
}
