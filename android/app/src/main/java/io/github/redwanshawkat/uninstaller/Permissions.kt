package io.github.redwanshawkat.uninstaller

import android.app.AppOpsManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.os.Process
import android.provider.Settings

/**
 * The two optional grants this app asks for, and the Settings screens that
 * hand them out. Both are "special access" permissions: they can't be
 * requested with a dialog, only by sending the user to Settings, and the app
 * has to work without them. See ai-knowledgebase.md.
 */

/** Usage access — without it, sizes fall back to the APK's own size. */
fun hasUsageAccess(context: Context): Boolean {
    val appOps = context.getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
    @Suppress("DEPRECATION") // the non-deprecated unsafeCheckOpNoThrow is API 29+
    val mode = appOps.checkOpNoThrow(
        AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), context.packageName
    )
    return mode == AppOpsManager.MODE_ALLOWED
}

fun usageAccessIntent(): Intent = Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS)

/** All files access — without it, the leftover scan finds nothing on API 30+. */
fun hasAllFilesAccess(): Boolean =
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) Environment.isExternalStorageManager() else true

fun allFilesAccessIntent(context: Context): Intent =
    Intent(
        Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
        Uri.fromParts("package", context.packageName, null),
    )
