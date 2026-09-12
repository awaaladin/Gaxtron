package com.gaxtron.mobile.ui.merchant

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedCard
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.gaxtron.mobile.data.SessionStore
import com.gaxtron.mobile.ui.ViewModelFactory

@Composable
fun ApiKeysScreen(
    session: SessionStore,
    viewModelFactory: ViewModelFactory,
    onBack: () -> Unit,
) {
    val viewModel: MerchantViewModel = viewModel(factory = viewModelFactory)
    val serverKeys by viewModel.serverApiKeys.collectAsState()
    val localKeys by session.apiKeys.collectAsState()
    val clipboard = LocalClipboardManager.current

    var newKeyName by remember { mutableStateOf("My device") }
    var error by remember { mutableStateOf<String?>(null) }
    var justCreatedRawKey by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) { viewModel.refreshServerApiKeys { error = it } }

    Scaffold(topBar = { TopAppBar(title = { Text("API keys") }) }) { padding ->
        Column(modifier = Modifier.padding(padding).padding(16.dp)) {
            Text(
                "Payment endpoints authenticate with an API key (not your login). " +
                    "The raw key is shown only once, right after creation.",
                style = MaterialTheme.typography.bodyMedium,
            )

            Row(modifier = Modifier.padding(top = 16.dp).fillMaxWidth(), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                OutlinedTextField(
                    value = newKeyName,
                    onValueChange = { newKeyName = it },
                    label = { Text("Key name") },
                    modifier = Modifier.weight(1f),
                )
                Button(
                    onClick = {
                        error = null
                        viewModel.createApiKey(newKeyName.trim()) { result ->
                            result.onSuccess { justCreatedRawKey = it.rawKey }.onFailure { error = it.message }
                        }
                    },
                    modifier = Modifier.padding(start = 8.dp),
                ) {
                    Text("Create")
                }
            }

            error?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 8.dp)) }

            Text("Usable on this device", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 24.dp))
            if (localKeys.isEmpty()) {
                Text("None yet — keys created on other devices can't be used here (raw value never re-sent).")
            }
            localKeys.forEach { key ->
                OutlinedCard(modifier = Modifier.fillMaxWidth().padding(top = 8.dp)) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        Text(key.name, style = MaterialTheme.typography.titleMedium)
                        Text(key.rawKey, style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }

            Text("All keys on your account", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 24.dp))
            LazyColumn {
                items(serverKeys, key = { it.id }) { key ->
                    OutlinedCard(modifier = Modifier.fillMaxWidth().padding(top = 8.dp)) {
                        Row(
                            modifier = Modifier.padding(12.dp).fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                        ) {
                            Column {
                                Text("${key.name} (${key.keyPrefix}…)")
                                Text(if (key.isActive) "Active" else "Revoked", style = MaterialTheme.typography.bodyMedium)
                            }
                            if (key.isActive) {
                                TextButton(onClick = { viewModel.revokeApiKey(key.id) { } }) {
                                    Text("Revoke")
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    justCreatedRawKey?.let { rawKey ->
        AlertDialog(
            onDismissRequest = { justCreatedRawKey = null },
            title = { Text("Save this key now") },
            text = {
                Column {
                    Text("This is the only time the raw key is shown. It's saved on this device automatically.")
                    Text(rawKey, modifier = Modifier.padding(top = 12.dp))
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    clipboard.setText(AnnotatedString(rawKey))
                    justCreatedRawKey = null
                }) { Text("Copy & close") }
            },
            dismissButton = {
                TextButton(onClick = { justCreatedRawKey = null }) { Text("Close") }
            },
        )
    }
}
