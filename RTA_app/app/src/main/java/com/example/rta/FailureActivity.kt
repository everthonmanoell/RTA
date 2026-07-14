package com.example.rta
import android.graphics.Color
import android.os.Bundle
import android.util.Log
import android.view.Gravity
import android.widget.RelativeLayout
import android.widget.TextView

class FailureActivity : BaseRtaActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val hits = intent.getIntExtra("hits", 0)
        val total = intent.getIntExtra("total", 0)
        val errors = intent.getIntExtra("errors", 0)
        val errorMsg = intent.getStringExtra("errorMessage") ?: "Unknown error"
        Log.i("RTA_RESULT", "{\"status\":\"fail\",\"hits\":$hits,\"total\":$total,\"errors\":$errors,\"reason\":\"$errorMsg\",\"device_type\":\"$deviceType\"}")
        val layout = RelativeLayout(this).apply {
            setBackgroundColor(Color.parseColor("#C62828"))
            setOnClickListener { navigateTo(ArucoMarkersActivity::class.java) }
        }
        addCenteredArucoMarker(layout, R.drawable.tag15)
        val message = TextView(this).apply {
            text = "ALIGNMENT FAILED"
            textSize = 28f
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
        }
        layout.addView(message, RelativeLayout.LayoutParams(RelativeLayout.LayoutParams.WRAP_CONTENT, RelativeLayout.LayoutParams.WRAP_CONTENT).apply {
            addRule(RelativeLayout.ALIGN_PARENT_BOTTOM)
            addRule(RelativeLayout.CENTER_HORIZONTAL)
            setMargins(0, 0, 0, 260)
        })
        val scoreText = TextView(this).apply {
            text = "✅ Hits: $hits / $total    ❌ Errors: $errors"
            textSize = 18f
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
        }
        layout.addView(scoreText, RelativeLayout.LayoutParams(RelativeLayout.LayoutParams.WRAP_CONTENT, RelativeLayout.LayoutParams.WRAP_CONTENT).apply {
            addRule(RelativeLayout.ALIGN_PARENT_BOTTOM)
            addRule(RelativeLayout.CENTER_HORIZONTAL)
            setMargins(0, 0, 0, 140)
        })
        val reasonText = TextView(this).apply {
            text = errorMsg
            textSize = 14f
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
        }
        layout.addView(reasonText, RelativeLayout.LayoutParams(RelativeLayout.LayoutParams.WRAP_CONTENT, RelativeLayout.LayoutParams.WRAP_CONTENT).apply {
            addRule(RelativeLayout.ALIGN_PARENT_BOTTOM)
            addRule(RelativeLayout.CENTER_HORIZONTAL)
            setMargins(0, 0, 0, 80)
        })
        setContentView(layout)
    }
}
