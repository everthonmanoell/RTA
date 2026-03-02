package com.example.rta

import android.app.Activity
import android.graphics.Bitmap
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.util.DisplayMetrics
import android.view.WindowInsets
import android.widget.ImageView
import android.widget.RelativeLayout
import com.google.zxing.BarcodeFormat
import com.google.zxing.qrcode.QRCodeWriter

class MainActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        // 1. PRIMEIRO criamos a tela e o layout
        val jsonString = extractPreciseDeviceMetrics()
        val qrBitmap = generateQRCode(jsonString, 800)

        val imageView = ImageView(this).apply {
            setImageBitmap(qrBitmap)
            setBackgroundColor(Color.WHITE)
        }

        val layout = RelativeLayout(this).apply {
            setBackgroundColor(Color.WHITE)
            addView(imageView, RelativeLayout.LayoutParams(
                RelativeLayout.LayoutParams.WRAP_CONTENT,
                RelativeLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                addRule(RelativeLayout.CENTER_IN_PARENT, RelativeLayout.TRUE)
            })
        }

        // 2. Colocamos o layout na Activity
        setContentView(layout)

        // 3. AGORA SIM, com a tela criada, podemos pedir para esconder as barras!
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            window.insetsController?.hide(WindowInsets.Type.statusBars() or WindowInsets.Type.navigationBars())
        }
    }

    private fun generateQRCode(text: String, size: Int): Bitmap {
        val writer = QRCodeWriter()
        val bitMatrix = writer.encode(text, BarcodeFormat.QR_CODE, size, size)
        val width = bitMatrix.width
        val height = bitMatrix.height
        val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.RGB_565)
        
        for (x in 0 until width) {
            for (y in 0 until height) {
                bitmap.setPixel(x, y, if (bitMatrix.get(x, y)) Color.BLACK else Color.WHITE)
            }
        }
        return bitmap
    }

    private fun extractPreciseDeviceMetrics(): String {
        val widthPx: Int
        val heightPx: Int
        var xdpi = 0f
        var ydpi = 0f
        var density = 0f

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val bounds = windowManager.currentWindowMetrics.bounds
            widthPx = bounds.width()
            heightPx = bounds.height()
            
            val display = display
            if (display != null) {
                val metrics = DisplayMetrics()
                display.getRealMetrics(metrics)
                xdpi = metrics.xdpi
                ydpi = metrics.ydpi
                density = metrics.density
            }
        } else {
            val metrics = DisplayMetrics()
            @Suppress("DEPRECATION")
            windowManager.defaultDisplay.getRealMetrics(metrics)
            widthPx = metrics.widthPixels
            heightPx = metrics.heightPixels
            xdpi = metrics.xdpi
            ydpi = metrics.ydpi
            density = metrics.density
        }

        return """
            {
                "fabricante": "${Build.MANUFACTURER}",
                "modelo": "${Build.MODEL}",
                "w_px": $widthPx,
                "h_px": $heightPx,
                "xdpi": $xdpi,
                "ydpi": $ydpi
            }
        """.trimIndent()
    }
}