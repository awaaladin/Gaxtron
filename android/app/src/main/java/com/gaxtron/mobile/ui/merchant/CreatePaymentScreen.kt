package com.gaxtron.mobile.ui.merchant

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.gaxtron.mobile.data.SessionStore
import com.gaxtron.mobile.data.network.dto.CreatePaymentResponse
import com.gaxtron.mobile.ui.ViewModelFactory
import com.gaxtron.mobile.util.generateQrBitmap

@Composable
fun CreatePaymentScreen(
    session: SessionStore,
    viewModelFactory: ViewModelFactory,
    onBack: () -> Unit,
) {
    val viewModel: MerchantViewModel = viewModel(factory = viewModelFactory)
    val isLoading by viewModel.isLoading.collectAsState()
    val apiKeys by session.apiKeys.collectAsState()
    val activeKey = apiKeys.lastOrNull()

    var amount by remember { mutableStateOf("") }
    var callbackUrl by remember { mutableStateOf("https://webhook.site/") }
    var error by remember { mutableStateOf<String?>(null) }
    var created by remember { mutableStateOf<CreatePaymentResponse?>(null) }

    Scaffold(topBar = { TopAppBar(title = { Text("Create payment") }) }) { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .padding(24.dp)
                .verticalScroll(rememberScrollState()),
        ) {
            if (activeKey == null) {
                Text("Create an API key first, then come back here.")
                return@Column
            }

            val result = created
            if (result != null) {
                Text("Payment link ready", style = MaterialTheme.typography.titleLarge)
                Text(result.paymentUrl, modifier = Modifier.padding(top = 8.dp))
                val qr = remember(result.paymentUrl) { generateQrBitmap(result.paymentUrl) }
                Image(
                    bitmap = qr.asImageBitmap(),
                    contentDescription = "Checkout QR code",
                    modifier = Modifier
                        .size(220.dp)
                        .padding(top = 16.dp),
                )
                Text(
                    "Share this link or QR with your customer. Amount: ${result.amount} ${result.currency}",
                    modifier = Modifier.padding(top = 16.dp),
                )
                Button(onClick = onBack, modifier = Modifier.padding(top = 24.dp)) {
                    Text("Done")
                }
                return@Column
            }

            Text("Using API key: ${activeKey.keyPrefix}…", style = MaterialTheme.typography.bodyMedium)

            OutlinedTextField(
                value = amount,
                onValueChange = { amount = it },
                label = { Text("Amount (ETH)") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 16.dp),
            )
            OutlinedTextField(
                value = callbackUrl,
                onValueChange = { callbackUrl = it },
                label = { Text("Webhook callback URL") },
                supportingText = { Text("Use https://webhook.site to get a free test URL you can watch live.") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 8.dp),
            )

            error?.let {
                Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 8.dp))
            }

            Button(
                onClick = {
                    error = null
                    viewModel.createPayment(activeKey.rawKey, amount.trim(), callbackUrl.trim()) { result2 ->
                        result2.onSuccess { created = it }.onFailure { error = it.message }
                    }
                },
                enabled = !isLoading && amount.toDoubleOrNull() != null && callbackUrl.startsWith("http"),
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 16.dp),
            ) {
                if (isLoading) {
                    CircularProgressIndicator(modifier = Modifier.size(20.dp))
                } else {
                    Text("Create")
                }
            }
        }
    }
}
