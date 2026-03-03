package com.example.rta

import android.app.Activity
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.Bundle
import android.util.DisplayMetrics
import android.util.Log
import android.view.Gravity
import android.view.MotionEvent
import android.view.WindowInsets
import android.widget.Button
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.RelativeLayout
import android.widget.TextView
import com.google.zxing.BarcodeFormat
import com.google.zxing.qrcode.QRCodeWriter

class MainActivity : Activity() {

    // Device type: "flat" (4 markers) or "foldable" (8 markers)
    // Set via ADB: adb shell am start -n com.example.rta/.MainActivity --es device_type foldable
    private var deviceType = "flat"

    // Marker profiles per device type
    private val markerProfiles = mapOf(
        "flat" to listOf(
            R.drawable.tag1,
            R.drawable.tag2,
            R.drawable.tag3,
            R.drawable.tag4
        ),
        "foldable" to listOf(
            R.drawable.tag1,
            R.drawable.tag2,
            R.drawable.tag3,
            R.drawable.tag4,
            R.drawable.tag5,
            R.drawable.tag6,
            R.drawable.tag7,
            R.drawable.tag8
        ),
        "one" to listOf(
            R.drawable.tag1
        ),
        "two" to listOf(
            R.drawable.tag1,
            R.drawable.tag2,
        ),
        "three" to listOf(
            R.drawable.tag1,
            R.drawable.tag2,
            R.drawable.tag3
        ),
        "six" to listOf(
            R.drawable.tag1,
            R.drawable.tag2,
            R.drawable.tag3,
            R.drawable.tag4,
            R.drawable.tag5,
            R.drawable.tag6
        ),
        "seven" to listOf(
            R.drawable.tag1,
            R.drawable.tag2,
            R.drawable.tag3,
            R.drawable.tag4,
            R.drawable.tag5,
            R.drawable.tag6,
            R.drawable.tag7,
        ),
        "eight" to listOf(
            R.drawable.tag1,
            R.drawable.tag2,
            R.drawable.tag3,
            R.drawable.tag4,
            R.drawable.tag5,
            R.drawable.tag6,
            R.drawable.tag7,
            R.drawable.tag8,
        ),

    )

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Read device type from ADB intent extra (defaults to "flat")
        deviceType = intent.getStringExtra("device_type") ?: "flat"
        
        // Keep the screen on so the robot doesn't lose calibration
        window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        // 1. FIRST start Screen 1 (THIS CREATES THE WINDOW)
        showArucoMarkersScreen()

        // 2. ONLY NOW we can hide the bars (Immersive Mode)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            window.insetsController?.hide(WindowInsets.Type.statusBars() or WindowInsets.Type.navigationBars())
        }
    }

    override fun onResume() {
        super.onResume()
        // Always return to ArUco markers screen when app comes back to foreground
        showArucoMarkersScreen()
    }

    // ==========================================
    // SCREEN 1: QR CODE (Device Metadata)
    // ==========================================
    private fun showQrCodeScreen() {
        val jsonString = extractPreciseDeviceMetrics()
        val qrBitmap = generateQRCode(jsonString, 800)

        val imageView = ImageView(this).apply {
            setImageBitmap(qrBitmap)
            setBackgroundColor(Color.WHITE)
        }

        val layout = RelativeLayout(this).apply {
            setBackgroundColor(Color.parseColor("#121212")) // Dark background
            addView(imageView, RelativeLayout.LayoutParams(
                RelativeLayout.LayoutParams.WRAP_CONTENT,
                RelativeLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                addRule(RelativeLayout.CENTER_IN_PARENT, RelativeLayout.TRUE)
            })
        }

        // "Next" button to advance to ArUco Markers
        val nextButton = Button(this).apply {
            text = "Next"
            textSize = 18f
            setTextColor(Color.WHITE)
            background = GradientDrawable().apply {
                setColor(Color.parseColor("#1565C0"))
                cornerRadius = 24f
            }
            setPadding(60, 20, 60, 20)
            setOnClickListener { showArucoMarkersScreen() }
        }
        layout.addView(nextButton, RelativeLayout.LayoutParams(
            RelativeLayout.LayoutParams.WRAP_CONTENT,
            RelativeLayout.LayoutParams.WRAP_CONTENT
        ).apply {
            addRule(RelativeLayout.ALIGN_PARENT_BOTTOM)
            addRule(RelativeLayout.CENTER_HORIZONTAL)
            setMargins(0, 0, 0, 60)
        })

        setContentView(layout)
    }

    // ==========================================
    // SCREEN 2: ARUCO MARKERS AT EXACT CORNERS
    // ==========================================
    private fun showArucoMarkersScreen() {
        val layout = RelativeLayout(this).apply {
            setBackgroundColor(Color.WHITE)
        }

        // Get markers for current device type (defaults to flat if unknown)
        val tags = markerProfiles[deviceType] ?: markerProfiles["flat"]!!
        val markerViews = addLateralArucoMarkers(layout, tags)

        // Track how many markers remain visible
        var remainingMarkers = markerViews.size

        // Each marker hides on click; when all are gone, advance to grid
        for (marker in markerViews) {
            marker.setOnClickListener {
                marker.visibility = android.view.View.INVISIBLE
                remainingMarkers--
                if (remainingMarkers <= 0) {
                    showGridScreen()
                }
            }
        }

        setContentView(layout)
    }

    // ==========================================
    // MODULAR: Add ArUco markers to any layout
    // ==========================================

    /**
     * Places ArUco markers on the screen edges.
     *
     * For ≤6 markers: diagonal placement order:
     *   1st → Top-Left, 2nd → Bottom-Right, 3rd → Bottom-Left,
     *   4th → Top-Right, 5th → Center-Left, 6th → Center-Right
     *
     * For >6 markers (foldable): the screen is split in two equal halves.
     *   - Top half: first 4 markers at the 4 corners (rectangle)
     *   - Bottom half: remaining markers fill corners starting from
     *     Bottom-Left, Bottom-Right, Top-Left, Top-Right
     *     (7 tags = 4 top + 3 bottom [BL, BR, TL], 8 tags = both rectangles closed)
     *
     * @param layout    The RelativeLayout to add markers to.
     * @param tags      List of drawable resource IDs.
     * @param tagSizeDp Size in dp for each marker.
     * @param marginDp  Margin in dp from the screen edges.
     */
    private fun addLateralArucoMarkers(
        layout: RelativeLayout,
        tags: List<Int>,
        tagSizeDp: Int = 120,
        marginDp: Int = 16
    ): List<ImageView> {
        val density = resources.displayMetrics.density
        val tagSize = (tagSizeDp * density).toInt()
        val margin = (marginDp * density).toInt()
        val screenHeight = resources.displayMetrics.heightPixels
        val screenWidth = resources.displayMetrics.widthPixels

        val left = margin
        val right = screenWidth - margin - tagSize
        val centerX = (screenWidth - tagSize) / 2

        val positions: List<Pair<Int, Int>>

        if (tags.size <= 6) {
            // Diagonal placement for flat devices
            val top = margin
            val bottom = screenHeight - margin - tagSize
            val centerY = (screenHeight - tagSize) / 2
            val midTopY = (top + centerY) / 2
            val midBottomY = (centerY + bottom) / 2

            positions = listOf(
                left to top,            // 1: Top-Left
                right to bottom,        // 2: Bottom-Right
                left to bottom,         // 3: Bottom-Left
                right to top,           // 4: Top-Right
                left to centerY,        // 5: Center-Left
                right to centerY        // 6: Center-Right
            )
        } else {
            // Foldable: split screen in 2 equal halves
            val halfHeight = screenHeight / 2

            // Top half corners
            val topHalfTop = margin
            val topHalfBottom = halfHeight - margin - tagSize

            // Bottom half corners
            val bottomHalfTop = halfHeight + margin
            val bottomHalfBottom = screenHeight - margin - tagSize

            // First 4: corners of the top half
            val topHalfPositions = listOf(
                left to topHalfTop,         // 1: Top-half Top-Left
                right to topHalfTop,        // 2: Top-half Top-Right
                left to topHalfBottom,      // 3: Top-half Bottom-Left
                right to topHalfBottom      // 4: Top-half Bottom-Right
            )

            // Remaining: bottom half (fill from bottom-left, bottom-right, top-left, top-right)
            val bottomCount = tags.size - 4
            val bottomHalfPositions = when (bottomCount) {
                1 -> listOf(
                    left to bottomHalfBottom         // Bottom-Left
                )
                2 -> listOf(
                    left to bottomHalfBottom,         // Bottom-Left
                    right to bottomHalfBottom         // Bottom-Right
                )
                3 -> listOf(
                    left to bottomHalfBottom,         // Bottom-Left
                    right to bottomHalfBottom,        // Bottom-Right
                    left to bottomHalfTop             // Top-Left
                )
                else -> listOf(
                    left to bottomHalfBottom,         // Bottom-Left
                    right to bottomHalfBottom,        // Bottom-Right
                    left to bottomHalfTop,            // Top-Left
                    right to bottomHalfTop            // Top-Right
                )
            }

            positions = topHalfPositions + bottomHalfPositions
        }

        val createdViews = mutableListOf<ImageView>()

        for ((i, resId) in tags.withIndex()) {
            if (i >= positions.size) break
            val (x, y) = positions[i]

            val tag = ImageView(this).apply {
                setImageResource(resId)
                setBackgroundColor(Color.WHITE)
            }
            val params = RelativeLayout.LayoutParams(tagSize, tagSize).apply {
                leftMargin = x
                topMargin = y
            }

            layout.addView(tag, params)
            createdViews.add(tag)
        }

        return createdViews
    }

    /**
     * Adds a single centered ArUco marker (for success/failure screens).
     *
     * @param layout    The RelativeLayout to add the marker to.
     * @param resId     Drawable resource ID of the marker.
     * @param tagSizeDp Size in dp for the marker.
     */
    private fun addCenteredArucoMarker(
        layout: RelativeLayout,
        resId: Int,
        tagSizeDp: Int = 140
    ) {
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

    // ==========================================
    // SCREEN 3: INTERACTIVE VALIDATION GRID
    // ==========================================
    private fun showGridScreen() {
        val rows = 20
        val cols = 10

        // Stores all cells with their position (row, column)
        data class CellInfo(val view: TextView, val row: Int, val col: Int)
        val cells = mutableListOf<CellInfo>()

        // Set to track which border cells have been painted
        val paintedBorderCells = mutableSetOf<Pair<Int, Int>>()
        // Set to track which internal cells were touched
        val paintedInternalCells = mutableSetOf<Pair<Int, Int>>()
        // Flag to track if any internal cell was touched
        var internalCellTouched = false

        // Identifies if the cell is on the border (sides, top, bottom)
        fun isBorderCell(row: Int, col: Int): Boolean {
            return row == 0 || row == rows - 1 || col == 0 || col == cols - 1
        }

        // Count total border cells
        val totalBorderCells = (0 until rows).sumOf { r ->
            (0 until cols).count { c -> isBorderCell(r, c) }
        }

        // Main Vertical Layout
        val mainLayout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.BLACK)
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.MATCH_PARENT
            )
        }

        // Fill the Grid
        for (i in 0 until rows) {
            val rowLayout = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    0, 1.0f
                )
            }

            for (j in 0 until cols) {
                val cell = TextView(this).apply {
                    // Border cells are light gray, internal cells are dark gray
                    setBackgroundColor(if (isBorderCell(i, j)) Color.LTGRAY else Color.DKGRAY)
                    layoutParams = LinearLayout.LayoutParams(
                        0, LinearLayout.LayoutParams.MATCH_PARENT, 1.0f
                    ).apply {
                        setMargins(2, 2, 2, 2)
                    }
                }
                cells.add(CellInfo(cell, i, j))
                rowLayout.addView(cell)
            }
            mainLayout.addView(rowLayout)
        }

        // Camera tolerance zone: top row, columns 4 and 5 (between cells 5 and 6, 1-indexed)
        // If the finger lifts in this zone, don't validate — wait for finger to return
        fun isCameraZone(x: Int, y: Int): Boolean {
            for (cellInfo in cells) {
                if (cellInfo.row == 0 && cellInfo.col in 4..5) {
                    val loc = IntArray(2)
                    cellInfo.view.getLocationOnScreen(loc)
                    val left = loc[0]
                    val top = loc[1]
                    val right = left + cellInfo.view.width
                    val bottom = top + cellInfo.view.height
                    if (x in left..right && y in top..bottom) return true
                }
            }
            return false
        }

        // Intercept touch to detect swipe + tap
        mainLayout.setOnTouchListener { _, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN,
                MotionEvent.ACTION_MOVE -> {
                    val x = event.rawX.toInt()
                    val y = event.rawY.toInt()
                    for (cellInfo in cells) {
                        val loc = IntArray(2)
                        cellInfo.view.getLocationOnScreen(loc)
                        val left = loc[0]
                        val top = loc[1]
                        val right = left + cellInfo.view.width
                        val bottom = top + cellInfo.view.height
                        if (x in left..right && y in top..bottom) {
                            cellInfo.view.setBackgroundColor(if (isBorderCell(cellInfo.row, cellInfo.col)) Color.GREEN else Color.RED)
                            if (isBorderCell(cellInfo.row, cellInfo.col)) {
                                paintedBorderCells.add(Pair(cellInfo.row, cellInfo.col))
                            } else {
                                paintedInternalCells.add(Pair(cellInfo.row, cellInfo.col))
                                internalCellTouched = true
                            }
                        }
                    }
                    true
                }
                MotionEvent.ACTION_UP -> {
                    val x = event.rawX.toInt()
                    val y = event.rawY.toInt()

                    // If finger lifted in the camera zone, ignore — don't validate yet
                    if (isCameraZone(x, y)) {
                        // Do nothing, let the user put finger back and continue
                        true
                    } else {
                        // Normal validation on finger release
                        if (paintedBorderCells.size >= totalBorderCells && !internalCellTouched) {
                            showSuccessScreen(paintedBorderCells.size, totalBorderCells)
                        } else if (internalCellTouched) {
                            showFailureScreen(
                                "Touch detected outside the borders.",
                                paintedBorderCells.size, totalBorderCells, paintedInternalCells.size
                            )
                        } else {
                            showFailureScreen(
                                "Borders incomplete.",
                                paintedBorderCells.size, totalBorderCells, paintedInternalCells.size
                            )
                        }
                        true
                    }
                }
                else -> true
            }
        }

        setContentView(mainLayout)
    }

    // ==========================================
    // SCREEN 4: SUCCESS (Green Screen + ArUco tag5)
    // ==========================================
    private fun showSuccessScreen(hits: Int = 0, totalBorder: Int = 0) {
        Log.i("RTA_RESULT", "{\"status\":\"success\",\"hits\":$hits,\"total\":$totalBorder,\"errors\":0,\"device_type\":\"$deviceType\"}")

        val layout = RelativeLayout(this).apply {
            setBackgroundColor(Color.parseColor("#2E7D32")) // Dark green
            setOnClickListener { showArucoMarkersScreen() }
        }

        // ArUco marker for robot detection (tag7 = SUCCESS)
        addCenteredArucoMarker(layout, R.drawable.tag14)

        val message = TextView(this).apply {
            text = "ALIGNMENT APPROVED"
            textSize = 28f
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
        }
        layout.addView(message, RelativeLayout.LayoutParams(
            RelativeLayout.LayoutParams.WRAP_CONTENT,
            RelativeLayout.LayoutParams.WRAP_CONTENT
        ).apply {
            addRule(RelativeLayout.ALIGN_PARENT_BOTTOM)
            addRule(RelativeLayout.CENTER_HORIZONTAL)
            setMargins(0, 0, 0, 140)
        })

        setContentView(layout)
    }

    // ==========================================
    // SCREEN 5: FAILURE (Red Screen + ArUco tag6)
    // ==========================================
    private fun showFailureScreen(errorMessage: String, hits: Int = 0, totalBorder: Int = 0, errors: Int = 0) {
        Log.i("RTA_RESULT", "{\"status\":\"fail\",\"hits\":$hits,\"total\":$totalBorder,\"errors\":$errors,\"reason\":\"$errorMessage\",\"device_type\":\"$deviceType\"}")

        val layout = RelativeLayout(this).apply {
            setBackgroundColor(Color.parseColor("#C62828")) // Dark red
            setOnClickListener { showArucoMarkersScreen() }
        }

        // ArUco marker for robot detection (tag8 = FAILURE)
        addCenteredArucoMarker(layout, R.drawable.tag15)

        val message = TextView(this).apply {
            text = "ALIGNMENT FAILED"
            textSize = 28f
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
        }
        layout.addView(message, RelativeLayout.LayoutParams(
            RelativeLayout.LayoutParams.WRAP_CONTENT,
            RelativeLayout.LayoutParams.WRAP_CONTENT
        ).apply {
            addRule(RelativeLayout.ALIGN_PARENT_BOTTOM)
            addRule(RelativeLayout.CENTER_HORIZONTAL)
            setMargins(0, 0, 0, 260)
        })

        // Score summary
        val scoreText = TextView(this).apply {
            text = "✅ Hits: $hits / $totalBorder    ❌ Errors: $errors"
            textSize = 18f
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
        }
        layout.addView(scoreText, RelativeLayout.LayoutParams(
            RelativeLayout.LayoutParams.WRAP_CONTENT,
            RelativeLayout.LayoutParams.WRAP_CONTENT
        ).apply {
            addRule(RelativeLayout.ALIGN_PARENT_BOTTOM)
            addRule(RelativeLayout.CENTER_HORIZONTAL)
            setMargins(0, 0, 0, 200)
        })

        val detail = TextView(this).apply {
            text = errorMessage
            textSize = 16f
            setTextColor(Color.parseColor("#FFCDD2")) // Light pink
            gravity = Gravity.CENTER
        }
        layout.addView(detail, RelativeLayout.LayoutParams(
            RelativeLayout.LayoutParams.WRAP_CONTENT,
            RelativeLayout.LayoutParams.WRAP_CONTENT
        ).apply {
            addRule(RelativeLayout.ALIGN_PARENT_BOTTOM)
            addRule(RelativeLayout.CENTER_HORIZONTAL)
            setMargins(0, 0, 0, 120)
        })

        setContentView(layout)
    }

    // ==========================================
    // UTILITIES: QR Code and Metadata
    // ==========================================
    private fun generateQRCode(text: String, size: Int): Bitmap {
        val writer = QRCodeWriter()
        val bitMatrix = writer.encode(text, BarcodeFormat.QR_CODE, size, size)
        val bitmap = Bitmap.createBitmap(size, size, Bitmap.Config.RGB_565)
        for (x in 0 until size) {
            for (y in 0 until size) {
                bitmap.setPixel(x, y, if (bitMatrix.get(x, y)) Color.BLACK else Color.WHITE)
            }
        }
        return bitmap
    }

    private fun extractPreciseDeviceMetrics(): String {
        val bounds = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            windowManager.currentWindowMetrics.bounds
        } else {
            val metrics = DisplayMetrics()
            @Suppress("DEPRECATION")
            windowManager.defaultDisplay.getRealMetrics(metrics)
            android.graphics.Rect(0, 0, metrics.widthPixels, metrics.heightPixels)
        }

        return """
            {
                "fabricante": "${Build.MANUFACTURER}",
                "modelo": "${Build.MODEL}",
                "w_px": ${bounds.width()},
                "h_px": ${bounds.height()}
            }
        """.trimIndent()
    }
}