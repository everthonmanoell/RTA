package com.example.rta

import android.app.Activity
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.Bundle
import android.util.DisplayMetrics
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

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
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

        // Place ArUco markers at edge positions
        val markerViews = addArucoMarkers(layout, mapOf(
            MarkerPosition.TOP_LEFT      to R.drawable.tag1,
            MarkerPosition.TOP_RIGHT     to R.drawable.tag2,
            MarkerPosition.CENTER_LEFT   to R.drawable.tag3,
            MarkerPosition.CENTER_RIGHT  to R.drawable.tag4,
            MarkerPosition.BOTTOM_LEFT   to R.drawable.tag5,
            MarkerPosition.BOTTOM_RIGHT  to R.drawable.tag6
        ))

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

    /** Position presets for placing markers on screen. */
    enum class MarkerPosition {
        TOP_LEFT, TOP_RIGHT, BOTTOM_LEFT, BOTTOM_RIGHT, CENTER,
        TOP_CENTER, BOTTOM_CENTER, CENTER_LEFT, CENTER_RIGHT
    }

    /**
     * Adds any number of ArUco markers to a RelativeLayout at predefined positions.
     *
     * Usage examples:
     *   // 4 corners:
     *   addArucoMarkers(layout, mapOf(
     *       MarkerPosition.TOP_LEFT     to R.drawable.tag1,
     *       MarkerPosition.TOP_RIGHT    to R.drawable.tag2,
     *       MarkerPosition.BOTTOM_LEFT  to R.drawable.tag3,
     *       MarkerPosition.BOTTOM_RIGHT to R.drawable.tag4
     *   ))
     *
     *   // Only 2 markers:
     *   addArucoMarkers(layout, mapOf(
     *       MarkerPosition.TOP_LEFT     to R.drawable.tag1,
     *       MarkerPosition.BOTTOM_RIGHT to R.drawable.tag2
     *   ))
     *
     *   // Single centered:
     *   addArucoMarkers(layout, mapOf(
     *       MarkerPosition.CENTER to R.drawable.tag5
     *   ))
     *
     * @param layout    The RelativeLayout to add markers to.
     * @param markers   Map of position to drawable resource ID.
     * @param tagSizeDp Size in dp for each marker (converted to px automatically).
     * @param marginDp  Margin in dp from the screen edges (converted to px automatically).
     */
    private fun addArucoMarkers(
        layout: RelativeLayout,
        markers: Map<MarkerPosition, Int>,
        tagSizeDp: Int = 120,
        marginDp: Int = 16
    ): List<ImageView> {
        val density = resources.displayMetrics.density
        val tagSize = (tagSizeDp * density).toInt()
        val margin = (marginDp * density).toInt()

        val createdViews = mutableListOf<ImageView>()
        for ((position, resId) in markers) {
            val tag = ImageView(this).apply {
                setImageResource(resId)
                setBackgroundColor(Color.WHITE)
            }
            val params = RelativeLayout.LayoutParams(tagSize, tagSize)

            when (position) {
                MarkerPosition.TOP_LEFT -> params.apply {
                    addRule(RelativeLayout.ALIGN_PARENT_TOP)
                    addRule(RelativeLayout.ALIGN_PARENT_LEFT)
                    setMargins(margin, margin, 0, 0)
                }
                MarkerPosition.TOP_RIGHT -> params.apply {
                    addRule(RelativeLayout.ALIGN_PARENT_TOP)
                    addRule(RelativeLayout.ALIGN_PARENT_RIGHT)
                    setMargins(0, margin, margin, 0)
                }
                MarkerPosition.BOTTOM_LEFT -> params.apply {
                    addRule(RelativeLayout.ALIGN_PARENT_BOTTOM)
                    addRule(RelativeLayout.ALIGN_PARENT_LEFT)
                    setMargins(margin, 0, 0, margin)
                }
                MarkerPosition.BOTTOM_RIGHT -> params.apply {
                    addRule(RelativeLayout.ALIGN_PARENT_BOTTOM)
                    addRule(RelativeLayout.ALIGN_PARENT_RIGHT)
                    setMargins(0, 0, margin, margin)
                }
                MarkerPosition.CENTER -> params.apply {
                    addRule(RelativeLayout.CENTER_IN_PARENT)
                }
                MarkerPosition.TOP_CENTER -> params.apply {
                    addRule(RelativeLayout.ALIGN_PARENT_TOP)
                    addRule(RelativeLayout.CENTER_HORIZONTAL)
                    setMargins(0, margin, 0, 0)
                }
                MarkerPosition.BOTTOM_CENTER -> params.apply {
                    addRule(RelativeLayout.ALIGN_PARENT_BOTTOM)
                    addRule(RelativeLayout.CENTER_HORIZONTAL)
                    setMargins(0, 0, 0, margin)
                }
                MarkerPosition.CENTER_LEFT -> params.apply {
                    addRule(RelativeLayout.CENTER_VERTICAL)
                    addRule(RelativeLayout.ALIGN_PARENT_LEFT)
                    setMargins(margin, 0, 0, 0)
                }
                MarkerPosition.CENTER_RIGHT -> params.apply {
                    addRule(RelativeLayout.CENTER_VERTICAL)
                    addRule(RelativeLayout.ALIGN_PARENT_RIGHT)
                    setMargins(0, 0, margin, 0)
                }
            }

            layout.addView(tag, params)
            createdViews.add(tag)
        }
        return createdViews
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
                                internalCellTouched = true
                            }
                        }
                    }
                    true
                }
                MotionEvent.ACTION_UP -> {
                    // On finger release, check:
                    // 1. All border cells were painted
                    // 2. No internal cell was touched
                    if (paintedBorderCells.size >= totalBorderCells && !internalCellTouched) {
                        showSuccessScreen()
                    } else if (internalCellTouched) {
                        showFailureScreen("Touch detected outside the borders.")
                    } else {
                        val painted = paintedBorderCells.size
                        showFailureScreen("Borders incomplete: $painted / $totalBorderCells")
                    }
                    true
                }
                else -> true
            }
        }

        setContentView(mainLayout)
    }

    // ==========================================
    // SCREEN 4: SUCCESS (Green Screen + ArUco tag5)
    // ==========================================
    private fun showSuccessScreen() {
        val layout = RelativeLayout(this).apply {
            setBackgroundColor(Color.parseColor("#2E7D32")) // Dark green
            setOnClickListener { showArucoMarkersScreen() }
        }

        // ArUco marker for robot detection (tag7 = SUCCESS)
        addArucoMarkers(layout, mapOf(MarkerPosition.CENTER to R.drawable.tag7), tagSizeDp = 140)

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
    private fun showFailureScreen(errorMessage: String) {
        val layout = RelativeLayout(this).apply {
            setBackgroundColor(Color.parseColor("#C62828")) // Dark red
            setOnClickListener { showArucoMarkersScreen() }
        }

        // ArUco marker for robot detection (tag8 = FAILURE)
        addArucoMarkers(layout, mapOf(MarkerPosition.CENTER to R.drawable.tag8), tagSizeDp = 140)

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
            setMargins(0, 0, 0, 180)
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