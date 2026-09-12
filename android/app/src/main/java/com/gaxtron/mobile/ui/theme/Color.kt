package com.gaxtron.mobile.ui.theme

import androidx.compose.ui.graphics.Color

// "Premium Editorial Fintech" design system — pulled directly from the Stitch
// DESIGN.md token set. The Android app keeps the original gold accent (the web
// redesign swaps this family for emerald; every other token is shared).
val Gold = Color(0xFFF5BD51)
val GoldContainer = Color(0xFFC9962C)
val OnGold = Color(0xFF412D00)
val OnGoldContainer = Color(0xFF483200)
val GoldFixed = Color(0xFFFFDEA7)
val OnGoldFixedVariant = Color(0xFF5E4200)
val InverseGold = Color(0xFF7C5800)

val BgPrimaryDark = Color(0xFF0B0B0A)
val SurfaceDark = Color(0xFF131312)
val SurfaceContainerLowest = Color(0xFF0E0E0D)
val SurfaceContainerLow = Color(0xFF1C1C1A)
val SurfaceContainer = Color(0xFF20201E)
val SurfaceContainerHigh = Color(0xFF2A2A29)
val SurfaceContainerHighest = Color(0xFF353533)

val OnSurfaceDark = Color(0xFFE5E2DF)
val OnSurfaceVariantDark = Color(0xFFD3C4B0)
val OutlineDark = Color(0xFF9C8F7C)
val OutlineVariantDark = Color(0xFF3A3833)

val Secondary = Color(0xFFC9C6C0)
val OnSecondary = Color(0xFF31312C)
val SecondaryContainer = Color(0xFF474742)
val OnSecondaryContainer = Color(0xFFB7B5AF)

val Tertiary = Color(0xFFA2C9FF)
val OnTertiary = Color(0xFF00315C)
val TertiaryContainer = Color(0xFF6BA1E5)
val OnTertiaryContainer = Color(0xFF003764)

val ErrorColor = Color(0xFFFFB4AB)
val OnErrorColor = Color(0xFF690005)
val ErrorContainer = Color(0xFF93000A)
val OnErrorContainer = Color(0xFFFFDAD6)

// Light variant — same gold accent, conventional light neutrals (DESIGN.md is dark-first).
val BgPrimaryLight = Color(0xFFFAF7F2)
val SurfaceLight = Color(0xFFFFFFFF)
val OnSurfaceLight = Color(0xFF1C1B1A)
val OnSurfaceVariantLight = Color(0xFF4F4536)

val StatusPending = OnSurfaceVariantDark
val StatusConfirming = Tertiary
val StatusConfirmed = Gold
val StatusFailed = ErrorColor
