package com.example.rta
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.widget.Button
import android.widget.ImageView
import android.widget.RelativeLayout

class QrCodeActivity : BaseRtaActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val jsonString = extractPreciseDeviceMetrics()
        val qrBitmap = generateQRCode(jsonString, 800)
        val imageView = ImageView(this).apply {
            setImageBitmap(qrBitmap)
            setBackgroundColor(Color.WHITE)
        }
        val layout = RelativeLayout(this).apply {
            setBackgroundColor(Color.parseColor("#121212"))
            addView(imageView, RelativeLayout.LayoutParams(RelativeLayout.LayoutParams.WRAP_CONTENT, RelativeLayout.LayoutParams.WRAP_CONTENT).apply {
                addRule(RelativeLayout.CENTER_IN_PARENT, RelativeLayout.TRUE)
            })
        }
        val nextButton = Button(this).apply {
            text = "Next"
            textSize = 18f
            setTextColor(Color.WHITE)
            background = GradientDrawable().apply { setColor(Color.parseColor("#1565C0")); cornerRadius = 24f }
            setPadding(60, 20, 60, 20)
            setOnClickListener { navigateTo(ArucoMarkersActivity::class.java) }
        }
        layout.addView(nextButton, RelativeLayout.LayoutParams(RelativeLayout.LayoutParams.WRAP_CONTENT, RelativeLayout.LayoutParams.WRAP_CONTENT).apply {
            addRule(RelativeLayout.ALIGN_PARENT_BOTTOM)
            addRule(RelativeLayout.CENTER_HORIZONTAL)
            setMargins(0, 0, 0, 60)
        })
        setContentView(layout)
    }
}
