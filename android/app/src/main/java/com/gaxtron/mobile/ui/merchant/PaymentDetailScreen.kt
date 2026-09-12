package com.gaxtron.mobile.ui.merchant

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.CircularProgressIndicator
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
import com.gaxtron.mobile.data.SessionStore
import com.gaxtron.mobile.data.network.dto.VerifyPaymentResponse
import com.gaxtron.mobile.ui.ViewModelFactory
import com.gaxtron.mobile.util.checkoutPhase
import com.gaxtron.mobile.util.formatAmount
import com.gaxtron.mobile.util.formatTimestamp

@Composable
fun PaymentDetailScreen(
    paymentId: Int,
    session: SessionStore,
    viewModelFactory: ViewModelFactory,
    onBack: () -> Unit,
) {
    val viewModel: MerchantViewModel = viewModel(factory = viewModelFactory)
    val apiKeys by session.apiKeys.collectAsState()
    val activeKey = apiKeys.lastOrNull()

    var payment by remember { mutableStateOf<VerifyPaymentResponse?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var isLoading by remember { mutableStateOf(true) }

    fun refresh() {
        val key = activeKey ?: return
        isLoading = true
        viewModel.verifyPayment(key.rawKey, paymentId) { result ->
            isLoading = false
            result.onSuccess { payment = it }.onFailure { error = it.message }
        }
    }

    LaunchedEffect(paymentId, activeKey?.rawKey) { refresh() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Payment #$paymentId") },
                actions = {
                    IconButton(onClick = { refresh() }) {
                        Icon(Icons.Filled.Refresh, contentDescription = "Refresh")
                    }
                },
            )
        },
    ) { padding ->
        Box(modifier = Modifier.padding(padding).fillMaxSize(), contentAlignment = Alignment.Center) {
            when {
                isLoading && payment == null -> CircularProgressIndicator()
                error != null && payment == null -> Text(error ?: "", color = MaterialTheme.colorScheme.error)
                payment != null -> {
                    val p = payment!!
                    Column(modifier = Modifier.padding(24.dp)) {
                        Text(formatAmount(p.amount, p.currency), style = MaterialTheme.typography.headlineMedium)
                        val phase = checkoutPhase(p.status, p.confirmations)
                        Text(
                            statusLabel(phase),
                            style = MaterialTheme.typography.titleMedium,
                            color = statusColor(phase),
                            modifier = Modifier.padding(top = 4.dp),
                        )
                        Text("Chain: ${p.chain}", modifier = Modifier.padding(top = 16.dp))
                        Text("Address: ${p.walletAddress}", modifier = Modifier.padding(top = 4.dp))
                        Text("Confirmations: ${p.confirmations}", modifier = Modifier.padding(top = 4.dp))
                        p.txHash?.let { Text("Tx hash: $it", modifier = Modifier.padding(top = 4.dp)) }
                        p.confirmedAt?.let {
                            Text("Confirmed: ${formatTimestamp(it)}", modifier = Modifier.padding(top = 4.dp))
                        }
                    }
                }
            }
        }
    }
}
