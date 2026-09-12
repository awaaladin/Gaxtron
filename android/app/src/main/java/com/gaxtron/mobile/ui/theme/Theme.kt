package com.gaxtron.mobile.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

private val DarkColors = darkColorScheme(
    primary = Gold,
    onPrimary = OnGold,
    primaryContainer = GoldContainer,
    onPrimaryContainer = OnGoldContainer,
    secondary = Secondary,
    onSecondary = OnSecondary,
    secondaryContainer = SecondaryContainer,
    onSecondaryContainer = OnSecondaryContainer,
    tertiary = Tertiary,
    onTertiary = OnTertiary,
    tertiaryContainer = TertiaryContainer,
    onTertiaryContainer = OnTertiaryContainer,
    background = BgPrimaryDark,
    onBackground = OnSurfaceDark,
    surface = SurfaceDark,
    onSurface = OnSurfaceDark,
    surfaceVariant = SurfaceContainerHighest,
    onSurfaceVariant = OnSurfaceVariantDark,
    outline = OutlineDark,
    outlineVariant = OutlineVariantDark,
    error = ErrorColor,
    onError = OnErrorColor,
    errorContainer = ErrorContainer,
    onErrorContainer = OnErrorContainer,
)

private val LightColors = lightColorScheme(
    primary = GoldContainer,
    onPrimary = Color.White,
    primaryContainer = GoldFixed,
    onPrimaryContainer = OnGoldFixedVariant,
    background = BgPrimaryLight,
    onBackground = OnSurfaceLight,
    surface = SurfaceLight,
    onSurface = OnSurfaceLight,
    onSurfaceVariant = OnSurfaceVariantLight,
    error = Color(0xFFBA1A1A),
)

// Sharp (0dp) corners everywhere — the "Premium Editorial Fintech" design system is
// strictly flat, no rounded consumer-app aesthetics.
private val ZeroCorner = RoundedCornerShape(0.dp)
private val GaxtronShapes = Shapes(
    extraSmall = ZeroCorner,
    small = ZeroCorner,
    medium = ZeroCorner,
    large = ZeroCorner,
    extraLarge = ZeroCorner,
)

@Composable
fun GaxtronTheme(darkTheme: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColors else LightColors,
        typography = GaxtronTypography,
        shapes = GaxtronShapes,
        content = content,
    )
}
