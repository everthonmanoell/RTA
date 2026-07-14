package com.example.rta

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.provider.Settings
import android.util.DisplayMetrics
import android.util.Log
import android.view.WindowInsets
import android.view.WindowManager
import android.widget.ImageView
import android.widget.RelativeLayout
import com.google.zxing.BarcodeFormat
import com.google.zxing.qrcode.QRCodeWriter
import org.json.JSONObject
import java.net.InetSocketAddress
import java.net.SocketTimeoutException

abstract class BaseRtaActivity : Activity() {
    val markerTagSizeDp = 120f
    val markerMarginDp = 16f
    private val markerSendMaxAttempts = 20
    private val markerSendRetryDelayMs = 750L

    @Volatile
    private var markerSendInProgress = false

    var markerRealWidthMm: Float = 0f
    var markerRealHeightMm: Float = 0f
    var markerXDistanceMm: Float = 0f

    var pythonServerIp = "192.168.0.100"
    var pythonServerPort = 50605

    var deviceType = "flat"

    companion object {
        private const val PREFS_NAME = "rta_runtime_config"
        private const val PREF_KEY_PYTHON_IP = "python_server_ip"
        private const val PREF_KEY_PYTHON_PORT = "python_server_port"
        const val EXTRA_PYTHON_IP = "python_server_ip"
        const val EXTRA_PYTHON_PORT = "python_server_port"
        const val EXTRA_DEVICE_TYPE = "device_type"
        
        // Prevent spamming python server on every activity change
        var hasSentParamsThisSession = false
    }

    val markerProfiles = mapOf(
        "flat" to listOf(
            R.drawable.tag1, R.drawable.tag2, R.drawable.tag3, R.drawable.tag4
        ),
        "foldable" to listOf(
            R.drawable.tag1, R.drawable.tag2, R.drawable.tag3, R.drawable.tag4,
            R.drawable.tag5, R.drawable.tag6, R.drawable.tag7, R.drawable.tag8
        ),
        "one" to listOf(R.drawable.tag1),
        "two" to listOf(R.drawable.tag1, R.drawable.tag2),
        "three" to listOf(R.drawable.tag1, R.drawable.tag2, R.drawable.tag3),
        "six" to listOf(
            R.drawable.tag1, R.drawable.tag2, R.drawable.tag3,
            R.drawable.tag4, R.drawable.tag5, R.drawable.tag6
        ),
        "seven" to listOf(
            R.drawable.tag1, R.drawable.tag2, R.drawable.tag3,
            R.drawable.tag4, R.drawable.tag5, R.drawable.tag6, R.drawable.tag7
        ),
        "eight" to listOf(
            R.drawable.tag1, R.drawable.tag2, R.drawable.tag3,
            R.drawable.tag4, R.drawable.tag5, R.drawable.tag6,
            R.drawable.tag7, R.drawable.tag8
        )
    )

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        applyPythonServerConfigFromIntentOrPrefs()
        deviceType = intent.getStringExtra(EXTRA_DEVICE_TYPE) ?: "flat"

        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        setMaximumBrightness()

        val density = resources.displayMetrics.density
        val xdpi = resources.displayMetrics.xdpi
        val ydpi = resources.displayMetrics.ydpi
        val tagSizePx = markerTagSizeDp * density
        markerRealWidthMm = tagSizePx / xdpi * 25.4f
        markerRealHeightMm = tagSizePx / ydpi * 25.4f

        val snapshot = captureDisplaySnapshot()
        val marginPx = markerMarginDp * density
        val usableWidthPx = snapshot.widthPx.toFloat()
        val left = marginPx
        val right = usableWidthPx - marginPx - tagSizePx
        markerXDistanceMm = maxOf(0f, (right - left) / xdpi * 25.4f)
    }

    override fun onResume() {
        super.onResume()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            window.insetsController?.hide(WindowInsets.Type.statusBars() or WindowInsets.Type.navigationBars())
        }

        if (!hasSentParamsThisSession) {
            Handler(Looper.getMainLooper()).postDelayed({
                sendMarkerParamsToPython()
            }, 250)
        }
    }

    private fun applyPythonServerConfigFromIntentOrPrefs() {
        val prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

        val intentIp = intent?.getStringExtra(EXTRA_PYTHON_IP)?.trim().orEmpty()
        val intentPort = intent?.getIntExtra(EXTRA_PYTHON_PORT, -1) ?: -1

        val hasIntentIp = intentIp.isNotEmpty()
        val hasIntentPort = intentPort in 1..65535

        if (hasIntentIp || hasIntentPort) {
            if (hasIntentIp) {
                pythonServerIp = intentIp
                prefs.edit().putString(PREF_KEY_PYTHON_IP, pythonServerIp).apply()
            }
            if (hasIntentPort) {
                pythonServerPort = intentPort
                prefs.edit().putInt(PREF_KEY_PYTHON_PORT, pythonServerPort).apply()
            }
            return
        }

        val storedIp = prefs.getString(PREF_KEY_PYTHON_IP, null)
        val storedPort = prefs.getInt(PREF_KEY_PYTHON_PORT, -1)

        if (!storedIp.isNullOrBlank()) pythonServerIp = storedIp
        if (storedPort in 1..65535) pythonServerPort = storedPort
    }

    private fun sendMarkerParamsToPython() {
        if (markerSendInProgress) return
        markerSendInProgress = true
        hasSentParamsThisSession = true

        Thread {
            try {
                val snapshot = captureDisplaySnapshot()
                val params = JSONObject().apply {
                    put("MARKER_REAL_WIDTH_MM", markerRealWidthMm)
                    put("MARKER_REAL_HEIGHT_MM", markerRealHeightMm)
                    put("MARKER_X_DISTANCE_MM", markerXDistanceMm)
                    put("tag_size_dp", markerTagSizeDp)
                    put("tag_size_px", markerTagSizeDp * snapshot.density)
                    put("margin_dp", markerMarginDp)
                    put("margin_px", markerMarginDp * snapshot.density)
                    put("density", snapshot.density)
                    put("density_dpi", snapshot.densityDpi)
                    put("xdpi", snapshot.xdpi)
                    put("ydpi", snapshot.ydpi)
                    put("screen_width_px", snapshot.widthPx)
                    put("screen_height_px", snapshot.heightPx)
                    put("orientation", snapshot.orientation)
                    put("rotation", snapshot.rotation)
                    put("inset_left_px", snapshot.insetLeftPx)
                    put("inset_top_px", snapshot.insetTopPx)
                    put("inset_right_px", snapshot.insetRightPx)
                    put("inset_bottom_px", snapshot.insetBottomPx)
                    put("timestamp_ms", System.currentTimeMillis())
                    put("elapsed_realtime_ms", SystemClock.elapsedRealtime())
                    put("device_type", deviceType)
                    put("manufacturer", Build.MANUFACTURER)
                    put("model", Build.MODEL)
                    put("sdk_int", Build.VERSION.SDK_INT)
                }.toString()
                val payload = params.toByteArray(Charsets.UTF_8)

                var sent = false
                for (attempt in 1..markerSendMaxAttempts) {
                    try {
                        java.net.Socket().use { socket ->
                            socket.tcpNoDelay = true
                            socket.connect(InetSocketAddress(pythonServerIp, pythonServerPort), 1500)
                            socket.soTimeout = 1500
                            val out = socket.getOutputStream()
                            out.write(payload)
                            out.flush()
                            socket.shutdownOutput()

                            val ackBytes = ByteArray(2)
                            val read = socket.getInputStream().read(ackBytes)
                            val ack = if (read > 0) String(ackBytes, 0, read) else ""
                            if (ack != "OK") throw SocketTimeoutException("ACK inválido")
                        }
                        sent = true
                        break
                    } catch (e: Exception) {
                        if (attempt < markerSendMaxAttempts) Thread.sleep(markerSendRetryDelayMs)
                    }
                }
                if (!sent) Log.e("RTA", "Falha definitiva ao enviar parâmetros.")
            } catch (e: Exception) {
                Log.e("RTA", "Erro: \${e.message}")
            } finally {
                markerSendInProgress = false
            }
        }.start()
    }

    data class DisplaySnapshot(
        val widthPx: Int,
        val heightPx: Int,
        val density: Float,
        val densityDpi: Int,
        val xdpi: Float,
        val ydpi: Float,
        val orientation: Int,
        val rotation: Int,
        val insetLeftPx: Int,
        val insetTopPx: Int,
        val insetRightPx: Int,
        val insetBottomPx: Int
    )

    fun captureDisplaySnapshot(): DisplaySnapshot {
        val displayMetrics = DisplayMetrics()
        windowManager.defaultDisplay.getRealMetrics(displayMetrics)
        val density = displayMetrics.density
        val densityDpi = displayMetrics.densityDpi
        val xdpi = displayMetrics.xdpi
        val ydpi = displayMetrics.ydpi
        val orientation = resources.configuration.orientation
        val rotation = windowManager.defaultDisplay.rotation

        var insetLeftPx = 0
        var insetTopPx = 0
        var insetRightPx = 0
        var insetBottomPx = 0

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val windowInsets = windowManager.currentWindowMetrics.windowInsets
            val insets = windowInsets.getInsetsIgnoringVisibility(WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
            insetLeftPx = insets.left
            insetTopPx = insets.top
            insetRightPx = insets.right
            insetBottomPx = insets.bottom
        }

        return DisplaySnapshot(
            displayMetrics.widthPixels, displayMetrics.heightPixels,
            density, densityDpi, xdpi, ydpi, orientation, rotation,
            insetLeftPx, insetTopPx, insetRightPx, insetBottomPx
        )
    }

    private fun setMaximumBrightness() {
        try {
            val layoutParams = window.attributes
            layoutParams.screenBrightness = WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_FULL
            window.attributes = layoutParams
        } catch (e: Exception) {
            Log.e("RTA", "Erro ao ajustar brilho: \${e.message}")
        }
    }

    fun extractPreciseDeviceMetrics(): String {
        val snapshot = captureDisplaySnapshot()
        return JSONObject().apply {
            put("density", snapshot.density)
            put("density_dpi", snapshot.densityDpi)
            put("xdpi", snapshot.xdpi)
            put("ydpi", snapshot.ydpi)
            put("screen_width_px", snapshot.widthPx)
            put("screen_height_px", snapshot.heightPx)
            put("orientation", snapshot.orientation)
            put("rotation", snapshot.rotation)
            put("inset_left_px", snapshot.insetLeftPx)
            put("inset_top_px", snapshot.insetTopPx)
            put("inset_right_px", snapshot.insetRightPx)
            put("inset_bottom_px", snapshot.insetBottomPx)
            put("device_type", deviceType)
            put("manufacturer", Build.MANUFACTURER)
            put("model", Build.MODEL)
            put("sdk_int", Build.VERSION.SDK_INT)
        }.toString()
    }

    fun generateQRCode(text: String, size: Int): Bitmap {
        val qrCodeWriter = QRCodeWriter()
        val bitMatrix = qrCodeWriter.encode(text, BarcodeFormat.QR_CODE, size, size)
        val width = bitMatrix.width
        val height = bitMatrix.height
        val bmp = Bitmap.createBitmap(width, height, Bitmap.Config.RGB_565)
        for (x in 0 until width) {
            for (y in 0 until height) {
                bmp.setPixel(x, y, if (bitMatrix.get(x, y)) Color.BLACK else Color.WHITE)
            }
        }
        return bmp
    }

    fun addLateralArucoMarkers(layout: RelativeLayout, tags: List<Int>, tagSizeDp: Int = markerTagSizeDp.toInt(), marginDp: Int = markerMarginDp.toInt()): List<ImageView> {
        val snapshot = captureDisplaySnapshot()
        val density = resources.displayMetrics.density
        val tagSize = (tagSizeDp * density).toInt()
        val margin = (marginDp * density).toInt()
        val contentLeft = 0
        val contentTop = 0
        val contentRight = snapshot.widthPx
        val contentBottom = snapshot.heightPx

        val contentWidth = maxOf(tagSize + (2 * margin) + 1, contentRight - contentLeft)
        val contentHeight = maxOf(tagSize + (2 * margin) + 1, contentBottom - contentTop)

        val areaLeft = contentLeft
        val areaTop = contentTop
        val areaRight = areaLeft + contentWidth
        val areaBottom = areaTop + contentHeight

        val left = areaLeft + margin
        val right = areaRight - margin - tagSize
        val createdViews = mutableListOf<ImageView>()

        if (tags.size <= 6) {
            for ((i, resId) in tags.withIndex()) {
                val tag = ImageView(this).apply {
                    setImageResource(resId)
                    setBackgroundColor(Color.WHITE)
                    scaleType = ImageView.ScaleType.FIT_XY
                    adjustViewBounds = false
                }
                val params = RelativeLayout.LayoutParams(tagSize, tagSize).apply {
                    when (i) {
                        0 -> { addRule(RelativeLayout.ALIGN_PARENT_START); addRule(RelativeLayout.ALIGN_PARENT_TOP); marginStart = margin; topMargin = margin }
                        1 -> { addRule(RelativeLayout.ALIGN_PARENT_END); addRule(RelativeLayout.ALIGN_PARENT_BOTTOM); marginEnd = margin; bottomMargin = margin }
                        2 -> { addRule(RelativeLayout.ALIGN_PARENT_START); addRule(RelativeLayout.ALIGN_PARENT_BOTTOM); marginStart = margin; bottomMargin = margin }
                        3 -> { addRule(RelativeLayout.ALIGN_PARENT_END); addRule(RelativeLayout.ALIGN_PARENT_TOP); marginEnd = margin; topMargin = margin }
                        4 -> { addRule(RelativeLayout.ALIGN_PARENT_START); addRule(RelativeLayout.CENTER_VERTICAL); marginStart = margin }
                        else -> { addRule(RelativeLayout.ALIGN_PARENT_END); addRule(RelativeLayout.CENTER_VERTICAL); marginEnd = margin }
                    }
                }
                layout.addView(tag, params)
                createdViews.add(tag)
            }
            return createdViews
        } else {
            val halfHeight = contentHeight / 2
            val topHalfTop = areaTop + margin
            val topHalfBottom = areaTop + halfHeight - margin - tagSize
            val bottomHalfTop = areaTop + halfHeight + margin
            val bottomHalfBottom = areaBottom - margin - tagSize

            val topHalfPositions = listOf(
                left to topHalfTop, right to topHalfTop, left to topHalfBottom, right to topHalfBottom
            )

            val bottomCount = tags.size - 4
            val bottomHalfPositions = when (bottomCount) {
                1 -> listOf(left to bottomHalfBottom)
                2 -> listOf(left to bottomHalfBottom, right to bottomHalfBottom)
                3 -> listOf(left to bottomHalfBottom, right to bottomHalfBottom, left to bottomHalfTop)
                else -> listOf(left to bottomHalfBottom, right to bottomHalfBottom, left to bottomHalfTop, right to bottomHalfTop)
            }

            val positions = topHalfPositions + bottomHalfPositions
            for ((i, resId) in tags.withIndex()) {
                if (i >= positions.size) break
                val (x, y) = positions[i]

                val tag = ImageView(this).apply {
                    setImageResource(resId)
                    setBackgroundColor(Color.WHITE)
                    scaleType = ImageView.ScaleType.FIT_XY
                    adjustViewBounds = false
                }
                val params = RelativeLayout.LayoutParams(tagSize, tagSize).apply {
                    leftMargin = x; topMargin = y
                }
                layout.addView(tag, params)
                createdViews.add(tag)
            }
            return createdViews
        }
    }

    fun addCenteredArucoMarker(layout: RelativeLayout, resId: Int, tagSizeDp: Int = 140) {
        val density = resources.displayMetrics.density
        val tagSize = (tagSizeDp * density).toInt()

        val tag = ImageView(this).apply {
            setImageResource(resId)
            setBackgroundColor(Color.WHITE)
        }
        val params = RelativeLayout.LayoutParams(tagSize, tagSize).apply {
            addRule(RelativeLayout.CENTER_IN_PARENT)
        }
        layout.addView(tag, params)
    }
    
    // Helper para iniciar outras activities passando os parametros importantes
    fun navigateTo(clazz: Class<*>) {
        val intent = Intent(this, clazz)
        intent.putExtra(EXTRA_DEVICE_TYPE, deviceType)
        intent.putExtra(EXTRA_PYTHON_IP, pythonServerIp)
        intent.putExtra(EXTRA_PYTHON_PORT, pythonServerPort)
        intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_NEW_TASK)
        startActivity(intent)
        finish()
    }
}
