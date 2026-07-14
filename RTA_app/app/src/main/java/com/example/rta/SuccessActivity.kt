package com.example.rta
import android.graphics.Color
import android.os.Bundle
import android.util.Log
import android.view.Gravity
import android.widget.RelativeLayout
import android.widget.TextView

class SuccessActivity : BaseRtaActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val hits = intent.getIntExtra("hits", 0)
        val total = intent.getIntExtra("total", 0)
        Log.i("RTA_RESULT", "{\"status\":\"success\",\"hits\":$hits,\"total\":$total,\"errors\":0,\"device_type\":\"$deviceType\"}")
        val layout = RelativeLayout(this).apply {
            setBackgroundColor(Color.parseColor("#2E7D32"))
            setOnClickListener { navigateTo(ArucoMarkersActivity::class.java) }
        }
        addCenteredArucoMarker(layout, R.drawable.tag14)
        val message = TextView(this).apply {
            text = "ALIGNMENT APPROVED"
            textSize = 28f
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
        }
        layout.addView(message, RelativeLayout.LayoutParams(RelativeLayout.LayoutParams.WRAP_CONTENT, RelativeLayout.LayoutParams.WRAP_CONTENT).apply {
            addRule(RelativeLayout.ALIGN_PARENT_BOTTOM)
            addRule(RelativeLayout.CENTER_HORIZONTAL)
            setMargins(0, 0, 0, 140)
        })
        setContentView(layout)
    }
}
