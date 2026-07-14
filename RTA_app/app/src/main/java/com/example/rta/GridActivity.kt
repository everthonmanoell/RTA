package com.example.rta
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.view.MotionEvent
import android.widget.LinearLayout
import android.widget.TextView

class GridActivity : BaseRtaActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val rows = 20
        val cols = 10
        data class CellInfo(val view: TextView, val row: Int, val col: Int)
        val cells = mutableListOf<CellInfo>()
        val paintedBorderCells = mutableSetOf<Pair<Int, Int>>()
        val paintedInternalCells = mutableSetOf<Pair<Int, Int>>()
        var internalCellTouched = false

        fun isBorderCell(row: Int, col: Int) = row == 0 || row == rows - 1 || col == 0 || col == cols - 1
        val totalBorderCells = (0 until rows).sumOf { r -> (0 until cols).count { c -> isBorderCell(r, c) } }

        val mainLayout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.BLACK)
            layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.MATCH_PARENT)
        }

        for (i in 0 until rows) {
            val rowLayout = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1.0f)
            }
            for (j in 0 until cols) {
                val cell = TextView(this).apply {
                    setBackgroundColor(if (isBorderCell(i, j)) Color.LTGRAY else Color.DKGRAY)
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1.0f).apply { setMargins(2, 2, 2, 2) }
                }
                cells.add(CellInfo(cell, i, j))
                rowLayout.addView(cell)
            }
            mainLayout.addView(rowLayout)
        }

        fun isCameraZone(x: Int, y: Int): Boolean {
            for (cellInfo in cells) {
                if (cellInfo.row == 0 && cellInfo.col in 4..5) {
                    val loc = IntArray(2)
                    cellInfo.view.getLocationOnScreen(loc)
                    if (x in loc[0]..(loc[0] + cellInfo.view.width) && y in loc[1]..(loc[1] + cellInfo.view.height)) return true
                }
            }
            return false
        }

        mainLayout.setOnTouchListener { _, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN, MotionEvent.ACTION_MOVE -> {
                    val x = event.rawX.toInt()
                    val y = event.rawY.toInt()
                    for (cellInfo in cells) {
                        val loc = IntArray(2)
                        cellInfo.view.getLocationOnScreen(loc)
                        if (x in loc[0]..(loc[0] + cellInfo.view.width) && y in loc[1]..(loc[1] + cellInfo.view.height)) {
                            cellInfo.view.setBackgroundColor(if (isBorderCell(cellInfo.row, cellInfo.col)) Color.GREEN else Color.RED)
                            if (isBorderCell(cellInfo.row, cellInfo.col)) paintedBorderCells.add(Pair(cellInfo.row, cellInfo.col))
                            else { paintedInternalCells.add(Pair(cellInfo.row, cellInfo.col)); internalCellTouched = true }
                        }
                    }
                    true
                }
                MotionEvent.ACTION_UP -> {
                    val x = event.rawX.toInt()
                    val y = event.rawY.toInt()
                    if (isCameraZone(x, y)) true
                    else {
                        val intent = if (paintedBorderCells.size >= totalBorderCells && !internalCellTouched) {
                            Intent(this, SuccessActivity::class.java).apply {
                                putExtra("hits", paintedBorderCells.size)
                                putExtra("total", totalBorderCells)
                            }
                        } else {
                            val msg = if (internalCellTouched) "Touch detected outside the borders." else "Borders incomplete."
                            Intent(this, FailureActivity::class.java).apply {
                                putExtra("errorMessage", msg)
                                putExtra("hits", paintedBorderCells.size)
                                putExtra("total", totalBorderCells)
                                putExtra("errors", paintedInternalCells.size)
                            }
                        }
                        intent.putExtra(EXTRA_DEVICE_TYPE, deviceType)
                        intent.putExtra(EXTRA_PYTHON_IP, pythonServerIp)
                        intent.putExtra(EXTRA_PYTHON_PORT, pythonServerPort)
                        intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_NEW_TASK)
                        startActivity(intent)
                        finish()
                        true
                    }
                }
                else -> true
            }
        }
        setContentView(mainLayout)
    }
}
