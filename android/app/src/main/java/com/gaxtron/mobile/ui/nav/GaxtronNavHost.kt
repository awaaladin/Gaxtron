package com.gaxtron.mobile.ui.nav

import android.net.Uri
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Payment
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.gaxtron.mobile.GaxtronApp
import com.gaxtron.mobile.ui.ViewModelFactory
import com.gaxtron.mobile.ui.auth.AuthViewModel
import com.gaxtron.mobile.ui.auth.LoginScreen
import com.gaxtron.mobile.ui.auth.RegisterScreen
import com.gaxtron.mobile.ui.merchant.ApiKeysScreen
import com.gaxtron.mobile.ui.merchant.CreatePaymentScreen
import com.gaxtron.mobile.ui.merchant.DashboardScreen
import com.gaxtron.mobile.ui.merchant.MerchantViewModel
import com.gaxtron.mobile.ui.merchant.PaymentDetailScreen
import com.gaxtron.mobile.ui.pay.PayCheckoutScreen
import com.gaxtron.mobile.ui.pay.PayEntryScreen
import com.gaxtron.mobile.ui.pay.PayViewModel
import com.gaxtron.mobile.ui.settings.SettingsScreen

private object Routes {
    const val LOGIN = "login"
    const val REGISTER = "register"
    const val DASHBOARD = "dashboard"
    const val PAY_ENTRY = "pay_entry"
    const val SETTINGS = "settings"
    const val CREATE_PAYMENT = "create_payment"
    const val API_KEYS = "api_keys"
    const val PAYMENT_DETAIL = "payment_detail/{id}"
    const val PAY_CHECKOUT = "pay_checkout/{ref}"

    fun paymentDetail(id: Int) = "payment_detail/$id"
    fun payCheckout(ref: String) = "pay_checkout/${Uri.encode(ref)}"
}

private val bottomNavRoutes = listOf(Routes.DASHBOARD, Routes.PAY_ENTRY, Routes.SETTINGS)

@Composable
fun GaxtronRoot(app: GaxtronApp) {
    val navController = rememberNavController()
    val session = app.session
    val token by session.token.collectAsState()
    val loggedIn = token != null

    val merchantFactory = ViewModelFactory { MerchantViewModel(app.paymentRepository, app.apiKeyRepository) }
    val payFactory = ViewModelFactory { PayViewModel(app.paymentRepository) }
    val authFactory = ViewModelFactory { AuthViewModel(app.authRepository) }

    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = backStackEntry?.destination?.route
    val showBottomBar = currentRoute in bottomNavRoutes

    Scaffold(
        bottomBar = {
            if (showBottomBar) {
                NavigationBar {
                    NavigationBarItem(
                        selected = currentRoute == Routes.DASHBOARD,
                        onClick = { navController.navigateToTab(Routes.DASHBOARD) },
                        icon = { Icon(Icons.Filled.Payment, contentDescription = "Merchant") },
                        label = { Text("Merchant") },
                    )
                    NavigationBarItem(
                        selected = currentRoute == Routes.PAY_ENTRY,
                        onClick = { navController.navigateToTab(Routes.PAY_ENTRY) },
                        icon = { Icon(Icons.Filled.QrCodeScanner, contentDescription = "Pay a link") },
                        label = { Text("Pay") },
                    )
                    NavigationBarItem(
                        selected = currentRoute == Routes.SETTINGS,
                        onClick = { navController.navigateToTab(Routes.SETTINGS) },
                        icon = { Icon(Icons.Filled.Settings, contentDescription = "Settings") },
                        label = { Text("Settings") },
                    )
                }
            }
        },
    ) { padding ->
        NavHost(
            navController = navController,
            startDestination = if (loggedIn) Routes.DASHBOARD else Routes.LOGIN,
            modifier = Modifier.padding(padding),
        ) {
            composable(Routes.LOGIN) {
                LoginScreen(
                    viewModelFactory = authFactory,
                    onLoggedIn = { navController.navigate(Routes.DASHBOARD) { popUpTo(0) } },
                    onGoToRegister = { navController.navigate(Routes.REGISTER) },
                )
            }
            composable(Routes.REGISTER) {
                RegisterScreen(
                    viewModelFactory = authFactory,
                    onRegistered = { navController.navigate(Routes.DASHBOARD) { popUpTo(0) } },
                    onGoToLogin = { navController.popBackStack() },
                )
            }
            composable(Routes.DASHBOARD) {
                DashboardScreen(
                    session = session,
                    viewModelFactory = merchantFactory,
                    onCreatePayment = { navController.navigate(Routes.CREATE_PAYMENT) },
                    onOpenPayment = { id -> navController.navigate(Routes.paymentDetail(id)) },
                    onOpenApiKeys = { navController.navigate(Routes.API_KEYS) },
                )
            }
            composable(Routes.CREATE_PAYMENT) {
                CreatePaymentScreen(
                    session = session,
                    viewModelFactory = merchantFactory,
                    onBack = { navController.popBackStack() },
                )
            }
            composable(Routes.API_KEYS) {
                ApiKeysScreen(
                    session = session,
                    viewModelFactory = merchantFactory,
                    onBack = { navController.popBackStack() },
                )
            }
            composable(
                Routes.PAYMENT_DETAIL,
                arguments = listOf(navArgument("id") { type = NavType.IntType }),
            ) { entry ->
                PaymentDetailScreen(
                    paymentId = entry.arguments?.getInt("id") ?: 0,
                    session = session,
                    viewModelFactory = merchantFactory,
                    onBack = { navController.popBackStack() },
                )
            }
            composable(Routes.PAY_ENTRY) {
                PayEntryScreen(
                    viewModelFactory = payFactory,
                    onOpenCheckout = { ref -> navController.navigate(Routes.payCheckout(ref)) },
                )
            }
            composable(
                Routes.PAY_CHECKOUT,
                arguments = listOf(navArgument("ref") { type = NavType.StringType }),
            ) { entry ->
                PayCheckoutScreen(
                    paymentRef = entry.arguments?.getString("ref") ?: "",
                    viewModelFactory = payFactory,
                    onBack = { navController.popBackStack() },
                )
            }
            composable(Routes.SETTINGS) {
                SettingsScreen(
                    session = session,
                    onLoggedOut = { navController.navigate(Routes.LOGIN) { popUpTo(0) } },
                )
            }
        }
    }
}

private fun NavHostController.navigateToTab(route: String) {
    navigate(route) {
        popUpTo(graph.findStartDestination().id) { saveState = true }
        launchSingleTop = true
        restoreState = true
    }
}
