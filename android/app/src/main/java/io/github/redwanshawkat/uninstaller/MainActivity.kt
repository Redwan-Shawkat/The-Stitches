package io.github.redwanshawkat.uninstaller

import android.app.Activity
import android.app.AlertDialog
import android.content.Context
import android.content.Intent
import android.content.res.Configuration
import android.os.Build
import android.os.Bundle
import android.view.View
import android.widget.PopupMenu

/**
 * The Stitches window, as on Linux: the open page, and a dock under it (the
 * logo is Home, then Uninstall, then theme and optional access). Each page is
 * its own class, HomePage and UninstallPage; this holds what they share.
 */
class MainActivity : Activity() {

    private lateinit var home: HomePage
    private lateinit var uninstall: UninstallPage
    private lateinit var pages: List<Pair<View, View>> // (dock button, page)
    private var current = 0

    override fun onCreate(savedInstanceState: Bundle?) {
        setTheme(THEMES.getValue(themeName()))
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        home = HomePage(this, findViewById(R.id.page_home))
        uninstall = UninstallPage(this, findViewById(R.id.page_uninstall))
        pages = listOf(
            findViewById<View>(R.id.dock_home) to findViewById(R.id.page_home),
            findViewById<View>(R.id.dock_uninstall) to findViewById(R.id.page_uninstall),
        )
        pages.forEachIndexed { i, (button, _) -> button.setOnClickListener { show(i) } }
        findViewById<View>(R.id.dock_theme).setOnClickListener { pickTheme(it) }
        findViewById<View>(R.id.dock_access).setOnClickListener { showPermissionsDialog() }
        if (Build.VERSION.SDK_INT >= 26) { // names on a long press, as on hover on Linux
            for (id in listOf(R.id.dock_home, R.id.dock_uninstall, R.id.dock_theme, R.id.dock_access)) {
                findViewById<View>(id).apply { tooltipText = contentDescription }
            }
        }
        show(savedInstanceState?.getInt(KEY_PAGE) ?: 0)
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putInt(KEY_PAGE, current) // a theme change recreates the window; stay on the same page
    }

    override fun onResume() {
        super.onResume()
        uninstall.refreshBanner()
        home.refresh()
    }

    private fun show(index: Int) {
        current = index
        pages.forEachIndexed { i, (button, page) ->
            button.isSelected = i == index
            page.visibility = if (i == index) View.VISIBLE else View.GONE
        }
    }

    // ---- themes ----

    private fun prefs() = getSharedPreferences("uninstaller", Context.MODE_PRIVATE)

    /** Light, Dark, AMOLED or Glass; at first, whatever the system is set to.
     *  Before there were four, a boolean said dark or not. */
    private fun themeName(): String {
        val night = resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK == Configuration.UI_MODE_NIGHT_YES
        val old = prefs().getBoolean(KEY_DARK, night)
        return prefs().getString(KEY_THEME, null)?.takeIf { it in THEMES } ?: if (old) "Dark" else "Light"
    }

    private fun pickTheme(anchor: View) {
        PopupMenu(this, anchor).apply {
            THEMES.keys.forEach { menu.add(it) }
            menu.setGroupCheckable(0, true, true)
            menu.getItem(THEMES.keys.indexOf(themeName())).isChecked = true
            setOnMenuItemClickListener { item ->
                prefs().edit().putString(KEY_THEME, item.title.toString()).apply()
                recreate() // a theme applies at inflation, so the window starts again
                true
            }
            show()
        }
    }

    // ---- optional access ----

    fun showPermissionsDialog() {
        AlertDialog.Builder(this)
            .setTitle("Optional access")
            .setMessage(
                "The app scans and lists without either of these.\n\n" +
                    "• All files access — lets it find the folders an app leaves behind in " +
                    "shared storage after Android removes it.\n\n" +
                    "• Usage access — lets it report an app's real size (code, data and " +
                    "cache) instead of just the size of its APK."
            )
            .setPositiveButton("All files") { _, _ -> startSettings(allFilesAccessIntent(this)) }
            .setNeutralButton("Usage") { _, _ -> startSettings(usageAccessIntent()) }
            .setNegativeButton("Not now", null)
            .show()
    }

    private fun startSettings(intent: Intent) {
        runCatching { startActivity(intent) }.onFailure {
            AlertDialog.Builder(this).setMessage("This device has no Settings screen for that permission.")
                .setPositiveButton("OK", null).show()
        }
    }

    @Deprecated("Framework Activity callback; kept to avoid an AndroidX dependency")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        @Suppress("DEPRECATION")
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQ_REMOVE) uninstall.onRemovalReturned()
    }

    companion object {
        const val REQ_REMOVE = 1
        private const val KEY_PAGE = "page"
        private const val KEY_THEME = "theme"
        private const val KEY_DARK = "dark"
        private val THEMES = linkedMapOf(
            "Light" to R.style.Theme_Stitches_Light,
            "Dark" to R.style.Theme_Stitches_Dark,
            "AMOLED" to R.style.Theme_Stitches_AMOLED,
            "Glass" to R.style.Theme_Stitches_Glass,
        )
    }
}
