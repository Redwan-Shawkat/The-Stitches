package io.github.redwanshawkat.uninstaller

import android.app.ActivityManager
import android.app.KeyguardManager
import android.app.admin.DevicePolicyManager
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.Build
import android.os.Environment
import android.os.PowerManager
import android.os.StatFs
import android.provider.Settings
import java.io.File
import java.text.SimpleDateFormat
import java.util.Locale

/**
 * Health check: the Android side of the Linux build's Diagnose page. An app
 * can't verify system files, test RAM or read the storage chip's wear without
 * root — those stay out rather than being faked. What Android does report is
 * whether its own boot-time integrity check passed (the closest thing to
 * sfc /scannow), plus a handful of facts worth a warning.
 *
 * The verdicts are pure functions over plain values, so they're tested on the
 * JVM; healthCheck() is the only part that reads the device.
 */

enum class Health(val label: String) { OK("OK"), WARNING("Warning"), PROBLEM("Problem"), INFO("Info") }

data class Finding(val title: String, val health: Health, val detail: String)

private const val DAY_MS = 24L * 60 * 60 * 1000

fun integrityFinding(verifiedBootState: String): Finding = when (verifiedBootState) {
    "green" -> Finding("System integrity", Health.OK,
        "Verified boot passed: the system is exactly what the maker signed.")
    "yellow" -> Finding("System integrity", Health.WARNING,
        "The system is verified, but against a custom key rather than the maker's.")
    "orange" -> Finding("System integrity", Health.PROBLEM,
        "The bootloader is unlocked, so the system isn't verified at boot and could have been changed.")
    "red" -> Finding("System integrity", Health.PROBLEM, "Verified boot failed: the system doesn't match its signature.")
    else -> Finding("System integrity", Health.INFO, "This device doesn't let apps read its verified-boot state.")
}

fun storageFinding(free: Long, total: Long): Finding {
    val share = if (total > 0) free.toDouble() / total else 1.0
    val health = when {
        share < 0.05 -> Health.PROBLEM
        share < 0.10 -> Health.WARNING
        else -> Health.OK
    }
    val advice = if (health == Health.OK) "" else " Android slows down and apps stop updating as it fills up."
    return Finding("Storage", health, "${formatSize(free)} free of ${formatSize(total)}.$advice")
}

fun memoryFinding(available: Long, total: Long, low: Boolean): Finding = Finding(
    "Memory", if (low) Health.WARNING else Health.OK,
    "${formatSize(available)} free of ${formatSize(total)}" +
        if (low) ". Android is closing background apps to make room." else ".",
)

fun batteryFinding(health: Int, tenthsCelsius: Int): Finding {
    val celsius = tenthsCelsius / 10
    val verdict = when (health) {
        BatteryManager.BATTERY_HEALTH_GOOD -> if (celsius >= 45) Health.WARNING else Health.OK
        BatteryManager.BATTERY_HEALTH_COLD -> Health.WARNING
        BatteryManager.BATTERY_HEALTH_OVERHEAT, BatteryManager.BATTERY_HEALTH_DEAD,
        BatteryManager.BATTERY_HEALTH_OVER_VOLTAGE, BatteryManager.BATTERY_HEALTH_UNSPECIFIED_FAILURE -> Health.PROBLEM
        else -> Health.INFO
    }
    val words = when (health) {
        BatteryManager.BATTERY_HEALTH_GOOD -> "Good"
        BatteryManager.BATTERY_HEALTH_COLD -> "Too cold to charge well"
        BatteryManager.BATTERY_HEALTH_OVERHEAT -> "Overheating"
        BatteryManager.BATTERY_HEALTH_DEAD -> "Worn out: it needs replacing"
        BatteryManager.BATTERY_HEALTH_OVER_VOLTAGE -> "Over voltage: check the charger"
        BatteryManager.BATTERY_HEALTH_UNSPECIFIED_FAILURE -> "Failing"
        else -> "Not reported"
    }
    return Finding("Battery", verdict, "$words · $celsius °C")
}

/** PowerManager.THERMAL_STATUS_*: 0 none … 6 shutdown. */
fun thermalFinding(status: Int): Finding = when {
    status <= 1 -> Finding("Temperature", Health.OK, "Normal; the phone isn't slowing itself down.")
    status == 2 -> Finding("Temperature", Health.WARNING, "Warm enough that the phone is slowing itself down.")
    else -> Finding("Temperature", Health.PROBLEM, "Hot: the phone is throttling hard. Let it cool down.")
}

/** `patch` is Build.VERSION.SECURITY_PATCH, "2024-09-05". */
fun patchFinding(patch: String, nowMillis: Long): Finding {
    val date = runCatching { SimpleDateFormat("yyyy-MM-dd", Locale.US).parse(patch) }.getOrNull()
        ?: return Finding("Security patch", Health.INFO, "Not reported.")
    val days = (nowMillis - date.time) / DAY_MS
    val health = when {
        days <= 90 -> Health.OK
        days <= 365 -> Health.WARNING
        else -> Health.PROBLEM
    }
    return Finding("Security patch", health, "$patch · $days days old" +
        if (health == Health.OK) "." else ". Check Settings › System update; if none comes, the maker has stopped patching.")
}

fun lockFinding(secure: Boolean): Finding =
    if (secure) Finding("Screen lock", Health.OK, "A PIN, pattern or password protects the phone.")
    else Finding("Screen lock", Health.PROBLEM, "No screen lock: anyone holding the phone can open everything on it.")

/** DevicePolicyManager.ENCRYPTION_STATUS_*. */
fun encryptionFinding(status: Int): Finding = when (status) {
    DevicePolicyManager.ENCRYPTION_STATUS_ACTIVE, DevicePolicyManager.ENCRYPTION_STATUS_ACTIVE_PER_USER ->
        Finding("Encryption", Health.OK, "Storage is encrypted.")
    DevicePolicyManager.ENCRYPTION_STATUS_ACTIVE_DEFAULT_KEY ->
        Finding("Encryption", Health.WARNING, "Encrypted, but with a default key: set a screen lock to protect it.")
    DevicePolicyManager.ENCRYPTION_STATUS_INACTIVE -> Finding("Encryption", Health.PROBLEM, "Storage isn't encrypted.")
    else -> Finding("Encryption", Health.INFO, "This device doesn't report encryption.")
}

fun debuggingFinding(developerOptions: Boolean, usbDebugging: Boolean): Finding = when {
    usbDebugging -> Finding("USB debugging", Health.WARNING,
        "On: a computer you plug into can install apps and read data once you tap Allow. Turn it off when you're done.")
    developerOptions -> Finding("USB debugging", Health.OK, "Off. Developer options are on, which is harmless by itself.")
    else -> Finding("USB debugging", Health.OK, "Off.")
}

fun rootFinding(suFound: Boolean): Finding =
    if (suFound) Finding("Root", Health.WARNING, "An su binary is present: apps given root can get around Android's protections.")
    else Finding("Root", Health.OK, "Not rooted.")

// ---- reading the device ----

private val SU_PATHS = listOf("/system/bin/su", "/system/xbin/su", "/sbin/su", "/su/bin/su", "/data/local/xbin/su")

private fun systemProperty(name: String): String =
    runCatching { Runtime.getRuntime().exec(arrayOf("getprop", name)).inputStream.bufferedReader().readText().trim() }
        .getOrDefault("")

fun healthCheck(context: Context): List<Finding> {
    val data = StatFs(Environment.getDataDirectory().path)
    val memory = ActivityManager.MemoryInfo().also {
        (context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager).getMemoryInfo(it)
    }
    // A sticky system broadcast: registering with no receiver just returns the last one.
    val battery = context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
    val resolver = context.contentResolver
    return listOfNotNull(
        integrityFinding(systemProperty("ro.boot.verifiedbootstate")),
        storageFinding(data.availableBytes, data.totalBytes),
        memoryFinding(memory.availMem, memory.totalMem, memory.lowMemory),
        battery?.let {
            batteryFinding(it.getIntExtra(BatteryManager.EXTRA_HEALTH, 0), it.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, 0))
        },
        if (Build.VERSION.SDK_INT >= 29) {
            thermalFinding((context.getSystemService(Context.POWER_SERVICE) as PowerManager).currentThermalStatus)
        } else null,
        patchFinding(Build.VERSION.SECURITY_PATCH, System.currentTimeMillis()),
        lockFinding((context.getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager).isDeviceSecure),
        encryptionFinding(
            (context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager).storageEncryptionStatus
        ),
        debuggingFinding(
            Settings.Global.getInt(resolver, Settings.Global.DEVELOPMENT_SETTINGS_ENABLED, 0) == 1,
            Settings.Global.getInt(resolver, Settings.Global.ADB_ENABLED, 0) == 1,
        ),
        rootFinding(SU_PATHS.any { File(it).exists() }),
    )
}
