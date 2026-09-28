package io.github.redwanshawkat.uninstaller

import android.app.AlertDialog
import android.os.Environment
import android.text.Editable
import android.text.SpannableStringBuilder
import android.text.TextWatcher
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.BaseAdapter
import android.widget.CheckBox
import android.widget.EditText
import android.widget.ImageView
import android.widget.ListView
import android.widget.Spinner
import android.widget.TextView
import java.io.File

enum class Ticked { NONE, SOME, ALL }

/** CLAUDE.md non-negotiable: system and Critical apps are never picked in
 *  bulk. They're ticked one at a time, or not at all. */
fun bulkPickable(app: App) = !app.isSystem && app.risk != Risk.CRITICAL

/** The circle over the list, as on Linux: ALL once every app shown that can
 *  be picked in bulk is ticked, SOME while anything shown is, else NONE. */
fun ticked(shown: List<App>, selected: Set<String>): Ticked {
    val pickable = shown.filter(::bulkPickable)
    return when {
        pickable.isNotEmpty() && pickable.all { it.id in selected } -> Ticked.ALL
        shown.any { it.id in selected } -> Ticked.SOME
        else -> Ticked.NONE
    }
}

/**
 * Uninstall: every installed app, where it came from and how risky it is to
 * remove. Same flow as the Linux and Windows builds: scan on a background
 * thread and marshal results back to the main thread, filter the list,
 * confirm before removing anything, then offer the leftovers. Nothing is
 * ticked until you tick it.
 *
 * The selected set holds package names, not row positions or checkbox states,
 * so filtering the list can't silently drop a selection.
 */
class UninstallPage(private val activity: MainActivity, root: View) {

    private val subtitle: TextView = root.findViewById(R.id.subtitle)
    private val refreshButton: View = root.findViewById(R.id.refresh)
    private val banner: TextView = root.findViewById(R.id.banner)
    private val search: EditText = root.findViewById(R.id.search)
    private val sourceFilter: Spinner = root.findViewById(R.id.source_filter)
    private val selectAllRow: View = root.findViewById(R.id.select_all_row)
    private val selectAll: ImageView = root.findViewById(R.id.select_all)
    private val shown: TextView = root.findViewById(R.id.shown)
    private val list: ListView = root.findViewById(R.id.list)
    private val bar = PageBar(root)

    private var allApps: List<App> = emptyList()
    private var visible: List<App> = emptyList()
    private val selected = mutableSetOf<String>()
    private val adapter = AppAdapter()
    private var busy = false

    // One removal at a time: Android draws its own dialog per package and
    // there is no batch uninstall for a normal app.
    private val queue = ArrayDeque<App>()
    private var pending: App? = null
    private var removalTotal = 0
    private val results = mutableListOf<RemovalResult>()

    private data class RemovalResult(val app: App, val ok: Boolean, val message: String)

    private val storage: File get() = Environment.getExternalStorageDirectory()

    init {
        root.findViewById<TextView>(R.id.title).setText(R.string.uninstall)
        root.findViewById<View>(R.id.list_card).clipToOutline = true // rows stay inside the rounded corners
        list.adapter = adapter
        list.setOnItemClickListener { _, _, position, _ -> toggle(visible[position]) }

        search.addTextChangedListener(object : TextWatcher {
            override fun afterTextChanged(s: Editable?) = refreshRows()
            override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) = Unit
            override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) = Unit
        })

        val filterLabels = listOf(activity.getString(R.string.all_sources)) + Source.entries.map { it.label }
        sourceFilter.adapter = ArrayAdapter(activity, android.R.layout.simple_spinner_item, filterLabels)
            .apply { setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item) }
        sourceFilter.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(p: AdapterView<*>?, v: View?, pos: Int, id: Long) = refreshRows()
            override fun onNothingSelected(p: AdapterView<*>?) = Unit
        }

        selectAllRow.setOnClickListener { onSelectAll() }
        refreshButton.setOnClickListener { startScan() }
        bar.button.visibility = View.VISIBLE
        bar.button.setOnClickListener { onUninstallClicked() }
        banner.setOnClickListener { activity.showPermissionsDialog() }

        startScan()
    }

    // ---- permissions ----

    fun refreshBanner() {
        val missing = buildList {
            if (!hasAllFilesAccess()) add("leftover cleanup needs All files access")
            if (!hasUsageAccess(activity)) add("real app sizes need Usage access")
        }
        banner.visibility = if (missing.isEmpty()) View.GONE else View.VISIBLE
        if (missing.isNotEmpty()) {
            banner.text = missing.joinToString("; ").replaceFirstChar { it.uppercase() } + ". Tap to grant."
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
        selectAll.setImageResource(
            when (ticked(visible, selected)) {
                Ticked.ALL -> R.drawable.circle_checked
                Ticked.SOME -> R.drawable.circle_some
                Ticked.NONE -> R.drawable.circle_empty
            }
        )
        shown.text = if (visible.size == allApps.size) "${allApps.size} apps" else "${visible.size} of ${allApps.size} shown"
        val chosen = allApps.filter { it.id in selected }
        bar.button.isEnabled = !busy && chosen.isNotEmpty()
        bar.button.text = activity.getString(R.string.uninstall_selected) + if (chosen.isEmpty()) "" else " · ${chosen.size}"
        bar.say(
            if (chosen.isEmpty()) "Tick apps to remove, or the circle for all of them."
            else "${formatSize(chosen.sumOf { it.sizeBytes })} to free · Android asks once per app"
        )
    }

    private fun toggle(app: App) {
        if (!selected.add(app.id)) selected.remove(app.id)
        refreshRows()
    }

    /** The circle: everything shown that can be picked in bulk, or, when
     *  there's nothing left to add, nothing shown (so apps picked by hand
     *  can be cleared with it too). */
    private fun onSelectAll() {
        val pickable = visible.filter(::bulkPickable)
        if (pickable.all { it.id in selected }) visible.forEach { selected.remove(it.id) }
        else pickable.forEach { selected.add(it.id) }
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
            view.findViewById<TextView>(R.id.name).text =
                SpannableStringBuilder(app.name).append("  ").append(tag(app.source.label, SOURCE_TAG.getValue(app.source)))
            view.findViewById<TextView>(R.id.meta).text = buildList {
                // "Other app store" on its own says nothing; the installing
                // package is the whole point of the tag.
                if (app.source == Source.OTHER_STORE) add("via ${app.installerLabel}")
                if (app.version.isNotEmpty()) add("v${app.version}")
                add(app.sizeHuman)
            }.joinToString(" · ")
            view.findViewById<TextView>(R.id.reason).text =
                SpannableStringBuilder(app.riskReason).append("  ").append(tag(app.risk.label, RISK_TAG.getValue(app.risk)))
            return view
        }
    }

    // ---- scanning ----

    private fun startScan() {
        setBusy(true)
        subtitle.text = "Looking…"
        bar.pulse()
        bar.say("Looking at every installed app…")
        Thread {
            val apps = Scanner(activity).scanAll()
            activity.runOnUiThread {
                allApps = apps
                selected.retainAll(apps.mapTo(mutableSetOf()) { it.id })
                val preinstalled = apps.count { it.isSystem }
                subtitle.text = "${apps.size} apps · ${apps.size - preinstalled} installed by you, $preinstalled preinstalled"
                setBusy(false)
                refreshRows()
            }
        }.start()
    }

    private fun setBusy(busy: Boolean) {
        this.busy = busy
        for (view in listOf(search, sourceFilter, list, selectAllRow, refreshButton)) view.isEnabled = !busy
        bar.button.isEnabled = !busy && selected.isNotEmpty()
        if (!busy) bar.done()
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
        val view = activity.layoutInflater.inflate(R.layout.dialog_confirm, null)
        val shownApps = apps.take(CONFIRM_LIST_LIMIT)
        view.findViewById<TextView>(R.id.listing).text = buildString {
            append(shownApps.joinToString("\n") { "• ${it.name} — ${it.source.label} — ${it.risk.label}" })
            if (apps.size > shownApps.size) append("\n… and ${apps.size - shownApps.size} more")
        }
        val acknowledge = view.findViewById<CheckBox>(R.id.acknowledge)
        val critical = apps.any { it.risk == Risk.CRITICAL }
        val systemOnly = apps.count { it.isSystem }

        val title = if (systemOnly > 0) {
            "Remove ${apps.size} item(s)? ($systemOnly preinstalled — Android only offers Disable)"
        } else {
            "Uninstall ${apps.size} item(s)?"
        }

        val dialog = AlertDialog.Builder(activity)
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
        bar.fill(0f, ok = true)
        nextRemoval()
    }

    private fun nextRemoval() {
        val app = queue.removeFirstOrNull()
        if (app == null) {
            finishRemovals()
            return
        }
        pending = app
        bar.say("Removing ${app.name} · ${results.size + 1} of $removalTotal · Android asks each time")
        @Suppress("DEPRECATION") // the AndroidX result API is a whole dependency for this one call
        activity.startActivityForResult(removalIntent(app), MainActivity.REQ_REMOVE)
    }

    /** Back from the system's uninstall dialog (or App Info). */
    fun onRemovalReturned() {
        val app = pending ?: return
        pending = null
        // The result code is ignored on purpose — see removalOutcome().
        val (ok, message) = removalOutcome(activity.packageManager, app)
        results.add(RemovalResult(app, ok, message))
        bar.fill(results.size.toFloat() / removalTotal, ok = results.all { it.ok })
        nextRemoval()
    }

    private fun finishRemovals() {
        // Only real uninstalls free space: a preinstalled app that was merely
        // disabled is still sitting on the partition.
        val appFreed = results.filter { it.ok && !it.app.isSystem }.sumOf { it.app.sizeBytes }
        val removed = results.filter { it.ok && !it.app.isSystem }.map { it.app }
        bar.say("Looking for leftover files…")
        Thread {
            val found = removed.flatMap { leftoversFor(it, storage) }
                .distinctBy { it.absolutePath }
                .map { it to pathSize(it) }
            activity.runOnUiThread {
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
        AlertDialog.Builder(activity)
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
        bar.pulse()
        bar.say("Deleting ${paths.size} leftover item(s)…")
        Thread {
            val (freed, errors) = cleanLeftovers(paths)
            activity.runOnUiThread {
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
        AlertDialog.Builder(activity)
            .setTitle("Done")
            .setMessage(text)
            .setPositiveButton("OK") { _, _ -> startScan() }
            .show()
    }

    private companion object {
        const val CONFIRM_LIST_LIMIT = 12 // fits a phone dialog; the count in the title is the total
    }
}
