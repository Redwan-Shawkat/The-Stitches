package io.github.redwanshawkat.uninstaller

import android.app.Activity
import android.app.AlertDialog
import android.content.Context
import android.content.Intent
import android.content.res.ColorStateList
import android.os.Bundle
import android.os.Environment
import android.text.Editable
import android.text.TextWatcher
import android.view.LayoutInflater
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.view.ViewGroup
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.BaseAdapter
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.ListView
import android.widget.ProgressBar
import android.widget.Spinner
import android.widget.TextView
import java.io.File

/**
 * The GUI. Same flow as the Linux and Windows builds: scan on a background
 * thread and marshal results back to the main thread, filter a list, confirm
 * before removing anything, then offer the leftovers.
 *
 * The selected set holds package names, not row positions or checkbox states,
 * so filtering the list can't silently drop a selection.
 */
class MainActivity : Activity() {

    private lateinit var banner: TextView
    private lateinit var search: EditText
    private lateinit var sourceFilter: Spinner
    private lateinit var progress: ProgressBar
    private lateinit var status: TextView
    private lateinit var list: ListView
    private lateinit var uninstallButton: Button

    private var allApps: List<App> = emptyList()
    private var visible: List<App> = emptyList()
    private val selected = mutableSetOf<String>()
    private val adapter = AppAdapter()

    // One removal at a time: Android draws its own dialog per package and
    // there is no batch uninstall for a normal app.
    private val queue = ArrayDeque<App>()
    private var pending: App? = null
    private var removalTotal = 0
    private val results = mutableListOf<RemovalResult>()

    private data class RemovalResult(val app: App, val ok: Boolean, val message: String)

    private val storage: File get() = Environment.getExternalStorageDirectory()

    override fun onCreate(savedInstanceState: Bundle?) {
        setTheme(if (isDark()) R.style.Theme_Uninstaller_Dark else R.style.Theme_Uninstaller_Light)
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        banner = findViewById(R.id.banner)
        search = findViewById(R.id.search)
        sourceFilter = findViewById(R.id.source_filter)
        progress = findViewById(R.id.progress)
        status = findViewById(R.id.status)
        list = findViewById(R.id.list)
        uninstallButton = findViewById(R.id.uninstall)

        list.adapter = adapter
        list.setOnItemClickListener { _, _, position, _ -> toggle(visible[position]) }

        search.addTextChangedListener(object : TextWatcher {
            override fun afterTextChanged(s: Editable?) = refreshRows()
            override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) = Unit
            override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) = Unit
        })

        val filterLabels = listOf(getString(R.string.all_sources)) + Source.entries.map { it.label }
        sourceFilter.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, filterLabels)
            .apply { setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item) }
        sourceFilter.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(p: AdapterView<*>?, v: View?, pos: Int, id: Long) = refreshRows()
            override fun onNothingSelected(p: AdapterView<*>?) = Unit
        }

        findViewById<Button>(R.id.select_all).setOnClickListener { selectAll() }
        findViewById<Button>(R.id.select_none).setOnClickListener {
            selected.clear(); refreshRows()
        }
        uninstallButton.setOnClickListener { onUninstallClicked() }
        banner.setOnClickListener { showPermissionsDialog() }

        startScan()
    }

    override fun onResume() {
        super.onResume()
        refreshBanner()
    }

    // ---- menu ----

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.main, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean = when (item.itemId) {
        R.id.action_theme -> {
            prefs().edit().putBoolean(KEY_DARK, !isDark()).apply()
            recreate() // the theme is applied at inflation, so the activity restarts
            true
        }
        R.id.action_rescan -> { startScan(); true }
        R.id.action_permissions -> { showPermissionsDialog(); true }
        else -> super.onOptionsItemSelected(item)
    }

    private fun prefs() = getSharedPreferences("uninstaller", Context.MODE_PRIVATE)
    private fun isDark() = prefs().getBoolean(KEY_DARK, false)

    // ---- permissions ----

    private fun refreshBanner() {
        val missing = buildList {
            if (!hasAllFilesAccess()) add("leftover cleanup needs All files access")
            if (!hasUsageAccess(this@MainActivity)) add("real app sizes need Usage access")
        }
        banner.visibility = if (missing.isEmpty()) View.GONE else View.VISIBLE
        if (missing.isNotEmpty()) {
            banner.text = missing.joinToString("; ").replaceFirstChar { it.uppercase() } + ". Tap to grant."
        }
    }

    private fun showPermissionsDialog() {
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
            toastDialog("This device has no Settings screen for that permission.")
        }
    }

    // ---- rows ----

    private fun refreshRows() {
        val term = search.text.toString().trim().lowercase()
        val wanted = sourceFilter.selectedItemPosition.takeIf { it > 0 }?.let { Source.entries[it - 1] }
        visible = allApps.filter { app ->
            (wanted == null || app.source == wanted) &&
                (term.isEmpty() || term in app.name.lowercase() || term in app.id.lowercase())
        }
        adapter.notifyDataSetChanged()
        status.text = "${visible.size} of ${allApps.size} shown · ${selected.size} selected"
        uninstallButton.isEnabled = selected.isNotEmpty()
    }

    private fun toggle(app: App) {
        if (!selected.add(app.id)) selected.remove(app.id)
        refreshRows()
    }

    /** CLAUDE.md non-negotiable, third rail: never pre-select system or
     *  Critical items — those get picked one at a time or not at all. */
    private fun selectAll() {
        visible.filter { !it.isSystem && it.risk != Risk.CRITICAL }.forEach { selected.add(it.id) }
        refreshRows()
    }

    private inner class AppAdapter : BaseAdapter() {
        override fun getCount() = visible.size
        override fun getItem(position: Int) = visible[position]
        override fun getItemId(position: Int) = position.toLong()

        override fun getView(position: Int, convertView: View?, parent: ViewGroup): View {
            val view = convertView
                ?: LayoutInflater.from(parent.context).inflate(R.layout.row_app, parent, false)
            val app = visible[position]
            view.findViewById<CheckBox>(R.id.check).isChecked = app.id in selected
            view.findViewById<TextView>(R.id.name).text = app.name
            view.findViewById<TextView>(R.id.meta).text = buildString {
                append(app.source.label)
                // "Other app store" on its own says nothing; the installing
                // package is the whole point of the tag.
                if (app.source == Source.OTHER_STORE) append(" (").append(app.installerLabel).append(")")
                if (app.version.isNotEmpty()) append(" · v").append(app.version)
                append(" · ").append(app.sizeHuman)
            }
            view.findViewById<TextView>(R.id.reason).apply {
                text = "${app.risk.label} — ${app.riskReason}"
                setTextColor(getColor(riskColour(app.risk)))
            }
            return view
        }
    }

    private fun riskColour(risk: Risk) = when (risk) {
        Risk.SAFE -> R.color.risk_safe
        Risk.CAUTION -> R.color.risk_caution
        Risk.CRITICAL -> R.color.risk_critical
    }

    // ---- scanning ----

    private fun startScan() {
        setBusy(true)
        status.setText(R.string.scanning)
        progress.isIndeterminate = true
        Thread {
            val apps = Scanner(this).scanAll()
            runOnUiThread {
                allApps = apps
                selected.retainAll(apps.mapTo(mutableSetOf()) { it.id })
                progress.isIndeterminate = false
                setBusy(false)
                refreshRows()
            }
        }.start()
    }

    private fun setBusy(busy: Boolean) {
        progress.visibility = if (busy) View.VISIBLE else View.GONE
        search.isEnabled = !busy
        sourceFilter.isEnabled = !busy
        uninstallButton.isEnabled = !busy && selected.isNotEmpty()
        list.isEnabled = !busy
    }

    // ---- uninstall flow ----

    private fun onUninstallClicked() {
        val apps = allApps.filter { it.id in selected }
        if (apps.isEmpty()) return
        confirm(apps) { startRemovals(apps) }
    }

    /**
     * CLAUDE.md non-negotiable: nothing is removed without this, and anything
     * Critical needs the extra acknowledgement before the button unlocks.
     */
    private fun confirm(apps: List<App>, onConfirmed: () -> Unit) {
        val view = layoutInflater.inflate(R.layout.dialog_confirm, null)
        val shown = apps.take(CONFIRM_LIST_LIMIT)
        view.findViewById<TextView>(R.id.listing).text = buildString {
            append(shown.joinToString("\n") { "• ${it.name} — ${it.source.label} — ${it.risk.label}" })
            if (apps.size > shown.size) append("\n… and ${apps.size - shown.size} more")
        }
        val acknowledge = view.findViewById<CheckBox>(R.id.acknowledge)
        val critical = apps.any { it.risk == Risk.CRITICAL }
        val systemOnly = apps.count { it.isSystem }

        val title = if (systemOnly > 0) {
            "Remove ${apps.size} item(s)? ($systemOnly preinstalled — Android only offers Disable)"
        } else {
            "Uninstall ${apps.size} item(s)?"
        }

        val dialog = AlertDialog.Builder(this)
            .setTitle(title)
            .setView(view)
            .setPositiveButton("Uninstall") { _, _ -> onConfirmed() }
            .setNegativeButton("Cancel", null)
            .create()

        if (critical) {
            acknowledge.visibility = View.VISIBLE
            dialog.setOnShowListener {
                val button = dialog.getButton(AlertDialog.BUTTON_POSITIVE)
                button.isEnabled = false
                acknowledge.setOnCheckedChangeListener { _, checked -> button.isEnabled = checked }
            }
        }
        dialog.show()
    }

    private fun startRemovals(apps: List<App>) {
        queue.clear()
        queue.addAll(apps)
        results.clear()
        removalTotal = apps.size
        setBusy(true)
        progress.progress = 0
        nextRemoval()
    }

    private fun nextRemoval() {
        val app = queue.removeFirstOrNull()
        if (app == null) {
            finishRemovals()
            return
        }
        pending = app
        status.text = "Removing ${app.name} (${results.size + 1} of $removalTotal)…"
        @Suppress("DEPRECATION") // the AndroidX result API is a whole dependency for this one call
        startActivityForResult(removalIntent(app), REQ_REMOVE)
    }

    @Deprecated("Framework Activity callback; kept to avoid an AndroidX dependency")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        @Suppress("DEPRECATION")
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != REQ_REMOVE) return
        val app = pending ?: return
        pending = null
        // resultCode is ignored on purpose — see removalOutcome().
        val (ok, message) = removalOutcome(packageManager, app)
        results.add(RemovalResult(app, ok, message))
        progress.progress = results.size * 100 / removalTotal
        progress.progressTintList = ColorStateList.valueOf(
            getColor(if (results.all { it.ok }) R.color.risk_safe else R.color.risk_critical)
        )
        nextRemoval()
    }

    private fun finishRemovals() {
        // Only real uninstalls free space: a preinstalled app that was merely
        // disabled is still sitting on the partition.
        val appFreed = results.filter { it.ok && !it.app.isSystem }.sumOf { it.app.sizeBytes }
        val removed = results.filter { it.ok && !it.app.isSystem }.map { it.app }
        status.text = "Looking for leftover files…"
        Thread {
            val found = removed.flatMap { leftoversFor(it, storage) }
                .distinctBy { it.absolutePath }
                .map { it to pathSize(it) }
            runOnUiThread {
                setBusy(false)
                if (found.isEmpty()) summarise(appFreed, 0L, emptyList())
                else offerLeftoverCleanup(found, appFreed)
            }
        }.start()
    }

    /** CLAUDE.md non-negotiable: leftovers are shown and opt-in, never
     *  deleted silently. */
    private fun offerLeftoverCleanup(found: List<Pair<File, Long>>, appFreed: Long) {
        val labels = found.map { (file, size) -> "${file.absolutePath}\n${formatSize(size)}" }
        val checked = BooleanArray(found.size) { true }
        AlertDialog.Builder(this)
            .setTitle("Leftover files found")
            .setMultiChoiceItems(labels.toTypedArray(), checked) { _, index, isChecked ->
                checked[index] = isChecked
            }
            .setPositiveButton("Delete") { _, _ ->
                val chosen = found.filterIndexed { i, _ -> checked[i] }.map { it.first }
                runLeftoverCleanup(chosen, appFreed)
            }
            .setNegativeButton("Keep") { _, _ -> summarise(appFreed, 0L, emptyList()) }
            .setCancelable(false)
            .show()
    }

    private fun runLeftoverCleanup(paths: List<File>, appFreed: Long) {
        setBusy(true)
        status.text = "Deleting ${paths.size} leftover item(s)…"
        Thread {
            val (freed, errors) = cleanLeftovers(paths)
            runOnUiThread {
                setBusy(false)
                summarise(appFreed, freed, errors.map { "${it.first.name}: ${it.second}" })
            }
        }.start()
    }

    private fun summarise(appFreed: Long, leftoverFreed: Long, errors: List<String>) {
        val ok = results.count { it.ok }
        val failures = results.filter { !it.ok }
        val text = buildString {
            append("$ok of ${results.size} removed.\n")
            append("Freed ${formatSize(appFreed + leftoverFreed)}")
            if (leftoverFreed > 0) append(" (${formatSize(leftoverFreed)} of it leftovers)")
            append(".")
            if (failures.isNotEmpty()) {
                append("\n\nNot removed:\n")
                append(failures.joinToString("\n") { "• ${it.app.name} — ${it.message}" })
            }
            if (errors.isNotEmpty()) {
                append("\n\nCouldn't delete:\n")
                append(errors.joinToString("\n") { "• $it" })
            }
        }
        selected.clear()
        AlertDialog.Builder(this)
            .setTitle("Done")
            .setMessage(text)
            .setPositiveButton("OK") { _, _ -> startScan() }
            .show()
    }

    private fun toastDialog(message: String) {
        AlertDialog.Builder(this).setMessage(message).setPositiveButton("OK", null).show()
    }

    private companion object {
        const val REQ_REMOVE = 1
        const val CONFIRM_LIST_LIMIT = 12 // fits a phone dialog; the count in the title is the total
        const val KEY_DARK = "dark"
    }
}
