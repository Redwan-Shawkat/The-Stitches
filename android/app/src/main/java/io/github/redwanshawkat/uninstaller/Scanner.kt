package io.github.redwanshawkat.uninstaller

import android.app.usage.StorageStatsManager
import android.content.Context
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.os.Build
import android.os.Process
import android.os.storage.StorageManager
import android.provider.Settings
import java.io.File

/**
 * The one backend. Linux and Windows each have four places software can hide,
 * so each has a backends/ directory; Android has exactly one register of
 * installed software, and every source below is a field on the same row of it.
 * An interface over a single implementation would be scaffolding (ponytail).
 */
class Scanner(private val context: Context) {

    private val pm: PackageManager get() = context.packageManager

    fun scanAll(): List<App> {
        // Three queries for the whole scan, not three per app: which packages
        // own a launcher icon, which one is the home screen, which hold
        // device-admin rights, and which keyboard is active.
        val launchers = launcherPackages()
        val defaultLauncher = defaultLauncherPackage()
        val deviceAdmins = deviceAdminPackages()
        val activeInputMethod = activeInputMethodPackage()
        val sizes = SizeReader(context)

        @Suppress("DEPRECATION") // PackageInfoFlags is API 33; this works everywhere
        val packages = pm.getInstalledPackages(0)

        return packages
            .filter { it.applicationInfo != null && it.packageName != context.packageName }
            .map { info ->
                val appInfo = info.applicationInfo!!
                val isSystem = (appInfo.flags and ApplicationInfo.FLAG_SYSTEM) != 0
                val installer = installerOf(info.packageName)
                val verdict = classify(
                    RiskSignals(
                        packageName = info.packageName,
                        isSystem = isSystem,
                        hasLauncherEntry = info.packageName in launchers,
                        isDeviceAdmin = info.packageName in deviceAdmins,
                        isDefaultLauncher = info.packageName == defaultLauncher,
                        isActiveInputMethod = info.packageName == activeInputMethod,
                    )
                )
                App(
                    name = pm.getApplicationLabel(appInfo).toString(),
                    id = info.packageName,
                    source = sourceFor(installer, isSystem),
                    version = info.versionName ?: "",
                    sizeBytes = sizes.sizeOf(appInfo),
                    isSystem = isSystem,
                    risk = verdict.risk,
                    riskReason = verdict.reason,
                    installerLabel = installerLabelFor(installer),
                )
            }
            .sortedBy { it.name.lowercase() }
    }

    private fun installerOf(packageName: String): String? = try {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            pm.getInstallSourceInfo(packageName).installingPackageName
        } else {
            @Suppress("DEPRECATION")
            pm.getInstallerPackageName(packageName)
        }
    } catch (_: PackageManager.NameNotFoundException) {
        null // uninstalled between the list call and this one
    } catch (_: IllegalArgumentException) {
        null
    }

    private fun launcherPackages(): Set<String> {
        val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        @Suppress("DEPRECATION")
        return pm.queryIntentActivities(intent, 0).mapTo(mutableSetOf()) { it.activityInfo.packageName }
    }

    private fun defaultLauncherPackage(): String? {
        val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME)
        @Suppress("DEPRECATION")
        return pm.resolveActivity(intent, PackageManager.MATCH_DEFAULT_ONLY)?.activityInfo?.packageName
    }

    private fun deviceAdminPackages(): Set<String> {
        val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE)
                as? android.app.admin.DevicePolicyManager ?: return emptySet()
        return dpm.activeAdmins.orEmpty().mapTo(mutableSetOf()) { it.packageName }
    }

    /** "com.example.keyboard/.ImeService" -> "com.example.keyboard". */
    private fun activeInputMethodPackage(): String? =
        Settings.Secure.getString(context.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD)
            ?.substringBefore('/')
            ?.takeIf { it.isNotBlank() }
}

/**
 * App size. The real number — code plus data plus cache — needs the user to
 * grant usage access in Settings, so the APK's own size is the fallback. That
 * under-reports an app with a large data directory, which is exactly the kind
 * of app worth uninstalling, hence the prompt in the UI.
 */
private class SizeReader(context: Context) {
    private val usable = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && hasUsageAccess(context)
    private val stats = if (usable) {
        context.getSystemService(Context.STORAGE_STATS_SERVICE) as? StorageStatsManager
    } else {
        null
    }

    fun sizeOf(appInfo: ApplicationInfo): Long {
        if (stats != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            try {
                val uuid = appInfo.storageUuid ?: StorageManager.UUID_DEFAULT
                val s = stats.queryStatsForPackage(uuid, appInfo.packageName, Process.myUserHandle())
                return s.appBytes + s.dataBytes + s.cacheBytes
            } catch (_: Exception) {
                // Revoked mid-scan, or a package on storage we can't stat.
            }
        }
        return runCatching { File(appInfo.sourceDir).length() }.getOrDefault(0L)
    }
}
