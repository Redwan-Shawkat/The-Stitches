package io.github.redwanshawkat.uninstaller

import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.Settings
import java.io.File

/**
 * Orchestrates one removal: hand the right Intent to the system, then look
 * for leftovers. Confirmation before either step is the GUI's job (CLAUDE.md:
 * non-negotiable), not this module's.
 *
 * Android has no silent uninstall for a normal app, and that is the privilege
 * escalation rail here: the system draws its own confirmation, under its own
 * identity, and this process never gets the ability to remove anything by
 * itself. The Linux build's pkexec and the Windows build's UAC prompt are the
 * same idea with more work behind them.
 */

/** ACTION_DELETE for anything removable; App Info for a preinstalled app,
 *  which is where "Disable" and "Uninstall updates" live — the only two
 *  things Android will let a user do to one. */
fun removalIntent(app: App): Intent =
    if (app.isSystem) {
        Intent(
            Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
            Uri.fromParts("package", app.id, null),
        )
    } else {
        Intent(Intent.ACTION_DELETE, Uri.fromParts("package", app.id, null))
    }

/**
 * Did it actually go? Asked of the package manager afterwards rather than
 * read off the activity result, for the same reason the Linux build trusts
 * dpkg's status field over a failing postrm's exit code, and the Windows
 * build treats MSI 1605 as success: the result code says what the dialog
 * returned, and the package manager says what is true.
 */
fun removalOutcome(pm: PackageManager, app: App): Pair<Boolean, String> {
    val info = try {
        pm.getApplicationInfo(app.id, PackageManager.MATCH_DISABLED_COMPONENTS)
    } catch (_: PackageManager.NameNotFoundException) {
        null
    }
    return when {
        info == null -> true to "Removed."
        !info.enabled -> true to "Disabled — Android won't fully remove a preinstalled app."
        else -> false to "Still installed — the removal was cancelled or refused."
    }
}

/** Leftovers are only worth looking for once the app is actually gone. */
fun leftoversFor(app: App, storage: File): List<File> = findLeftovers(app.name, app.id, storage)

fun cleanLeftovers(paths: List<File>): Pair<Long, List<Pair<File, String>>> = deletePaths(paths)
