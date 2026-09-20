package io.github.redwanshawkat.uninstaller

import java.io.File

/**
 * Leftover scan: after Android has uninstalled a package it removes
 * /data/data/<pkg> and the app's own Android/data and Android/obb folders.
 * What it never touches is a folder the app made for itself at the top of
 * shared storage. Heuristic name match; never deletes without the caller
 * showing the list first — see ai-knowledgebase.md.
 */

private const val MIN_TERM_LEN = 3 // ponytail: guards against short names matching everything

// The user's own media lives in these; a name match there could offer to
// delete someone's photos, and the leftover dialog pre-checks what it finds.
// Same call as excluding Documents on Windows.
private val USER_MEDIA_DIRS = setOf(
    "dcim", "pictures", "music", "movies", "documents", "audiobooks",
    "alarms", "notifications", "podcasts", "ringtones", "recordings",
)

/** Shared storage is the only place worth looking; Android owns the rest. */
fun scanRoots(storage: File): List<File> = listOf(
    storage,
    File(storage, "Download"),
    File(storage, "Android/data"),
    File(storage, "Android/obb"),
)

/** Terms to match a directory name against: the display name, the package
 *  name, and the package's last segment (com.acme.coolapp -> coolapp), which
 *  is what an app most often names its own folder after. */
fun searchTerms(appName: String, packageName: String): Set<String> =
    setOf(appName, packageName, packageName.substringAfterLast('.'))
        .map { it.lowercase() }
        .filter { it.length >= MIN_TERM_LEN }
        .toSet()

fun findLeftovers(appName: String, packageName: String, storage: File): List<File> {
    val terms = searchTerms(appName, packageName)
    if (terms.isEmpty()) return emptyList()
    val found = mutableListOf<File>()
    for (base in scanRoots(storage)) {
        if (!base.isDirectory) continue
        val entries = base.listFiles() ?: continue // no All files access, or unreadable
        for (entry in entries) {
            val name = entry.name.lowercase()
            // "Android" and "Download" are scanned as roots of their own, and
            // the media folders are the user's, not the app's.
            if (base == storage && (name in USER_MEDIA_DIRS || name == "android" || name == "download")) continue
            if (terms.any { name.contains(it) }) found.add(entry)
        }
    }
    return found.distinctBy { it.absolutePath }
}

/** Total bytes a leftover occupies, walked before deletion (a deleted tree
 *  reports 0, so callers must measure before removing it). */
fun pathSize(path: File): Long = when {
    !path.exists() -> 0L
    path.isFile -> path.length()
    else -> path.walkBottomUp().filter { it.isFile }.sumOf { it.length() }
}

/** Deletes each path. Returns (bytesFreed, [(path, error) for failures]) —
 *  bytesFreed only counts paths that were actually deleted. */
fun deletePaths(paths: List<File>): Pair<Long, List<Pair<File, String>>> {
    var freed = 0L
    val errors = mutableListOf<Pair<File, String>>()
    for (path in paths) {
        val size = pathSize(path)
        if (path.deleteRecursively()) {
            freed += size
        } else {
            errors.add(path to "Couldn't delete (no permission, or in use)")
        }
    }
    return freed to errors
}
