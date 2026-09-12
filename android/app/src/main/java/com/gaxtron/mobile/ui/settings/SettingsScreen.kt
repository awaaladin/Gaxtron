package com.gaxtron.mobile.ui.settings

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
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
import com.gaxtron.mobile.BuildConfig
import com.gaxtron.mobile.data.SessionStore

@Composable
fun SettingsScreen(session: SessionStore, onLoggedOut: () -> Unit) {
    val baseUrl by session.baseUrl.collectAsState()
    val user by session.user.collectAsState()
    var editedUrl by remember(baseUrl) { mutableStateOf(baseUrl) }

    Scaffold(topBar = { TopAppBar(title = { Text("Settings") }) }) { padding ->
        Column(modifier = Modifier.padding(padding).padding(24.dp)) {
            user?.let {
                Text("Signed in as ${it.username} (${it.email})", style = MaterialTheme.typography.titleMedium)
            }

            Text(
                "Backend base URL",
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(top = 24.dp),
            )
            Text(
                "Default points at the Django dev server via the emulator's localhost alias " +
                    "(${BuildConfig.DEFAULT_BASE_URL}). Use your machine's LAN IP instead of " +
                    "10.0.2.2 to reach it from a real device, or a deployed Django host.",
                style = MaterialTheme.typography.bodyMedium,
            )
            OutlinedTextField(
                value = editedUrl,
                onValueChange = { editedUrl = it },
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
            )
            Button(
                onClick = { session.setBaseUrl(editedUrl.trim()) },
                enabled = editedUrl.isNotBlank(),
                modifier = Modifier.padding(top = 8.dp),
            ) { Text("Save") }

            OutlinedButton(
                onClick = {
                    session.signOut()
                    onLoggedOut()
                },
                modifier = Modifier.fillMaxWidth().padding(top = 32.dp),
            ) { Text("Log out") }
        }
    }
}
