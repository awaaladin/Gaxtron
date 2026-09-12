package com.gaxtron.mobile.ui.pay

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
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
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.gaxtron.mobile.ui.ViewModelFactory
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions

/** Accepts either a raw reference or a full checkout link (e.g. .../pay/pay_xxx). */
fun extractPaymentRef(input: String): String {
    val trimmed = input.trim()
    for (marker in listOf("/pay/", "/checkout/", "/link/")) {
        val idx = trimmed.lastIndexOf(marker)
        if (idx >= 0) {
            return trimmed.substring(idx + marker.length).substringBefore('?').substringBefore('#')
        }
    }
    return trimmed
}

@Composable
fun PayEntryScreen(
    viewModelFactory: ViewModelFactory,
    onOpenCheckout: (String) -> Unit,
) {
    val viewModel: PayViewModel = viewModel(factory = viewModelFactory)
    val isLoading by viewModel.isLoading.collectAsState()

    var refInput by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }

    val scanLauncher = rememberLauncherForActivityResult(ScanContract()) { result ->
        result.contents?.let { refInput = extractPaymentRef(it) }
    }

    Scaffold(topBar = { TopAppBar(title = { Text("Pay a link") }) }) { padding ->
        Column(modifier = Modifier.padding(padding).padding(24.dp)) {
            Text(
                "Paste a Gaxtron checkout link, or scan the merchant's QR code.",
                style = MaterialTheme.typography.bodyMedium,
            )

            OutlinedTextField(
                value = refInput,
                onValueChange = { refInput = it },
                label = { Text("Checkout link or payment reference") },
                modifier = Modifier.fillMaxWidth().padding(top = 16.dp),
            )

            error?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 8.dp)) }

            Button(
                onClick = {
                    error = null
                    val ref = extractPaymentRef(refInput)
                    viewModel.lookup(ref) { result ->
                        result.onSuccess { onOpenCheckout(ref) }.onFailure { error = it.message }
                    }
                },
                enabled = !isLoading && refInput.isNotBlank(),
                modifier = Modifier.fillMaxWidth().padding(top = 16.dp),
            ) {
                if (isLoading) CircularProgressIndicator(modifier = Modifier.padding(2.dp)) else Text("Open")
            }

            OutlinedButton(
                onClick = {
                    scanLauncher.launch(
                        ScanOptions()
                            .setDesiredBarcodeFormats(ScanOptions.QR_CODE)
                            .setPrompt("Scan the merchant's payment QR code")
                            .setBeepEnabled(false),
                    )
                },
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
            ) {
                Text("Scan QR code")
            }
        }
    }
}
