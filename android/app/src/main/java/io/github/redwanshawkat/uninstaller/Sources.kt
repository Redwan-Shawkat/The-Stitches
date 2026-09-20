package io.github.redwanshawkat.uninstaller

/**
 * Which store put an app here, from the installer package name Android
 * recorded at install time. Pure — Scanner.kt makes the PackageManager call
 * and hands the answer in, so this is checkable without a device.
 */

private val PLAY_INSTALLERS = setOf(
    "com.android.vending",
    "com.google.android.feedback", // Play's own updater, on older releases
)

private val FDROID_INSTALLERS = setOf(
    "org.fdroid.fdroid",
    "org.fdroid.basic",
    "org.fdroid.fdroid.privileged",
)

// The system's own installer UI — what handles "open an APK and tap Install",
// plus the vendor-skinned variants of it. An app attributed to one of these
// was sideloaded, not fetched from a store.
private val SIDELOAD_INSTALLERS = setOf(
    "com.android.packageinstaller",
    "com.google.android.packageinstaller",
    "com.miui.packageinstaller",
    "com.samsung.android.packageinstaller",
    "com.android.shell", // `adb install`
)

private val KNOWN_STORES = mapOf(
    "com.amazon.venezia" to "Amazon Appstore",
    "com.sec.android.app.samsungapps" to "Galaxy Store",
    "com.huawei.appmarket" to "AppGallery",
    "com.xiaomi.market" to "Mi Store",
    "com.heytap.market" to "App Market",
    "com.oppo.market" to "App Market",
    "com.bbk.appstore" to "V-Appstore",
    "com.aurora.store" to "Aurora Store",
)

/**
 * Preinstalled wins over everything: a system app's installer is null anyway,
 * and "it shipped with the device" is the fact that decides what can be done
 * with it. An installer we don't recognise is still a store — reporting it as
 * a sideload would be a lie, and the label carries the package name through.
 */
fun sourceFor(installerPackage: String?, isSystemApp: Boolean): Source = when {
    isSystemApp -> Source.PREINSTALLED
    installerPackage in PLAY_INSTALLERS -> Source.PLAY
    installerPackage in FDROID_INSTALLERS -> Source.FDROID
    installerPackage.isNullOrBlank() -> Source.SIDELOADED
    installerPackage in SIDELOAD_INSTALLERS -> Source.SIDELOADED
    else -> Source.OTHER_STORE
}

/** Human name for the installing package, for the row's detail line. */
fun installerLabelFor(installerPackage: String?): String = when {
    installerPackage.isNullOrBlank() -> "no recorded installer"
    installerPackage in PLAY_INSTALLERS -> "Play Store"
    installerPackage in FDROID_INSTALLERS -> "F-Droid"
    installerPackage in SIDELOAD_INSTALLERS -> "installed from an APK file"
    else -> KNOWN_STORES[installerPackage] ?: installerPackage
}
