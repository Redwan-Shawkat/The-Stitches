package io.github.redwanshawkat.uninstaller

/**
 * Risk classification. Pure functions — see ai-knowledgebase.md for why this
 * is a heuristic on fields the scan already has in hand instead of a real
 * dependency graph.
 *
 * Unlike the Linux and Windows builds, three of the six signals here are
 * authoritative rather than guessed: Android will actually tell you which
 * package is the home screen, which ones hold device-admin rights and which
 * keyboard is active. Each costs one query per *scan*, not per app.
 */

// ponytail: name-pattern heuristic for "is this Android itself", used only to
// split core platform packages from vendor preinstalls. Everything else below
// is a real signal.
private val CORE_PACKAGE_PATTERNS = listOf(
    Regex("^android$"),
    Regex("^com\\.android\\."),
    Regex("^com\\.google\\.android\\.(gms|gsf|webview|packageinstaller|permissioncontroller|providers|ext)\\b"),
    Regex("^com\\.google\\.android\\.trichromelibrary"),
    Regex("^com\\.qualcomm\\."),
    Regex("^com\\.mediatek\\."),
)

data class RiskSignals(
    val packageName: String,
    val isSystem: Boolean,
    val hasLauncherEntry: Boolean,
    val isDeviceAdmin: Boolean,
    val isDefaultLauncher: Boolean,
    val isActiveInputMethod: Boolean,
)

data class RiskVerdict(val risk: Risk, val reason: String)

fun classify(signals: RiskSignals): RiskVerdict = when {
    signals.isDefaultLauncher -> RiskVerdict(
        Risk.CRITICAL,
        "Your home screen — removing it can leave the device with no way to open anything.",
    )

    signals.isDeviceAdmin -> RiskVerdict(
        Risk.CRITICAL,
        "Holds device-administrator rights — Android blocks removal until those are revoked.",
    )

    signals.isActiveInputMethod -> RiskVerdict(
        Risk.CRITICAL,
        "Your active keyboard — removing it leaves you with no way to type.",
    )

    signals.isSystem && CORE_PACKAGE_PATTERNS.any { it.containsMatchIn(signals.packageName) } ->
        RiskVerdict(
            Risk.CRITICAL,
            "Part of Android itself — other apps run on top of it and it can't be uninstalled.",
        )

    signals.isSystem -> RiskVerdict(
        Risk.CAUTION,
        "Preinstalled with the device — it can be disabled, but not fully uninstalled.",
    )

    !signals.hasLauncherEntry -> RiskVerdict(
        Risk.CAUTION,
        "No app icon — it runs in the background for something else, which may stop working.",
    )

    else -> RiskVerdict(
        Risk.SAFE,
        "A standalone app — nothing else is known to depend on it.",
    )
}
