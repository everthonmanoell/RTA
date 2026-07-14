package com.example.rta
import android.graphics.Color
import android.os.Bundle
import android.widget.ImageView
import android.widget.RelativeLayout

class InitialActivity : BaseRtaActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val layout = RelativeLayout(this).apply {
            setBackgroundColor(Color.WHITE)
            setOnClickListener { navigateTo(IntermediateActivity::class.java) }
        }
        val snapshot = captureDisplaySnapshot()
        val minDim = minOf(snapshot.widthPx, snapshot.heightPx)
        val tagSize = (minDim * 0.9f).toInt()
        val tag = ImageView(this).apply {
            setImageResource(R.drawable.tag0)
            setBackgroundColor(Color.WHITE)
            scaleType = ImageView.ScaleType.FIT_XY
        }
        layout.addView(tag, RelativeLayout.LayoutParams(tagSize, tagSize).apply {
            addRule(RelativeLayout.CENTER_IN_PARENT)
        })
        setContentView(layout)
    }
}
