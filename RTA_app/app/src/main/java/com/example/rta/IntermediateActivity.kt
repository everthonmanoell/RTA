package com.example.rta
import android.graphics.Color
import android.os.Bundle
import android.widget.RelativeLayout

class IntermediateActivity : BaseRtaActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val layout = RelativeLayout(this).apply {
            setBackgroundColor(Color.WHITE)
        }
        val redButton = android.view.View(this).apply {
            setBackgroundColor(Color.RED)
            setOnClickListener { navigateTo(ArucoMarkersActivity::class.java) }
        }
        layout.addView(redButton, RelativeLayout.LayoutParams(10, 10).apply {
            addRule(RelativeLayout.CENTER_IN_PARENT)
        })
        setContentView(layout)
    }
}
