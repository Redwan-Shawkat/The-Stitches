package io.github.redwanshawkat.uninstaller

import android.content.res.ColorStateList
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.text.SpannableString
import android.text.Spanned
import android.text.style.ReplacementSpan
import android.view.View
import android.widget.Button
import android.widget.ProgressBar
import android.widget.TextView

/**
 * What both pages are built from, as widgets.py is on the Linux build: a
 * coloured tag inside a line of text, and the dark action bar with its line
 * loader. The colours are that build's, so a tag reads the same on both.
 */

/** (text, background) for each tag. */
val RISK_TAG = mapOf(
    Risk.SAFE to (0xFF17663AL to 0xFFE6F5ECL),
    Risk.CAUTION to (0xFF7A4D00L to 0xFFFFF4DCL),
    Risk.CRITICAL to (0xFFA3231AL to 0xFFFDE9E7L),
)
val HEALTH_TAG = mapOf(
    Health.OK to RISK_TAG.getValue(Risk.SAFE),
    Health.WARNING to RISK_TAG.getValue(Risk.CAUTION),
    Health.PROBLEM to RISK_TAG.getValue(Risk.CRITICAL),
    Health.INFO to (0xFF3441B0L to 0xFFEEF1FFL),
)
val SOURCE_TAG = mapOf(
    Source.PLAY to (0xFF16664BL to 0xFFE7F6F0L),
    Source.FDROID to (0xFF3441B0L to 0xFFEEF1FFL),
    Source.OTHER_STORE to (0xFF8A4200L to 0xFFFFF1E6L),
    Source.SIDELOADED to (0xFF9B1F5BL to 0xFFFDEEF5L),
    Source.PREINSTALLED to (0xFF5A5C66L to 0xFFECECEFL),
)

/** A rounded label a little smaller than the text around it, sitting on its
 *  baseline. Linux draws the same thing square, because Pango can't round. */
private class TagSpan(private val fg: Int, private val bg: Int) : ReplacementSpan() {
    private fun small(paint: Paint) = Paint(paint).apply { textSize = paint.textSize * 0.82f }
    private fun pad(paint: Paint) = paint.textSize * 0.35f

    override fun getSize(paint: Paint, text: CharSequence, start: Int, end: Int, fm: Paint.FontMetricsInt?): Int {
        paint.getFontMetricsInt(fm) // the line's height, when the tag is all there is on it (Home's verdicts)
        return (small(paint).measureText(text, start, end) + 2 * pad(paint)).toInt()
    }

    override fun draw(
        canvas: Canvas, text: CharSequence, start: Int, end: Int, x: Float, top: Int, y: Int, bottom: Int, paint: Paint,
    ) {
        val small = small(paint)
        val pad = pad(paint)
        val box = RectF(x, y + small.ascent() - pad / 3, x + getSize(paint, text, start, end, null), y + small.descent() + pad / 3)
        canvas.drawRoundRect(box, pad, pad, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = bg })
        small.color = fg
        canvas.drawText(text, start, end, x + pad, y.toFloat(), small)
    }
}

fun tag(text: String, colors: Pair<Long, Long>): CharSequence = SpannableString(text).apply {
    setSpan(TagSpan(colors.first.toInt(), colors.second.toInt()), 0, length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
}

/** The floating dark bar at the bottom of a page: the line loader along its
 *  top edge, a status line, and the page's one button, if it has one. */
class PageBar(root: View) {
    private val line: ProgressBar = root.findViewById(R.id.line)
    private val status: TextView = root.findViewById(R.id.status)
    val button: Button = root.findViewById(R.id.action)

    fun say(text: CharSequence) {
        status.text = text
    }

    /** Sweeps back and forth while looking. */
    fun pulse() {
        line.isIndeterminate = true
        line.visibility = View.VISIBLE
    }

    /** Fills as the work gets done; red from the first failure on. */
    fun fill(fraction: Float, ok: Boolean) {
        line.isIndeterminate = false
        line.progress = (fraction * line.max).toInt()
        line.progressTintList = ColorStateList.valueOf(line.context.getColor(if (ok) R.color.line else R.color.line_error))
        line.visibility = View.VISIBLE
    }

    fun done() {
        line.visibility = View.GONE
    }
}
