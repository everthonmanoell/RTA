package com.example.rta
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.widget.Button
import android.widget.RelativeLayout

class ArucoMarkersActivity : BaseRtaActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val layout = RelativeLayout(this).apply { setBackgroundColor(Color.WHITE) }
        val tags = markerProfiles[deviceType] ?: markerProfiles["flat"]!!
        val markerViews = addLateralArucoMarkers(layout, tags)
        var remainingMarkers = markerViews.size
        for (marker in markerViews) {
            marker.setOnClickListener {
                marker.visibility = android.view.View.INVISIBLE
                remainingMarkers--
                if (remainingMarkers <= 0) {
                    navigateTo(GridActivity::class.java)
                }
            }
        }
        val resetButton = Button(this).apply {
            text = "RESET"
            textSize = 16f
            setTextColor(Color.WHITE)
            background = GradientDrawable().apply { setColor(Color.RED); cornerRadius = 20f }
            setPadding(40, 80, 40, 80)
            setOnClickListener { navigateTo(ArucoMarkersActivity::class.java) }
        }
        layout.addView(resetButton, RelativeLayout.LayoutParams(RelativeLayout.LayoutParams.WRAP_CONTENT, RelativeLayout.LayoutParams.WRAP_CONTENT).apply {
            addRule(RelativeLayout.CENTER_IN_PARENT)
        })
        setContentView(layout)
    }
}
