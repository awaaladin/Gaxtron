package com.gaxtron.mobile.ui.pay

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.gaxtron.mobile.ui.ViewModelFactory
import com.gaxtron.mobile.ui.merchant.statusColor
import com.gaxtron.mobile.ui.merchant.statusLabel
import com.gaxtron.mobile.util.CheckoutPhase
import com.gaxtron.mobile.util.checkoutPhase
import com.gaxtron.mobile.util.formatAmount
import com.gaxtron.mobile.util.generateQrBitmap

@Composable
fun PayCheckoutScreen(
    paymentRef: String,
    viewModelFactory: ViewModelFactory,
    onBack: () -> Unit,
) {
    val viewModel: PayViewModel = viewModel(factory = viewModelFactory)
    val status by viewModel.status.collectAsState()
    val error by viewModel.error.collectAsState()
    val clipboard = LocalClipboardManager.current

    LaunchedEffect(paymentRef) { viewModel.startPolling(paymentRef) }
    DisposableEffect(Unit) { onDispose { viewModel.stopPolling() } }

    Scaffold(topBar = { TopAppBar(title = { Text("Checkout") }) }) { padding ->
        Box(modifier = Modifier.padding(padding).fillMaxSize(), contentAlignment = Alignment.Center) {
            val current = status
            if (current == null) {
                if (error != null) Text(error ?: "", color = MaterialTheme.colorScheme.error) else CircularProgressIndicator()
                return@Box
            }

            val phase = checkoutPhase(current.status, current.confirmations)
            val address = current.address ?: current.walletAddress
            val qr = remember(address) { generateQrBitmap("ethereum:$address") }

            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()).padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Text(formatAmount(current.amount, current.currency), style = MaterialTheme.typography.headlineMedium)
                Text(
                    "${current.network} · ${current.currency}",
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.padding(top = 4.dp),
                )
                Text(
                    statusLabel(phase),
                    style = MaterialTheme.typography.titleMedium,
                    color = statusColor(phase),
                    modifier = Modifier.padding(top = 16.dp),
                )

                when (phase) {
                    CheckoutPhase.PENDING -> {
                        Image(
                            bitmap = qr.asImageBitmap(),
                            contentDescription = "Address QR code",
                            modifier = Modifier.size(240.dp).padding(top = 16.dp),
                        )
                        Text(address, modifier = Modifier.padding(top = 16.dp))
                        Button(
                            onClick = { clipboard.setText(AnnotatedString(address)) },
                            modifier = Modifier.padding(top = 12.dp),
                        ) { Text("Copy address") }
                        Text(
                            "Send exactly the amount shown above. This page updates automatically.",
                            style = MaterialTheme.typography.bodyMedium,
                            modifier = Modifier.padding(top = 16.dp),
                        )
                    }

                    CheckoutPhase.CONFIRMING -> {
                        LinearProgressIndicator(
                            progress = { current.confirmations.toFloat() / current.requiredConfirmations.coerceAtLeast(1) },
                            modifier = Modifier.fillMaxWidth().padding(top = 16.dp),
                        )
                        Text(
                            "${current.confirmations} of ${current.requiredConfirmations} confirmations",
                            modifier = Modifier.padding(top = 8.dp),
                        )
                        current.txHash?.let { Text(it, modifier = Modifier.padding(top = 8.dp)) }
                    }

                    CheckoutPhase.CONFIRMED -> {
                        Text("Payment complete — thank you.", modifier = Modifier.padding(top = 16.dp))
                        current.txHash?.let { Text(it, modifier = Modifier.padding(top = 8.dp)) }
                        Button(onClick = onBack, modifier = Modifier.padding(top = 16.dp)) { Text("Done") }
                    }

                    CheckoutPhase.FAILED -> {
                        Text(
                            "This link is no longer valid. Ask the merchant for a new one.",
                            modifier = Modifier.padding(top = 16.dp),
                        )
                        Button(onClick = onBack, modifier = Modifier.padding(top = 16.dp)) { Text("Back") }
                    }
                }
            }
        }
    }
}
