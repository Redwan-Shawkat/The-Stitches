package io.github.redwanshawkat.uninstaller

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files

/**
 * Self-check for every pure (non-PackageManager, non-Context) function: the
 * source mapping, the risk classifier and the leftover matcher.
 *
 * These run on the JVM with no device and no emulator, which is the point of
 * keeping Scanner.kt's IO out of Sources.kt, Risk.kt and Leftovers.kt — the
 * same split the Linux and Windows builds make. `./gradlew test`.
 */
class CoreTest {

    @Test
    fun formatsSizesLikeTheOtherBuilds() {
        assertEquals("512 B", formatSize(512))
        assertEquals("1.0 KB", formatSize(1024))
        assertEquals("1.5 MB", formatSize(1024 * 1024 * 3 / 2))
        assertEquals("2.0 GB", formatSize(2L * 1024 * 1024 * 1024))
    }

    @Test
    fun mapsInstallerPackagesToSources() {
        assertEquals(Source.PLAY, sourceFor("com.android.vending", false))
        assertEquals(Source.FDROID, sourceFor("org.fdroid.fdroid", false))
        assertEquals(Source.SIDELOADED, sourceFor("com.android.packageinstaller", false))
        assertEquals(Source.SIDELOADED, sourceFor(null, false))
        // An installer we don't recognise is still a store, not a sideload.
        assertEquals(Source.OTHER_STORE, sourceFor("com.sec.android.app.samsungapps", false))
        assertEquals(Source.OTHER_STORE, sourceFor("net.example.unknownstore", false))
        // Preinstalled wins: it decides what can be done with the app.
        assertEquals(Source.PREINSTALLED, sourceFor("com.android.vending", true))
        assertEquals(Source.PREINSTALLED, sourceFor(null, true))
    }

    @Test
    fun labelsUnknownInstallersByPackageName() {
        assertEquals("Play Store", installerLabelFor("com.android.vending"))
        assertEquals("Galaxy Store", installerLabelFor("com.sec.android.app.samsungapps"))
        assertEquals("net.example.unknownstore", installerLabelFor("net.example.unknownstore"))
        assertEquals("no recorded installer", installerLabelFor(null))
    }

    private fun signals(
        packageName: String = "com.example.app",
        isSystem: Boolean = false,
        hasLauncherEntry: Boolean = true,
        isDeviceAdmin: Boolean = false,
        isDefaultLauncher: Boolean = false,
        isActiveInputMethod: Boolean = false,
    ) = RiskSignals(packageName, isSystem, hasLauncherEntry, isDeviceAdmin, isDefaultLauncher, isActiveInputMethod)

    @Test
    fun classifiesOnTheAuthoritativeSignalsFirst() {
        assertEquals(Risk.CRITICAL, classify(signals(isDefaultLauncher = true)).risk)
        assertEquals(Risk.CRITICAL, classify(signals(isDeviceAdmin = true)).risk)
        assertEquals(Risk.CRITICAL, classify(signals(isActiveInputMethod = true)).risk)
        // The home screen outranks "it's preinstalled" — the reason has to be
        // the one that matters, not just the first flag that happens to be set.
        assertTrue(classify(signals(isSystem = true, isDefaultLauncher = true)).reason.contains("home screen"))
    }

    @Test
    fun splitsCoreAndroidFromVendorPreinstalls() {
        assertEquals(Risk.CRITICAL, classify(signals("com.android.settings", isSystem = true)).risk)
        assertEquals(Risk.CRITICAL, classify(signals("com.google.android.gms", isSystem = true)).risk)
        // Vendor bloat is preinstalled but not load-bearing: it can be disabled.
        val bloat = classify(signals("com.vendor.shoppingapp", isSystem = true))
        assertEquals(Risk.CAUTION, bloat.risk)
        assertTrue(bloat.reason.contains("disabled"))
    }

    @Test
    fun flagsBackgroundAppsWithNoLauncherIcon() {
        assertEquals(Risk.CAUTION, classify(signals(hasLauncherEntry = false)).risk)
        assertEquals(Risk.SAFE, classify(signals()).risk)
    }

    @Test
    fun buildsSearchTermsFromNameAndPackage() {
        assertEquals(setOf("coolapp", "com.acme.coolapp"), searchTerms("CoolApp", "com.acme.coolapp"))
        // Short terms are dropped, or every folder on the device would match.
        assertFalse(searchTerms("Hi", "com.a.b").contains("hi"))
    }

    @Test
    fun matchesLeftoversAndSkipsTheUsersOwnMedia() {
        val storage = Files.createTempDirectory("storage").toFile()
        File(storage, "CoolApp").mkdirs()
        File(storage, "Download/coolapp-backup").mkdirs()
        File(storage, "Android/data/com.acme.coolapp").mkdirs()
        File(storage, "unrelated").mkdirs()
        // A photo folder that happens to match must not be offered up.
        File(storage, "Pictures/coolapp").mkdirs()

        val found = findLeftovers("CoolApp", "com.acme.coolapp", storage).map { it.absolutePath }
        assertEquals(3, found.size)
        assertTrue(found.any { it.endsWith("/CoolApp") })
        assertTrue(found.any { it.endsWith("/Download/coolapp-backup") })
        assertTrue(found.any { it.endsWith("/Android/data/com.acme.coolapp") })
        assertFalse(found.any { it.contains("/Pictures/") })

        storage.deleteRecursively()
    }

    @Test
    fun measuresBeforeDeleting() {
        val storage = Files.createTempDirectory("storage").toFile()
        val leftover = File(storage, "CoolApp").apply { mkdirs() }
        File(leftover, "cache.bin").writeBytes(ByteArray(2048))

        assertEquals(2048L, pathSize(leftover))
        val (freed, errors) = deletePaths(listOf(leftover))
        assertEquals(2048L, freed)
        assertTrue(errors.isEmpty())
        assertFalse(leftover.exists())

        storage.deleteRecursively()
    }

    @Test
    fun healthVerdicts() {
        assertEquals(Health.OK, integrityFinding("green").health)
        assertEquals(Health.PROBLEM, integrityFinding("orange").health) // unlocked bootloader
        assertEquals(Health.INFO, integrityFinding("").health) // the device won't say
        assertEquals(Health.WARNING, storageFinding(free = 9, total = 100).health)
        assertEquals(Health.PROBLEM, storageFinding(free = 4, total = 100).health)
        assertEquals(Health.OK, storageFinding(free = 40, total = 100).health)
        assertEquals(Health.WARNING, memoryFinding(1, 10, low = true).health)
        assertEquals(Health.OK, batteryFinding(android.os.BatteryManager.BATTERY_HEALTH_GOOD, 310).health)
        assertEquals(Health.WARNING, batteryFinding(android.os.BatteryManager.BATTERY_HEALTH_GOOD, 470).health)
        assertEquals(Health.PROBLEM, batteryFinding(android.os.BatteryManager.BATTERY_HEALTH_DEAD, 300).health)
        assertEquals(Health.OK, thermalFinding(0).health)
        assertEquals(Health.PROBLEM, thermalFinding(4).health)
        val day = 24L * 60 * 60 * 1000
        val patched = java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.US).parse("2026-01-01")!!.time
        assertEquals(Health.OK, patchFinding("2026-01-01", patched + 30 * day).health)
        assertEquals(Health.WARNING, patchFinding("2026-01-01", patched + 200 * day).health)
        assertEquals(Health.PROBLEM, patchFinding("2026-01-01", patched + 400 * day).health)
        assertEquals(Health.INFO, patchFinding("", patched).health)
        assertEquals(Health.PROBLEM, lockFinding(false).health)
        assertEquals(Health.WARNING, debuggingFinding(developerOptions = true, usbDebugging = true).health)
        assertEquals(Health.WARNING, rootFinding(true).health)
    }
}
