package com.gaxtron.mobile

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import com.gaxtron.mobile.ui.nav.GaxtronRoot
import com.gaxtron.mobile.ui.theme.GaxtronTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            GaxtronTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    GaxtronRoot(app = application as GaxtronApp)
                }
            }
        }
    }
}
