package io.github.redwanshawkat.uninstaller

import android.app.Activity
import android.os.Build
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import java.text.DateFormat
import java.util.Date

/**
 * Home: what this phone is and how it's doing. The Linux build's Home and
 * Diagnose in one page, since an app on Android can read these but fix none
 * of them. Laid out as Home is there: groups with an icon by each heading,
 * no borders. Every reading is a system value, quick enough for the main
 * thread, so the page reads them again each time it comes back on screen.
 */
class HomePage(private val activity: Activity, root: View) {

    private val groups: LinearLayout = root.findViewById(R.id.groups)
    private val bar = PageBar(root)

    init {
        root.findViewById<TextView>(R.id.title).setText(R.string.home)
        root.findViewById<TextView>(R.id.subtitle).text =
            "Android ${Build.VERSION.RELEASE} · read each time you open this page"
        root.findViewById<View>(R.id.refresh).setOnClickListener { refresh() }
    }

    fun refresh() {
        val findings = healthCheck(activity)
        val (doing, security) = findings.partition { it.title in DOING }
        groups.removeAllViews()
        heading("This phone", R.drawable.ic_phone)
        val model = if (Build.MODEL.startsWith(Build.MANUFACTURER, ignoreCase = true)) Build.MODEL
        else "${Build.MANUFACTURER.replaceFirstChar { it.uppercase() }} ${Build.MODEL}"
        fact("Model", model)
        fact("Android", "${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})")
        fact("Build", Build.DISPLAY)
        fact("Kernel", System.getProperty("os.version").orEmpty())
        heading("How it's doing", R.drawable.ic_pulse)
        doing.forEach(::finding)
        heading("Security", R.drawable.ic_shield)
        security.forEach(::finding)
        groups.addView(TextView(activity).apply {
            text = "Android doesn't let an app scan system files, test memory or read the storage chip's wear " +
                "without root; System integrity above is Android's own boot-time check."
            textSize = 12f
            alpha = 0.6f
            setPadding(0, (18 * resources.displayMetrics.density).toInt(), 0, 0)
        })
        val flagged = findings.count { it.health == Health.WARNING || it.health == Health.PROBLEM }
        val at = DateFormat.getTimeInstance(DateFormat.SHORT).format(Date())
        bar.say(if (flagged > 0) "$flagged to look at · read at $at" else "Nothing to look at · read at $at")
    }

    private fun heading(title: String, icon: Int) {
        val view = activity.layoutInflater.inflate(R.layout.group_heading, groups, false) as TextView
        view.text = title
        view.setCompoundDrawablesRelativeWithIntrinsicBounds(icon, 0, 0, 0)
        groups.addView(view)
    }

    private fun fact(key: String, value: String) {
        val view = activity.layoutInflater.inflate(R.layout.row_fact, groups, false)
        view.findViewById<TextView>(R.id.key).text = key
        view.findViewById<TextView>(R.id.value).text = value
        groups.addView(view)
    }

    private fun finding(finding: Finding) {
        val view = activity.layoutInflater.inflate(R.layout.row_finding, groups, false)
        view.findViewById<TextView>(R.id.title).text = finding.title
        view.findViewById<TextView>(R.id.status).text = tag(finding.health.label, HEALTH_TAG.getValue(finding.health))
        view.findViewById<TextView>(R.id.detail).text = finding.detail
        groups.addView(view)
    }

    private companion object {
        val DOING = setOf("Storage", "Memory", "Battery", "Temperature") // the rest is security
    }
}
