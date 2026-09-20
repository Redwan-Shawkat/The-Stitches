package io.github.redwanshawkat.uninstaller

import java.util.Locale

/**
 * Shared data types. No IO here — see Scanner.kt, Risk.kt and Leftovers.kt.
 *
 * Same shape as the Linux and Windows builds' models.py; only `Source`
 * differs, because "how did this get onto the device" has different answers
 * on Android. There is no `extra` map: a package name is the whole handle an
 * uninstall needs, so nothing backend-specific has to travel with the row.
 */

fun formatSize(sizeBytes: Long): String {
    var size = sizeBytes.toDouble()
    for (unit in arrayOf("B", "KB", "MB", "GB")) {
        if (size < 1024 || unit == "GB") {
            val pattern = if (unit == "B") "%.0f %s" else "%.1f %s"
            return String.format(Locale.US, pattern, size, unit)
        }
        size /= 1024
    }
    return String.format(Locale.US, "%.1f GB", size)
}

enum class Source(val label: String) {
    PLAY("Play Store"),
    FDROID("F-Droid"),
    OTHER_STORE("Other app store"),
    SIDELOADED("Sideloaded APK"),
    PREINSTALLED("Preinstalled"),
}

enum class Risk(val label: String) {
    SAFE("Safe"),
    CAUTION("Caution"),
    CRITICAL("Critical"),
}

/** One installed thing, from any source. */
data class App(
    val name: String,
    val id: String, // the package name
    val source: Source,
    val version: String = "",
    val sizeBytes: Long = 0L,
    val isSystem: Boolean = false,
    val risk: Risk = Risk.SAFE,
    val riskReason: String = "",
    /** The installing package, shown verbatim when it isn't one we recognise. */
    val installerLabel: String = "",
) {
    val sizeHuman: String get() = formatSize(sizeBytes)
}
